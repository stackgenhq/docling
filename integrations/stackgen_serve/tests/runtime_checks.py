"""Linux-container checks that prevent healthy HTTP from hiding worker loss."""

import re
from pathlib import Path


def serving_pids(log_path: Path) -> set[str]:
    """Read historical serving PIDs; liveness must be checked independently."""
    return set(re.findall(r"Started server process \[(\d+)\]", log_path.read_text()))


class RuntimeGuard:
    """Require observable OOM counters and stable live workers throughout a smoke run."""

    def __init__(
        self, cgroup: Path = Path("/sys/fs/cgroup"), proc: Path = Path("/proc")
    ) -> None:
        self.proc = proc
        self.counter_path = cgroup / "memory.events"
        if not self.counter_path.exists():
            self.counter_path = cgroup / "memory/memory.oom_control"
        self.baseline = self.counters()

    def counters(self) -> dict[str, int]:
        """Read v2 events or v1 kill counters, failing closed if unavailable."""
        try:
            counters = {
                key: int(value)
                for key, value in (
                    line.split() for line in self.counter_path.read_text().splitlines()
                )
            }
            if "oom_kill" not in counters:
                raise ValueError("oom_kill counter missing")
            return {
                key: value
                for key, value in counters.items()
                if key in {"oom", "oom_kill", "oom_group_kill"}
            }
        except (OSError, ValueError) as error:
            raise RuntimeError(
                f"Cannot verify OOM counters at {self.counter_path}"
            ) from error

    def identity(self, pid: str) -> str:
        """Identify a live, non-zombie process by PID and Linux starttime."""
        try:
            fields = (self.proc / pid / "stat").read_text().rsplit(")", 1)[1].split()
            if fields[0] in {"Z", "X", "x"}:
                raise ValueError("dead/zombie process")
            return fields[19]
        except (OSError, ValueError, IndexError) as error:
            raise RuntimeError(f"Serving worker {pid} is not alive") from error

    def capture(self, pids: set[str]) -> dict[str, str]:
        """Capture the expected generation so PID reuse cannot mask worker loss."""
        return {pid: self.identity(pid) for pid in pids}

    def check(self, log_path: Path, active: dict[str, str], history: set[str]) -> None:
        """Reject OOM events, unplanned generations and lost/reused active workers."""
        counters = self.counters()
        if counters.keys() != self.baseline.keys() or any(
            value != self.baseline[key] for key, value in counters.items()
        ):
            raise RuntimeError(
                f"OOM counters changed: before={self.baseline}, after={counters}"
            )
        if serving_pids(log_path) != history:
            raise RuntimeError("Unexpected serving-worker restart")
        for pid, starttime in active.items():
            if self.identity(pid) != starttime:
                raise RuntimeError(f"Serving worker {pid} was replaced/reused")
