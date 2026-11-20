from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import stat
import tempfile


@contextmanager
def atomic_writer(path: Path):
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            yield temporary
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


class FileChanges:
    def __init__(self):
        self._undo = ExitStack()

    def mkdir(self, path: Path) -> None:
        missing = []
        parent = path
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for directory in reversed(missing):
            directory.mkdir()
            self._undo.callback(directory.rmdir)

    def preserve_file(self, path: Path) -> None:
        if path.exists():
            information = path.stat()
            data = path.read_bytes()
        else:
            information = data = None
        self._undo.callback(self._restore_file, path, data, information)

    @staticmethod
    def _restore_file(path: Path, data: bytes | None, information) -> None:
        if data is None:
            path.unlink(missing_ok=True)
            return
        # Avoid rewriting an unchanged file when the original write failed early.
        if not path.is_file() or path.read_bytes() != data:
            with atomic_writer(path) as temporary:
                temporary.write(data)
        os.chmod(path, stat.S_IMODE(information.st_mode))
        os.utime(path, ns=(information.st_atime_ns, information.st_mtime_ns))

    def rollback(self) -> None:
        # ExitStack attempts every callback even when one restoration fails.
        self._undo.close()

    def discard(self) -> None:
        self._undo.pop_all()
