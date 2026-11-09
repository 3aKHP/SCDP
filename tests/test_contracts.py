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
    assert verify_occurrences(story)==6
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
