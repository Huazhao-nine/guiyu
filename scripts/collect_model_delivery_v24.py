"""Report known retests honestly alongside the unchanged first-use failures."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from collect_model_search_v24 import summarize

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder=ROOT/'qa/v0.24/final';protocol=json.loads((folder/'protocol.json').read_text())
    records=json.loads((folder/'records.json').read_text())
    assert [r['suite'] for r in records]==[g['suite'] for g in protocol['groups']]
    assert protocol['backend_hashes']=={p.name:sha(p) for p in (ROOT/'backend').glob('*.py')}
    assert sha(ROOT/protocol['runner'])==protocol['runner_sha256']
    assert all(sha(ROOT/p)==h for p,h in protocol['input_hashes'].items())
    assert sha(ROOT/protocol['original_first_results'])==protocol['original_first_results_sha256']
    reports=[];cases=[]
    for record,group in zip(records,protocol['groups']):
        report=json.loads((ROOT/record['report']).read_text())
        assert [c['id'] for c in report['cases']]==group['expected_ids']
        assert report['source_hashes']==protocol['backend_hashes'] and report['source_hashes_unchanged'] and report['network_denied']
        assert report['runner_sha256']==protocol['runner_sha256'] and not report['thinking_enabled']
        assert report['common_token_limits']=={'input':8192,'output':1800}
        reports.append(report);cases.extend({'suite':record['suite'],**c} for c in report['cases'])
    summary=summarize(reports);assert summary['total']==5
    result={'time':datetime.now().astimezone().isoformat(),'model':protocol['model'],'summary':summary,
            'reports':records,'cases':cases,'backend_hashes':protocol['backend_hashes'],
            'unit_tests':protocol['unit_tests'],'known_retest':True,'additional_unseen_goals':0,
            'first_results':{'path':protocol['original_first_results'],'unchanged_sha256':protocol['original_first_results_sha256'],
                             'paired_known_six':'9B2/6;35B6/6','extended_known':'17/18','first_new':'1/4, including1 dependent task not run'},
            'changes':protocol['changes'],
            'limits':'Five known development retests after inspecting preserved first-use failures; not a replacement for the first1/4 result and not evidence of unseen4/4. No additional independent user or unknown-input evaluation was run after this fix. No original-file mutations.'}
    target=folder/'evaluation.json';assert not target.exists()
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
