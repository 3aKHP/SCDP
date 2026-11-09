import io
import json
import tarfile
import httpx
import pytest
from scdp.core import canonical
from scdp.official import asset_url, manifest_url
from scdp.pipeline import discover,fetch_stories
from scdp.build import build, decode_all
from scdp.package import pack, unpack, publish, validate_tree
from test_acquisition import encoded, response, downloader


def fixture_work(root):
    base="https://example.test/assets"
    values={manifest_url(base):{"version":1,"chunks":[{"chunk.json":1}]},
            asset_url("chunk.json",base):{"json/demo/fiction.json":1,"spine/fiction/data.atlas":1},
            asset_url("json/demo/fiction.json",base):[{"text":"Fiction"},{"select":"Continue","nextLabel":"end"},{"label":"end","text":"Fiction"}]}
    d=downloader(root,lambda r:response(encoded(values[str(r.url).split("?")[0]])))
    observation=discover(d,base)
    assert fetch_stories(d,observation)["complete"]
    d.close()


def test_full_offline_cycle(tmp_path):
    root=tmp_path/"work"
    fixture_work(root)
    assert decode_all(root)["stories"]==1
    output=tmp_path/"bundle"
    built=build(root,output)
    assert build(root,output)==built
    manifest=json.loads((output/"snapshot.json").read_bytes())
    assert manifest["scope"]["stories"]==1
    archive=tmp_path/"bundle.tar.gz"
    packed=pack(output,archive)
    assert packed==pack(output,archive)
    assert unpack(archive,tmp_path/"installed")==built
    result=publish(archive,tmp_path/"published")
    assert publish(archive,tmp_path/"published")==result
    assert result["snapshotId"]==built["snapshotId"]
    (output/"collection/docs/demo/fiction.md").write_text("bad")
    with pytest.raises(ValueError,match="digest"):
        validate_tree(output)


@pytest.mark.parametrize("name",["../escape.md","/absolute.md","a//b.md","a/../b.md"])
def test_archive_traversal(tmp_path,name):
    archive=tmp_path/"bad.tar.gz"
    with tarfile.open(archive,"w:gz") as t:
        item=tarfile.TarInfo(name);item.size=1;t.addfile(item,io.BytesIO(b"x"))
    with pytest.raises(ValueError):unpack(archive,tmp_path/"out")
    assert not (tmp_path/"out").exists()


def test_archive_link_and_capacity(tmp_path):
    archive=tmp_path/"bad.tar.gz"
    with tarfile.open(archive,"w:gz") as t:
        item=tarfile.TarInfo("link.md");item.type=tarfile.SYMTYPE;item.linkname="other";t.addfile(item)
    with pytest.raises(ValueError,match="unsafe"):unpack(archive,tmp_path/"out")
    with tarfile.open(archive,"w:gz") as t:
        item=tarfile.TarInfo("large.md");item.size=100;t.addfile(item,io.BytesIO(b"x"*100))
    with pytest.raises(ValueError,match="capacity"):unpack(archive,tmp_path/"out",max_bytes=10)
