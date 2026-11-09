import json
from pathlib import Path
from scdp.core import canonical
from scdp.history import inventory_history,save_fetch_record,story_records,content_fingerprint
from scdp.pipeline import discover,fetch_stories
from scdp.official import asset_url,manifest_url
from scdp.build import build
from test_acquisition import downloader,encoded,response


def test_retirement_and_same_counter_content_revision(tmp_path):
    base='https://example.test/assets';state={'version':1,'retired':False,'text':'First fictional version'}
    def handler(request):
        url=str(request.url).split('?')[0]
        if url==manifest_url(base):value={'version':state['version'],'chunks':[{'chunk.json':state['version']}]}
        elif url==asset_url('chunk.json',base):value={'images/fiction.png':1,**({} if state['retired'] else {'json/demo/fiction.json':1})}
        else:value=[{'text':state['text']}]
        return response(encoded(value))
    d=downloader(tmp_path/'work',handler)
    first=discover(d,base);assert fetch_stories(d,first)['complete']
    records=story_records(d.root,first);old=content_fingerprint(records)
    built=build(d.root,tmp_path/'first')
    state['text']='Second fictional version'
    record=d.fetch('json/demo/fiction.json',asset_url('json/demo/fiction.json',base)+'?v=1',lambda _:None,revalidate=True)
    record.update(sourceVersion=1,observationId=first['observationId']);save_fetch_record(d.root,first['observationId'],record)
    assert content_fingerprint(story_records(d.root,first))!=old
    assert len(list((d.root/'fetch-history').rglob('*.json')))==2
    changed=build(d.root,tmp_path/'changed',revision=1)
    assert changed['snapshotId']!=built['snapshotId']
    state.update(version=2,retired=True)
    second=discover(d,base);assert fetch_stories(d,second)['complete']
    history=inventory_history(d.root,second)
    assert history['json/demo/fiction.json']['presence']=='historical'
    assert history['json/demo/fiction.json']['firstSeen']==first['startedAt']
    final=build(d.root,tmp_path/'retired',sequence=2)
    manifest=json.loads((tmp_path/'retired/snapshot.json').read_bytes())
    assert manifest['scope']['selected']==0 and manifest['scope']['historicalStories']==1
    assert final['semantics']['stories']==1
    d.close()
