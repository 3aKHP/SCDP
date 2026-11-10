"""Read Markdown from an extracted SCDP standard bundle (Python 3.12+)."""
import argparse
import json
from pathlib import Path, PurePosixPath
import sys


def read(bundle, script_id=None):
    collection = Path(bundle).resolve() / 'collection'
    manifest = json.loads((collection / 'import-manifest.json').read_text(encoding='utf-8'))
    documents = manifest['documents']
    ids = [entry['scriptId'] for entry in documents]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate script ID')
    if script_id is None:
        return '\n'.join(ids) + '\n'
    for entry in documents:
        if entry['scriptId'] != script_id:
            continue
        relative = PurePosixPath(entry['path'])
        if relative.is_absolute() or '..' in relative.parts or not relative.parts or relative.parts[0] != 'docs':
            raise ValueError('unsafe document path')
        path = (collection / relative).resolve()
        if not path.is_relative_to(collection.resolve()):
            raise ValueError('document escapes collection')
        return path.read_text(encoding='utf-8')
    raise ValueError('unknown script ID: ' + script_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('script_id', nargs='?')
    args = parser.parse_args()
    try:
        sys.stdout.write(read(args.bundle, args.script_id))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('Cannot read bundle: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
