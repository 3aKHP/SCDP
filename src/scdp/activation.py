"""Coordinated source/index switching with a maintenance window and exact rollback."""
import json
import os
import re
import sqlite3
import subprocess
import uuid
from pathlib import Path
from .core import canonical, file_lock, job_lock, now, sha, write_json
from .kb import source_manifest


def index_matches_sources(sources, index):
    files = source_manifest(sources)
    with sqlite3.connect(f"file:{Path(index).resolve()}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT path,sha256 FROM documents").fetchall()
    if any(files.get(path) != digest for path, digest in rows):
        raise ValueError("active_source_index_mismatch")
    return len(rows)


def _link(target, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(".scdp-link-"+uuid.uuid4().hex)
    os.symlink(Path(target).resolve(), temporary)
    try:
        os.replace(temporary, destination)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def service_control(service, action):
    if service is None:
        return
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.service", service):
        raise ValueError("invalid_service_name")
    subprocess.run(["sudo", "systemctl", action, service], check=True, capture_output=True)


def activate(candidate, sources, index, recovery, *, service=None, control=service_control, deployment_lock=None):
    candidate = Path(candidate).resolve()
    # Preserve the configured pointer path; do not resolve existing active symlinks.
    sources, index, recovery = Path(sources).absolute(), Path(index).absolute(), Path(recovery).absolute()
    receipt = json.loads((candidate/"reconciliation.json").read_bytes())
    if not receipt.get("fileDigestsMatch") or not receipt.get("indexedNonemptyLinesCovered"):
        raise ValueError("candidate_not_verified")
    if sha(canonical(source_manifest(candidate/"sources"))) != receipt["candidateTreeFingerprint"]:
        raise ValueError("candidate_source_drift")
    if sha((candidate/"index.sqlite3").read_bytes()) != receipt["indexSha256"]:
        raise ValueError("candidate_index_drift")
    index_matches_sources(candidate/"sources", candidate/"index.sqlite3")
    with job_lock(recovery), file_lock(deployment_lock):
        baseline = source_manifest(sources) if sources.exists() else {}
        if sha(canonical(baseline)) != receipt["baselineFingerprint"]:
            raise ValueError("active_baseline_changed")
        if index.exists():
            index_matches_sources(sources, index)
        previous_active = json.loads((recovery/"active.json").read_bytes()) if (recovery/"active.json").exists() else {}
        previous_id = previous_active.get("activationId") if (previous_active.get("state")=="active" and previous_active.get("sourceFingerprint")==receipt["baselineFingerprint"] and index.exists() and previous_active.get("indexSha256")==sha(index.read_bytes())) else None
        identity = uuid.uuid4().hex
        backup = recovery/identity
        backup.mkdir()
        record = {"activationId": identity, "snapshotId": receipt["snapshotId"], "candidate": str(candidate),
                  "sources": str(sources), "index": str(index), "backup": str(backup), "startedAt": now(),
                  "sourceFingerprint": receipt["candidateTreeFingerprint"], "indexSha256": receipt["indexSha256"],
                  "baselineFingerprint": receipt["baselineFingerprint"], "state": "preparing", "previousActivationId": previous_id,
                  "hadPreviousSources": sources.exists() or sources.is_symlink(),
                  "hadPreviousIndex": index.exists() or index.is_symlink(),
                  "previousIndexSha256": sha(index.read_bytes()) if index.exists() else None}
        write_json(backup/"receipt.json", record)
        stopped = False
        moved_sources = moved_index = False
        installed_sources = installed_index = False
        try:
            control(service, "stop")
            stopped = True
            # Re-check after entering maintenance, in case a parallel operator changed
            # the active data while the candidate was being verified.
            if sha(canonical(source_manifest(sources) if sources.exists() else {})) != record["baselineFingerprint"]:
                raise ValueError("active_baseline_changed")
            if sources.exists() or sources.is_symlink():
                os.replace(sources, backup/"sources")
                moved_sources = True
            if index.exists() or index.is_symlink():
                os.replace(index, backup/"index.sqlite3")
                moved_index = True
            _link(candidate/"sources", sources)
            installed_sources = True
            _link(candidate/"index.sqlite3", index)
            installed_index = True
            control(service, "start")
            control(service, "is-active")
            record.update(state="active", endedAt=now(), hadPreviousSources=moved_sources, hadPreviousIndex=moved_index)
            write_json(backup/"receipt.json", record)
            write_json(recovery/"active.json", record)
            return {"snapshotId": record["snapshotId"], "activationId": identity, "state": "active"}
        except BaseException:
            if stopped:
                control(service, "stop")
                if installed_sources and sources.is_symlink():
                    sources.unlink()
                if installed_index and index.is_symlink():
                    index.unlink()
                if moved_sources:
                    os.replace(backup/"sources", sources)
                if moved_index:
                    os.replace(backup/"index.sqlite3", index)
                control(service, "start")
            record.update(state="failed-restored", endedAt=now())
            write_json(backup/"receipt.json", record)
            raise


def rollback(recovery, *, service=None, control=service_control, deployment_lock=None):
    recovery = Path(recovery).absolute()
    with job_lock(recovery), file_lock(deployment_lock):
        record = json.loads((recovery/"active.json").read_bytes())
        if record["state"] != "active":
            raise ValueError("no_active_switch_to_rollback")
        sources, index, backup = Path(record["sources"]), Path(record["index"]), Path(record["backup"])
        candidate = Path(record["candidate"])
        if not sources.is_symlink() or not index.is_symlink() or sources.resolve() != candidate/"sources" or index.resolve() != candidate/"index.sqlite3":
            raise ValueError("active_pointer_changed")
        if sha(canonical(source_manifest(sources))) != record["sourceFingerprint"] or sha(index.read_bytes()) != record["indexSha256"]:
            raise ValueError("active_content_changed")
        if record["hadPreviousSources"] and record["hadPreviousIndex"]:
            index_matches_sources(backup/"sources", backup/"index.sqlite3")
        control(service, "stop")
        try:
            sources.unlink()
            index.unlink()
            if record["hadPreviousSources"]:
                os.replace(backup/"sources", sources)
            if record["hadPreviousIndex"]:
                os.replace(backup/"index.sqlite3", index)
            control(service, "start")
            control(service, "is-active")
        except BaseException:
            # Keep evidence and both generations; the operator can resume the
            # maintenance procedure using the recorded pointer paths.
            record.update(state="rollback-needs-recovery", endedAt=now())
            write_json(recovery/"active.json", record)
            raise
        record.update(state="rolled-back", endedAt=now())
        write_json(backup/"receipt.json", record)
        _restore_active_registry(recovery,record)
        return {"snapshotId": record["snapshotId"], "state": "rolled-back", "activationId": record["activationId"]}


def recover_switch(recovery, activation_id, *, service=None, control=service_control, deployment_lock=None):
    """Recover a process interruption from the journal and actual filesystem state."""
    if not re.fullmatch(r"[0-9a-f]{32}", activation_id):
        raise ValueError("invalid_activation_identity")
    recovery = Path(recovery).absolute()
    with job_lock(recovery), file_lock(deployment_lock):
        journal = recovery/activation_id/"receipt.json"
        record = json.loads(journal.read_bytes())
        sources, index, backup = Path(record["sources"]), Path(record["index"]), Path(record["backup"])
        candidate = Path(record["candidate"])
        old_sources, old_index = backup/"sources", backup/"index.sqlite3"
        source_is_new = sources.is_symlink() and sources.resolve() == candidate/"sources"
        index_is_new = index.is_symlink() and index.resolve() == candidate/"index.sqlite3"
        if sources.exists() and not source_is_new and sha(canonical(source_manifest(sources))) != record["baselineFingerprint"]:
            raise ValueError("recovery_source_state_unknown")
        if index.exists() and not index_is_new and sha(index.read_bytes()) != record["previousIndexSha256"]:
            raise ValueError("recovery_index_state_unknown")
        if old_sources.exists() and sha(canonical(source_manifest(old_sources))) != record["baselineFingerprint"]:
            raise ValueError("recovery_backup_source_drift")
        if old_index.exists() and sha(old_index.read_bytes()) != record["previousIndexSha256"]:
            raise ValueError("recovery_backup_index_drift")
        if record["hadPreviousSources"] and not old_sources.exists() and (source_is_new or not sources.exists()):
            raise ValueError("recovery_source_backup_missing")
        if record["hadPreviousIndex"] and not old_index.exists() and (index_is_new or not index.exists()):
            raise ValueError("recovery_index_backup_missing")
        control(service,"stop")
        if source_is_new:
            sources.unlink()
        if index_is_new:
            index.unlink()
        if old_sources.exists() and not sources.exists():
            os.replace(old_sources,sources)
        if old_index.exists() and not index.exists():
            os.replace(old_index,index)
        if record["hadPreviousSources"] and record["hadPreviousIndex"]:
            index_matches_sources(sources,index)
        control(service,"start")
        control(service,"is-active")
        record.update(state="recovered-previous",endedAt=now())
        write_json(journal,record)
        active = recovery/"active.json"
        if active.exists() and json.loads(active.read_bytes())["activationId"] == activation_id:
            _restore_active_registry(recovery,record)
        return {"activationId":activation_id,"state":"recovered-previous"}


def _restore_active_registry(recovery, record):
    previous_id = record.get("previousActivationId")
    if previous_id:
        previous = json.loads((Path(recovery)/previous_id/"receipt.json").read_bytes())
        sources, index = Path(previous["sources"]), Path(previous["index"])
        if previous["state"] != "active" or sha(canonical(source_manifest(sources))) != previous["sourceFingerprint"] or sha(index.read_bytes()) != previous["indexSha256"]:
            raise ValueError("previous_activation_registry_mismatch")
        write_json(Path(recovery)/"active.json",previous)
    else:
        write_json(Path(recovery)/"active.json",record)
