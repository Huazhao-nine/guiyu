"""Frozen heterogeneous workbook tasks with real local routing, BGE, planning and exports."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime
from decimal import Decimal,InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo
import csv
import io
import json
import resource
import re
import shutil
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]

def same_rows(actual,expected):
 if len(actual)!=len(expected):return False
 def same(a,b):
  if a==b:return True
  try:return Decimal(a.rstrip('%'))==Decimal(b.rstrip('%')) and a.endswith('%')==b.endswith('%')
  except InvalidOperation:return False
 return all(len(a)==len(b) and all(same(str(x),str(y)) for x,y in zip(a,b)) for a,b in zip(actual,expected))

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--isolated',action='store_true');parser.add_argument('--model-id',default='qwen3.5-9b',choices=['qwen3.5-9b','qwen3-4b']);parser.add_argument('--cases',nargs='*');args=parser.parse_args()
 if not args.isolated:raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),'--isolated','--model-id',args.model_id]+(['--cases']+args.cases if args.cases else [])).returncode)
 sys.path.insert(0,str(ROOT/'backend'));import worker as core
 from office_agent import OfficeAgent
 from request_router import RequestRouter
 from workspace_index import WorkspaceIndex
 from bge_embedding import LocalEmbedder
 from openpyxl import load_workbook
 from workbook_export import read_cells
 from docx import Document
 import mlx.core as mx
 suite=ROOT/'fixtures/workbook_general/tasks.json';cases=json.loads(suite.read_text())['cases'];cases=[c for c in cases if not args.cases or c['id'] in args.cases]
 run=ROOT/'qa/private/v0.17'/('workbook-'+args.model_id+'-'+uuid.uuid4().hex[:8]);run.mkdir(parents=True)
 workspace=run/'workspace';shutil.copytree(ROOT/'fixtures/workbook_general/workspace',workspace)
 frozen={p.name:core.digest(p) for p in workspace.iterdir() if p.suffix in ('.csv','.xlsx')}
 modelpath=Path.home()/('Library/Application Support/GuiyuModels/Installed/qwen3.5-9b' if args.model_id=='qwen3.5-9b' else 'Library/Application Support/GuiyuRuntime/model')
 model=core.LocalModel(modelpath);embed=LocalEmbedder(Path.home()/'Library/Application Support/GuiyuModels/Installed/bge-small-zh-v1.5',ROOT/'packaging/model-catalog.json')
 office=OfficeAgent(core.Agent(model,run/'data'),core);index=WorkspaceIndex(workspace,run/'index',embed);router=RequestRouter(office.agent,core)
 output=ROOT/('qa/v0.17-'+args.model_id+('-workbook-probe-report.json' if args.cases else '-workbook-report.json'))
 if output.exists():shutil.copy2(output,run/'previous-report.json')
 report={'version':'0.17.0','time':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'hardware':'Apple M5 32GB;16GB support target, not16GB device validation','model':args.model_id,'network_denied':core.network_probe()['blocked'],'source_hashes':{p.name:core.digest(p) for p in (ROOT/'backend').glob('*.py')},'suite_sha256':core.digest(suite),'runner_sha256':core.digest(Path(__file__)),'fixture_hashes':frozen,'cases':[]}
 assert report['network_denied'];saved={};current='';original=model.generate
 def traced(system,user,**kw):
  result=original(system,user,**kw)
  with (run/'model-trace.jsonl').open('a') as f:f.write(json.dumps({'case':current,'system':system,'user':user,'output':result[0],'stats':result[1]},ensure_ascii=False)+'\n')
  return result
 model.generate=traced
 for case in cases:
  current=case['id'];start=time.perf_counter();row={'id':current,'prompt':case['prompt']};parent=saved.get(case.get('parent'))
  if case.get('parent') and parent is None:
   row.update(passed=False,error='Parent task did not complete; no fabricated continuation.');report['cases'].append(row);continue
  plan=None;exports_before={str(p) for p in (office.agent.data/'Outputs').rglob('*')} if (office.agent.data/'Outputs').exists() else set()
  try:
   with redirect_stdout(io.StringIO()):
    decision=router.decide({'prompt':case['prompt'],'kind':'auto','workspace_available':True,'previous_source':{'prompt':parent['prompt']} if parent else None})
    previous={'snapshots':parent['plan']['snapshot'],'retrieval':parent['plan'].get('retrieval',{})} if parent else None
    found=index.retrieve({'query':case['prompt'],'kind':'auto','previous':previous})
    plan=office.draft({'id':uuid.uuid4().hex,'prompt':case['prompt'],'kind':'auto','paths':found['paths'],'workspace_root':str(workspace),'retrieval':found,'adaptive':True,'parent_id':parent['id'] if parent else None})
    result=office.execute({'plan_id':plan['id'],'paths':plan['paths'],'workspace_root':str(workspace)})
   saved[current]=result;(run/(current+'-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
   data=next(r for r in result['plan']['results'].values() if 'workbook_check' in r)
   xlsx=next(a['path'] for a in data['artifacts'] if a['type']=='xlsx');book=load_workbook(xlsx,read_only=True,data_only=False)
   try:matrix=read_cells(book,'处理结果')
   finally:book.close()
   csvfile=next(a['path'] for a in data['artifacts'] if a['type']=='csv')
   with open(csvfile,encoding='utf-8-sig',newline='') as f:csvmatrix=list(csv.reader(f))
   summaries=data['result_table'].get('summaries',[]);summary_values=[v for s in summaries for r in s['rows'] for v in r]
   words=[a for a in result['artifacts'] if a['type']=='docx'];wordtext='\n'.join(text for a in words for text in ([p.text for p in Document(a['path']).paragraphs]+[' | '.join(c.text for c in r.cells) for t in Document(a['path']).tables for r in t.rows]))
   checks={'source_route':decision['mode']=='workspace','schema_agent_used':bool(result['plan'].get('workbook')),'completed':result['plan']['state']=='completed','expected_rows':same_rows(matrix[1:],case.get('rows',[])), 'expected_fields':not case.get('columns') or [re.sub(r'[（(][^）)]*[）)]|\s','',c) for c in matrix[0]]==case['columns'],'csv_same_cells':matrix==csvmatrix,'preview_same_cells':matrix==[data['columns']]+data['rows'],'summary_values':all(v in summary_values for v in case.get('summary_values',[])),'word_if_requested':not case.get('word') or bool(words),'word_numbers':all(re.search(r'(?<![\d.])'+re.escape(n)+r'(?:\.0+)?(?![\d.])',wordtext) for n in case.get('word_numbers',[])),'no_unrequested_word':bool(case.get('word')) or not words,'full_delivery':result['plan'].get('completion_check',{}).get('state')=='passed','no_grounded_fallback':not result['plan'].get('grounded_delivery'),'no_original_transaction':not result.get('transaction'),'source_hashes_preserved':all(core.digest(workspace/n)==h for n,h in frozen.items())}
   row.update(checks=checks,passed=all(checks.values()) and not case.get('clarify'),columns=matrix[0],rows=matrix[1:],program=result['plan']['workbook']['program'],selection=result['plan']['workbook']['selection'],repairs=result['plan']['workbook']['repairs'],structure_repairs=result['plan']['workbook']['structure_repairs'],summaries=summaries,word_text=wordtext)
  except Exception as exc:
   exports=list((office.agent.data/'Outputs').rglob('*')) if (office.agent.data/'Outputs').exists() else []
   # The ambiguous case must not create new files for its own task; successful
   # earlier tasks are retained. Count changes in the target output directory.
   row.update(passed=False,error=str(exc)[:1200])
   if case.get('clarify'):
    row.update(passed=bool(re.search(r'标准|依据|明确|补充|判断|最好|关联|结构',str(exc))) and not ({str(p) for p in exports}-exports_before) and plan is None,clarification=True)
  row['seconds']=round(time.perf_counter()-start,2);report['cases'].append(row);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(current,row['passed'],row.get('error',''),flush=True)
 report.update(passed=sum(c['passed'] for c in report['cases']),total=len(cases),peak_mlx_gb=round(mx.get_peak_memory()/1e9,3),peak_process_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,3),source_hashes_unchanged=all(core.digest(ROOT/'backend'/n)==h for n,h in report['source_hashes'].items()),limits='Frozen fictional developer cases across procurement, sales, inventory and registration. Not held-out user research or16GB device validation. Numeric normalization allows only equal values, not changed ordering or omitted fields.')
 output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');(run/'report.json').write_text(output.read_text());print(report['passed'],report['total'])
 raise SystemExit(0 if report['passed']==report['total'] and report['source_hashes_unchanged'] else 1)
if __name__=='__main__':main()
