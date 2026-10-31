"""Production-adapter verification on frozen fictional text, CPU + deny-network.
Weights must already exist; never downloads or reads user documents.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from privacy_filter import preview
from privacy_models import detect,verify_component
CASES=[
 {'id':'zh_contact','text':'请联系张伟，电话13812345678，邮箱zhangwei@example.com。收货地址北京市海淀区中关村大街27号。','hide':['张伟','13812345678','zhangwei@example.com','北京市海淀区中关村大街27号']},
 {'id':'zh_office_contact','text':'负责人林晓，办公联系地址：上海市徐汇区漕溪北路88号。预算1280元，办公日期2026-10-31。','hide':['林晓','上海市徐汇区漕溪北路88号'],'keep':['1280元','2026-10-31']},
 {'id':'english_secret','text':'Contact Jane Doe at jane.doe@example.org. Server 10.0.3.17, api_key="q7Vt2LmX9pRk4sWz8bNc3yHd6fJg1aE5"','hide':['Jane Doe','jane.doe@example.org','q7Vt2LmX9pRk4sWz8bNc3yHd6fJg1aE5']},
 {'id':'office_values','text':'订单号202409301234567890，预算3600元，场地1200元，物料35元买24份，交通480元。活动日期2026-11-06，提前7天确认。','hide':[],'keep':['202409301234567890','3600元','1200元','35元','24份','480元','2026-11-06','7天']},
 {'id':'code_values','text':'version="0.13.0"\ntimeout=120\nrequest_id="c34dbe91-2345-45ef-9000-fb98219b0312"\namount=1280.50','hide':[],'exact':True},
 {'id':'private_dates_opt_in','text':'王芳的生日是1992年7月8日，护照有效期至2031-05-01。','hide':['王芳','1992年7月8日','2031-05-01'],'policy':{'categories':{'date':True}}},
 {'id':'names_opt_out','text':'请联系张伟，邮箱zhangwei@example.com。','hide':['zhangwei@example.com'],'keep':['张伟'],'policy':{'categories':{'person':False}}},
 {'id':'allow_full_value','text':'请联系张伟，邮箱zhangwei@example.com。','hide':['张伟'],'keep':['zhangwei@example.com'],'policy':{'allow':['zhangwei@example.com']}},
 {'id':'numeric_secrets','text':'密码=2026-10-31，password=1280元，预算3600元。','hide':['2026-10-31','1280元'],'keep':['3600元']},
 {'id':'custom_rule_fallback','text':'请联系林晓，暗号夜航灯，oc_sk_localSecret88。','hide':['林晓','夜航灯','oc_sk_localSecret88'],'policy':{'words':['林晓','夜航灯'],'prefixes':['oc_sk_']}},
 {'id':'boundary_long','text':'日常记录，无个人信息。'*80+'联系人张伟，邮箱zhangwei@example.com。'+'普通工作记录。'*70,'hide':['张伟','zhangwei@example.com']},
]
def main():
 p=argparse.ArgumentParser();p.add_argument('--model-id',required=True,choices=['astrlink-guard','openai-privacy-filter']);p.add_argument('--isolated',action='store_true');a=p.parse_args()
 if not a.isolated:
  raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,'-I',str(Path(__file__).resolve()),'--model-id',a.model_id,'--isolated']).returncode)
 import worker as core
 assert core.network_probe()['blocked']
 modelroot=ROOT/'qa/private/v0.14/models';item,_=verify_component(a.model_id,modelroot)
 # Adapter loads once per preview, as the app does; the production UI serializes
 # these one-shot processes. One evaluation process reuses ORT import only.
 rows=[];start=time.perf_counter()
 for c in CASES:
  t=time.perf_counter();r=preview({'text':c['text'],'detector':a.model_id,'policy':c.get('policy',{})},detector=lambda t,id:detect(t,id,root=modelroot))
  missing=[s for s in c['hide'] if s in r['text']];lost=[s for s in c.get('keep',[]) if s not in r['text']]
  passed=not missing and not lost and (not c.get('exact') or r['text']==c['text'])
  rows.append({'id':c['id'],'passed':passed,'missed':missing,'overmasked':lost,'seconds':round(time.perf_counter()-t,3),'output':r['text'],'component':r['component']});print(c['id'],passed,flush=True)
 result={'version':'0.14.0','source_hashes':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'backend').glob('privacy*.py')},'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'model_id':a.model_id,'revision':item['revision'],'hardware':'M5 32 GB; not a 16 GB machine test','network_denied':True,'passed':sum(r['passed'] for r in rows),'total':len(rows),'seconds':round(time.perf_counter()-start,3),'peak_process_rss_gb':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,3),'cases':rows,'limitations':['11 fictional developer cases, not held-out benchmark or anonymization guarantee.','Model categories postfiltered; office currency and dates protected; rules merged.','Windowed CPU adapters, not vendor complete runtime parity.','Per-preview app process exits; this evaluator process reuses runtime import.']}
 (ROOT/f'qa/v0.14-{a.model_id}-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='cases'},ensure_ascii=False))
if __name__=='__main__':main()
