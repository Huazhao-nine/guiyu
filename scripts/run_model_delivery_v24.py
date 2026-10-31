"""Retest the known boundaries on a final freeze; preserve all first-use scores."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path.home()/'Library/Application Support/GuiyuRuntime/python/bin/python'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder=ROOT/'qa/v0.24/final';protocol=json.loads((folder/'protocol.json').read_text())
    target=folder/'records.json';assert not target.exists()
    (folder/'reports').mkdir()
    records=[]
    for group in protocol['groups']:
        assert protocol['backend_hashes']=={p.name:sha(p) for p in (ROOT/'backend').glob('*.py')}
        assert sha(ROOT/protocol['runner'])==protocol['runner_sha256']
        assert all(sha(ROOT/p)==h for p,h in protocol['input_hashes'].items())
        before=set((folder/'reports').glob('*.json'))
        command=[str(RUNTIME),protocol['runner'],'--suite',group['suite'],'--model-id',protocol['model']]
        if group['cases']:command+=['--cases']+group['cases']
        print('START_FINAL_RETEST',group['suite'],flush=True)
        began=time.monotonic();result=subprocess.run(command,cwd=ROOT)
        added=set((folder/'reports').glob('*.json'))-before;assert len(added)==1
        path=next(iter(added));report=json.loads(path.read_text())
        assert [c['id'] for c in report['cases']]==group['expected_ids']
        assert report['source_hashes']==protocol['backend_hashes'] and report['source_hashes_unchanged'] and report['network_denied']
        records.append({'suite':group['suite'],'model':protocol['model'],'report':str(path.relative_to(ROOT)),
                        'exit_code':result.returncode,'elapsed':round(time.monotonic()-began,3)})
        target.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
        print('END_FINAL_RETEST',group['suite'],report['passed'],'/',report['total'],flush=True)


if __name__=='__main__':main()
