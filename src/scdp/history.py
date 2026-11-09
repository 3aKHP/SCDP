"""Incremental inventory history and immutable fetched-version evidence."""
import json
import sqlite3
from pathlib import Path
from .core import canonical, safe_path, sha, write_json
from .official import manifest_url, selected


def verify_observation(observation):
    identity = {key: observation[key] for key in ("manifestSha256", "shards", "inventorySha256")}
    if sha(canonical(observation["resources"])) != observation["inventorySha256"] or sha(canonical(identity)) != observation["observationId"]:
        raise ValueError("observation_digest_mismatch")
    if observation["manifest"]["url"] != manifest_url(observation["sourceBase"]):
        raise ValueError("observation_manifest_locator_mismatch")


def inventory_history(root, current):
    root = Path(root)
    verify_observation(current)
    db = sqlite3.connect(root/"inventory-history.sqlite3")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript('''
        CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, ended_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assets(path TEXT PRIMARY KEY, source_version TEXT NOT NULL,
          observation_id TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL);
    ''')
    known = {row[0] for row in db.execute("SELECT id FROM observations")}
    pending = []
    for path in (root/"observations").glob("*.json"):
        if path.stem in known:
            continue
        observation = json.loads(path.read_bytes())
        # Diagnostic observations from a different resolver are retained as evidence,
        # but do not participate in the certified official inventory history.
        if observation["manifest"]["url"] != manifest_url(observation["sourceBase"]):
            continue
        verify_observation(observation)
        pending.append(observation)
    if current["observationId"] not in known and not any(o["observationId"] == current["observationId"] for o in pending):
        pending.append(current)
    try:
        for observation in sorted(pending, key=lambda o: (o["endedAt"], o["observationId"])):
            with db:
                db.executemany('''INSERT INTO assets VALUES(?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET
                    first_seen=min(assets.first_seen,excluded.first_seen),
                    source_version=CASE WHEN excluded.last_seen>=assets.last_seen THEN excluded.source_version ELSE assets.source_version END,
                    observation_id=CASE WHEN excluded.last_seen>=assets.last_seen THEN excluded.observation_id ELSE assets.observation_id END,
                    last_seen=max(assets.last_seen,excluded.last_seen)''',
                    ((safe_path(path), json.dumps(version), observation["observationId"], observation["startedAt"], observation["endedAt"])
                     for path, version in observation["resources"].items()))
                db.execute("INSERT OR IGNORE INTO observations VALUES(?,?)", (observation["observationId"], observation["endedAt"]))
        rows = {}
        for path, version, observation_id, first_seen, last_seen in db.execute("SELECT * FROM assets ORDER BY path"):
            present = path in current["resources"]
            rows[path] = {"sourceVersion": current["resources"][path] if present else json.loads(version),
                          "observationId": current["observationId"] if present else observation_id,
                          "firstSeen": first_seen, "lastSeen": last_seen,
                          "presence": "current" if present else "historical"}
        return rows
    finally:
        db.close()


def save_fetch_record(root, observation_id, record):
    root = Path(root)
    path_hash = sha(safe_path(record["logicalPath"]).encode())
    checkpoint = root/"fetch"/observation_id/(path_hash+".json")
    if checkpoint.exists():
        old = json.loads(checkpoint.read_bytes())
        if old.get("state") == "available":
            archive_fetch_record(root, old)
    if record.get("state") == "available":
        archive_fetch_record(root, record)
    write_json(checkpoint, record)


def archive_fetch_record(root, record):
    path_hash = sha(safe_path(record["logicalPath"]).encode())
    identity = sha(canonical([record["logicalPath"], record["observationId"], record["rawSha256"], record["decodedSha256"]]))
    target = Path(root)/"fetch-history"/path_hash/(identity+".json")
    if not target.exists():
        write_json(target, record)


def story_records(root, observation, history=None):
    """Current complete selection plus successfully archived retired stories."""
    root = Path(root)
    history = inventory_history(root, observation) if history is None else history
    chosen = {}
    for path, state in history.items():
        if not selected(path):
            continue
        path_hash = sha(path.encode())
        checkpoint = root/"fetch"/state["observationId"]/(path_hash+".json")
        record = json.loads(checkpoint.read_bytes()) if checkpoint.exists() else None
        if state["presence"] == "historical" and (not record or record.get("state") != "available"):
            candidates = []
            for archived in (root/"fetch-history"/path_hash).glob("*.json"):
                candidates.append(json.loads(archived.read_bytes()))
            record = max(candidates, key=lambda r: r["observedAt"]) if candidates else None
        if state["presence"] == "current" and (not record or record.get("state") != "available"):
            raise ValueError("unavailable_current_story")
        if record and record.get("state") == "available":
            if record["logicalPath"] != path or (state["presence"] == "current" and (record["sourceVersion"] != state["sourceVersion"] or record["observationId"] != state["observationId"])):
                raise ValueError("story_source_identity_mismatch")
            archive_fetch_record(root, record)
            chosen[path] = record
    return chosen


def content_fingerprint(records):
    return sha(canonical({path: [record["rawSha256"], record["decodedSha256"]] for path, record in sorted(records.items())}))
