"""Normalize native consumer archives without changing member bytes or paths."""
import gzip
import os
import tarfile
import tempfile
from pathlib import Path
from .core import safe_path, sha


def normalize_metadata(path):
    path=Path(path)
    before=sha(path.read_bytes())
    fd,temp=tempfile.mkstemp(prefix='.normalized-',dir=path.parent)
    os.close(fd)
    members=0
    try:
        with tarfile.open(path,'r:gz') as source, open(temp,'wb') as out, gzip.GzipFile(filename='',mode='wb',mtime=0,fileobj=out) as compressed, tarfile.open(fileobj=compressed,mode='w') as target:
            seen=set()
            for member in source:
                name=safe_path(member.name.rstrip('/'))
                if not (member.isfile() or member.isdir()) or name in seen:
                    raise ValueError('unsafe_native_archive')
                seen.add(name)
                member.uid=member.gid=member.mtime=0
                member.uname=member.gname=''
                member.mode=0o755 if member.isdir() else 0o644
                member.pax_headers={}
                with source.extractfile(member) if member.isfile() else _empty_context() as stream:
                    target.addfile(member,stream)
                members+=1
        with open(temp,'rb') as out:
            os.fsync(out.fileno())
        os.replace(temp,path)
        return {'rule':'anonymous-tar-metadata-v1','inputSha256':before,'outputSha256':sha(path.read_bytes()),'members':members}
    finally:
        if Path(temp).exists():Path(temp).unlink()


def _empty_context():
    from contextlib import nullcontext
    return nullcontext()
