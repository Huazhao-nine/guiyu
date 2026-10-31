"""Fixed fictional daily-office tasks with real local retrieval, tools and writing."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import io
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import time

from office_oracle import contains_wrong_claim

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--backend',type=Path,default=ROOT/'backend');parser.add_argument('--label',default='v0.10-qwen3.5-9b');parser.add_argument('--model-id',default='qwen3.5-9b');parser.add_argument('--isolated',action='store_true');parser.add_argument('--cases',nargs='*');args=parser.parse_args()
if not args.isolated:
    raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),*sys.argv[1:],'--isolated']).returncode)
source_hashes_at_start={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.backend.glob('*.py')}
sys.path.insert(0,str(args.backend.resolve()))
import worker as core
from office_agent import OfficeAgent
from workspace_index import WorkspaceIndex
from bge_embedding import LocalEmbedder
import mlx.core as mx
suite=json.loads((ROOT/'fixtures/office_showcase/tasks.json').read_text())
report={'schema':1,'label':args.label,'date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'hardware':'Apple M5 32 GB','model_id':args.model_id,'fixture':'18 fictional office files; 12 fixed tasks','protocol':{'temperature':0.1,'seed_per_case':91,'no_model_or_prompt_selection':True,'source_case_file_sha256':hashlib.sha256((ROOT/'fixtures/office_showcase/tasks.json').read_bytes()).hexdigest()},'network_denied':core.network_probe()['blocked'],'cases':[]}
assert report['network_denied']
model_path=Path.home()/'Library/Application Support'/('GuiyuRuntime/model' if args.model_id=='qwen3-4b' else 'GuiyuModels/Installed/'+args.model_id)
model=core.LocalModel(model_path)
report['runtime_policy']=model.policy.object()
report['hardware_limit']='Run on 32 GB host using the standard 16 GB runtime policy; not an actual 16 GB device test.'
trace=ROOT/'qa/private/v0.10'/f'{args.label}-daily-trace.jsonl';trace.parent.mkdir(parents=True,exist_ok=True)
original_generate=model.generate
current_case=''
def generate(system,user,**kw):
    value=original_generate(system,user,**kw)
    with trace.open('a') as f:f.write(json.dumps({'case':current_case,'system':system,'user':user,'text':value[0],'stats':value[1]},ensure_ascii=False)+'\n')
    return value
model.generate=generate
with tempfile.TemporaryDirectory(prefix='guiyu-daily-') as temp:
    base=Path(temp).resolve();workspace=base/'工作区';shutil.copytree(ROOT/'fixtures/office_showcase/workspace',workspace)
    hashes={str(p.relative_to(workspace)):core.digest(p) for p in workspace.rglob('*') if p.is_file()}
    encoder=LocalEmbedder(Path.home()/'Library/Application Support/GuiyuModels/Installed/bge-small-zh-v1.5',ROOT/'packaging/model-catalog.json')
    idx=WorkspaceIndex(workspace,base/'index',encoder);agent=OfficeAgent(core.Agent(model,base/'tasks'),core);parents={}
    for case in suite['cases']:
        if args.cases and case['id'] not in args.cases:continue
        current_case=case['id'];mx.random.seed(91);started=time.perf_counter();row={'id':case['id'],'title':case['title'],'prompt':case['prompt'],'category':case['category'],'checks':{},'outcome':'failed'}
        try:
            parent=parents.get(case.get('parent'));previous={'snapshots':parent['plan']['snapshot'],'retrieval':parent['plan']['retrieval']} if parent else None
            found=idx.retrieve({'query':case['prompt'],'kind':'auto',**({'previous':previous} if previous else {})})
            row['retrieved_files']=[str(Path(p).relative_to(workspace)) for p in found['paths']]
            row['checks']['correct_retrieval_scope']=set(row['retrieved_files'])==set(case['files']) if case['files'] else True
            if not found['paths'] and case['category']=='missing':
                row['outcome']='no_match';row['checks']['missing_record_not_fabricated']=True;row['delivered_text']='没有找到匹配资料，未执行写作。'
            else:
                request={'prompt':case['prompt'],'paths':found['paths'],'retrieval':found,'kind':'auto','adaptive':True}
                if parent:request['parent_id']=parent['id']
                if found.get('refreshed'):request['refresh_sources']=True
                with redirect_stdout(io.StringIO()):
                    plan=agent.draft(request);result=agent.execute({'plan_id':plan['id'],'paths':plan['paths']})
                parents[case['id']]=result;final=result['plan'];text=result['text'];compact=re.sub(r'[\s,*]','',re.sub(r'[\u2010-\u2015\u2212]','-',text))
                row.update(completion_check=final.get('completion_check'),delivered_text=text,plan_state=final['state'],grounded=final.get('grounded_delivery',False),tools=[s['tool'] for s in final['steps']],steps=[{k:s.get(k) for k in ('tool','attempts','check','summary')} for s in final['steps']],activity=final.get('events',[]),artifact_types=[a['type'] for a in result['artifacts']])
                row['outcome']='grounded' if row['grounded'] else 'completed' if final['state']=='completed' else final['state']
                row['checks']['task_completed']=(final['state']=='needs_input' and not result['artifacts'] and all(s['attempts']==0 for s in final['steps'] if s['tool']=='write')) if case['category']=='missing' else final['state']=='completed' and not row['grounded']
                row['checks']['expected_facts_retained']=all(any(re.sub(r'\s','',v) in compact for v in token.split('|')) for token in case['must'])
                row['checks']['no_known_wrong_claims']=not contains_wrong_claim(text,case.get('absent',[]))
                row['checks']['artifacts_valid']=all(Path(a['path']).is_file() for a in result['artifacts'])
                if case['category'] in ('write','statistics'):
                    row['checks']['usable_checked_draft']=any(s['tool']=='write' and s.get('check',{}).get('content_review')=='model' for s in final['steps']) and any(a['type']=='docx' for a in result['artifacts'])
                if case.get('none_required'):
                    row['checks']['no_ineligible_recommendation']=bool(re.search(r'(?:均|都|没有|无一|无法).{0,22}(?:满足|符合)',compact)) and not any(x in compact for x in ('需接受超预算','考虑调整预算','建议调整预算'))
                if case.get('grouped'):
                    stat=next(v for k,v in reversed(list(final.get('results',{}).items())) if '合计' in v.get('columns',[]))
                    totals={r[stat['columns'].index('经办人')]:r[stat['columns'].index('合计')] for r in stat['rows']}
                    row['checks']['exact_grouped_totals']=totals==case['grouped'];row['actual_grouped_totals']=totals
                if case['category']=='organize':row['checks']['original_change_only_preview']=result['transaction']['state']=='preview'
            row['checks']['original_files_unchanged']={str(p.relative_to(workspace)):core.digest(p) for p in workspace.rglob('*') if p.is_file()}==hashes
        except Exception as exc:row['error']=str(exc)[:400]
        row['passed']=bool(row['checks']) and all(row['checks'].values()) and 'error' not in row
        row['seconds']=round(time.perf_counter()-started,2);report['cases'].append(row)
        print('DAILY',case['id'],row['outcome'],row['passed'],row.get('error',''),flush=True)
        (ROOT/'qa'/f'{args.label}-daily-office-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    idx.close();encoder.close()
report['passed_cases']=sum(c['passed'] for c in report['cases']);report['case_count']=len(report['cases']);report['grounded_cases']=sum(c.get('grounded',False) for c in report['cases']);report['all_checks_passed']=all(c['passed'] for c in report['cases'])
report['source_hashes']=source_hashes_at_start
report['peak_mlx_gb']=round(mx.get_peak_memory()/1e9,3)
report['peak_process_rss_gb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,3)
(ROOT/'qa'/f'{args.label}-daily-office-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('passed_cases','case_count','grounded_cases','all_checks_passed')}))
