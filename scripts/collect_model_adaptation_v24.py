"""Keep the original model search and the adapted paired comparison distinct."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from collect_model_search_v24 import summarize

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder=ROOT/'qa/v0.24/adaptation'
    target=folder/'evaluation.json';assert not target.exists()
    protocol=json.loads((folder/'protocol.json').read_text())
    screen=json.loads((folder/'screen-summary.json').read_text())
    assert protocol['backend_hashes']=={p.name:sha(p) for p in (ROOT/'backend').glob('*.py')}
    assert sha(ROOT/protocol['runner'])==protocol['runner_sha256']
    assert all(sha(ROOT/p)==h for p,h in protocol['input_hashes'].items())
    reports={}
    for record in screen['reports']:
        r=json.loads((ROOT/record['report']).read_text())
        assert r['source_hashes']==protocol['backend_hashes'] and r['source_hashes_unchanged'] and r['network_denied']
        reports[record['suite'],record['model']]=r
    pairs=[]
    for group in protocol['screen']:
        left=reports[group['suite'],protocol['models'][0]]['cases']
        right=reports[group['suite'],protocol['models'][1]]['cases']
        assert [c['id'] for c in left]==[c['id'] for c in right]==group['expected_ids']
        for a,b in zip(left,right):
            assert a['prompt']==b['prompt']
            pairs.append({'id':a['id'],'suite':group['suite'],'baseline':a,'candidate':b})
    assert len(pairs)==6
    result={'time':datetime.now().astimezone().isoformat(),'hardware':'Apple M5 32GB',
            'original_search':'qa/v0.24/model-search.json','original_scores_unchanged':True,
            'protocol_sha256':sha(folder/'protocol.json'),'backend_hashes':protocol['backend_hashes'],
            'paired_six_goal_models':screen['models'],'selected':screen['selected'],'pairs':pairs,
            'changes':protocol['changes'],'unit_tests':protocol['unit_tests'],
            'scope':'The same six known goals freshly paired on a common adapted backend. Frozen grading, tool and correction limits unchanged. This is joint model/interface fit, not parameter-count causality. Prior v22/v23 full18 have a different backend scope.'}
    if screen['selected']:
        cp=json.loads((folder/'confirmation-protocol.json').read_text())
        records=json.loads((folder/'confirmation-records.json').read_text())
        assert cp['model']==screen['selected']
        assert [r['suite'] for r in records]==[g['suite'] for g in cp['groups']]
        known,new,cases=[],[],[]
        assert all(sha(ROOT/p)==h for p,h in cp['input_hashes'].items())
        for record,group in zip(records,cp['groups']):
            r=json.loads((ROOT/record['report']).read_text())
            assert [c['id'] for c in r['cases']]==group['expected_ids']
            assert r['source_hashes']==protocol['backend_hashes'] and r['source_hashes_unchanged'] and r['network_denied']
            assert r['runner_sha256']==protocol['runner_sha256']
            assert r['common_token_limits']=={'input':8192,'output':1800} and not r['thinking_enabled']
            (new if record['suite']=='novel' else known).append(r)
            cases.extend({'suite':record['suite'],**c} for c in r['cases'])
        result['confirmation']={'known':summarize(known),'new':summarize(new),'reports':records,'cases':cases,
                                'new_scope':'First-use four pre-frozen developer-synthesized goals; no tuning on their outputs.'}
        assert result['confirmation']['known']['total']==18 and result['confirmation']['new']['total']==4
    else:
        result['confirmation']={'executed':False,'reason':'No model met screen admission; new4 unused.'}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'selected':result['selected'],'paired_six_goal_models':result['paired_six_goal_models']}|
                     ({k:result['confirmation'][k] for k in ['known','new']} if screen['selected'] else
                      {'confirmation':result['confirmation']}),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
