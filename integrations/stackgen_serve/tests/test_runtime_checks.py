"""A healthy response must not hide killed or replaced server workers."""

import tempfile
import unittest
from pathlib import Path

from runtime_checks import RuntimeGuard


class RuntimeChecksTests(unittest.TestCase):
    """Exercise failure detection without killing actual test resources."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.cgroup = self.root / "cgroup"
        self.proc = self.root / "proc"
        self.cgroup.mkdir()
        self.proc.mkdir()
        self.events = self.cgroup / "memory.events"
        self.events.write_text("oom 0\noom_kill 0\noom_group_kill 0\n")
        self.log = self.root / "server.log"
        self.log.write_text(
            "Started server process [12]\nStarted server process [13]\n"
        )
        for pid in ("12", "13"):
            self.process(pid, "S", "42")
        self.guard = RuntimeGuard(self.cgroup, self.proc)

    def process(self, pid: str, state: str, start: str) -> None:
        """Write Linux stat fields through starttime, including a spaced comm."""
        folder = self.proc / pid
        folder.mkdir(exist_ok=True)
        (folder / "stat").write_text(
            f"{pid} (python worker) " + " ".join([state] + ["0"] * 18 + [start])
        )

    def test_oom_fails_even_when_both_workers_survive(self) -> None:
        identities = self.guard.capture({"12", "13"})
        self.events.write_text("oom 1\noom_kill 1\noom_group_kill 0\n")
        with self.assertRaisesRegex(RuntimeError, "OOM"):
            self.guard.check(self.log, identities, {"12", "13"})

    def test_dead_zombie_and_reused_pids_fail(self) -> None:
        identities = self.guard.capture({"12", "13"})
        for state, start in (("Z", "42"), ("S", "43")):
            self.process("12", state, start)
            with self.assertRaises(RuntimeError):
                self.guard.check(self.log, identities, {"12", "13"})
        (self.proc / "12" / "stat").unlink()
        with self.assertRaises(RuntimeError):
            self.guard.check(self.log, identities, {"12", "13"})

    def test_unexpected_replacement_worker_fails(self) -> None:
        identities = self.guard.capture({"12", "13"})
        self.log.write_text(self.log.read_text() + "Started server process [14]\n")
        with self.assertRaisesRegex(RuntimeError, "restart"):
            self.guard.check(self.log, identities, {"12", "13"})

    def test_explicit_reload_generation_is_allowed_but_oom_is_not(self) -> None:
        self.log.write_text(self.log.read_text() + "Started server process [14]\n")
        self.process("14", "S", "55")
        identities = self.guard.capture({"14"})
        self.guard.check(self.log, identities, {"12", "13", "14"})
        self.events.write_text("oom 0\noom_kill 1\noom_group_kill 0\n")
        with self.assertRaisesRegex(RuntimeError, "OOM"):
            self.guard.check(self.log, identities, {"12", "13", "14"})

    def test_missing_counters_fail_closed(self) -> None:
        self.events.unlink()
        with self.assertRaises(RuntimeError):
            RuntimeGuard(self.cgroup, self.proc)


if __name__ == "__main__":
    unittest.main()
