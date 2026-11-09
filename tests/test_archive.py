import io,tarfile
from scdp.archive import normalize_metadata


def test_archive_metadata_is_anonymous_and_repeatable(tmp_path):
    path=tmp_path/'native.tar.gz'
    with tarfile.open(path,'w:gz') as out:
        member=tarfile.TarInfo('collections/fiction/doc.md');member.size=7
        member.uid=1001;member.gid=1002;member.uname='fiction-user';member.gname='fiction-group';member.mtime=123456
        out.addfile(member,io.BytesIO(b'fiction'))
    first=normalize_metadata(path)
    with tarfile.open(path,'r:gz') as archive:
        member=archive.next()
        assert (member.uid,member.gid,member.mtime,member.uname,member.gname)==(0,0,0,'','')
        assert archive.extractfile(member).read()==b'fiction'
    assert normalize_metadata(path)['outputSha256']==first['outputSha256']
