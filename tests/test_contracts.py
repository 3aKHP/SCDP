import copy
import json
import subprocess
from pathlib import Path
import pytest
from jsonschema import ValidationError
from scdp.contracts import validate
from scdp.story import project, verify_occurrences
from scdp.core import sha,canonical


def golden():
    return json.loads(Path("tests/fixtures/golden.json").read_bytes())


def test_python_go_contract():
    bundle=golden()
    result=subprocess.run(["go","run","./examples/reader-go/main.go","tests/fixtures/golden.json"],capture_output=True,check=True)
    assert json.loads(result.stdout) == validate(bundle)


def test_required_dependency_and_schema():
    bundle=golden()
    bundle["assets"][0]["dependencies"]=[{"assetId":bundle["assets"][1]["assetId"],"required":True,"relation":"test"}]
    with pytest.raises(ValueError,match="required_dependency"):
        validate(bundle)
    bundle["assets"][0]["dependencies"][0]["required"]=False
    validate(bundle)
    bundle["snapshot"]["schemaVersion"]="2.0.0"
    with pytest.raises(ValidationError):
        validate(bundle)


def test_occurrences_not_game_ids_or_text():
    story=golden()["stories"][0]
    assert verify_occurrences(story)==7
    repeated=[o for o in story["occurrences"] if o["text"]=="また明日。"]
    assert len(repeated)==2 and repeated[0]["pointer"]!=repeated[1]["pointer"]
    assert any(c["status"]=="unresolved" for c in story["controls"])
    assert any(c.get("targets")==[5] for c in story["controls"])
    story["occurrences"].pop()
    with pytest.raises(ValueError,match="coverage"):
        verify_occurrences(story)


def test_multi_page_dependency_and_mime():
    bundle=golden()
    validate(bundle)
    assert bundle['versions'][4]['representations'][0]['mediaType']=='image/webp'
    assert bundle['assets'][4]['logicalPath'].endswith('.png')
    bundle['versions'][5]['availability']='inventoried'
    bundle['versions'][5]['representations']=[]
    with pytest.raises(ValueError,match='required_dependency'):
        validate(bundle)


def test_unknown_field_text_and_graph_are_preserved():
    frames=[{'select':'Left','nextLabel':'left'},{'select':'Right','nextLabel':'right'},
            {'label':'left','text':'Fiction left','nextLabel':'end'},
            {'label':'right','newNestedCommand':{'text':'Unknown fictional dialogue','value':'unknown argument'}},
            {'label':'end','nextLabel':'end'}]
    parsed=project('demo/graph',frames,'0'*64,'0'*64)
    assert parsed['graph']['entries']==[0,1]
    assert parsed['graph']['hasResolvedCycle']
    assert parsed['unknownFrameFields']==['newNestedCommand']
    assert any(o['pointer']=='/3/newNestedCommand/text' for o in parsed['occurrences'])
    assert any(o['text']=='unknown argument' for o in parsed['occurrences'])
    assert any(e['from']==3 and e['status']=='unresolved' for e in parsed['graph']['edges'])
    assert parsed['frames']==frames
