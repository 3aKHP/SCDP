import copy
import io
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest

from scdp.checkpoint import export_checkpoint, restore_checkpoint
from scdp.core import sha
from scdp.cycle import cycle
from scdp.github_release import publish_data, newest_data, read_descriptor
from scdp.runner import initialize, run, state_record, recover
from test_cycle import source_fixture


class MemoryGitHub:
    def __init__(self):
        self.records, self.blobs = {}, {}
        self.counter = 0
        self.fail_upload = False
        self.tags = {}

    def ensure_tag(self, tag, commit):
        if tag in self.tags and self.tags[tag] != commit:
            raise ValueError('github_existing_tag_conflict')
        self.tags[tag] = commit

    def releases(self):
        return iter(copy.deepcopy(list(self.records.values())))

    def find(self, tag):
        return next((r for r in self.releases() if r['tag_name'] == tag), None)

    def request(self, method, path, **kwargs):
        if method == 'POST':
            self.counter += 1
            record = {'id': self.counter, 'prerelease': False, **kwargs['json']}
            self.records[self.counter] = record
        elif path.startswith('/releases/assets/'):
            self.blobs.pop(int(path.split('/')[-1]))
            return
        else:
            record = self.records[int(path.split('/')[-1])]
            if method == 'PATCH':
                record.update(kwargs['json'])
        return copy.deepcopy(record)

    def assets(self, release_id):
        return [copy.deepcopy(a) for a, _ in self.blobs.values() if a['release_id'] == release_id]

    def upload(self, release_id, name, path):
        if self.fail_upload:
            raise ValueError('synthetic_upload_failure')
        self.counter += 1
        data = Path(path).read_bytes()
        asset = {'id': self.counter, 'name': name, 'state': 'uploaded', 'size': len(data), 'release_id': release_id}
        self.blobs[self.counter] = (asset, data)
        return copy.deepcopy(asset)

    def download(self, asset, target, *, expected_sha=None, max_bytes=2*1024**3):
        data = self.blobs[asset['id']][1]
        if len(data) != asset['size'] or len(data) > max_bytes or (expected_sha and sha(data) != expected_sha):
            raise ValueError('github_asset_digest_or_length')
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(data)


def seed(tmp_path):
    config, source, transport = source_fixture(tmp_path/'origin')
    first = cycle(config, transport=transport)
    checkpoint = tmp_path/'checkpoint.tar.gz'
    export_checkpoint(config, checkpoint)
    return config, source, transport, checkpoint, first


def ledger(config):
    with sqlite3.connect(Path(config['work'])/'state.sqlite3') as db:
        return db.execute('SELECT received,requests FROM ledger').fetchone()


def test_portable_checkpoint_keeps_ledger_history_and_unchanged_identity(tmp_path):
    config, source, transport, checkpoint, first = seed(tmp_path)
    restored = restore_checkpoint(checkpoint, tmp_path/'second-machine')
    assert ledger(restored) == ledger(config)
    assert cycle(restored, transport=transport)['snapshotId'] == first['snapshotId']
    assert ledger(restored)[1] > ledger(config)[1]
    with tarfile.open(checkpoint) as archive:
        names = archive.getnames()
    assert not any('/builds/' in n or '/runs/' in n or '/consumer-receipts/' in n for n in names)


@pytest.mark.parametrize('name', ['../escape', 'work/../escape', 'etc/token', 'work/runs/log.json'])
def test_checkpoint_rejects_unmanaged_paths(tmp_path, name):
    path = tmp_path/'unsafe.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        member = tarfile.TarInfo(name)
        member.size = 1
        archive.addfile(member, io.BytesIO(b'x'))
    with pytest.raises(ValueError):
        restore_checkpoint(path, tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_runner_moves_between_hosts_and_retains_two_checkpoints(tmp_path):
    config, source, transport, checkpoint, _ = seed(tmp_path)
    api = MemoryGitHub()
    initialize(api, checkpoint, 'a'*40)
    invoke = lambda conf, **kw: cycle(conf, transport=transport, **kw)
    assert run(api, tmp_path/'run1', 'a'*40, cycle_fn=invoke)['state'] == 'unchanged'
    source['version'] = 2
    result = run(api, tmp_path/'run2', 'a'*40, cycle_fn=invoke)
    assert result['state'] == 'published'
    release, state = state_record(api)
    assert state['lease'] is None
    assert len(api.assets(release['id'])) == 2
    descriptor, _ = read_descriptor(api, newest_data(api))
    assert descriptor['snapshotId'] == result['snapshotId']
    assert run(api, tmp_path/'run3', 'a'*40, cycle_fn=invoke)['state'] == 'unchanged'
    assert len(api.assets(release['id'])) == 2


def test_failed_source_run_persists_charges_and_resumes(tmp_path):
    config, source, transport, checkpoint, _ = seed(tmp_path)
    api = MemoryGitHub()
    initialize(api, checkpoint, 'a'*40)
    source['fail'] = True
    with pytest.raises(Exception):
        run(api, tmp_path/'failure', 'a'*40, cycle_fn=lambda conf, **kw: cycle(conf, transport=transport, **kw))
    _, state = state_record(api)
    assert state['lease'] is None
    api.download(state['head'], tmp_path/'failed.tar.gz')
    restored = restore_checkpoint(tmp_path/'failed.tar.gz', tmp_path/'inspect')
    assert ledger(restored)[0] > ledger(config)[0]
    assert ledger(restored)[1] > ledger(config)[1]


def test_lost_checkpoint_upload_leaves_lease_and_blocks_next_host(tmp_path):
    _, _, _, checkpoint, _ = seed(tmp_path)
    api = MemoryGitHub()
    initialize(api, checkpoint, 'a'*40)
    def fail_after_acquiring_lease(config, **kwargs):
        api.fail_upload = True
        raise RuntimeError('simulated_runner_loss')
    with pytest.raises(ValueError, match='upload_failure'):
        run(api, tmp_path/'failure', 'a'*40, cycle_fn=fail_after_acquiring_lease)
    assert state_record(api)[1]['lease']
    with pytest.raises(ValueError, match='unfinished_run'):
        run(api, tmp_path/'next-host', 'a'*40, cycle_fn=fail_after_acquiring_lease)
    lease = state_record(api)[1]['lease']['id']
    api.fail_upload = False
    assert recover(api, tmp_path/'recovery', lease)['state'] == 'recovered-budget-exhausted'
    _, state = state_record(api)
    api.download(state['head'], tmp_path/'recovered.tar.gz')
    restored = restore_checkpoint(tmp_path/'recovered.tar.gz', tmp_path/'verified-recovery')
    assert ledger(restored)[0] == 1024**3
    assert state['lease'] is None


def test_published_asset_conflict_never_overwrites(tmp_path):
    config, source, transport, _, first = seed(tmp_path)
    api = MemoryGitHub()
    archive = Path(config['work'])/'packages'/(first['snapshotId']+'.tar.gz')
    bundle = Path(config['work'])/'builds'/first['snapshotId']
    publish_data(api, archive, bundle, first['publication'], commit='a'*40)
    publish_data(api, archive, bundle, first['publication'], commit='a'*40)
    asset = next((a for a, _ in api.blobs.values() if a['name'] == 'scdp-phase-one.tar.gz'))
    api.blobs[asset['id']] = (asset, b'corrupt')
    with pytest.raises(ValueError, match='digest_or_length'):
        publish_data(api, archive, bundle, first['publication'], commit='a'*40)
    assert api.blobs[asset['id']][1] == b'corrupt'
