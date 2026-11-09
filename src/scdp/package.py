"""Text-only immutable packages, verified extraction and filesystem publication."""
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
import jsonschema
from .contracts import schema
from .core import atomic_write, canonical, safe_path, sha, write_json

ALLOWED_SUFFIXES={".json", ".jsonl", ".md", ".yaml", ".txt"}


def validate_tree(root):
    root=Path(root)
    manifest=json.loads((root/"snapshot.json").read_bytes())
    jsonschema.Draft202012Validator({**schema(),"$ref":"#/$defs/Snapshot","required":[],"additionalProperties":True}).validate(manifest)
    expected={}
    for entry in manifest["files"]:
        path=safe_path(entry["path"])
        if path in expected or Path(path).suffix not in ALLOWED_SUFFIXES:
            raise ValueError("unsafe_package_member")
        expected[path]=entry
    actual={p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p!=root/"snapshot.json"}
    if actual!=set(expected):
        raise ValueError("package_file_set_mismatch")
    for path,entry in expected.items():
        target=root/path
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if p!=root.parent):
            raise ValueError("package_symlink")
        data=target.read_bytes()
        if len(data)!=entry["size"] or sha(data)!=entry["sha256"]:
            raise ValueError("package_digest_mismatch")
        data.decode("utf-8")
    if manifest["baseline"] is not None:
        raise ValueError("unsupported_baseline")
    return {"snapshotId":manifest["snapshotId"],"files":len(expected),"bytes":sum(e["size"] for e in expected.values())}


def pack(root, output):
    root,output=Path(root),Path(output)
    result=validate_tree(root)
    output.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=output.parent,prefix=".package-")
    os.close(fd)
    try:
        # gzip mtime is intentionally outside semantic identity; member metadata is fixed.
        with tarfile.open(temp,"w:gz") as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    info=archive.gettarinfo(str(path),arcname=path.relative_to(root).as_posix())
                    info.uid=info.gid=info.mtime=0
                    info.uname=info.gname=""
                    info.mode=0o644
                    with path.open("rb") as stream:
                        archive.addfile(info,stream)
        data=Path(temp).read_bytes()
        if output.exists() and sha(output.read_bytes())!=sha(data):
            # Existing archive may have a different gzip timestamp. Never overwrite it.
            with tempfile.TemporaryDirectory() as check:
                unpack(output,Path(check)/"unpacked")
                if json.loads((Path(check)/"unpacked/snapshot.json").read_bytes()) != json.loads((root/"snapshot.json").read_bytes()):
                    raise ValueError("immutable_package_conflict")
            data=output.read_bytes()
        else:
            os.replace(temp,output)
        return {**result,"sha256":sha(data),"compressedBytes":len(data)}
    finally:
        if Path(temp).exists():
            Path(temp).unlink()


def unpack(archive_path, target, *, max_bytes=4*1024**3, max_files=100000):
    target=Path(target)
    if target.exists():
        raise ValueError("extraction_target_exists")
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent,prefix=".extract-") as temporary:
        stage=Path(temporary)
        total=0
        names=set()
        with tarfile.open(archive_path,"r:gz") as archive:
            for member in archive:
                name=safe_path(member.name)
                if not member.isfile() or name in names or Path(name).suffix not in ALLOWED_SUFFIXES:
                    raise ValueError("unsafe_archive_member")
                total+=member.size
                names.add(name)
                if total>max_bytes or len(names)>max_files:
                    raise ValueError("archive_capacity_limit")
                dest=stage/name
                dest.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(member) as source, dest.open("wb") as out:
                    shutil.copyfileobj(source,out,length=65536)
        result=validate_tree(stage)
        os.replace(stage,target)
    return result


def publish_plan(archive, destination):
    archive=Path(archive)
    with tempfile.TemporaryDirectory() as temp:
        validate=unpack(archive,Path(temp)/"candidate")
        manifest=json.loads((Path(temp)/"candidate/snapshot.json").read_bytes())
    return {"snapshotId":validate["snapshotId"],"sha256":sha(archive.read_bytes()),"bytes":archive.stat().st_size,
            "releaseSequence":manifest["releaseSequence"],"publicationRevision":manifest["publicationRevision"],
            "destinationKind":"filesystem","visibility":"private","filename":validate["snapshotId"]+".tar.gz"}


def publish(archive, destination):
    # Filesystem backend: web/object-store serving and consumer activation are separate operations.
    plan=publish_plan(archive,destination)
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    path=destination/plan["filename"]
    if path.exists():
        if sha(path.read_bytes())!=plan["sha256"]:
            raise ValueError("immutable_publication_conflict")
    else:
        atomic_write(path,Path(archive).read_bytes())
    if sha(path.read_bytes())!=plan["sha256"]:
        raise ValueError("publication_readback_mismatch")
    current=destination/"latest.json"
    if current.exists():
        previous=json.loads(current.read_bytes())
        old=(previous["releaseSequence"],previous["publicationRevision"])
        new=(plan["releaseSequence"],plan["publicationRevision"])
        if new<old or (new==old and plan["snapshotId"]!=previous["snapshotId"]):
            raise ValueError("publication_order_conflict")
        if previous!=plan:
            write_json(destination/"previous.json",previous)
    write_json(current,plan)
    return plan
