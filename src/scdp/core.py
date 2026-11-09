"""Stable encoding, safe paths, immutable objects and process exclusion."""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def now():
    return datetime.now(UTC).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value):
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value or ":" in value:
        raise ValueError("unsafe_path")
    if any(part in ("", ".", "..") for part in value.split("/")) or any(ord(c) < 32 for c in value):
        raise ValueError("unsafe_path")
    return value


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_json(path, value):
    atomic_write(path, canonical(value) + b"\n")


class Objects:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, digest):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid_digest")
        return self.root / digest[:2] / digest

    def put(self, data):
        digest = sha(data)
        path = self.path(digest)
        if not path.exists() or sha(path.read_bytes()) != digest:
            atomic_write(path, data)
        return digest

    def get(self, digest):
        data = self.path(digest).read_bytes()
        if sha(data) != digest:
            raise ValueError("object_digest_mismatch")
        return data


@contextlib.contextmanager
def job_lock(root):
    Path(root).mkdir(parents=True, exist_ok=True)
    with (Path(root) / "job.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("job_locked") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
