"""CPU compatibility check of previously verified plans, without model calls.

This checks current argument/intent validation against the old valid operations.
It is deliberately separate from generating a new plan on an unseen workbook.
The public fixture contains only previously verified fictional tables/plans.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import worker as core
from workbook_data import inspect_documents,prepare_table
from workbook_flow import TableFlow


def action(operation):
    op=deepcopy(operation);tool=op.pop('op')
    if tool=='derive':op['formula']=op.pop('expression')
    if tool in ('select','distinct'):op['fields']=op.pop('columns')
    if tool=='group':
        for metric in op['metrics']:
            metric['name']=metric.pop('as');metric.pop('precision',None)
            if 'column' in metric:metric['field']=metric.pop('column')
    if tool=='sort':
        for key in op['by']:key['field']=key.pop('column');key.pop('type',None)
    return dict(tool=tool,**op)


def cells(table):
    return {'columns':table['columns'],'rows':table['rows'],
            'summaries':[{'columns':s['columns'],'rows':s['rows']} for s in table.get('summaries',[])]}


def capture_legacy():
    old=json.loads((ROOT/'qa/v0.21-evaluation.json').read_text());rows=[]
    for suite,path in old['final_reports'].items():
        report=json.loads((ROOT/path).read_text());stamp=Path(path).stem.split('qwen3.5-9b-',1)[1]
        run=ROOT/'qa/private/v0.21'/stamp
        for case in report['cases']:
            if not case['passed'] or case.get('clarification') or case.get('checks',{}).get('chat_route'):continue
            rawpath=run/(case['id']+'-result.json')
            if not rawpath.exists():continue
            raw=json.loads(rawpath.read_text());plan=raw['plan'];config=plan['workbook']
            if config.get('mode')!='flow':continue
            item={'suite':suite,'id':case['id']}
            try:
                inputs=plan['paths']
                source=prepare_table(inspect_documents([{'path':p,'name':Path(p).name} for p in inputs],core),config['selection'])
                goals=config['flow'].get('goals',[plan['prompt']])
                expected=next(v['result_table'] for v in plan['results'].values() if 'workbook_check' in v)
                item.update(source=source,goal='\n'.join(goals),current_goal=plan['prompt'],previous=config.get('previous_result'),
                            recipes=config['flow'].get('row_derivations',[]),previous_shape=config.get('previous_shape'),
                            graph=config['flow']['graph'],finish=config['flow']['finish'],contract=config['flow']['contract'],expected=cells(expected))
            except Exception as exc:raise ValueError('Could not recover fictional plan '+case['id']) from exc
            rows.append(item)
    # No path from the private harness is part of a reusable table/plan fixture.
    encoded=json.dumps({'scope':'Previously completed v21 fictional plans; expected cells retained from original delivery, not recomputed to fit v22.','cases':rows},ensure_ascii=False,indent=2)+'\n'
    assert str(ROOT) not in encoded and '/Users/' not in encoded
    return encoded


def main():
    fixture=ROOT/'fixtures/workbook_plan_replay_v22/cases.json'
    if '--capture-legacy' in sys.argv:
        assert not fixture.exists(),'Preserving frozen old-plan expected cells.'
        encoded=capture_legacy();fixture.parent.mkdir(parents=True,exist_ok=True);fixture.write_text(encoded)
    records=json.loads(fixture.read_text())['cases'];rows=[]
    for record in records:
        item={k:record[k] for k in ('suite','id')}
        try:
            flow=TableFlow(record['source'],record['goal'],record.get('previous'),current_goal=record['current_goal'],
                           recipes=record['recipes'],previous_shape=record['previous_shape'])
            mapping={'V0':'V0','P0':'P0'}
            for step in record['graph']:
                event=flow.apply(dict(action(step['operation']),input=mapping[step['input']]))
                mapping[step['id']]=event['view']
            finish=deepcopy(record['finish']);finish['result']=mapping[finish['result']]
            finish['summaries']=[mapping[k] for k in finish.get('summaries',[])]
            actual=flow.finish(finish,record['contract'])
            item.update(passed=cells(actual)==record['expected'],operation_count=len(flow.graph),
                        automatic_intent_corrections=sum(len(s.get('intent_corrections',[])) for s in flow.graph))
            if not item['passed']:item.update(actual=cells(actual),expected=record['expected'])
        except Exception as exc:item.update(passed=False,error=type(exc).__name__+': '+str(exc)[:600])
        rows.append(item)
    result={'version':'0.22.0','time':datetime.now().astimezone().isoformat(),'model_calls':0,
            'scope':'Replay previously completed v21 fictional plans through current typed action and intent validation. Not new planning, unseen-input evaluation, or end-user testing.',
            'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
            'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'backend').glob('*.py')},
            'cases':rows,'passed':sum(r['passed'] for r in rows),'total':len(rows)}
    (ROOT/'qa/v0.22/verified-plan-replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('passed','total','model_calls')}))
    for row in rows:
        if not row['passed']:print(row['id'],row.get('error','different delivered cells'))
    raise SystemExit(0 if result['passed']==result['total'] else 1)


if __name__=='__main__':main()
