"""End-to-end fictional share tasks using real local retrieval, chat and privacy models."""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
CASES=[
 {'id':'full_copy','detector':'astrlink-guard','prompt':'把客户跟进纪要.md整理成可分享版本，保留全部正文、预算和办公日期。'},
 {'id':'edited_mail','detector':'astrlink-guard','prompt':'把客户跟进纪要.md整理成可分享版本，写一份简短跟进邮件，保留预算、截止日期和尚未付款的条件，不要落款。'},
 {'id':'openai_copy','detector':'openai-privacy-filter','prompt':'把客户跟进纪要.md整理成可分享版本，保留正文。'},
]
TEXT='# 客户跟进纪要（虚构）\n\n联系人张伟，邮箱zhangwei@example.com，电话13812345678。\n联系地址北京市海淀区中关村大街27号。\n活动预算1280元，办公截止日期2026-10-31。费用尚未付款，先确认交付再安排付款。\napi_key=sk-proj-fictionalSecret123456789\n待办：核对物料清单，保持预算和截止日期。\n'
def main():
 p=argparse.ArgumentParser();p.add_argument('--isolated',action='store_true');a=p.parse_args()
 if not a.isolated:raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),'--isolated']).returncode)
 sys.path.insert(0,str(ROOT/'backend'));import worker as core
 from office_agent import OfficeAgent
 from workspace_index import WorkspaceIndex
 from bge_embedding import LocalEmbedder
 import mlx.core as mx
 from docx import Document
 run=ROOT/'qa/private/v0.15'/('share-'+uuid.uuid4().hex[:8]);run.mkdir(parents=True)
 model=core.LocalModel(Path.home()/'Library/Application Support/GuiyuModels/Installed/qwen3.5-9b')
 embed=LocalEmbedder(Path.home()/'Library/Application Support/GuiyuModels/Installed/bge-small-zh-v1.5',ROOT/'packaging/model-catalog.json')
 original_generate=model.generate
 def traced(system,user,**kw):
  value=original_generate(system,user,**kw)
  with (run/'model-trace.jsonl').open('a') as f:f.write(json.dumps({'system':system,'user':user,'output':value[0],'stats':value[1]},ensure_ascii=False)+'\n')
  return value
 model.generate=traced
 report={'version':'0.15.0','hardware':'M5 32 GB;16 GB target, not16 GB device test','network_denied':core.network_probe()['blocked'],'cases':[],'source_hashes':{p.name:core.digest(p) for p in (ROOT/'backend').glob('*.py')}}
 assert report['network_denied']
 for c in CASES:
  d=run/c['id'];d.mkdir();workspace=d/'workspace';workspace.mkdir();(workspace/'客户跟进纪要.md').write_text(TEXT);(workspace/'无关制度.md').write_text('公司午休制度：每日12:00至13:00。与客户纪要无关。')
  original={p.name:core.digest(p) for p in workspace.iterdir()};office=OfficeAgent(core.Agent(model,d/'data'),core);started=time.perf_counter();row={'id':c['id'],'checks':{}}
  try:
   with redirect_stdout(io.StringIO()):
    index=WorkspaceIndex(workspace,d/'index',embed);found=index.retrieve({'query':c['prompt'],'kind':'auto'})
    plan=office.draft({'id':uuid.uuid4().hex,'prompt':c['prompt'],'paths':found['paths'],'workspace_root':str(workspace),'retrieval':found,'adaptive':True,'privacy':{'detector':c['detector']}})
    result=office.execute({'plan_id':plan['id'],'paths':plan['paths'],'workspace_root':str(workspace)})
   (d/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
   bodies=[]
   for artifact in result['artifacts']:
    body='\n'.join(p.text for p in Document(artifact['path']).paragraphs) if artifact['type']=='docx' else Path(artifact['path']).read_text();bodies.append(body)
   row['checks']={'completed':result['plan']['state']=='completed','privacy_passed':result['share_check']['state']=='passed','all_three_formats':{x['type'] for x in result['artifacts']}=={'txt','md','docx'},'sensitive_values_absent':all(all(v not in body for v in ['张伟','zhangwei@example.com','13812345678','北京市海淀区中关村大街27号','sk-proj-fictionalSecret123456789']) for body in bodies),'office_budget_label_retained':c['id']=='edited_mail' or all('活动预算' in body for body in bodies),'budget_date_condition_retained':all(all(v in body for v in ['1280','2026-10-31','尚未付款']) for body in bodies),'no_original_filename_export':all('客户跟进纪要.md' not in body for body in bodies),'originals_unchanged':all(core.digest(workspace/n)==h for n,h in original.items()),'no_transaction':not result.get('transaction'),'entire_selected_sources_checked':result['share_check']['source_count']==len(result['sources']),'checked_same_preview_all_exports':all(result['text'].replace('#','').splitlines()[0].strip() in b for b in bodies),'editorial_completed':c['id']!='edited_mail' or result['share_check']['writing']=='edited'}
   row.update(output=result['text'],share_check=result['share_check'],source_names=[x['name'] for x in result['sources']],passed=all(row['checks'].values()))
  except Exception as e:row.update(passed=False,error=str(e))
  row['seconds']=round(time.perf_counter()-started,3);report['cases'].append(row);print(c['id'],row['passed'],row.get('error',''),flush=True)
 report.update(passed=sum(r['passed'] for r in report['cases']),total=len(CASES),peak_mlx_gb=round(mx.get_peak_memory()/1e9,3),peak_process_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,3),source_hashes_unchanged=all(core.digest(ROOT/'backend'/n)==h for n,h in report['source_hashes'].items()),limits='Three fictional development tasks. Per-detector child-process memory not included in parent RSS. No16GB device or independent user study.')
 (ROOT/'qa/v0.15-share-agent-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');(run/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(report['passed'],report['total'])
if __name__=='__main__':main()
