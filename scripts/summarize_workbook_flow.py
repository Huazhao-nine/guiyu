"""Bind final measurements to the source freeze without combining old successes."""
import argparse
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())

def main():
    parser=argparse.ArgumentParser()
    for name in ('regression','transfer','adaptation'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();freeze=read(ROOT/'qa/v0.18/freeze.json')
    hashes={p.name:digest(p) for p in (ROOT/'backend').glob('*.py')}
    assert freeze['backend_hashes']==hashes
    assert freeze['runner_sha256']==digest(ROOT/'scripts/check_workbook_flow.py')
    assert all(digest(ROOT/name)==h for name,h in freeze['adaptation_hashes'].items())
    final={};results={};loaded={}
    for label in ('regression','transfer','adaptation'):
        path=ROOT/getattr(args,label);relative=path.resolve().relative_to(ROOT).as_posix()
        assert relative.startswith('qa/v0.18/reports/')
        report=read(path)
        assert report['source_hashes']==hashes and report['source_hashes_unchanged'] and report['network_denied']
        assert report['runner_sha256']==freeze['runner_sha256']
        assert report['passed']==sum(c['passed'] for c in report['cases']) and report['total']==len(report['cases'])
        final[label]=relative;loaded[label]=report
        results[label]={'passed':report['passed'],'total':report['total'],
            'failures':[{'id':c['id'],'error':c.get('error'), 'failed_checks':[k for k,v in c.get('checks',{}).items() if not v]} for c in report['cases'] if not c['passed']],
            'seconds':[c['seconds'] for c in report['cases']],
            'peak_mlx_gb':report['peak_mlx_gb'],'peak_process_rss_gb':report['peak_process_rss_gb']}
    spec=read(ROOT/'fixtures/workbook_adaptation/tasks.json')['metamorphic_pair']
    cases={c['id']:c for c in loaded['adaptation']['cases']}
    before,after=cases[spec['before']],cases[spec['after']]
    def total(case):
        for summary in case.get('summaries',[]):
            fields=[i for i,c in enumerate(summary['columns']) if summary.get('units',{}).get(c)=='CNY']
            if len(fields)==1 and len(summary['rows'])==1:
                return Decimal(summary['rows'][0][fields[0]])
        return None
    a,b=total(before),total(after)
    same_ids=bool(before.get('rows')) and [r[0] for r in before['rows']]==[r[0] for r in after.get('rows',[])]
    pair={'before':spec['before'],'after':spec['after'],'expected_delta':spec['expected_total_delta'],
          'actual_before':str(a) if a is not None else None,'actual_after':str(b) if b is not None else None,
          'actual_delta':str(b-a) if a is not None and b is not None else None,'same_ids':same_ids,
          'passed':bool(before['passed'] and after['passed'] and same_ids and a is not None and b is not None and b-a==Decimal(spec['expected_total_delta']))}
    historical=[]
    for p in sorted((ROOT/'qa/v0.18/reports').glob('*.json')):
        if p.relative_to(ROOT).as_posix() in final.values():continue
        d=read(p);historical.append({'report':p.relative_to(ROOT).as_posix(),'passed':d.get('passed'),
            'total':d.get('total',len(d.get('cases',[]))),'complete':'source_hashes_unchanged' in d})
    output={'version':'0.18.0','date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'hardware':'Apple M5 32GB;16GB design target, not16GB hardware validation',
        'freeze':'qa/v0.18/freeze.json','freeze_sha256':digest(ROOT/'qa/v0.18/freeze.json'),
        'source_hashes':hashes,'final_reports':final,'results':results,'metamorphic_pair':pair,
        'python_unit_tests':freeze['python_unit_tests'],'historical_attempts':historical,
        'scores_from_different_snapshots_combined':False,
        'limits':'Fictional development and fixed variant checks, not independent user research or a general task success-rate guarantee. All model work locally network-denied. MLX and RSS overlap and are not whole-system memory. No4B or16GB device quality claim. Native observations are reported separately.'}
    (ROOT/'qa/v0.18-evaluation.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'results':results,'metamorphic_pair':pair},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
