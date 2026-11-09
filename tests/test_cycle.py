import json
import httpx
import pytest
from scdp.cycle import cycle
from scdp.official import asset_url,manifest_url
from test_acquisition import encoded,response


def source_fixture(tmp_path):
    base='https://example.test/assets';state={'version':1,'text':'First fictional scene','fail':False}
    def handler(request):
        if state['fail']:return response(b'maintenance',503,**{'Retry-After':'120'})
        url=str(request.url).split('?')[0]
        if url==manifest_url(base):value={'version':state['version'],'chunks':[{'chunk.json':state['version']}]}
        elif url==asset_url('chunk.json',base):value={'json/demo/fiction.json':state['version']}
        else:value=[{'text':state['text']}]
        return response(encoded(value))
    config={'work':str(tmp_path/'work'),'destination':str(tmp_path/'releases'),'sourceBase':base,'rate':100000,'rollingChecks':1,'shardChecks':1}
    return config,state,httpx.MockTransport(handler)


def test_no_change_same_number_drift_and_source_increment(tmp_path):
    config,state,transport=source_fixture(tmp_path)
    first=cycle(config,transport=transport)
    assert first['state']=='published'
    before=(tmp_path/'releases/latest.json').read_bytes()
    assert cycle(config,transport=transport)['state']=='unchanged'
    assert (tmp_path/'releases/latest.json').read_bytes()==before
    state['text']='Changed without a source counter bump'
    changed=cycle(config,transport=transport)
    assert changed['drift'] and changed['publication']['publicationRevision']==1
    assert changed['publication']['releaseSequence']==1
    state['version']=2
    advanced=cycle(config,transport=transport)
    assert advanced['publication']['releaseSequence']==2
    assert advanced['publication']['publicationRevision']==0
    assert (tmp_path/'releases/first-invalid-file').exists() is False


def test_maintenance_and_consumer_failure_preserve_published_baseline(tmp_path):
    config,state,transport=source_fixture(tmp_path)
    first=cycle(config,transport=transport)
    baseline=(tmp_path/'releases/latest.json').read_bytes()
    state['fail']=True
    with pytest.raises(Exception):cycle(config,transport=transport)
    assert (tmp_path/'releases/latest.json').read_bytes()==baseline
    state['fail']=False
    # An independent job demonstrates consumer failure and deterministic retry,
    # keeping the source publication identity immutable.
    config,state,transport=source_fixture(tmp_path/'other')
    import sys
    config['consumerCommand']=[sys.executable,'-c','raise SystemExit(7)']
    with pytest.raises(ValueError,match='consumer_activation_failed'):cycle(config,transport=transport)
    published=(tmp_path/'other/releases/latest.json').read_bytes()
    config['consumerCommand']=[sys.executable,'-c','pass']
    assert cycle(config,transport=transport)['state']=='activated'
    assert (tmp_path/'other/releases/latest.json').read_bytes()==published


def test_translation_updates_do_not_fetch_unchanged_body(tmp_path):
    import csv,io,tarfile
    from scdp.core import sha
    config,state,transport=source_fixture(tmp_path)
    body_requests=[]
    original=transport.handler
    def tracking(request):
        if str(request.url).split('?')[0]==asset_url('json/demo/fiction.json',config['sourceBase']):body_requests.append(1)
        return original(request)
    transport=httpx.MockTransport(tracking)
    config.update(rollingChecks=0,shardChecks=0)
    def translated(version,text):
        archive=tmp_path/(version+'.tar.gz');buffer=io.StringIO();writer=csv.writer(buffer,lineterminator='\n')
        writer.writerows([['id','name','text','trans'],['0','','First fictional scene',text],['info','demo/fiction.json','','']]);raw=buffer.getvalue().encode()
        with tarfile.open(archive,'w:gz') as out:
            info=tarfile.TarInfo('synthetic/data/story/fiction.csv');info.size=len(raw);out.addfile(info,io.BytesIO(raw))
        return {'path':str(archive),'identity':version,'sha256':sha(archive.read_bytes())}
    config['translation']=translated('first','虚构的第一版译文')
    first=cycle(config,transport=transport);count=len(body_requests)
    config['translation']=translated('second','虚构的第二版译文')
    second=cycle(config,transport=transport)
    assert len(body_requests)==count
    assert second['snapshotId']!=first['snapshotId'] and second['publication']['releaseSequence']==2
