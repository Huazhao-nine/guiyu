"""Local, network-denied evaluation of the production incremental workbook protocol."""
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
 p=argparse.ArgumentParser();p.add_argument('--isolated',action='store_true');p.add_argument('--suite',choices=['known','regression','adaptation'],default='known');p.add_argument('--cases',nargs='*');p.add_argument('--model-id',choices=['qwen3.5-9b','qwen3-4b'],default='qwen3.5-9b');args=p.parse_args()
 if not args.isolated:
  command=['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),'--isolated','--suite',args.suite,'--model-id',args.model_id]
  if args.cases:command+=['--cases']+args.cases
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
 else:cases=json.loads((adapt/'tasks.json').read_text())['cases'];folders=[adapt]
 if args.cases:cases=[c for c in cases if c['id'] in args.cases]
 stamp=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]
 run=ROOT/'qa/private/v0.18'/stamp;workspace=run/'workspace';workspace.mkdir(parents=True)
 for folder in folders:
  for file in (folder/'workspace').iterdir():
   if file.is_file() and file.suffix.lower() in ('.csv','.xlsx'):shutil.copy2(file,workspace/file.name)
 frozen={f.name:core.digest(f) for f in workspace.iterdir()}
 modelpath=Path.home()/('Library/Application Support/GuiyuModels/Installed/qwen3.5-9b' if args.model_id=='qwen3.5-9b' else 'Library/Application Support/GuiyuRuntime/model')
 model=core.LocalModel(modelpath);office=OfficeAgent(core.Agent(model,run/'data'),core)
 target=ROOT/'qa/v0.18/reports'/f'{args.suite}-{args.model_id}-{stamp}.json';target.parent.mkdir(parents=True,exist_ok=True)
 report={'version':'0.18.0','suite':args.suite,'time':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'model':args.model_id,'structured_temperature':0,'seed':20261029,'hardware':'Apple M5 32GB;16GB target, not16GB hardware validation','network_denied':core.network_probe()['blocked'],'source_hashes':{f.name:core.digest(f) for f in (ROOT/'backend').glob('*.py')},'fixture_hashes':frozen,'suite_hashes':{str((f/'tasks.json').relative_to(ROOT)):core.digest(f/'tasks.json') for f in folders},'runner_sha256':core.digest(Path(__file__)),'cases':[]}
 assert report['network_denied'];current='';generate=model.generate;saved={}
 def traced(system,user,**kw):
  result=generate(system,user,**kw)
  with (run/'model-trace.jsonl').open('a') as f:f.write(json.dumps({'case':current,'system':system,'user':user,'kwargs':kw,'output':result[0],'stats':result[1]},ensure_ascii=False)+'\n')
  return result
 model.generate=traced
 for case in cases:
  current=case['id'];start=time.perf_counter();row={'id':current,'prompt':case['prompt']};parent=saved.get(case.get('parent'));before={str(f) for f in (run/'data/Outputs').rglob('*')} if (run/'data/Outputs').exists() else set();plan=None
  try:
   if case.get('parent') and parent is None:raise ValueError('上一任务未完成，未伪造后续上下文。')
   paths=parent['plan']['paths'] if parent else [str(f) for f in workspace.iterdir()]
   row['authorized_file_count']=len(paths)
   with redirect_stdout(io.StringIO()) as events:
    plan=office.draft({'id':uuid.uuid4().hex,'prompt':case['prompt'],'kind':'auto','adaptive':True,'workbook_mode':'flow','paths':paths,'parent_id':parent['id'] if parent else None})
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
    'word_if_requested':not case.get('word') or bool(words),'word_values':all(re.search(r'(?<![\d.])'+re.escape(n)+r'(?:\.0+)?(?![\d.])',text) for n in case.get('word_numbers',[])),
    'no_unrequested_word':bool(case.get('word')) or not words,'completed':result['plan']['state']=='completed','checked_delivery':result['plan']['completion_check']['state']=='passed','no_original_transaction':not result.get('transaction'),
    'originals_unchanged':all(core.digest(workspace/n)==h for n,h in frozen.items())}
   row.update(passed=all(checks.values()) and not case.get('clarify'),checks=checks,rows=matrix[1:],columns=matrix[0],summaries=summaries,word_text=text,graph=plan['workbook']['flow']['graph'],finish=plan['workbook']['flow']['finish'],repairs=plan['workbook']['repairs'])
  except Exception as exc:
   row.update(passed=False,error=str(exc)[:1500])
   if case.get('clarify'):
    after={str(f) for f in (run/'data/Outputs').rglob('*')} if (run/'data/Outputs').exists() else set()
    row.update(passed=bool(re.search(r'标准|依据|明确|补充|判断|最好|关联|结构',str(exc))) and before==after and plan is None,clarification=True)
  row['seconds']=round(time.perf_counter()-start,2);report['cases'].append(row);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(current,row['passed'],row.get('error',''),flush=True)
 report.update(passed=sum(c['passed'] for c in report['cases']),total=len(cases),peak_mlx_gb=round(mx.get_peak_memory()/1e9,3),peak_process_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,3),source_hashes_unchanged=all(core.digest(ROOT/'backend'/n)==h for n,h in report['source_hashes'].items()),limits='Fictional developer tasks with explicitly authorized local files; routing/retrieval and native conversations are checked separately. Known failures are development data. Adaptation is a fixed variant check, not independent user research or a general success-rate guarantee.')
 target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');(run/'report.json').write_text(target.read_text());print(json.dumps({'passed':report['passed'],'total':report['total'],'report':str(target.relative_to(ROOT))}))
 raise SystemExit(0 if report['passed']==report['total'] and report['source_hashes_unchanged'] else 1)

if __name__=='__main__':main()
