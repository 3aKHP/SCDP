import json
from pathlib import Path

import pytest

from scdp.activation import activate, rollback
from scdp.core import canonical, sha, write_json
from scdp.kb import source_manifest
from scdp.storage import collect_candidates, retention_plan, capacity_plan, GiB
from test_activation import source_index


def generations(tmp_path):
    sources, index = source_index(tmp_path/'active', 'Fiction baseline')
    root, recovery = tmp_path/'candidates', tmp_path/'recovery'
    for number in range(3):
        candidate = root/str(number)
        s, i = source_index(candidate, 'Fiction generation '+str(number))
        baseline = sha(canonical(source_manifest(sources)))
        receipt = {'snapshotId': str(number)*64, 'fileDigestsMatch': True, 'indexedNonemptyLinesCovered': True,
                   'candidateTreeFingerprint': sha(canonical(source_manifest(s))),
                   'indexSha256': sha(i.read_bytes()), 'baselineFingerprint': baseline}
        write_json(candidate/'reconciliation.json', receipt)
        write_json(candidate/'scdp-stage.json', {'snapshotId': receipt['snapshotId'],
                   'componentSha256': 'a'*64, 'baselineFingerprint': baseline})
        scratch = candidate/'candidate'
        scratch.mkdir()
        (scratch/'copied.txt').write_text('Synthetic scratch')
        activate(candidate, sources, index, recovery)
    return {'candidates': str(root), 'recovery': str(recovery), 'sources': str(sources), 'index': str(index),
            'work': str(tmp_path), 'reserveBytes': 4*GiB}


def test_collection_keeps_active_and_previous_and_rollback_works(tmp_path):
    config = generations(tmp_path)
    before_sources = source_manifest(config['sources'])
    plan = collect_candidates(config)
    assert {Path(p).name for p in plan['keep']} == {'1', '2'}
    assert {Path(p).name for p in plan['remove']} == {'0'}
    assert not (Path(config['candidates'])/'0').exists()
    assert source_manifest(config['sources']) == before_sources
    assert all(not (Path(p)/'candidate').exists() for p in plan['keep'])
    assert rollback(config['recovery'])['state'] == 'rolled-back'
    assert (Path(config['sources'])/'fiction.md').read_text() == 'Fiction generation 1'
    assert retention_plan(config)['activeSnapshotId'] == '1'*64
    with pytest.raises(ValueError, match='previous_generation_retired'):
        rollback(config['recovery'])
    assert (Path(config['sources'])/'fiction.md').read_text() == 'Fiction generation 1'


def test_unknown_recovery_and_changed_pointers_block_all_cleanup(tmp_path):
    config = generations(tmp_path)
    journal = Path(config['recovery'])/'interrupted/receipt.json'
    write_json(journal, {'state': 'preparing'})
    with pytest.raises(ValueError, match='unfinished_recovery'):
        collect_candidates(config)
    assert (Path(config['candidates'])/'0').exists()
    journal.unlink()
    (Path(config['sources'])/'fiction.md').write_text('Unexpected external mutation')
    with pytest.raises(ValueError, match='active_content_changed'):
        collect_candidates(config)
    assert (Path(config['candidates'])/'0').exists()


def test_capacity_gate_before_extraction(tmp_path, monkeypatch):
    from test_runner import seed
    import scdp.storage as storage
    config = generations(tmp_path/'consumer')
    source, _, _, _, first = seed(tmp_path/'producer')
    archive = Path(source['work'])/'packages'/(first['snapshotId']+'.tar.gz')
    class Disk:
        free = 100
    monkeypatch.setattr(storage.shutil, 'disk_usage', lambda root: Disk())
    with pytest.raises(ValueError, match='insufficient_disk_space'):
        capacity_plan(config, archive)
    Disk.free = 30*GiB
    plan = capacity_plan(config, archive)
    assert plan['requiredBytes'] > 8*GiB
    assert plan['collectionBytes'] > 0


def test_pull_failure_keeps_active_release_and_removes_expanded_package(tmp_path, monkeypatch):
    import subprocess
    import scdp.consumer as consumer
    from scdp.cycle import cycle
    from scdp.github_release import publish_data
    from test_runner import seed, MemoryGitHub
    config = generations(tmp_path/'consumer')
    config.update(repository='synthetic/data', deploymentLock=str(tmp_path/'deploy.lock'),
                  consumerCommand=['synthetic-consumer', '{bundle}', '{archive}', '{snapshotId}'])
    Path(config['deploymentLock']).touch()
    source, upstream, transport, _, first = seed(tmp_path/'producer')
    write_json(Path(config['work'])/'active-release.json', first['publication'])
    upstream['version'] = 2
    second = cycle(source, transport=transport)
    api = MemoryGitHub()
    archive = Path(source['work'])/'packages'/(second['snapshotId']+'.tar.gz')
    bundle = Path(source['work'])/'builds'/second['snapshotId']
    publish_data(api, archive, bundle, second['publication'], commit='a'*40)
    baseline = source_manifest(config['sources'])
    monkeypatch.setattr(consumer, 'capacity_plan', lambda *args: {'requiredBytes': 1})
    monkeypatch.setattr(consumer, 'require_space', lambda *args: {})
    monkeypatch.setattr(consumer.subprocess, 'run', lambda *args, **kwargs: subprocess.CompletedProcess(args, 9))
    with pytest.raises(ValueError, match='activation_failed'):
        consumer.pull(config, api)
    assert source_manifest(config['sources']) == baseline
    assert json.loads((Path(config['work'])/'active-release.json').read_bytes()) == first['publication']
    assert not (Path(config['work'])/'incoming').exists()


def test_download_transport_strips_authorization_on_asset_redirect(tmp_path):
    import httpx
    from scdp.github_release import GitHub
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.host == 'api.github.com':
            return httpx.Response(302, headers={'Location': 'https://release-assets.githubusercontent.com/file'})
        return httpx.Response(200, content=b'fiction')
    api = GitHub('synthetic/data', 'synthetic-token', transport=httpx.MockTransport(handler))
    api.download({'id': 1, 'size': 7}, tmp_path/'asset', expected_sha=sha(b'fiction'))
    assert requests[0].headers['Authorization'] == 'Bearer synthetic-token'
    assert 'Authorization' not in requests[1].headers
    api.close()


def test_distribution_collects_only_old_archives_after_validating_both_pointers(tmp_path):
    from scdp.storage import collect_distribution
    for number in range(3):
        data = f'fiction {number}'.encode()
        filename = str(number)*64+'.tar.gz'
        (tmp_path/filename).write_bytes(data)
        if number:
            write_json(tmp_path/('latest.json' if number == 2 else 'previous.json'),
                       {'snapshotId': str(number)*64, 'filename': filename, 'bytes': len(data), 'sha256': sha(data)})
    keep = tmp_path/('1'*64+'.tar.gz')
    keep.write_bytes(b'broken predecessor')
    with pytest.raises(ValueError, match='retained_archive_invalid'):
        collect_distribution(tmp_path)
    assert (tmp_path/('0'*64+'.tar.gz')).exists()
    keep.write_bytes(b'fiction 1')
    assert collect_distribution(tmp_path) == len(b'fiction 0')
    assert keep.exists() and not (tmp_path/('0'*64+'.tar.gz')).exists()


def test_pull_success_then_unchanged_keeps_two_generations_without_redownloading(tmp_path, monkeypatch):
    import subprocess
    import scdp.consumer as consumer
    from scdp.cycle import cycle
    from scdp.github_release import publish_data
    from test_runner import seed, MemoryGitHub
    config = generations(tmp_path/'consumer')
    config.update(repository='synthetic/data', deploymentLock=str(tmp_path/'deploy.lock'),
                  consumerCommand=['synthetic-consumer', '{bundle}', '{archive}', '{snapshotId}'])
    Path(config['deploymentLock']).touch()
    source, upstream, transport, _, first = seed(tmp_path/'producer')
    write_json(Path(config['work'])/'active-release.json', first['publication'])
    upstream['version'] = 2
    second = cycle(source, transport=transport)
    api = MemoryGitHub()
    archive = Path(source['work'])/'packages'/(second['snapshotId']+'.tar.gz')
    bundle = Path(source['work'])/'builds'/second['snapshotId']
    publish_data(api, archive, bundle, second['publication'], commit='a'*40)
    monkeypatch.setattr(consumer, 'capacity_plan', lambda *args: {'requiredBytes': 1})
    monkeypatch.setattr(consumer, 'require_space', lambda *args: {})
    def adapter(args, **kwargs):
        candidate = Path(config['candidates'])/'new'
        s, i = source_index(candidate, 'Synthetic activated release')
        baseline = sha(canonical(source_manifest(config['sources'])))
        write_json(candidate/'scdp-stage.json', {'snapshotId': args[-1], 'componentSha256': 'a'*64,
                                                'baselineFingerprint': baseline})
        write_json(candidate/'reconciliation.json', {'snapshotId': args[-1], 'fileDigestsMatch': True,
            'indexedNonemptyLinesCovered': True, 'candidateTreeFingerprint': sha(canonical(source_manifest(s))),
            'indexSha256': sha(i.read_bytes()), 'baselineFingerprint': baseline})
        activate(candidate, config['sources'], config['index'], config['recovery'])
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(consumer.subprocess, 'run', adapter)
    assert consumer.pull(config, api)['state'] == 'activated'
    assert not (Path(config['work'])/'incoming').exists()
    assert len(retention_plan(config)['keep']) == 2
    downloads = []
    download = api.download
    def tracked(asset, *args, **kwargs):
        downloads.append(asset['name'])
        return download(asset, *args, **kwargs)
    api.download = tracked
    assert consumer.pull(config, api)['state'] == 'unchanged'
    assert downloads == ['manifest.json']
