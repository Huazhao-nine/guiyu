"""Bind final v0.22 scores to complete input sets and frozen implementation."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo
from validate_workbook_v22_evidence import SUITES, validate

ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    frozen=json.loads((ROOT/'qa/v0.22/freeze.json').read_text())
    assert frozen['backend_hashes']=={p.name:digest(p) for p in (ROOT/'backend').glob('*.py')}
    records=json.loads((ROOT/'qa/v0.22/matrix-records.json').read_text())
    assert tuple(r['suite'] for r in records)==SUITES
    result={'version':'0.22.0','time':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
            'hardware':'Apple M5 32GB;16GB design target only','model':'Qwen3.5 9B',
            'python_tests':frozen['python_tests'],'final_reports':{},'suites':{},
            'scope':'Two frozen phases. First v22 new inputs scored0/4 and are now known development data; first source and complete45-goal results are preserved. Final code runs45 known goals plus4 different, pre-frozen confirmation goals without tuning on their model outcomes. Developer synthesis, not an independent user study.',
            'first_phase':'qa/v0.22/first-evaluation.json'}
    for row in records:
        assert len(row['reports'])==1
        name=row['reports'][0];report=json.loads((ROOT/name).read_text());label=row['suite']
        validate(ROOT,label,report)
        assert report['source_hashes']==frozen['backend_hashes'] and report['source_hashes_unchanged'] and report['network_denied']
        assert report['runner_sha256']==frozen['runner_sha256']
        times=[c['seconds'] for c in report['cases'] if c['passed']]
        result['final_reports'][label]=name
        result['suites'][label]={'passed':report['passed'],'total':report['total'],
            'model_executed':sum(c.get('model_executed',False) for c in report['cases']),
            'dependency_blocked':sum(c.get('dependency_blocked',False) for c in report['cases']),
            'failures':[{'id':c['id'],'error':c.get('error'),'rows':c.get('rows'),
                         'failed_checks':[k for k,v in c.get('checks',{}).items() if not v]} for c in report['cases'] if not c['passed']],
            'seconds':{c['id']:c['seconds'] for c in report['cases']},
            'successful_seconds':{'min':min(times) if times else None,'max':max(times) if times else None,'median':median(times) if times else None},
            'peak_mlx_gb':report['peak_mlx_gb'],'peak_process_rss_gb':report['peak_process_rss_gb']}
    for path,sha in frozen['new_input_hashes'].items():assert digest(ROOT/path)==sha
    result['known_passed']=sum(v['passed'] for k,v in result['suites'].items() if k!='unseen')
    result['known_total']=sum(v['total'] for k,v in result['suites'].items() if k!='unseen')
    result['new_passed']=result['suites']['unseen']['passed'];result['new_total']=result['suites']['unseen']['total']
    (ROOT/'qa/v0.22-evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print({key:str(value['passed'])+'/'+str(value['total']) for key,value in result['suites'].items()})

if __name__=='__main__':main()
