"""Bounded GitHub Release transport and immutable public data publications."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .core import canonical, sha

DATA_TAG = re.compile(r"data-s([1-9][0-9]*)-r(0|[1-9][0-9]*)\Z")
ARCHIVE_NAME = "scdp-phase-one.tar.gz"


class GitHub:
    def __init__(self, repository, token=None, *, transport=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid_repository")
        self.repository = repository
        self.base = "https://api.github.com/repos/"+repository
        self.headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            self.headers["Authorization"] = "Bearer "+token
        self.client = httpx.Client(timeout=120, follow_redirects=False, transport=transport)

    def close(self):
        self.client.close()

    def request(self, method, path, **kwargs):
        response = self.client.request(method, self.base+path, headers=self.headers, **kwargs)
        if response.status_code not in (200, 201, 204):
            raise ValueError("github_http_"+str(response.status_code))
        return response.json() if response.content else None

    def releases(self):
        for page in range(1, 1001):
            values = self.request("GET", "/releases", params={"per_page": 100, "page": page})
            yield from values
            if len(values) < 100:
                return
        raise ValueError("github_release_page_limit")

    def find(self, tag):
        matches = [r for r in self.releases() if r["tag_name"] == tag]
        if len(matches) > 1:
            raise ValueError("github_duplicate_release")
        return matches[0] if matches else None

    def assets(self, release_id):
        result = []
        for page in range(1, 101):
            values = self.request("GET", f"/releases/{release_id}/assets", params={"per_page": 100, "page": page})
            result.extend(values)
            if len(values) < 100:
                return result
        raise ValueError("github_asset_page_limit")

    def download(self, asset, target, *, expected_sha=None, max_bytes=2*1024**3):
        size = asset["size"]
        if not isinstance(size, int) or size < 0 or size > max_bytes:
            raise ValueError("github_asset_size_limit")
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=target.parent)
        digest, received = hashlib.sha256(), 0
        url = self.base+f'/releases/assets/{int(asset["id"])}'
        headers = {**self.headers, "Accept": "application/octet-stream", "Accept-Encoding": "identity"}
        try:
            with os.fdopen(fd, "wb") as out:
                for attempt in range(5):
                    with self.client.stream("GET", url, headers=headers) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            url = response.headers["Location"]
                            parsed = urlparse(url)
                            if parsed.scheme != "https" or parsed.username or not (parsed.hostname or "").endswith(".githubusercontent.com"):
                                raise ValueError("github_asset_redirect")
                            headers = {"Accept-Encoding": "identity"}
                            continue
                        if response.status_code != 200:
                            raise ValueError("github_download_http_"+str(response.status_code))
                        for chunk in response.iter_bytes():
                            received += len(chunk)
                            if received > size:
                                raise ValueError("github_asset_length")
                            digest.update(chunk)
                            out.write(chunk)
                        break
                else:
                    raise ValueError("github_redirect_limit")
            if received != size or (expected_sha and digest.hexdigest() != expected_sha):
                raise ValueError("github_asset_digest_or_length")
            os.replace(temporary, target)
        finally:
            if Path(temporary).exists():
                Path(temporary).unlink()

    def upload(self, release_id, name, path):
        path = Path(path)
        if path.stat().st_size >= 2*1024**3:
            raise ValueError("github_asset_size_limit")
        with path.open("rb") as stream:
            response = self.client.post("https://uploads.github.com/repos/"+self.repository+f"/releases/{release_id}/assets",
                                        params={"name": name}, content=stream,
                                        headers={**self.headers, "Content-Type": "application/octet-stream",
                                                 "Content-Length": str(path.stat().st_size)})
        if response.status_code != 201:
            raise ValueError("github_upload_http_"+str(response.status_code))
        asset = response.json()
        with tempfile.TemporaryDirectory() as tmp:
            self.download(asset, Path(tmp)/"readback", expected_sha=sha(path.read_bytes()))
        return asset


def release_identity(tag):
    match = DATA_TAG.fullmatch(tag)
    return tuple(map(int, match.groups())) if match else None


def newest_data(api):
    candidates = [(release_identity(r["tag_name"]), r) for r in api.releases()
                  if not r["draft"] and not r["prerelease"] and release_identity(r["tag_name"])]
    return max(candidates, key=lambda pair: pair[0])[1] if candidates else None


def unique_asset(assets, name):
    matches = [a for a in assets if a["name"] == name and a["state"] == "uploaded"]
    if len(matches) != 1:
        raise ValueError("github_missing_or_duplicate_asset")
    return matches[0]


def read_descriptor(api, release):
    assets = api.assets(release["id"])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)/"manifest.json"
        api.download(unique_asset(assets, "manifest.json"), path, max_bytes=65536)
        descriptor = json.loads(path.read_bytes())
    required = {"format", "snapshotId", "releaseSequence", "publicationRevision", "filename", "bytes", "sha256"}
    if set(descriptor) != required or descriptor["format"] != "scdp-release/v1" or descriptor["filename"] != ARCHIVE_NAME:
        raise ValueError("github_release_descriptor")
    if (descriptor["releaseSequence"], descriptor["publicationRevision"]) != release_identity(release["tag_name"]):
        raise ValueError("github_release_identity")
    for key in ("sha256", "snapshotId"):
        if not re.fullmatch(r"[a-f0-9]{64}", descriptor[key]):
            raise ValueError("github_release_digest")
    asset = unique_asset(assets, ARCHIVE_NAME)
    if asset["size"] != descriptor["bytes"]:
        raise ValueError("github_release_length")
    return descriptor, asset


def publish_data(api, archive, bundle, publication, *, commit):
    manifest = json.loads((Path(bundle)/"snapshot.json").read_bytes())
    descriptor = {key: publication[key] for key in ("snapshotId", "releaseSequence", "publicationRevision", "bytes", "sha256")}
    descriptor.update(format="scdp-release/v1", filename=ARCHIVE_NAME)
    if sha(Path(archive).read_bytes()) != descriptor["sha256"] or manifest["snapshotId"] != descriptor["snapshotId"]:
        raise ValueError("github_publication_input_mismatch")
    sequence, revision = descriptor["releaseSequence"], descriptor["publicationRevision"]
    tag = f"data-s{sequence}-r{revision}"
    latest = newest_data(api)
    if latest and release_identity(latest["tag_name"]) > (sequence, revision):
        raise ValueError("github_publication_order")
    release = api.find(tag)
    if release is None:
        release = api.request("POST", "/releases", json={"tag_name": tag, "target_commitish": commit,
                              "name": f"闪彩剧情数据 · {sequence}.{revision}", "draft": True,
                              "body": f"收录 {manifest['scope']['stories']:,} 篇剧情，保留原文、已有译文及分支。\n\n"
                                      "下载标准包后先核对 SHA256SUMS；程序可读取 manifest.json。\n\n"
                                      "游戏原文及译文保留各自权利，说明和权利通知入口见随包 NOTICE.md。"})
    if release.get("prerelease"):
        raise ValueError("github_publication_prerelease_conflict")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root/"manifest.json").write_bytes(canonical(descriptor)+b"\n")
        notice = Path(bundle)/"NOTICE.md"
        # Use the repository notice when the historical bundle has no copy.
        if not notice.exists():
            notice = Path("NOTICE.md")
        (root/"SHA256SUMS").write_text(f"{descriptor['sha256']}  {ARCHIVE_NAME}\n", encoding="utf-8")
        paths = {ARCHIVE_NAME: Path(archive), "manifest.json": root/"manifest.json", "SHA256SUMS": root/"SHA256SUMS", "NOTICE.md": notice}
        assets = api.assets(release["id"])
        if {a["name"] for a in assets} - paths.keys():
            raise ValueError("github_publication_unexpected_assets")
        for name, path in paths.items():
            existing = [a for a in assets if a["name"] == name]
            if existing:
                asset = unique_asset(assets, name)
                api.download(asset, root/("verify-"+name), expected_sha=sha(path.read_bytes()))
            elif release["draft"]:
                api.upload(release["id"], name, path)
            else:
                raise ValueError("github_publication_incomplete")
    if release["draft"]:
        release = api.request("PATCH", f'/releases/{release["id"]}', json={"draft": False, "make_latest": "true"})
    actual, _ = read_descriptor(api, release)
    if release["draft"] or actual != descriptor:
        raise ValueError("github_publication_readback")
    return descriptor
