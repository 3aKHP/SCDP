"""Portable acquisition state. Never include deployment configuration or run logs."""
import gzip
import contextlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path

from .core import canonical, job_lock, safe_path, sha, write_json

FILES = {"current.json", "cycle-state.json", "state.sqlite3", "inventory-history.sqlite3"}
DIRECTORIES = {"objects", "observations", "fetch", "fetch-history", "build-identities", "translation-cache"}
OPTIONS = {"budgetBytes", "rate", "workers", "rollingChecks", "shardChecks", "sourceBase"}
TRANSLATION = {"identity", "sha256", "repository", "budgetBytes", "responseLimit"}


def allowed(name):
    parts = safe_path(name).split("/")
    return (name == "config.json" or
            (parts[0] == "work" and len(parts) >= 2 and
             ((len(parts) == 2 and parts[1] in FILES) or (len(parts) >= 3 and parts[1] in DIRECTORIES))) or
            name == "inputs/translations.tar.gz" or
            (len(parts) == 3 and parts[:2] == ["inputs", "metadata"] and parts[2].endswith(".json")))


def _copy(source, target):
    source, target = Path(source), Path(target)
    if source.is_symlink() or not source.is_file():
        raise ValueError("checkpoint_non_regular_input")
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix == ".sqlite3":
        with contextlib.closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as src, contextlib.closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")
            if dst.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("checkpoint_database_corrupt")
    else:
        shutil.copyfile(source, target)


def export_checkpoint(config, output, *, locked=False):
    """Caller must stop the old scheduler before the final migration export."""
    root, output = Path(config["work"]), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with (contextlib.nullcontext() if locked else job_lock(root)), tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary)/"state"
        stage.mkdir()
        portable = {key: config[key] for key in OPTIONS if key in config}
        for name in FILES:
            if (root/name).exists():
                _copy(root/name, stage/"work"/name)
        for name in DIRECTORIES:
            for path in sorted((root/name).rglob("*")):
                if path.is_symlink():
                    raise ValueError("checkpoint_symlink")
                if path.is_file() and not path.name.startswith("."):
                    _copy(path, stage/"work"/path.relative_to(root))
        if "translation" in config:
            translation = config["translation"]
            portable["translation"] = {key: translation[key] for key in TRANSLATION if key in translation}
            portable["translation"]["path"] = "inputs/translations.tar.gz"
            _copy(translation["path"], stage/"inputs/translations.tar.gz")
        if config.get("metadata"):
            portable["metadata"] = "inputs/metadata"
            for path in sorted(Path(config["metadata"]).iterdir()):
                if path.suffix != ".json":
                    raise ValueError("checkpoint_unexpected_metadata")
                _copy(path, stage/"inputs/metadata"/path.name)
        write_json(stage/"config.json", portable)
        validate_checkpoint(stage)
        entries = []
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                entries.append({"path": path.relative_to(stage).as_posix(), "size": path.stat().st_size,
                                "sha256": sha(path.read_bytes())})
        write_json(stage/"checkpoint.json", {"format": "scdp-checkpoint/v1", "files": entries})
        archive_path = Path(temporary)/"checkpoint.tar.gz"
        with archive_path.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed, tarfile.open(fileobj=compressed, mode="w") as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    info = archive.gettarinfo(str(path), arcname=path.relative_to(stage).as_posix())
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ""
                    info.mode, info.pax_headers = 0o600, {}
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
        result = {"sha256": sha(archive_path.read_bytes()), "bytes": archive_path.stat().st_size}
        os.replace(archive_path, output)
        return result


def validate_checkpoint(root):
    root = Path(root)
    config = json.loads((root/"config.json").read_bytes())
    if set(config) - OPTIONS - {"translation", "metadata"}:
        raise ValueError("checkpoint_configuration_not_portable")
    if "translation" in config:
        translation = config["translation"]
        if set(translation) - TRANSLATION - {"path"} or translation["path"] != "inputs/translations.tar.gz":
            raise ValueError("checkpoint_translation_not_portable")
        if sha((root/translation["path"]).read_bytes()) != translation["sha256"]:
            raise ValueError("checkpoint_translation_digest")
    if "metadata" in config and config["metadata"] != "inputs/metadata":
        raise ValueError("checkpoint_metadata_not_portable")
    for name in FILES:
        if not (root/"work"/name).is_file():
            raise ValueError("checkpoint_missing_baseline")
    for name in ("state.sqlite3", "inventory-history.sqlite3"):
        with contextlib.closing(sqlite3.connect(f"file:{root/'work'/name}?mode=ro&immutable=1", uri=True)) as db:
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("checkpoint_database_corrupt")
    # Full source/decoder validation also runs in cycle/build before publication.
    for path in (root/"work/objects").rglob("*"):
        if path.is_file() and sha(path.read_bytes()) != path.name:
            raise ValueError("checkpoint_object_digest")
    state = json.loads((root/"work/cycle-state.json").read_bytes())
    if not {"inputs", "snapshotId", "releaseSequence", "publicationRevision"} <= state.keys():
        raise ValueError("checkpoint_missing_publication_identity")
    return state


def restore_checkpoint(archive_path, target, *, max_bytes=4*1024**3, max_files=300000):
    target = Path(target)
    if target.exists():
        raise ValueError("checkpoint_target_exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        stage = Path(temporary)/"state"
        stage.mkdir()
        seen, total = set(), 0
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive:
                name = safe_path(member.name)
                if not member.isfile() or name in seen or (name != "checkpoint.json" and not allowed(name)):
                    raise ValueError("checkpoint_unsafe_member")
                total += member.size
                seen.add(name)
                if total > max_bytes or len(seen) > max_files:
                    raise ValueError("checkpoint_capacity_limit")
                path = stage/name
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as src, path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        manifest = json.loads((stage/"checkpoint.json").read_bytes())
        entries = manifest["files"]
        if manifest["format"] != "scdp-checkpoint/v1" or len(entries) != len(seen)-1 or {e["path"] for e in entries} != seen-{"checkpoint.json"}:
            raise ValueError("checkpoint_file_set")
        for entry in entries:
            path = stage/safe_path(entry["path"])
            if path.stat().st_size != entry["size"] or sha(path.read_bytes()) != entry["sha256"]:
                raise ValueError("checkpoint_digest")
        validate_checkpoint(stage)
        os.replace(stage, target)
    config = json.loads((target/"config.json").read_bytes())
    config.update(work=str(target/"work"), destination=str(target/"releases"))
    if config.get("translation"):
        config["translation"]["path"] = str(target/config["translation"]["path"])
    if config.get("metadata"):
        config["metadata"] = str(target/config["metadata"])
    return config
