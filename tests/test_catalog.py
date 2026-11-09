from scdp.catalog import Catalog, media_references
from scdp.core import sha, canonical
from scdp.story import project


def test_media_reference_templates_and_unknowns():
    inventory = {'sounds/voice/events/demo/1.m4a': 1, 'images/event/bg/fiction.jpg': 2,
                 'spine/idols/stand/fiction/data.json': 1}
    frames = [{'voice': 'demo/1', 'bg': 'fiction', 'bgm': 'off', 'se': 'unknown',
               'charType': 'idols', 'charId': 'fiction', 'charCategory': 'stand_fix'}]
    refs = media_references(frames, inventory)
    assert sum(r['status'] == 'resolved' for r in refs) == 3
    assert any(r['field'] == 'bgm' and r['status'] == 'sentinel' for r in refs)
    assert any(r['field'] == 'se' and r['status'] == 'unresolved' for r in refs)
    assert all(r['assetId'] is None or r['assetId'].removeprefix('enza:') in inventory for r in refs)


def test_metadata_identity_conflict_and_no_application_state():
    catalog = Catalog({'json/fiction/42.json': 1})
    data = {'id': 1, 'name': 'Fiction Character', 'firstName': 'Fiction', 'albumCommunicationTitles': [],
            'userSecret': 'must-not-appear', 'produceIdols': [{'id': '100', 'name': 'Fiction Card', 'userIdolId': 'private-id'}],
            'communications': [{'communicationId': '42', 'title': 'Fiction Title', 'failureCommunicationId': '99'}]}
    catalog.ingest('https://metadata.example.test/album/1', data, sha(canonical(data)))
    story = project('fiction/42', [{'text': 'Invented'}], '0'*64, '0'*64)
    catalog.enrich(story)
    assert story['title'] == 'Fiction Title'
    assert catalog.story_metadata['fiction/42'][0]['confidence'] == 'inferred'
    serialized = canonical([catalog.entities, catalog.relations, catalog.story_metadata])
    assert b'must-not-appear' not in serialized and b'private-id' not in serialized
    assert any(r['kind'] == 'script_lookup' for r in catalog.unresolved)
