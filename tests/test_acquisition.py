import gzip
import json
import zlib
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from scdp.core import Objects, canonical, job_lock, safe_path
from scdp.fetch import AcquisitionError, BudgetExceeded, Downloader
from scdp.official import decode, xor, validate_story
from scdp.pipeline import discover, fetch_stories


def encoded(value, flushed=False):
    raw = canonical(value)
    if flushed:
        compressor = zlib.compressobj(wbits=31)
        return xor(compressor.compress(raw)+compressor.flush(zlib.Z_SYNC_FLUSH))
    return xor(gzip.compress(raw, mtime=0))


def response(body, status=200, **headers):
    return httpx.Response(status, headers={"Content-Type": "application/octet-stream", **headers}, stream=httpx.ByteStream(body))


def downloader(tmp_path, handler, **kwargs):
    return Downloader(tmp_path, rate=100000, transport=httpx.MockTransport(handler), **kwargs)


@pytest.mark.parametrize("path", ["/a", "a/../b", "a//b", "a/./b", "C:/x", "a\\b", "a\x00b", ""])
def test_paths(path):
    with pytest.raises(ValueError):
        safe_path(path)


def test_decode():
    value = [{"id": 0, "text": "Invented scene"}, {"id": 0, "select": "Invented choice", "nextLabel": "end"}]
    for flushed in (True, False):
        data = encoded(value, flushed)
        assert json.loads(decode("x.json", data)) == value
        with pytest.raises(ValueError):
            decode("x.json", data[:-5])
        with pytest.raises(ValueError, match="decoded_limit"):
            decode("x.json", data, 4)
    with pytest.raises(ValueError, match="maintenance_html"):
        decode("x.json", b"<html>maintenance</html>")


def test_resume_cache_and_drift(tmp_path):
    content = encoded([{"text": "Fiction A"}])
    d = downloader(tmp_path, lambda r: response(content, ETag='"one"'))
    first = d.fetch("story.json", "https://example.test/one", validate_story)
    first_bytes = d.status()["receivedBytes"]
    d.close()
    d = downloader(tmp_path, lambda r: response(b"", 304))
    assert d.fetch("story.json", "https://example.test/one", validate_story)["decodedSha256"] == first["decodedSha256"]
    assert d.status()["requests"] == 1
    assert d.fetch("story.json", "https://example.test/one", validate_story, revalidate=True)["httpStatus"] == 304
    assert d.status()["receivedBytes"] == first_bytes
    d.close()
    changed = encoded([{"text": "Fiction B"}])
    d = downloader(tmp_path, lambda r: response(changed))
    new = d.fetch("story.json", "https://example.test/one", validate_story, revalidate=True)
    assert new["decodedSha256"] != first["decodedSha256"]
    assert d.objects.get(first["decodedSha256"])
    assert d.db.execute("SELECT count(*) FROM events WHERE kind='same_locator_drift'").fetchone()[0] == 1
    d.close()


@pytest.mark.parametrize("body,status,headers", [
    (b"maintenance", 503, {}), (b"<html>maintenance</html>", 200, {}),
    (encoded([{"text":"Fiction"}])[:-8], 200, {}),
    (encoded({"wrong":"shape"}), 200, {}),
    (encoded([]), 200, {"Content-Type":"text/html"}),
    (encoded([]), 200, {"Content-Length":"999"}),
    (b"x"*200, 200, {}),
])
def test_failed_entities_never_available(tmp_path, body, status, headers):
    d = downloader(tmp_path, lambda r: response(body,status,**headers), attempts=1, response_limit=100)
    with pytest.raises((AcquisitionError, BudgetExceeded)):
        d.fetch("story.json", "https://example.test/one", validate_story)
    records = [json.loads(row[0]) for row in d.db.execute("SELECT record FROM requests")]
    assert all(r["state"] != "available" for r in records)
    assert d.status()["receivedBytes"] > 0
    d.close()


def test_retry_counts_failed_bytes(tmp_path):
    body = encoded([{"text":"Invented"}])
    responses = iter([response(b"slow",429,**{"Retry-After":"0"}), response(body)])
    d = downloader(tmp_path, lambda r: next(responses))
    d.fetch("story.json", "https://example.test/one", validate_story)
    assert d.status()["requests"] == 2
    assert d.status()["receivedBytes"] == len(body)+4
    d.close()


def test_persistent_budget(tmp_path):
    body = encoded([{"text":"Invented"}])
    d = downloader(tmp_path, lambda r: response(body), budget=10)
    with pytest.raises(BudgetExceeded):
        d.fetch("story.json", "https://example.test/one", validate_story)
    assert d.status()["receivedBytes"] == len(body)
    d.close()
    d = downloader(tmp_path, lambda r: response(body), budget=10)
    with pytest.raises(BudgetExceeded):
        d.fetch("story.json", "https://example.test/one", validate_story)
    assert d.status()["receivedBytes"] == len(body)
    d.close()


def test_corrupt_cache_refetched(tmp_path):
    body = encoded([{"text":"Fiction"}])
    d = downloader(tmp_path, lambda r: response(body))
    first = d.fetch("story.json", "https://example.test/one", validate_story)
    d.objects.path(first["rawSha256"]).write_bytes(b"corrupt")
    d.fetch("story.json", "https://example.test/one", validate_story)
    assert d.status()["requests"] == 2
    assert d.objects.get(first["rawSha256"]) == body
    d.close()


def test_lock(tmp_path):
    with job_lock(tmp_path):
        with pytest.raises(ValueError, match="job_locked"):
            with job_lock(tmp_path):
                pass
    with job_lock(tmp_path):
        pass


def test_discover_fetch_offline(tmp_path):
    from scdp.official import asset_url, manifest_url
    base = "https://example.test/assets"
    values = {"asset-map.json": {"version": 7, "chunks": [{"chunk.json":2}]},
              "chunk.json": {"json/demo/fiction.json":1, "json/support_skills/excluded.json":1, "sounds/bgm/sample.mp3":1},
              "json/demo/fiction.json": [{"id":0,"text":"Invented"}, {"id":0,"select":"Go", "nextLabel":"end"}, {"label":"end"}]}
    bodies = {(manifest_url(base) if p=="asset-map.json" else asset_url(p, base)): encoded(v) for p,v in values.items()}
    d = downloader(tmp_path, lambda r: response(bodies[str(r.url).split("?")[0]]))
    observation = discover(d,base)
    assert observation["selected"] == 1
    assert len(observation["resources"]) == 3
    result = fetch_stories(d,observation)
    assert result["complete"]
    before = d.status()
    assert fetch_stories(d,observation)["complete"]
    assert d.status() == before
    d.close()


def test_manifest_url_is_distinct():
    from scdp.official import asset_url,manifest_url
    assert manifest_url().rsplit("/",1)[1]=="asset-map-"+asset_url("asset-map.json").rsplit("/",1)[1]


def test_concurrent_accounting(tmp_path):
    body=encoded([{"text":"fiction"}])
    d=downloader(tmp_path,lambda r:response(body),response_limit=100,budget=1000)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda i:d.fetch("story.json",f"https://example.test/{i}",validate_story),range(2)))
    assert all(r["state"]=="available" for r in results)
    assert d.status()["receivedBytes"]==2*len(body)
    d.close()


def test_timeout_and_negative_cache(tmp_path):
    def handler(request):raise httpx.ReadTimeout("synthetic")
    d=downloader(tmp_path,handler,attempts=1)
    with pytest.raises(AcquisitionError,match="ReadTimeout"):d.fetch("story.json","https://example.test/one",validate_story)
    with pytest.raises(AcquisitionError):d.fetch("story.json","https://example.test/one",validate_story)
    assert d.status()["requests"]==1
    d.close()


def test_disk_error_does_not_commit_available(tmp_path,monkeypatch):
    d=downloader(tmp_path,lambda r:response(encoded([])),attempts=1)
    def full(_):raise OSError("synthetic disk full")
    monkeypatch.setattr(d.objects,"put",full)
    with pytest.raises(OSError):d.fetch("story.json","https://example.test/one",validate_story)
    assert all(json.loads(r[0])["state"]!="available" for r in d.db.execute("SELECT record FROM requests"))
    d.close()


def test_interrupted_body_is_charged_and_recoverable(tmp_path):
    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b'x'*65536
            raise httpx.ReadError('synthetic disconnect')
    body=encoded([{'text':'Fiction recovered'}])
    calls=0
    def handler(request):
        nonlocal calls
        calls+=1
        if calls==1:return httpx.Response(200,headers={'Content-Type':'application/octet-stream'},stream=Interrupted())
        return response(body)
    d=downloader(tmp_path,handler)
    result=d.fetch('story.json','https://example.test/recovery',validate_story)
    assert result['state']=='available'
    assert d.status()['requests']==2
    assert d.status()['receivedBytes']==65536+len(body)
    d.close()


def test_short_interrupted_body_is_also_charged(tmp_path):
    class ShortInterrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial"
            raise httpx.ReadError("synthetic short disconnect")
    d=downloader(tmp_path,lambda _:httpx.Response(200,stream=ShortInterrupted()),attempts=1)
    with pytest.raises(AcquisitionError):
        d.fetch("story.json","https://example.test/short",validate_story)
    assert d.status()["receivedBytes"]==7
    d.close()
