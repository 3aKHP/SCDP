import sqlite3
import pytest
from scdp.activation import activate,rollback
from scdp.core import canonical,sha,write_json
from scdp.kb import source_manifest


def source_index(root,text):
    sources=root/'sources';sources.mkdir(parents=True)
    (sources/'fiction.md').write_text(text)
    index=root/'index.sqlite3'
    with sqlite3.connect(index) as db:
        db.execute('CREATE TABLE documents(path TEXT,sha256 TEXT)')
        db.execute('INSERT INTO documents VALUES(?,?)',('fiction.md',sha(text.encode())))
    return sources,index


def candidate(tmp_path):
    sources,index=source_index(tmp_path/'active','Fiction original')
    stage=tmp_path/'candidate';s,i=source_index(stage,'Fiction revised')
    receipt={'snapshotId':'a'*64,'fileDigestsMatch':True,'indexedNonemptyLinesCovered':True,
             'candidateTreeFingerprint':sha(canonical(source_manifest(s))), 'indexSha256':sha(i.read_bytes()),
             'baselineFingerprint':sha(canonical(source_manifest(sources)))}
    write_json(stage/'reconciliation.json',receipt)
    return stage,sources,index


def test_coordinated_activation_and_rollback(tmp_path):
    stage,sources,index=candidate(tmp_path);calls=[]
    control=lambda service,action:calls.append(action)
    result=activate(stage,sources,index,tmp_path/'recovery',control=control)
    assert result['state']=='active' and calls==['stop','start','is-active']
    assert (sources/'fiction.md').read_text()=='Fiction revised'
    assert rollback(tmp_path/'recovery',control=control)['state']=='rolled-back'
    assert (sources/'fiction.md').read_text()=='Fiction original'


def test_health_failure_restores_original_pair(tmp_path):
    stage,sources,index=candidate(tmp_path);old=index.read_bytes()
    def control(service,action):
        if action=='is-active':raise RuntimeError('synthetic health failure')
    with pytest.raises(RuntimeError):activate(stage,sources,index,tmp_path/'recovery',control=control)
    assert (sources/'fiction.md').read_text()=='Fiction original'
    assert index.read_bytes()==old


def test_wrong_baseline_and_corrupt_candidate_rejected(tmp_path):
    stage,sources,index=candidate(tmp_path)
    (sources/'fiction.md').write_text('Concurrent change')
    with pytest.raises(ValueError,match='baseline'):activate(stage,sources,index,tmp_path/'recovery')
    (stage/'index.sqlite3').write_bytes(b'bad')
    with pytest.raises(ValueError,match='index_drift'):activate(stage,sources,index,tmp_path/'recovery')


def test_killed_process_after_source_move_recovers_from_filesystem(tmp_path):
    import subprocess,sys,json
    from scdp.activation import recover_switch
    stage,sources,index=candidate(tmp_path)
    script='''
import os,sys
import scdp.activation as a
original=os.replace
sources=sys.argv[2]
def interrupted(source,target):
    original(source,target)
    if str(source)==sources:os._exit(23)
a.os.replace=interrupted
a.activate(sys.argv[1],sources,sys.argv[3],sys.argv[4])
'''
    recovery=tmp_path/'recovery'
    result=subprocess.run([sys.executable,'-c',script,str(stage),str(sources),str(index),str(recovery)])
    assert result.returncode==23 and not sources.exists()
    journal=next(recovery.glob('*/receipt.json'))
    identity=json.loads(journal.read_bytes())['activationId']
    assert recover_switch(recovery,identity)['state']=='recovered-previous'
    assert (sources/'fiction.md').read_text()=='Fiction original'
