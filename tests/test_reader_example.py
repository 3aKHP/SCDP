"""Exercise the public reader against a fictional bundle, not game text."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'examples/read_story.py'
spec = importlib.util.spec_from_file_location('read_story', SCRIPT)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


@pytest.fixture
def bundle(tmp_path):
    collection = tmp_path / 'collection'
    (collection / 'docs').mkdir(parents=True)
    text = '# Fictional walk\n\n日文：架空の散歩。\n中文：一次虚构的散步。\n\n选项 A：向左\n选项 B：向右\n未译：架空の帰り道。\n'
    (collection / 'docs/demo.md').write_text(text, encoding='utf-8')
    (collection / 'import-manifest.json').write_text(json.dumps({'documents': [{'scriptId': 'demo', 'path': 'docs/demo.md'}]}))
    return tmp_path, text


def test_list_and_exact_read(bundle):
    root, text = bundle
    assert reader.read(root) == 'demo\n'
    assert reader.read(root, 'demo') == text
    result = subprocess.run([sys.executable, str(SCRIPT), str(root), 'demo'], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == text


@pytest.mark.parametrize('unknown', [False, True])
def test_bad_input_exits_nonzero(bundle, unknown):
    root, _ = bundle
    args = [str(root), 'missing'] if unknown else [str(root / 'missing')]
    result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
    assert result.returncode != 0 and 'Cannot read bundle:' in result.stderr


def test_escape_is_rejected(bundle):
    root, _ = bundle
    manifest = root / 'collection/import-manifest.json'
    manifest.write_text(json.dumps({'documents': [{'scriptId': 'demo', 'path': '../outside.md'}]}))
    with pytest.raises(ValueError, match='unsafe'):
        reader.read(root, 'demo')
