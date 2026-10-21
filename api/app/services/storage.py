import uuid
from pathlib import Path

from app.core.config import get_settings


class StorageError(Exception):
    pass


class LocalFilesystemStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        root = self.root.resolve()
        path = (self.root / key).resolve()
        if root != path and root not in path.parents:
            raise StorageError("Invalid storage key")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


def generate_storage_key(prefix: str) -> str:
    return f"{prefix}/{uuid.uuid4()}.pdf"


def get_storage() -> LocalFilesystemStorage:
    return LocalFilesystemStorage(get_settings().storage_root)
