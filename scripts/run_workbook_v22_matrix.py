"""Serial local-model evaluation on frozen v0.22 sources; retain every report."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
runtime=Path.home()/'Library/Application Support/GuiyuRuntime/python/bin/python'
SUITES=[('new',[]),('confirmation',[]),('regression',[]),('known',['--cases','renamed_units','chinese_goal_english_fields']),
        ('adaptation',[]),('followups',[]),('variants',[]),('prior_new',[]),('fresh',[]),('unseen',[])]

def main():
    frozen=json.loads((ROOT/'qa/v0.22/freeze.json').read_text());records=[]
    for suite,extra in SUITES:
        current={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'backend').glob('*.py')}
        assert current==frozen['backend_hashes'],'Frozen backend changed; stopped before next model run.'
        before=set((ROOT/'qa/v0.22/reports').glob('*.json'));started=time.monotonic()
        print('START_SUITE',suite,flush=True)
        run=subprocess.run([str(runtime),'scripts/check_workbook_v22.py','--suite',suite]+extra,cwd=ROOT)
        added=set((ROOT/'qa/v0.22/reports').glob('*.json'))-before
        records.append({'suite':suite,'exit_code':run.returncode,'elapsed':round(time.monotonic()-started,3),
                        'reports':[str(p.relative_to(ROOT)) for p in sorted(added)]})
        (ROOT/'qa/v0.22/matrix-records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
        print('END_SUITE',suite,run.returncode,flush=True)

if __name__=='__main__':main()
