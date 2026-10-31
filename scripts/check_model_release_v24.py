"""Candidate model search using the unchanged v0.22 workbook protocol."""
import argparse,csv,hashlib,io,json,re,resource,shutil,subprocess,sys,time,uuid
from contextlib import redirect_stdout
from datetime import datetime
from decimal import Decimal,InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]

def equal_rows(actual,expected):
 def eq(a,b):
  if str(a)==str(b):return True
  try:return Decimal(str(a).rstrip('%'))==Decimal(str(b).rstrip('%')) and str(a).endswith('%')==str(b).endswith('%')
  except InvalidOperation:return False
 return len(actual)==len(expected) and all(len(a)==len(b) and all(eq(x,y) for x,y in zip(a,b)) for a,b in zip(actual,expected))

def main():
 p=argparse.ArgumentParser();p.add_argument('--isolated',action='store_true');p.add_argument('--suite',choices=['known','regression','adaptation','followups','variants','prior_new','fresh','confirmation','new','unseen','novel'],default='known');p.add_argument('--cases',nargs='*');p.add_argument('--model-id',choices=['qwen3.5-9b','glm-4.7-flash','qwen3-coder-30b-a3b','qwen3.6-35b-a3b'],default='qwen3.5-9b');p.add_argument('--model-path',type=Path);args=p.parse_args()
 if not args.isolated:
  command=['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),'--isolated','--suite',args.suite,'--model-id',args.model_id]
  if args.cases:command+=['--cases']+args.cases
  if args.model_path:command+=['--model-path',str(args.model_path)]
  raise SystemExit(subprocess.run(command).returncode)
 sys.path.insert(0,str(ROOT/'backend'));import worker as core
 from office_agent import OfficeAgent
 from workbook_export import read_cells
 from openpyxl import load_workbook
 from docx import Document
 import mlx.core as mx
 mx.random.seed(20261029)
 general=ROOT/'fixtures/workbook_general';variant=ROOT/'fixtures/workbook_transfer';adapt=ROOT/'fixtures/workbook_adaptation'
 if args.suite=='known':
  cases=[c for c in json.loads((general/'tasks.json').read_text())['cases'] if c['id'] in ('detail_summary_write','union_dedup_group')]+json.loads((variant/'tasks.json').read_text())['cases'];folders=[general,variant]
 elif args.suite=='regression':cases=json.loads((general/'tasks.json').read_text())['cases'];folders=[general]
 elif args.suite=='followups':cases=json.loads((ROOT/'fixtures/workbook_followups/tasks.json').read_text())['cases'];folders=[adapt]
 elif args.suite=='novel':
  folder=ROOT/'fixtures/workbook_model_search_v24';cases=json.loads((folder/'tasks.json').read_text())['cases'];folders=[folder]
 elif args.suite=='new':
  folder=ROOT/'fixtures/workbook_variants_v22';cases=json.loads((folder/'tasks.json').read_text())['cases'];folders=[folder]
 elif args.suite=='unseen':
  folder=ROOT/'fixtures/workbook_confirmation_v22';cases=json.loads((folder/'tasks.json').read_text())['cases'];folders=[folder]
 elif args.suite in ('fresh','confirmation'):
  fresh=ROOT/('fixtures/workbook_variants_v21' if args.suite=='fresh' else 'fixtures/workbook_confirmation_v21');cases=json.loads((fresh/'tasks.json').read_text())['cases'];folders=[fresh]
 elif args.suite=='prior_new':
  prior=ROOT/'fixtures/workbook_variants_v20';cases=json.loads((prior/'tasks.json').read_text())['cases'];folders=[prior]
 elif args.suite=='variants':
  variant19=ROOT/'fixtures/workbook_variants_v19';cases=json.loads((variant19/'tasks.json').read_text())['cases'];folders=[variant19]
 else:cases=json.loads((adapt/'tasks.json').read_text())['cases'];folders=[adapt]
 if args.cases:cases=[c for c in cases if c['id'] in args.cases]
 stamp=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]
 run=ROOT/'qa/private/v0.24/release'/stamp;workspace=run/'workspace';workspace.mkdir(parents=True)
 for folder in folders:
  for file in (folder/'workspace').iterdir():
   if file.is_file() and file.suffix.lower() in ('.csv','.xlsx'):shutil.copy2(file,workspace/file.name)
 frozen={f.name:core.digest(f) for f in workspace.iterdir()}
 modelpath=args.model_path or (Path.home()/'Library/Application Support/GuiyuModels'/('Installed/qwen3.5-9b' if args.model_id=='qwen3.5-9b' else 'Research/'+args.model_id))
 load_started=time.perf_counter();model=core.LocalModel(modelpath);load_seconds=time.perf_counter()-load_started
 from dataclasses import replace
 model.policy=replace(model.policy,input_tokens=8192,output_tokens=1800);model.info['runtime_policy']=model.policy.object()
 office=OfficeAgent(core.Agent(model,run/'data'),core)
 target=ROOT/'qa/v0.24/release/reports'/f'{args.suite}-{args.model_id}-{stamp}.json';target.parent.mkdir(parents=True,exist_ok=True)
 report={'version':'0.24-model-release','suite':args.suite,'time':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'model':args.model_id,'structured_temperature':0,'seed':20261029,'hardware':'Apple M5 32GB; user-selected32GB baseline','load_seconds':round(load_seconds,3),'model_info':{k:v for k,v in model.info.items() if k not in ['path','key']},'thinking_enabled':False,'common_token_limits':{'input':8192,'output':1800},'network_denied':core.network_probe()['blocked'],'source_hashes':{f.name:core.digest(f) for f in (ROOT/'backend').glob('*.py')},'fixture_hashes':frozen,'suite_hashes':{str((f/'tasks.json').relative_to(ROOT)):core.digest(f/'tasks.json') for f in folders}|({ 'fixtures/workbook_followups/tasks.json':core.digest(ROOT/'fixtures/workbook_followups/tasks.json')} if args.suite=='followups' else {}),'runner_sha256':core.digest(Path(__file__)),'cases':[]}
 assert report['network_denied'];current='';generate=model.generate;saved={};call_log=[]
 def traced(system,user,**kw):
  try:result=generate(system,user,**kw)
  except Exception as exc:
   call_log.append({'case':current,'stats':{'error':type(exc).__name__}})
   with (run/'model-trace.jsonl').open('a') as f:f.write(json.dumps({'case':current,'error':str(exc),'stats':{}},ensure_ascii=False)+'\n')
   raise
  call_log.append({'case':current,'stats':result[1]})
  with (run/'model-trace.jsonl').open('a') as f:f.write(json.dumps({'case':current,'system':system,'user':user,'kwargs':kw,'output':result[0],'stats':result[1]},ensure_ascii=False)+'\n')
  return result
 model.generate=traced
 for case in cases:
  current=case['id'];events=io.StringIO();start=time.perf_counter();row={'id':current,'prompt':case['prompt']};parent=saved.get(case.get('parent'));before={str(f) for f in (run/'data/Outputs').rglob('*')} if (run/'data/Outputs').exists() else set();plan=None;call_start=len(call_log)
  try:
   if case.get('parent') and parent is None:raise ValueError('上一任务未完成，未伪造后续上下文。')
   paths=parent['plan']['paths'] if parent else [str(f) for f in workspace.iterdir()]
   row['authorized_file_count']=len(paths)
   conversation_parent=saved.get(case.get('conversation_parent')) or parent
   with redirect_stdout(io.StringIO()) as events:
    if case.get('chat'):
     from request_router import RequestRouter
     router=RequestRouter(office.agent,core);request={'id':uuid.uuid4().hex,'prompt':case['prompt'],'history':[],'thread_id':parent['thread_id'] if parent else None,'conversation_parent_id':parent['id'] if parent else None,'workspace_available':True,'previous_source':{'prompt':parent['prompt']} if parent else None}
     decision=router.decide(request);assert decision['mode']=='chat';result=router.chat(request);saved[current]=result
     row.update(passed=not result['sources'] and not result.get('tool_calls') and '归屿' in result['text'],checks={'chat_route':decision['mode']=='chat','no_source_reads':not result['sources']},text=result['text'],seconds=round(time.perf_counter()-start,2))
     (run/(current+'-events.jsonl')).write_text(events.getvalue());(run/(current+'-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2));row['model_calls']=len(call_log)-call_start;row['model_executed']=bool(row['model_calls']);report['cases'].append(row);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(current,row['passed'],flush=True);continue
    plan=office.draft({'conversation_parent_id':conversation_parent['id'] if conversation_parent else None,'thread_id':parent['thread_id'] if parent else None,'id':uuid.uuid4().hex,'prompt':case['prompt'],'kind':'auto','adaptive':True,'workbook_mode':'flow','paths':paths,'parent_id':parent['id'] if parent else None})
    result=office.execute({'plan_id':plan['id'],'paths':plan['paths']})
   (run/(current+'-events.jsonl')).write_text(events.getvalue());(run/(current+'-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2));saved[current]=result
   data=next(r for r in result['plan']['results'].values() if 'workbook_check' in r);xlsx=next(a['path'] for a in data['artifacts'] if a['type']=='xlsx');book=load_workbook(xlsx,read_only=True,data_only=False)
   try:matrix=read_cells(book,'处理结果')
   finally:book.close()
   csvpath=next(a['path'] for a in data['artifacts'] if a['type']=='csv')
   with open(csvpath,encoding='utf-8-sig',newline='') as f:csvmatrix=list(csv.reader(f))
   summaries=data['result_table'].get('summaries',[]);values=[str(v) for s in summaries for r in s['rows'] for v in r]
   words=[a for a in result['artifacts'] if a['type']=='docx'];text='\n'.join(t for a in words for t in ([p.text for p in Document(a['path']).paragraphs]+[' | '.join(c.text for c in r.cells) for table in Document(a['path']).tables for r in table.rows]))
   checks={'incremental_tools':result['plan']['workbook'].get('mode')=='flow','expected_rows':equal_rows(matrix[1:],case.get('rows',[])),
    'expected_columns':not case.get('columns') or [re.sub(r'[（(][^）)]*[）)]|\s','',c) for c in matrix[0]]==case['columns'],
    'preview_matches_xlsx':matrix==[data['columns']]+data['rows'],'csv_matches_xlsx':csvmatrix==matrix,'required_summary':all(str(v) in values for v in case.get('summary_values',[])),
    'typed_summary_rows':not case.get('summary_rows') or equal_rows([r for item in summaries for r in item['rows']],case['summary_rows']),
    'word_if_requested':not case.get('word') or bool(words),'word_values':all(re.search(r'(?<![\d.])'+re.escape(n)+r'(?:\.0+)?(?![\d.])',text) for n in case.get('word_numbers',[])),
    'no_unrequested_word':bool(case.get('word')) or not words,'completed':result['plan']['state']=='completed','checked_delivery':result['plan']['completion_check']['state']=='passed','no_original_transaction':not result.get('transaction'),
    'originals_unchanged':all(core.digest(workspace/n)==h for n,h in frozen.items())}
   row.update(passed=all(checks.values()) and not case.get('clarify'),checks=checks,rows=matrix[1:],columns=matrix[0],summaries=summaries,word_text=text,graph=plan['workbook']['flow']['graph'],finish=plan['workbook']['flow']['finish'],repairs=plan['workbook']['repairs'],planning_stats=plan['workbook']['planning_stats'],revision=plan['workbook']['flow']['contract'].get('revision'),operation_count=len(plan['workbook']['flow']['graph']))
  except Exception as exc:
   row.update(passed=False,error=str(exc)[:1500]);(run/(current+'-events.jsonl')).write_text(events.getvalue() if 'events' in locals() else '')
   if case.get('clarify'):
    after={str(f) for f in (run/'data/Outputs').rglob('*')} if (run/'data/Outputs').exists() else set()
    row.update(passed=bool(re.search(r'标准|依据|明确|补充|判断|最好|关联|结构',str(exc))) and before==after and plan is None,clarification=True)
  row['seconds']=round(time.perf_counter()-start,2);row['model_calls']=len(call_log)-call_start;row['model_executed']=bool(row['model_calls']);row['dependency_blocked']=bool(case.get('parent') and parent is None);row['input_tokens']=sum(c['stats'].get('input_tokens',0) for c in call_log[call_start:]);report['cases'].append(row);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(current,row['passed'],row.get('error',''),flush=True)
 report.update(passed=sum(c['passed'] for c in report['cases']),total=len(cases),peak_mlx_gb=round(mx.get_peak_memory()/1e9,3),peak_process_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,3),source_hashes_unchanged=all(core.digest(ROOT/'backend'/n)==h for n,h in report['source_hashes'].items()),limits='Known developer retest after preserved first-use failures. No new generalization estimate. '+'v0.24 release backend with row/column, calendar, continuity and file-stage contracts, common windows, typed tools and repair bounds; native thinking disabled. Developer synthesis is not independent user research. Models differ beyond size. Native GUI and normal user data are not operated.')
 target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');(run/'report.json').write_text(target.read_text());print(json.dumps({'passed':report['passed'],'total':report['total'],'report':str(target.relative_to(ROOT))}))
 raise SystemExit(0 if report['passed']==report['total'] and report['source_hashes_unchanged'] else 1)

if __name__=='__main__':main()
