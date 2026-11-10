"""Capacity planning and reference-aware collection of owned consumer candidates."""
import json
import re
import shutil
import tarfile
from pathlib import Path

from .core import canonical, safe_path, sha
from .kb import source_manifest

GiB = 1024**3


def tree_bytes(root):
    root = Path(root).resolve()
    if root.is_file():
        return root.stat().st_size
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())


def require_space(root, required):
    free = shutil.disk_usage(root).free
    if free < required:
        raise ValueError("consumer_insufficient_disk_space")
    return {"freeBytes": free, "requiredBytes": required}


def archive_capacity(archive, *, max_bytes=3*GiB, max_files=100000):
    seen, total, collection = set(), 0, 0
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream:
            name = safe_path(member.name)
            if not member.isfile() or name in seen:
                raise ValueError("consumer_unsafe_archive")
            seen.add(name)
            total += member.size
            if name.startswith("collection/"):
                collection += member.size
            if total > max_bytes or len(seen) > max_files:
                raise ValueError("consumer_archive_capacity")
    return {"unpackedBytes": total, "collectionBytes": collection, "files": len(seen)}


def capacity_plan(config, archive):
    layout = archive_capacity(archive, max_bytes=config.get("maxUnpackedBytes", 3*GiB))
    sources = tree_bytes(config["sources"])
    index = Path(config["index"]).stat().st_size
    max_index = config.get("maxIndexBytes", 2*GiB)
    if index > max_index:
        raise ValueError("consumer_index_exceeds_capacity_plan")
    # Existing active and rollback generations are already deducted from free.
    # Native staging clones sources and may retain a replaced collection backup;
    # include preparation, imported collection, native tar, index + journal/temp.
    distribution = layout["unpackedBytes"] + Path(archive).stat().st_size if config.get("distribution") else 0
    required = (layout["unpackedBytes"] + sources + 3*layout["collectionBytes"] + distribution +
                2*max_index + config.get("reserveBytes", 4*GiB))
    return {**layout, "sourceBytes": sources, "maxIndexBytes": max_index,
            **require_space(config["work"], required)}


def retention_plan(config):
    """Only direct owned candidates are managed. Unknown recovery states block GC."""
    root = Path(config["candidates"]).resolve()
    recovery = Path(config["recovery"]).resolve()
    protected = [Path(config["sources"]).resolve(), Path(config["index"]).resolve()]
    active_path = recovery/"active.json"
    active = json.loads(active_path.read_bytes()) if active_path.exists() else None
    if active is None or active.get("state") != "active":
        raise ValueError("retention_active_registry_required")
    candidate = Path(active["candidate"]).resolve()
    if protected != [candidate/"sources", candidate/"index.sqlite3"]:
        raise ValueError("retention_active_pointer_changed")
    backup = recovery/active["activationId"]
    if Path(active["backup"]).resolve() != backup:
        raise ValueError("retention_backup_path_changed")
    for name, flag in (("sources", "hadPreviousSources"), ("index.sqlite3", "hadPreviousIndex")):
        if active[flag]:
            if not (backup/name).exists():
                raise ValueError("retention_previous_generation_missing")
            protected.append((backup/name).resolve())
    if sha(canonical(source_manifest(config["sources"]))) != active["sourceFingerprint"] or sha(Path(config["index"]).read_bytes()) != active["indexSha256"]:
        raise ValueError("retention_active_content_changed")
    if active["hadPreviousSources"] and sha(canonical(source_manifest(backup/"sources"))) != active["baselineFingerprint"]:
        raise ValueError("retention_previous_sources_changed")
    if active["hadPreviousIndex"] and sha((backup/"index.sqlite3").read_bytes()) != active["previousIndexSha256"]:
        raise ValueError("retention_previous_index_changed")
    complete = {"active", "rolled-back", "failed-restored", "recovered-previous"}
    for journal in recovery.glob("*/receipt.json"):
        if json.loads(journal.read_bytes()).get("state") not in complete:
            raise ValueError("retention_unfinished_recovery")
    remove, scratch, keep = [], [], []
    for path in sorted(root.iterdir()):
        if path.is_symlink() or not path.is_dir() or not (path/"scdp-stage.json").is_file():
            continue
        ownership = json.loads((path/"scdp-stage.json").read_bytes())
        if set(ownership) != {"snapshotId", "componentSha256", "baselineFingerprint"}:
            raise ValueError("retention_unknown_ownership")
        in_use = any(p == path or p.is_relative_to(path) for p in protected)
        if in_use:
            keep.append(str(path))
            if not (path/"reconciliation.json").exists():
                raise ValueError("retention_incomplete_active_candidate")
            for child in (path/"candidate", path/"sources/.kbctl-backups", path/"sources/.kbctl-installing"):
                if child.exists() and not child.is_symlink() and not any(p == child or p.is_relative_to(child) for p in protected):
                    scratch.append(str(child))
        else:
            remove.append(str(path))
    return {"keep": keep, "remove": remove, "scratch": scratch,
            "reclaimBytes": sum(tree_bytes(p) for p in remove+scratch)}


def collect_candidates(config):
    # Caller holds the consumer lock and shared deployment lock. Active pointer
    # and recovery checks are repeated immediately before deleting owned paths.
    plan = retention_plan(config)
    for path in plan["remove"]+plan["scratch"]:
        shutil.rmtree(path)
    return plan


def collect_distribution(directory):
    """Caller holds the distribution job lock; keep current and previous archives."""
    directory = Path(directory)
    keep = set()
    for name in ("latest.json", "previous.json"):
        pointer = directory/name
        if not pointer.exists():
            if name == "latest.json":
                raise ValueError("distribution_latest_missing")
            continue
        record = json.loads(pointer.read_bytes())
        filename = record["filename"]
        if filename != record["snapshotId"]+".tar.gz" or not re.fullmatch(r"[a-f0-9]{64}\.tar\.gz", filename):
            raise ValueError("distribution_pointer_invalid")
        path = directory/filename
        if path.is_symlink() or path.stat().st_size != record["bytes"] or sha(path.read_bytes()) != record["sha256"]:
            raise ValueError("distribution_retained_archive_invalid")
        keep.add(filename)
    removed = 0
    for path in directory.iterdir():
        if path.is_file() and not path.is_symlink() and re.fullmatch(r"[a-f0-9]{64}\.tar\.gz", path.name) and path.name not in keep:
            removed += path.stat().st_size
            path.unlink()
    return removed
