"""Bounded HTTP acquisition with durable attempts, conservative byte accounting and cache."""
import email.utils
import json
import sqlite3
import threading
import time
from pathlib import Path

import httpx
from .core import Objects, canonical, now, sha
from .official import decode


class BudgetExceeded(RuntimeError):
    pass


class AcquisitionError(RuntimeError):
    pass


class Downloader:
    def __init__(self, root, *, budget=1024**3, response_limit=16*1024**2, rate=1.0,
                 attempts=4, timeout=30, transport=None):
        if budget < 1 or response_limit < 1 or rate <= 0 or attempts < 1:
            raise ValueError("invalid_download_configuration")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects = Objects(self.root / "objects")
        self.db = sqlite3.connect(self.root / "state.sqlite3", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY CHECK(id=1), received INTEGER NOT NULL, requests INTEGER NOT NULL);
          INSERT OR IGNORE INTO ledger VALUES(1,0,0);
          CREATE TABLE IF NOT EXISTS requests(key TEXT PRIMARY KEY, record TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, record TEXT NOT NULL);
        ''')
        self.db.commit()
        self.mutex = threading.RLock()
        self.rate_lock = threading.Lock()
        self.next_start = 0
        self.budget, self.response_limit, self.rate, self.attempts = budget, response_limit, rate, attempts
        self.client = httpx.Client(timeout=timeout, follow_redirects=False, transport=transport,
                                   headers={"Accept-Encoding": "identity", "User-Agent": "SCDP/0.1"})

    def close(self):
        self.client.close()
        self.db.close()

    def event(self, kind, value):
        with self.mutex, self.db:
            self.db.execute("INSERT INTO events(at,kind,record) VALUES(?,?,?)", (now(), kind, canonical(value).decode()))

    def status(self):
        with self.mutex:
            received, requests = self.db.execute("SELECT received,requests FROM ledger WHERE id=1").fetchone()
            return {"receivedBytes": received, "requests": requests, "budgetBytes": self.budget}

    def _charge(self, amount):
        with self.mutex, self.db:
            used = self.db.execute("SELECT received FROM ledger WHERE id=1").fetchone()[0]
            if used + amount > self.budget:
                raise BudgetExceeded("job_byte_budget")
            self.db.execute("UPDATE ledger SET received=received+? WHERE id=1", (amount,))

    def _save(self, key, value):
        with self.mutex, self.db:
            self.db.execute("INSERT OR REPLACE INTO requests VALUES(?,?)", (key, canonical(value).decode()))

    def _load(self, key):
        with self.mutex:
            row = self.db.execute("SELECT record FROM requests WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _pace(self):
        with self.rate_lock:
            time.sleep(max(0, self.next_start - time.monotonic()))
            self.next_start = time.monotonic() + 1 / self.rate

    def fetch(self, path, url, validator, *, revalidate=False):
        # Cache identity includes logical path, actual URL (including version), and decoder version.
        key = sha(canonical([path, url, "official-v1"]))
        previous = self._load(key)
        cached = None
        if previous and previous.get("state") == "available":
            try:
                raw = self.objects.get(previous["rawSha256"])
                decoded = self.objects.get(previous["decodedSha256"])
                if decode(path, raw, self.response_limit) != decoded:
                    raise ValueError("cache_decode_mismatch")
                validator(decoded)
                cached = previous
                if not revalidate:
                    return cached
            except (ValueError, OSError):
                self.event("cache_corrupt", {"key": key})
        used_attempts = previous.get("attempts", 0) if previous and not cached else 0
        if used_attempts >= self.attempts:
            # Negative results have an explicit expiry; retries retain cumulative accounting.
            if time.time() < previous.get("retryAfter", 0):
                raise AcquisitionError(previous.get("error", "attempts_exhausted"))
            used_attempts = 0
        headers = {}
        if cached and cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        for attempt in range(used_attempts + 1, self.attempts + 1):
            self._pace()
            record = {"logicalPath": path, "url": url, "state": "pending", "attempts": attempt, "observedAt": now()}
            self._save(key, record)
            with self.mutex, self.db:
                self.db.execute("UPDATE ledger SET requests=requests+1 WHERE id=1")
            retry_delay = min(2 ** (attempt - 1), 30)
            chunks = []
            error = "unknown_error"
            received = 0
            try:
                with self.client.stream("GET", url, headers=headers) as response:
                    record["httpStatus"] = response.status_code
                    record["contentType"] = response.headers.get("Content-Type")
                    if response.status_code == 304:
                        if not cached:
                            raise ValueError("unexpected_304")
                        result = {**cached, "observedAt": now(), "httpStatus": 304, "attempts": 0}
                        self._save(key, result)
                        return result
                    if response.headers.get("Retry-After"):
                        value = response.headers["Retry-After"]
                        try:
                            retry_delay = max(0, float(value))
                        except ValueError:
                            retry_delay = max(0, email.utils.parsedate_to_datetime(value).timestamp() - time.time())
                    # Reserve up to one response before reading; crash conservatively charges the
                    # reservation. Release only known unused bytes on normal exit. Concurrent
                    # reservations share one persistent budget; final transport buffers are charged too.
                    with self.mutex:
                        remaining = self.budget - self.status()["receivedBytes"]
                        reservation = min(self.response_limit + 1, remaining)
                        if reservation <= 0:
                            raise BudgetExceeded("job_byte_budget")
                        self._charge(reservation)
                    try:
                        for chunk in response.iter_raw():
                            received += len(chunk)
                            chunks.append(chunk)
                            record["receivedBytes"] = received
                            if received > reservation:
                                # A final transport buffer may already have arrived; account for it.
                                with self.mutex, self.db:
                                    self.db.execute("UPDATE ledger SET received=received+? WHERE id=1", (received-reservation,))
                                reservation = received
                                if received > self.response_limit:
                                    raise ValueError("response_limit")
                                raise BudgetExceeded("job_byte_budget")
                            if received > self.response_limit:
                                raise ValueError("response_limit")
                            if received >= reservation and reservation <= self.response_limit:
                                raise BudgetExceeded("job_byte_budget")
                    finally:
                        self._charge(-(reservation - received))
                    content = b"".join(chunks)
                    record["receivedBytes"] = received
                    record["rawSha256"] = self.objects.put(content)
                    if response.status_code != 200:
                        raise ValueError(f"http_{response.status_code}")
                    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                        raise ValueError("unexpected_http_encoding")
                    mime = response.headers.get("Content-Type", "").split(";")[0].lower()
                    if mime not in ("application/octet-stream", "application/json", "binary/octet-stream", "text/plain", ""):
                        raise ValueError("unexpected_content_type")
                    if response.headers.get("Content-Length") and int(response.headers["Content-Length"]) != received:
                        raise ValueError("truncated_response")
                    decoded = decode(path, content, self.response_limit)
                    validator(decoded)
                    record.update(state="available", decodedSha256=self.objects.put(decoded),
                                  decodedBytes=len(decoded), etag=response.headers.get("ETag"), attempts=0)
                    if cached and cached["decodedSha256"] != record["decodedSha256"]:
                        self.event("same_locator_drift", {"key": key, "old": cached["decodedSha256"], "new": record["decodedSha256"]})
                    self._save(key, record)
                    return record
            except BudgetExceeded:
                if chunks:
                    record["quarantineSha256"] = self.objects.put(b"".join(chunks))
                record.update(state="retryable_error", error="job_byte_budget", attempts=attempt-1)
                self._save(key, record)
                raise
            except (httpx.HTTPError, ValueError, OSError) as exc:
                error = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                # Store partial entities as quarantine evidence, never as available cache.
                if chunks:
                    record["quarantineSha256"] = self.objects.put(b"".join(chunks))
                record.update(state="retryable_error", error=error, retryAfter=time.time()+max(retry_delay, 300))
                self._save(key, record)
                self.event("request_failed", {"key": key, "attempt": attempt, "error": error, "receivedBytes": received})
            if attempt < self.attempts:
                # Long server backoff is persisted; do not occupy a worker indefinitely.
                if retry_delay > 60:
                    record["attempts"] = self.attempts
                    self._save(key, record)
                    break
                time.sleep(retry_delay)
        raise AcquisitionError(error)
