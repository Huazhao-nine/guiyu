"""Real local routing/retrieval/planning/filtering/export on frozen fictional workbook tasks."""
from contextlib import redirect_stdout
from pathlib import Path
import io
import json
import resource
import shutil
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
CASES=[
 {'id':'user_exact','prompt':'在我给你的工作簿 1 文件中，把计算技术研究所的同学的名单分离出来，发给我','ids':['00001','00003','00006','00004','00009','00011']},
 {'id':'two_conditions','prompt':'从工作簿1里挑出计算技术研究所且年级为2025级且状态为已确认的同学名单，发给我。','ids':['00001','00006','00004']},
 {'id':'projection','prompt':'把工作簿1中计算技术研究所的同学名单分离出来，只保留姓名、学号。','ids':['00001','00003','00006','00004','00009','00011'],'columns':['姓名','学号']},
 {'id':'followup','parent':'user_exact','prompt':'那软件研究所的同学名单呢？','ids':['00002','00007','00010']},
 {'id':'one_sheet','prompt':'从工作簿1的工作表“一班”里把计算技术研究所的同学名单分离出来。','ids':['00001','00003','00006']},
 {'id':'zero_matches','prompt':'在工作簿1中筛选培养单位等于不存在研究所的同学，导出名单。','ids':[]},
 {'id':'filtered_sum','prompt':'把工作簿1中计算技术研究所的同学名单分离出来，统计补助合计。','ids':['00001','00003','00006','00004','00009','00011'],'sum':'4650'},
]

def main():
 if '--isolated' not in sys.argv:
  raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),'--isolated']).returncode)
 sys.path.insert(0,str(ROOT/'backend'))
 import worker as core
 from office_agent import OfficeAgent
 from request_router import RequestRouter
 from workspace_index import WorkspaceIndex
 from bge_embedding import LocalEmbedder
 from openpyxl import load_workbook
 import mlx.core as mx
 run=ROOT/'qa/private/v0.16'/('roster-'+uuid.uuid4().hex[:8]);run.mkdir(parents=True)
 workspace=run/'workspace';shutil.copytree(ROOT/'fixtures/roster/workspace',workspace)
 (workspace/'工作簿10.csv').write_text('姓名,培养单位,学号,年级,状态,补助（元）\n不应出现,计算技术研究所,99999,2025级,已确认,99999\n')
 frozen={p.name:core.digest(p) for p in workspace.iterdir()}
 model=core.LocalModel(Path.home()/'Library/Application Support/GuiyuModels/Installed/qwen3.5-9b')
 embed=LocalEmbedder(Path.home()/'Library/Application Support/GuiyuModels/Installed/bge-small-zh-v1.5',ROOT/'packaging/model-catalog.json')
 office=OfficeAgent(core.Agent(model,run/'data'),core);index=WorkspaceIndex(workspace,run/'index',embed);router=RequestRouter(office.agent,core)
 reports=ROOT/'qa/v0.16-roster-agent-report.json'
 if reports.exists():shutil.copy2(reports,run/'previous-report.json')
 report={'version':'0.16.0','hardware':'Apple M5 32 GB;16 GB target, not actual16 GB validation','network_denied':core.network_probe()['blocked'],'source_hashes':{p.name:core.digest(p) for p in (ROOT/'backend').glob('*.py')},'fixture_hashes':frozen,'cases':[]}
 assert report['network_denied']
 original=model.generate;current='';saved={}
 def traced(system,user,**kw):
  response=original(system,user,**kw)
  with (run/'model-trace.jsonl').open('a') as f:f.write(json.dumps({'case':current,'system':system,'user':user,'response':response[0],'stats':response[1]},ensure_ascii=False)+'\n')
  return response
 model.generate=traced
 for case in CASES:
  current=case['id'];started=time.perf_counter();row={'id':current,'prompt':case['prompt']}
  try:
   parent=saved.get(case.get('parent'));previous={'prompt':parent['prompt']} if parent else None
   with redirect_stdout(io.StringIO()):
    decision=router.decide({'prompt':case['prompt'],'workspace_available':True,'previous_source':previous})
    found=index.retrieve({'query':case['prompt'] if not parent else parent['prompt'],'kind':'auto'})
    plan=office.draft({'id':uuid.uuid4().hex,'prompt':case['prompt'],'paths':found['paths'],'retrieval':found,'workspace_root':str(workspace),'adaptive':True,'parent_id':parent['id'] if parent else None})
    result=office.execute({'plan_id':plan['id'],'paths':plan['paths'],'workspace_root':str(workspace)})
   saved[current]=result
   (run/(current+'-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
   filters=[r for r in result['plan']['results'].values() if 'filtered_table' in r]
   selected=filters[0];book=load_workbook(next(a['path'] for a in selected['artifacts'] if a['type']=='xlsx'),read_only=True,data_only=False)
   try:matrix=[[str(x) if x is not None else '' for x in r] for r in book.active.iter_rows(values_only=True)]
   finally:book.close()
   ids=[r[matrix[0].index('学号')] for r in matrix[1:]]
   checks={'route_workspace':decision['mode']=='workspace','completed':result['plan']['state']=='completed','exact_ids':ids==case['ids'],'export_matches_preview':matrix==[selected['columns']]+selected['rows'],'columns':not case.get('columns') or matrix[0]==case['columns'],'no_wrong_workbook':set(result['plan']['source_names'])=={'工作簿1.xlsx'},'not_calculator':not any(s['tool']=='calculate' for s in result['plan']['steps']),'originals_unchanged':all(core.digest(workspace/n)==h for n,h in frozen.items()),'no_transaction':result.get('transaction') is None,'checked_export':selected['selection_check']['export_verified'],'delivery_checked':result['plan'].get('completion_check',{}).get('state')=='passed','sum':not case.get('sum') or case['sum'] in result['text']}
   row.update(checks=checks,passed=all(checks.values()),ids=ids,query=result['plan']['query'],tools=[s['tool'] for s in result['plan']['steps']],text=result['text'],planner=result['plan']['planner_source'])
  except Exception as e:row.update(passed=False,error=str(e)[:1000])
  row['seconds']=round(time.perf_counter()-started,2);report['cases'].append(row)
  reports.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(current,row['passed'],row.get('error',''),flush=True)
 report.update(passed=sum(x['passed'] for x in report['cases']),total=len(CASES),peak_mlx_gb=round(mx.get_peak_memory()/1e9,3),peak_process_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,3),source_hashes_unchanged=all(core.digest(ROOT/'backend'/n)==h for n,h in report['source_hashes'].items()),limits='Seven fictional development cases; not the user workbook, a held-out benchmark or16 GB device test. Peak metrics overlap and must not be added.')
 reports.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');(run/'report.json').write_text(reports.read_text());print(report['passed'],report['total'])
 raise SystemExit(0 if report['passed']==report['total'] and report['source_hashes_unchanged'] else 1)
if __name__=='__main__':main()
