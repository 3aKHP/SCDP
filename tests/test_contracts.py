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


def test_source_state_condition_keeps_both_routes():
    frames=[{'command':'conditional_jump','commandKey':'fiction_read','nextLabel':'seen'},
            {'text':'Fiction unseen route','nextLabel':'end'},
            {'label':'seen','text':'Fiction seen route'}, {'label':'end'}]
    story=project('demo/condition',frames,'0'*64,'0'*64)
    edges=[e for e in story['graph']['edges'] if e['from']==0]
    assert {e['predicate']['equals'] for e in edges}=={True,False}
    assert {tuple(e['targets']) for e in edges}=={(1,),(2,)}
    assert all(e['status']=='conditional' for e in edges)
    assert not story['graph']['notProvenReachable']


def test_duplicate_label_uses_first_source_occurrence():
    frames=[{'nextLabel':'same'},{'label':'same','text':'Fiction first'},{'label':'same','text':'Fiction second'}]
    story=project('demo/duplicate-label',frames,'0'*64,'0'*64)
    jump=story['graph']['edges'][0]
    assert jump['targets']==[1] and jump['labelCandidates']==[1,2] and jump['status']=='resolved'


def test_control_graph_schema_rejects_invalid_target_type():
    bundle=golden()
    bundle['stories'][0]['graph']['edges'][0]['targets']=['not-an-index']
    with pytest.raises(ValidationError):validate(bundle)
