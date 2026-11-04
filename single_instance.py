"""Single-instance lock for the long-running collectors (prevents two concurrent collectors writing the
same file). The lock is an OS-level lock on '<output>.lock': it is released automatically when the
process ends, even after a crash or a killed window, so a stale lock file never blocks a restart."""
from __future__ import annotations

import os
from pathlib import Path


class AlreadyRunning(SystemExit):
    pass


class SingleInstance:
    def __init__(self, target: Path):
        self.path = Path(str(target) + ".lock")
        self.fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            raise AlreadyRunning(f"Another collector is already writing {Path(str(self.path)[:-5]).name} "
                                 f"(lock {self.path.name} held). Not starting a second one.")
        self.fh.seek(0)
        self.fh.truncate()
        self.fh.write(str(os.getpid()))
        self.fh.flush()
        return self

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()
