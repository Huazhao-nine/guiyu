"""Real local multi-delivery and personal-planning goals; isolated fictional data."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime
import hashlib,io,json,re,resource,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--model-id',default='qwen3.5-9b');p.add_argument('--cases',nargs='*');p.add_argument('--isolated',action='store_true');p.add_argument('--label',default='v0.10');args=p.parse_args()
if not args.isolated:raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),*sys.argv[1:],'--isolated']).returncode)
source_hashes_at_start={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'backend').glob('*.py')}
sys.path.insert(0,str(ROOT/'backend'))
import worker as core
from office_agent import OfficeAgent
import mlx.core as mx
suite=ROOT/'fixtures/general_agent/tasks.json'
report={'version':'0.10.0','date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'model_id':args.model_id,'network_denied':core.network_probe()['blocked'],'cases':[],
        'protocol':{'case_file_sha256':hashlib.sha256(suite.read_bytes()).hexdigest(),'seed':133,'method':'One execution per fixed goal; normal bounded repair and final delivery review enabled. No injected drafts or review decisions.','limits':'Developer cases on M5 32 GB with standard 16 GB runtime policy, not an actual 16 GB device or user study.'}}
assert report['network_denied']
model_path=Path.home()/'Library/Application Support'/('GuiyuRuntime/model' if args.model_id=='qwen3-4b' else 'GuiyuModels/Installed/'+args.model_id)
model=core.LocalModel(model_path);report['runtime_policy']=model.policy.object()
trace=ROOT/'qa/private/v0.10'/('general-'+args.model_id+'.jsonl');trace.parent.mkdir(parents=True,exist_ok=True)
original=model.generate
current=''
def generate(system,user,**kwargs):
 result=original(system,user,**kwargs)
 with trace.open('a') as f:f.write(json.dumps({'case':current,'system':system,'user':user,'text':result[0],'stats':result[1]},ensure_ascii=False)+'\n')
 return result
model.generate=generate
with tempfile.TemporaryDirectory(prefix='guiyu-general-') as temp:
 base=Path(temp).resolve();workspace=base/'fictional';shutil.copytree(ROOT/'fixtures/office_showcase/workspace',workspace)
 before={str(f.relative_to(workspace)):core.digest(f) for f in workspace.rglob('*') if f.is_file()}
 office=OfficeAgent(core.Agent(model,base/'data'),core)
 for case in json.loads(suite.read_text())['cases']:
  if args.cases and case['id'] not in args.cases:continue
  current=case['id'];mx.random.seed(133);start=time.perf_counter();row={'id':current,'prompt':case['prompt'],'checks':{}}
  try:
   paths=[str(workspace/f) for f in case['files']]
   with redirect_stdout(io.StringIO()):
    plan=office.draft({'prompt':case['prompt'],'paths':paths,'kind':'auto','adaptive':True});result=office.execute({'plan_id':plan['id'],'paths':paths})
   plan=result['plan'];text=result['text'];flat=re.sub(r'[\s*]','',re.sub(r'[\u2010-\u2015\u2212]','-',text))
   kinds=[a['type'] for a in result['artifacts']]
   row.update(delivered_text=text,tools=[s['tool'] for s in plan['steps']],completion_check=plan.get('completion_check'),
              steps=[{k:s.get(k) for k in ('tool','instruction','attempts','check')} for s in plan['steps']],artifact_types=kinds,activity=plan.get('events',[]))
   row['checks'].update(completed_without_grounded=plan['state']=='completed' and not plan.get('grounded_delivery'),
                        expected_facts=all(any(re.sub(r'\s','',v) in flat for v in token.split('|')) for token in case['must']),
                        editable_deliveries=kinds.count('docx')>=case['minimum_docx'] and kinds.count('xlsx')>=case['minimum_xlsx'],
                        original_files_unchanged=before=={str(f.relative_to(workspace)):core.digest(f) for f in workspace.rglob('*') if f.is_file()},
                        all_artifacts_exist=all(Path(a['path']).is_file() for a in result['artifacts']),
                        no_source_change=not result.get('transaction'),delivery_review_recorded=plan.get('completion_check',{}).get('state')=='passed')
   if current=='meeting_multi_delivery':
    table=next(v for v in plan['results'].values() if '负责人' in v.get('columns',[]) or '任务' in v.get('columns',[]))
    rows=[re.sub(r'[\u2010-\u2015]','-',str(r)) for r in table['rows']]
    row['checks']['three_correct_assignments']=all(any(name in r and task in r and date in r for r in rows) for name,task,date in [('林晓','演示','10-23'),('陈雨','费用','10-22'),('周宁','测试','10-24')])
  except Exception as exc:row['error']=type(exc).__name__+': '+str(exc)[:350]
  row['seconds']=round(time.perf_counter()-start,2);row['passed']=bool(row['checks']) and all(row['checks'].values()) and 'error' not in row;report['cases'].append(row)
  print('GENERAL',current,row['passed'],row.get('error',''),flush=True)
  (ROOT/'qa'/f'{args.label}-{args.model_id}-general-agent-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
report.update(passed_cases=sum(c['passed'] for c in report['cases']),case_count=len(report['cases']),peak_mlx_gb=round(mx.get_peak_memory()/1e9,3),peak_process_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,3))
report['all_checks_passed']=all(c['passed'] for c in report['cases'])
report['source_hashes']=source_hashes_at_start
(ROOT/'qa'/f'{args.label}-{args.model_id}-general-agent-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('passed_cases','case_count','peak_mlx_gb','peak_process_rss_gb','all_checks_passed')}))
