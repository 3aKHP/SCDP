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
    assert manifest["scope"]["visibility"] == "public"
    assert "visibility: public\n" in (output/"collection/collection.yaml").read_text()
    archive=tmp_path/"bundle.tar.gz"
    packed=pack(output,archive)
    assert packed==pack(output,archive)
    second=tmp_path/"bundle-second"
    assert build(root,second)==built
    assert pack(second,tmp_path/"second.tar.gz")["sha256"]==packed["sha256"]
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


def test_semantic_check_rejects_rehashed_body_omission(tmp_path):
    from scdp.core import sha,write_json
    root=tmp_path/'work';fixture_work(root)
    output=tmp_path/'bundle';build(root,output)
    path=output/'stories.jsonl'
    story=json.loads(path.read_bytes());story['occurrences'].pop()
    path.write_bytes(canonical(story)+b'\n')
    manifest=json.loads((output/'snapshot.json').read_bytes())
    for entry in manifest['files']:
        if entry['path']=='stories.jsonl':
            entry.update(size=path.stat().st_size,sha256=sha(path.read_bytes()))
    write_json(output/'snapshot.json',manifest)
    with pytest.raises(ValueError,match='body_occurrence_set_mismatch'):
        validate_tree(output)


def test_reading_line_endings_preserve_original_evidence():
    from scdp.story import project
    from scdp.build import render
    from scdp.validation import check_occurrences
    frames=[{'text':'Fiction first\r\nFiction second\rFiction third'}]
    story=project('demo/fiction',frames,'0'*64,'0'*64)
    document=render(story,[])
    assert '\r' not in document
    assert story['frames'][0]['text']==frames[0]['text']
    assert check_occurrences(story,document)[0]==1


def test_interrupted_publication_and_truncated_upload_keep_previous(tmp_path):
    import subprocess
    import sys
    root=tmp_path/'work';fixture_work(root)
    first=tmp_path/'first';second=tmp_path/'second'
    build(root,first);build(root,second,revision=1)
    old=tmp_path/'old.tar.gz';new=tmp_path/'new.tar.gz'
    pack(first,old);pack(second,new)
    destination=tmp_path/'releases'
    previous=publish(old,destination)
    script='''
import os,sys
from pathlib import Path
from scdp.package import publish
original=os.replace
def interrupted(source,target):
    if Path(target).name=='latest.json':os._exit(23)
    original(source,target)
os.replace=interrupted
publish(sys.argv[1],sys.argv[2])
'''
    process=subprocess.run([sys.executable,'-c',script,str(new),str(destination)])
    assert process.returncode==23
    assert json.loads((destination/'latest.json').read_bytes())==previous
    assert len(list(destination.glob('*.tar.gz')))==2
    truncated=tmp_path/'truncated.tar.gz'
    raw=new.read_bytes();truncated.write_bytes(raw[:len(raw)//2])
    with pytest.raises((EOFError,tarfile.ReadError,OSError)):
        publish(truncated,destination)
    assert json.loads((destination/'latest.json').read_bytes())==previous
    current=publish(new,destination)
    assert current['snapshotId']!=previous['snapshotId']
    assert json.loads((destination/'previous.json').read_bytes())==previous
    assert publish(new,destination)==current


def test_reading_segments_keep_dialogue_context_and_control_boundaries():
    from scdp.story import project
    from scdp.build import render
    from scdp.validation import check_occurrences
    frames = [
        {"speaker": "架空甲", "text": "青い傘を持った。"},
        {"speaker": "架空乙", "text": "白い橋で待った。"},
        {"select": "左へ", "nextLabel": "left"},
        {"select": "右へ", "nextLabel": "right"},
        {"label": "left", "text": "左側の出来事。"},
        {"text": "左側の続き。", "nextLabel": "end"},
        {"label": "right", "text": "右側の出来事。"},
        {"command": "conditional_jump", "commandKey": "flag", "nextLabel": "end"},
        {"text": "条件が偽の出来事。"},
        {"futureControl": {"text": "未知の証拠。"}},
        {"label": "end", "text": "終点。"},
        {"label": "end", "text": "同名ラベルも保持。"},
    ]
    story = project('demo/branches', frames, '0'*64, '0'*64)
    translations = [{"pointer": "/0/text", "status": "aligned", "kind": "human", "text": "拿着蓝伞。"}]
    document = render(story, translations)
    sections = document.split('\n## ')
    assert any('青い傘' in s and '白い橋' in s and '拿着蓝伞' in s for s in sections)
    assert not any('左側の出来事' in s and '右側の出来事' in s for s in sections)
    assert not any('条件が偽' in s and '終点。' in s for s in sections)
    assert not any('未知の証拠' in s and '条件が偽' in s for s in sections)
    assert '译文状态：missing' in document
    assert '条件为真' in document and '为假' in document
    assert check_occurrences(story, document)[0] == len(story['occurrences'])
    assert all('控制证据：' + canonical(c).decode() in document for c in story['controls'])
    assert len([s for s in sections if '同名ラベルも保持' in s]) == 1
