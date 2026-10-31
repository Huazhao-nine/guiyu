"""Paired serial screening after generic contract fixes; original scores stay intact."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path.home()/'Library/Application Support/GuiyuRuntime/python/bin/python'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol=json.loads((ROOT/'qa/v0.24/adaptation/protocol.json').read_text())
    assert json.loads((ROOT/'qa/v0.24/qwen3.6-35b-a3b-compatibility.json').read_text())['passed']
    target=ROOT/'qa/v0.24/adaptation/screen-records.json'
    assert not target.exists()
    records=[]
    (ROOT/'qa/v0.24/adaptation/reports').mkdir()
    for group in protocol['screen']:
        for model in protocol['models']:
            assert protocol['backend_hashes']=={p.name:sha(p) for p in (ROOT/'backend').glob('*.py')}
            assert sha(ROOT/protocol['runner'])==protocol['runner_sha256']
            assert all(sha(ROOT/p)==h for p,h in protocol['input_hashes'].items())
            before=set((ROOT/'qa/v0.24/adaptation/reports').glob('*.json'))
            command=[str(RUNTIME),protocol['runner'],'--suite',group['suite'],'--model-id',model,'--cases']+group['cases']
            print('START_ADAPTATION',group['suite'],model,flush=True)
            started=time.monotonic();result=subprocess.run(command,cwd=ROOT)
            added=set((ROOT/'qa/v0.24/adaptation/reports').glob('*.json'))-before
            assert len(added)==1
            report_path=next(iter(added));report=json.loads(report_path.read_text())
            assert [c['id'] for c in report['cases']]==group['expected_ids']
            assert report['source_hashes']==protocol['backend_hashes']
            assert report['source_hashes_unchanged'] and report['network_denied']
            records.append({'suite':group['suite'],'model':model,'exit_code':result.returncode,
                            'elapsed':round(time.monotonic()-started,3),'report':str(report_path.relative_to(ROOT))})
            target.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
            print('END_ADAPTATION',group['suite'],model,report['passed'],'/',report['total'],flush=True)
    (ROOT/'qa/v0.24/adaptation/screen-exclusions.json').write_text('[]\n')


if __name__=='__main__':main()
