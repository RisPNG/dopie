from __future__ import annotations

import errno
import os
import threading
import time
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_thread_locks: weakref.WeakValueDictionary[Path, threading.RLock] = weakref.WeakValueDictionary()
_registry_lock = threading.Lock()
_held_transactions = threading.local()


@contextmanager
def shared_folder_transaction(path: Path) -> Iterator[None]:
    path = path.resolve()
    with _registry_lock:
        thread_lock = _thread_locks.setdefault(path, threading.RLock())
    with thread_lock:
        held = getattr(_held_transactions, "paths", None)
        if held is None:
            held = _held_transactions.paths = set()
        if path in held:
            yield
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                while True:
                    try:
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as error:
                        if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                            raise
                        time.sleep(0.05)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX)
            held.add(path)
            try:
                yield
            finally:
                held.remove(path)
                if os.name == "nt":
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)
