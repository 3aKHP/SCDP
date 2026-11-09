"""Independent, pinned translation input refresh with a separate persistent budget."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
import httpx
from .core import sha, write_json
from .translation import read_archive


def translation_source(config, root, *, transport=None):
    if not config:
        return None, "absent", {"state": "absent", "receivedBytes": 0}
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    identity = config["identity"]
    repository = config.get("repository")
    if repository:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid_translation_repository")
        result = subprocess.run(["git", "ls-remote", "https://github.com/"+repository+".git", "HEAD"],
                                capture_output=True, text=True, timeout=30, check=True)
        identity = result.stdout.split()[0]
        if not re.fullmatch(r"[a-f0-9]{40}", identity):
            raise ValueError("invalid_translation_commit")
    if identity == config["identity"]:
        path = Path(config["path"])
        if sha(path.read_bytes()) != config["sha256"]:
            raise ValueError("pinned_translation_digest_mismatch")
        return path, identity, {"state": "pinned-cache", "receivedBytes": 0, "versionChecks": int(bool(repository))}
    archive, metadata = root/(identity+".tar.gz"), root/(identity+".json")
    if archive.exists() and metadata.exists():
        record = json.loads(metadata.read_bytes())
        if record["identity"] == identity and sha(archive.read_bytes()) == record["sha256"]:
            return archive, identity, {"state": "cache", "receivedBytes": 0}
    ledger_path = root/"ledger.json"
    ledger = json.loads(ledger_path.read_bytes()) if ledger_path.exists() else {"receivedBytes": 0, "requests": 0}
    budget = config.get("budgetBytes", 256*1024**2)
    limit = config.get("responseLimit", 64*1024**2)
    remaining = budget-ledger["receivedBytes"]
    if remaining <= 0:
        raise ValueError("translation_budget_exhausted")
    reservation = min(limit+1, remaining)
    ledger["receivedBytes"] += reservation
    ledger["requests"] += 1
    write_json(ledger_path, ledger)
    fd, temporary = tempfile.mkstemp(dir=root, prefix=".translation-")
    received = 0
    try:
        with os.fdopen(fd, "wb") as out, httpx.Client(timeout=60, follow_redirects=False, transport=transport, headers={"Accept-Encoding":"identity"}) as client:
            with client.stream("GET", "https://codeload.github.com/"+repository+"/tar.gz/"+identity) as response:
                for chunk in response.iter_raw():
                    received += len(chunk)
                    if received > reservation or received > limit:
                        raise ValueError("translation_response_limit")
                    out.write(chunk)
                    if received == reservation and reservation <= limit:
                        raise ValueError("translation_budget_exhausted")
                if response.status_code != 200:
                    raise ValueError("translation_http_failure")
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise ValueError("translation_http_encoding")
                out.flush()
                os.fsync(out.fileno())
        records, _ = read_archive(temporary, identity)
        if not records:
            raise ValueError("translation_snapshot_empty")
        digest = sha(Path(temporary).read_bytes())
        os.replace(temporary, archive)
        write_json(metadata, {"identity": identity, "sha256": digest, "bytes": received})
        return archive, identity, {"state": "downloaded", "receivedBytes": received, "sha256": digest}
    finally:
        ledger["receivedBytes"] += received-reservation
        write_json(ledger_path, ledger)
        if Path(temporary).exists():
            Path(temporary).unlink()
