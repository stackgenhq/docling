#!/bin/sh
set -eu
# Download the pinned python3 RPMs for the requested architectures.
# Pass amd64, arm64, or both. With no arguments, use this machine's architecture.
root=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
if [ "$#" -eq 0 ]; then
  case $(uname -m) in
    x86_64) set -- amd64 ;;
    aarch64 | arm64) set -- arm64 ;;
    *)
      echo "Unsupported architecture: $(uname -m). Pass amd64 or arm64." >&2
      exit 1
      ;;
  esac
fi
for arch in "$@"; do
  case $arch in
    amd64 | arm64) ;;
    *)
      echo "Unsupported architecture: $arch. Pass amd64 or arm64." >&2
      exit 1
      ;;
  esac
done
python3 - "$root/python3-rpms.txt" "$root/rpms" "$@" <<'PY'
import hashlib
import pathlib
import sys
import urllib.request

manifest_path, dest_root, *arches = sys.argv[1:]
wanted = set(arches)
dest_root = pathlib.Path(dest_root)
rows: list[tuple[str, str, str, str]] = []
for line in pathlib.Path(manifest_path).read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    arch, filename, sha, url = stripped.split()
    if arch in wanted:
        rows.append((arch, filename, sha, url))
missing = sorted(wanted - {arch for arch, _filename, _sha, _url in rows})
if missing:
    raise SystemExit(f"No RPMs listed for {', '.join(missing)}.")
counts = {arch: 0 for arch in wanted}
for arch, filename, sha, url in rows:
    dest = dest_root / arch / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == sha:
        counts[arch] += 1
        continue
    partial = dest.with_suffix(dest.suffix + ".partial")
    with urllib.request.urlopen(url, timeout=180) as response:
        partial.write_bytes(response.read())
    digest = hashlib.sha256(partial.read_bytes()).hexdigest()
    if digest != sha:
        partial.unlink()
        raise SystemExit(f"{filename} sha256 {digest} != {sha}")
    partial.replace(dest)
    counts[arch] += 1
bad = [f"{arch}={count}" for arch, count in sorted(counts.items()) if count != 2]
if bad:
    raise SystemExit(f"Expected 2 RPMs per architecture, got {', '.join(bad)}.")
for arch, count in sorted(counts.items()):
    print(f"{arch}: {count} RPMs")
PY
