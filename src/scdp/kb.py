"""MCP-KB native CLI staging and complete index reconciliation."""
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from .build import COLLECTION
from .core import canonical, sha, write_json
from .package import validate_tree


def reconcile(collection, sources, index):
    collection, sources = Path(collection), Path(sources)
    manifest = json.loads((collection/"import-manifest.json").read_bytes())
    installed = sources/"collections"/COLLECTION
    expected_files = {p.relative_to(collection).as_posix(): sha(p.read_bytes()) for p in collection.rglob("*") if p.is_file()}
    actual_files = {p.relative_to(installed).as_posix(): sha(p.read_bytes()) for p in installed.rglob("*") if p.is_file()}
    if actual_files != expected_files:
        raise ValueError("kb_installed_file_mismatch")
    expected_docs = {"collections/"+COLLECTION+"/"+d["path"]: d for d in manifest["documents"]}
    with sqlite3.connect(f"file:{Path(index).resolve()}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT path,sha256,line_count,chunk_count FROM documents WHERE collection_id=?", (COLLECTION,)).fetchall()
        if {r[0] for r in rows} != set(expected_docs) or len(rows) != len(expected_docs):
            raise ValueError("kb_index_document_set_mismatch")
        chunk_total = 0
        for path, digest, line_count, chunk_count in rows:
            raw = (sources/path).read_bytes()
            lines = raw.decode("utf-8").splitlines()
            if sha(raw) != digest or digest != expected_docs[path]["sha256"] or len(lines) != line_count:
                raise ValueError("kb_index_document_digest_mismatch")
            chunks = db.execute("SELECT start_line,end_line,text FROM chunks WHERE path=? ORDER BY start_line", (path,)).fetchall()
            if len(chunks) != chunk_count:
                raise ValueError("kb_index_chunk_count_mismatch")
            covered = set()
            for start, end, text in chunks:
                if start < 1 or end > len(lines) or "\n".join(lines[start-1:end]).strip() != text:
                    raise ValueError("kb_index_chunk_text_mismatch")
                covered.update(range(start, end+1))
            if any(line.strip() and i not in covered for i, line in enumerate(lines, 1)):
                raise ValueError("kb_index_body_line_missing")
            chunk_total += chunk_count
    return {"snapshotId": manifest["snapshotId"], "documents": len(rows), "chunks": chunk_total,
            "installedFiles": len(actual_files), "fileDigestsMatch": True, "indexedNonemptyLinesCovered": True}


def stage(bundle, kb_root, python, output):
    bundle, kb_root, output = Path(bundle).resolve(), Path(kb_root).resolve(), Path(output).resolve()
    verified = validate_tree(bundle)
    if output.exists():
        raise ValueError("kb_stage_target_exists")
    output.mkdir(parents=True)
    receipts = output/"receipts"
    receipts.mkdir()
    source = output/"candidate/collections"/COLLECTION
    source.parent.mkdir(parents=True)
    shutil.copytree(bundle/"collection", source)

    def run(name, *arguments):
        process = subprocess.run([str(python), str(kb_root/"kbctl.py"), *arguments, "--json"], capture_output=True, text=True, env={**os.environ, "KB_TOKENS_FILE": str(output/"unused-tokens")})
        # Native receipts may contain deployment paths and belong only in the local stage.
        write_json(receipts/(name+".json"), {"exitCode": process.returncode, "stdout": process.stdout, "stderr": process.stderr})
        if process.returncode:
            raise ValueError("kb_native_command_failed:"+name)

    native = output/"collection.tar.gz"
    run("validate", "validate-collection", "--sources-root", str(output/"candidate"), "--collection-id", COLLECTION)
    run("pack", "pack-collection", "--sources-root", str(output/"candidate"), "--collection-id", COLLECTION, "--output", str(native))
    run("install", "install-package", "--package", str(native), "--sources-root", str(output/"sources"))
    run("reinstall", "install-package", "--package", str(native), "--sources-root", str(output/"sources"), "--replace")
    run("index", "rebuild-index", "--sources-root", str(output/"sources"), "--index", str(output/"index.sqlite3"))
    result = reconcile(bundle/"collection", output/"sources", output/"index.sqlite3")
    result.update(componentSha256=sha(canonical({p.name:sha(p.read_bytes()) for p in sorted(kb_root.glob("*.py"))})), nativePackageSha256=sha(native.read_bytes()), nativePackageBytes=native.stat().st_size,
                  repeatedInstall=True, bundleVerified=verified["snapshotId"])
    write_json(output/"reconciliation.json", result)
    return result
