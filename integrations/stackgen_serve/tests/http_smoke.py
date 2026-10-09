"""Real HTTP checks for single-process, spawned workers and reload startup."""

import argparse
import csv
import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from runtime_checks import RuntimeGuard, serving_pids


def wait_ready(
    server: subprocess.Popen, log_path: Path, count: int, previous: set[str]
) -> set[str]:
    """Require healthy new serving processes so a stale worker cannot mask reload."""
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("Serve exited before health check")
        pids = serving_pids(log_path) - previous
        if len(pids) >= count:
            try:
                with urllib.request.urlopen("http://127.0.0.1:5001/health", timeout=3):
                    text = log_path.read_text()
                    if all(
                        f"Record table factory installed pid={pid}" in text
                        for pid in pids
                    ):
                        return pids
            except (OSError, urllib.error.URLError):
                pass
        time.sleep(1)
    raise TimeoutError("Serve processes/factory installation timed out")


def main() -> None:
    """Verify record output in real server children, including a reload restart."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=["default", "workers", "reload"], nargs="?", default="default"
    )
    parser.add_argument("--csv", type=Path, help="Use an existing UTF-8 CSV fixture")
    parser.add_argument("--requests", type=int, help="Requests per server generation")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if args.requests is not None and args.requests < 1:
        parser.error("--requests must be positive")
    mode = args.mode
    if args.csv is not None:
        source_bytes = args.csv.read_bytes()
    else:
        rows = [
            [f"h{i}" for i in range(1881)],
            [],  # The backend drops blank lines, but not explicit empty-field rows.
            ["alpha", "123", "", "line1\nline2 ü <tag>"],
            ["", ""],
        ]
        source = io.StringIO(newline="")
        csv.writer(source).writerows(rows)
        source_bytes = source.getvalue().encode()
    rows = [
        row
        for row in csv.reader(io.StringIO(source_bytes.decode("utf-8-sig"), newline=""))
        if row
    ]
    boundary = "docling-record-smoke"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="to_formats"\r\n\r\nmd\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="image_export_mode"\r\n'
            "\r\nplaceholder\r\n"
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
            'filename="records.csv"\r\n'
            "Content-Type: text/csv\r\n\r\n"
        ).encode()
        + source_bytes
        + f"\r\n--{boundary}--\r\n".encode()
    )
    env = {
        **os.environ,
        "UVICORN_WORKERS": "2" if mode == "workers" else "1",
        "UVICORN_RELOAD": "true" if mode == "reload" else "false",
        "DOCLING_SERVE_LOG_LEVEL": "INFO",
    }
    # CSV and HTML need no model weights. Apply the same test budget in all modes.
    env["DOCLING_SERVE_LOAD_MODELS_AT_BOOT"] = "false"
    with tempfile.TemporaryDirectory() as directory:
        log_path = Path(directory) / "serve.log"
        watched = Path(directory) / "reload_probe.py"
        watched.write_text("# initial reload probe\n")
        with log_path.open("w+") as log:
            guard = RuntimeGuard()
            pids: set[str] = set()
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "stackgen_docling",
                    "run",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5001",
                ],
                cwd=directory,
                env=env,
                start_new_session=True,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                expected = 2 if mode == "workers" else 1
                pids = wait_ready(server, log_path, expected, set())
                assert len(pids) == expected, "Unexpected startup worker replacement"
                active = guard.capture(pids)
                guard.check(log_path, active, pids)
                generations = 2 if mode == "reload" else 1
                # New HTTP connections exercise worker dispatch; installation
                # markers independently confirm the hook ran in every worker.
                requests = (
                    args.requests
                    if args.requests is not None
                    else (6 if mode == "workers" else 1)
                )
                conversion_seconds = []
                for generation in range(generations):
                    if generation:
                        guard.check(log_path, active, pids)
                        watched.write_text("# changed reload probe\n")
                        new_pids = wait_ready(server, log_path, 1, pids)
                        assert len(new_pids) == 1, "Unexpected extra reload generation"
                        pids |= new_pids
                        active = guard.capture(new_pids)
                        guard.check(log_path, active, pids)
                    for _ in range(requests):
                        assert server.poll() is None, "Server supervisor exited"
                        guard.check(log_path, active, pids)
                        request = urllib.request.Request(
                            "http://127.0.0.1:5001/v1/convert/file",
                            data=body,
                            headers={
                                "Content-Type": f"multipart/form-data; boundary={boundary}"
                            },
                        )
                        started = time.monotonic()
                        with urllib.request.urlopen(
                            request, timeout=args.timeout
                        ) as response:
                            assert response.status == 200
                            markdown = json.load(response)["document"]["md_content"]
                        conversion_seconds.append(time.monotonic() - started)
                        values = [
                            json.loads(line.split(": ", 1)[1])
                            for line in markdown.splitlines()
                            if line.startswith("- Column ")
                        ]
                        assert values == [value for row in rows for value in row]
                        record_labels = [
                            line
                            for line in markdown.splitlines()
                            if line.startswith("Record ")
                        ]
                        assert record_labels == [
                            f"Record {i + 1}" for i in range(len(rows))
                        ]
                        assert "## Record " not in markdown
                        assert not any(
                            not line.strip() for line in markdown.splitlines()
                        )
                        guard.check(log_path, active, pids)
                html_body = body[: body.index(source_bytes)].replace(
                    b'filename="records.csv"', b'filename="records.html"'
                ).replace(b"text/csv", b"text/html") + (
                    b"<html><body><h1>Native HTML</h1><table><tr><td>blue</td>"
                    b"<td><b>green</b></td></tr></table></body></html>"
                    + f"\r\n--{boundary}--\r\n".encode()
                )
                request = urllib.request.Request(
                    "http://127.0.0.1:5001/v1/convert/file",
                    data=html_body,
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={boundary}"
                    },
                )
                with urllib.request.urlopen(request, timeout=180) as response:
                    html_markdown = json.load(response)["document"]["md_content"]
                assert all(
                    token in html_markdown
                    for token in ("Native HTML", "blue", "green", "Record 1")
                )
                with urllib.request.urlopen(
                    "http://127.0.0.1:5001/health", timeout=5
                ) as response:
                    assert response.status == 200
                assert server.poll() is None, "Server supervisor exited"
                guard.check(log_path, active, pids)
                report = {
                    "status": "passed",
                    "mode": mode,
                    "verified_fields": len(values),
                    "source_rows": len(rows),
                    "source_bytes": len(source_bytes),
                    "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                    "conversion_seconds": conversion_seconds,
                    "output_bytes": len(markdown.encode()),
                    "serving_pids": sorted(pids),
                    "active_pids": sorted(active),
                    "requests": requests * generations,
                    "health": 200,
                    "oom_events_before": guard.baseline,
                }
            except BaseException:
                log.flush()
                print(log_path.read_text(), file=sys.stderr)
                raise
            finally:
                try:
                    os.killpg(server.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    server.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(server.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    server.wait(timeout=5)
                # Intentional shutdown no longer requires live workers, but
                # cannot hide a last-moment OOM or unplanned replacement.
                try:
                    guard.check(log_path, {}, pids or serving_pids(log_path))
                except BaseException:
                    log.flush()
                    print(log_path.read_text(), file=sys.stderr)
                    raise
            report["oom_events_after"] = guard.counters()
            peak_path = Path("/sys/fs/cgroup/memory.peak")
            report["memory_peak_bytes"] = (
                int(peak_path.read_text(encoding="utf-8"))
                if peak_path.exists()
                else None
            )
            print(json.dumps(report))


if __name__ == "__main__":
    main()
