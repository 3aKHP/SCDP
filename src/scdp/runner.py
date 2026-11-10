"""GitHub-hosted producer with durable private checkpoints and crash exclusion."""
import argparse
import json
import os
import re
import sys
import sqlite3
import tempfile
import uuid
from pathlib import Path

from .checkpoint import export_checkpoint, restore_checkpoint
from .core import canonical, now, sha, write_json
from .cycle import cycle
from .github_release import GitHub, publish_data

STATE_TAG = "scdp-runner-state"
STATE_FORMAT = "scdp-runner-state/v1"


def state_record(api):
    release = api.find(STATE_TAG)
    if release is None or not release["draft"]:
        raise ValueError("runner_private_state_missing")
    state = json.loads(release["body"])
    if state.get("format") != STATE_FORMAT or not state.get("head"):
        raise ValueError("runner_state_format")
    return release, state


def write_state(api, release, state):
    fresh = api.request("GET", f'/releases/{release["id"]}')
    if not fresh["draft"] or fresh["tag_name"] != STATE_TAG or fresh["body"] != release["body"]:
        raise ValueError("runner_state_changed")
    updated = api.request("PATCH", f'/releases/{release["id"]}', json={"body": canonical(state).decode()})
    if not updated["draft"] or json.loads(updated["body"]) != state:
        raise ValueError("runner_state_readback")
    return updated


def upload_checkpoint(api, release, config, output, *, locked=False):
    metadata = export_checkpoint(config, output, locked=locked)
    asset = api.upload(release["id"], "checkpoint-"+uuid.uuid4().hex+".tar.gz", output)
    return {**metadata, "id": asset["id"], "name": asset["name"], "size": asset["size"]}


def initialize(api, checkpoint, commit):
    release = api.find(STATE_TAG)
    if release is not None and (not release["draft"] or json.loads(release["body"]).get("head")):
        raise ValueError("runner_state_already_exists")
    with tempfile.TemporaryDirectory() as tmp:
        restore_checkpoint(checkpoint, Path(tmp)/"verify")
    release = release or api.request("POST", "/releases", json={"tag_name": STATE_TAG, "target_commitish": commit,
                          "draft": True, "name": "SCDP private runner state — DO NOT PUBLISH",
                          "body": canonical({"format": STATE_FORMAT, "head": None, "lease": None}).decode()})
    asset = api.upload(release["id"], "checkpoint-"+uuid.uuid4().hex+".tar.gz", checkpoint)
    head = {"id": asset["id"], "name": asset["name"], "size": asset["size"],
            "bytes": Path(checkpoint).stat().st_size, "sha256": sha(Path(checkpoint).read_bytes())}
    write_state(api, release, {"format": STATE_FORMAT, "head": head, "previous": None, "lease": None, "updatedAt": now()})
    return {"state": "initialized", "sha256": head["sha256"]}


def recover(api, directory, expected_lease):
    release, state = state_record(api)
    lease = state.get("lease")
    if not lease or lease["id"] != expected_lease:
        raise ValueError("runner_recovery_lease_changed")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    head = lease.get("pending", state["head"])
    api.download(head, directory/"recovery.tar.gz", expected_sha=head["sha256"])
    config = restore_checkpoint(directory/"recovery.tar.gz", directory/"restored")
    # A lost runner can have received unrecorded bytes after this checkpoint.
    # Charge ALL remaining authorized bytes, never silently reset the budget.
    with sqlite3.connect(Path(config["work"])/"state.sqlite3") as db:
        db.execute("UPDATE ledger SET received=max(received,?) WHERE id=1", (config.get("budgetBytes", 1024**3),))
    if config.get("translation"):
        ledger_path = Path(config["work"])/"translation-cache/ledger.json"
        ledger = json.loads(ledger_path.read_bytes()) if ledger_path.exists() else {"receivedBytes": 0, "requests": 0}
        ledger["receivedBytes"] = max(ledger["receivedBytes"], config["translation"].get("budgetBytes", 256*1024**2))
        write_json(ledger_path, ledger)
    recovered = upload_checkpoint(api, release, config, directory/"recovered.tar.gz")
    state.update(previous=state["head"], head=recovered, lease=None, updatedAt=now(),
                 recovery={"leaseId": expected_lease, "accounting": "all-remaining-authorized-bytes-charged", "requestCount": "lower-bound"})
    write_state(api, release, state)
    return {"state": "recovered-budget-exhausted", "sha256": recovered["sha256"]}


def run(api, directory, commit, *, cycle_fn=cycle):
    release, state = state_record(api)
    if state.get("lease"):
        raise ValueError("runner_unfinished_run_requires_recovery")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    api.download(state["head"], directory/"input.tar.gz", expected_sha=state["head"]["sha256"])
    config = restore_checkpoint(directory/"input.tar.gz", directory/"restored")
    config["codeCommit"] = commit
    state["lease"] = {"id": uuid.uuid4().hex, "startedAt": now(), "commit": commit}
    release = write_state(api, release, state)

    def publisher(archive, bundle, publication):
        nonlocal release
        # Persist newly acquired originals before making their derived package public.
        pending = upload_checkpoint(api, release, config, directory/"pending.tar.gz", locked=True)
        state["lease"]["pending"] = pending
        release = write_state(api, release, state)
        publish_data(api, archive, bundle, publication, commit=commit)

    result = None
    try:
        result = cycle_fn(config, publisher=publisher)
    finally:
        # Normal failures preserve the cumulative ledger too. If this fails, the
        # lease remains occupied; later runs must never silently use the old ledger.
        head = upload_checkpoint(api, release, config, directory/"output.tar.gz")
        state.update(previous=state["head"], head=head, lease=None, updatedAt=now())
        release = write_state(api, release, state)
        # Only managed checkpoint assets are collected; current + predecessor stay.
        keep = {state["head"]["id"], state["previous"]["id"]}
        for asset in api.assets(release["id"]):
            if asset["id"] not in keep and re.fullmatch(r"checkpoint-[a-f0-9]{32}\.tar\.gz", asset["name"]):
                api.request("DELETE", f'/releases/assets/{asset["id"]}')
    return {key: result[key] for key in ("state", "snapshotId")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--config", required=True)
    export.add_argument("--output", required=True)
    for name in ("initialize", "run"):
        command = sub.add_parser(name)
        command.add_argument("--repository", required=True)
        command.add_argument("--commit", required=True)
        if name == "initialize":
            command.add_argument("--checkpoint", required=True)
        else:
            command.add_argument("--directory", required=True)
    recovery = sub.add_parser("recover")
    recovery.add_argument("--repository", required=True)
    recovery.add_argument("--directory", required=True)
    recovery.add_argument("--expected-lease", required=True)
    args = parser.parse_args()
    api = None
    try:
        if args.command == "export":
            result = export_checkpoint(json.loads(Path(args.config).read_bytes()), args.output)
        else:
            if args.command != "recover" and not re.fullmatch(r"[0-9a-f]{40}", args.commit):
                raise ValueError("runner_commit_required")
            if args.command == "run" and (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
                raise ValueError("runner_requires_github_hosted")
            api = GitHub(args.repository, os.environ["GH_TOKEN"])
            if args.command == "recover":
                result = recover(api, args.directory, args.expected_lease)
            else:
                result = initialize(api, args.checkpoint, args.commit) if args.command == "initialize" else run(api, args.directory, args.commit)
        print(json.dumps(result, sort_keys=True))
    except BaseException as exc:
        # Public logs contain classifications only, never local paths, URLs or credentials.
        code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[a-z0-9_]+", str(exc)) else type(exc).__name__
        print(json.dumps({"state": "failed", "error": code}), file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        if api:
            api.close()


if __name__ == "__main__":
    main()
