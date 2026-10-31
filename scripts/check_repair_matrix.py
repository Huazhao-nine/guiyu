"""Paired real-model recovery tests, injecting only the first erroneous draft."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,io,json,re,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--backend',type=Path,default=ROOT/'backend');p.add_argument('--label',default='v0.9');p.add_argument('--isolated',action='store_true');args=p.parse_args()
if not args.isolated:raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),*sys.argv[1:],'--isolated']).returncode)
source_hashes_at_start={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.backend.glob('*.py')}
sys.path.insert(0,str(args.backend.resolve()))
import worker as core
from office_agent import OfficeAgent
import fact_guard
import mlx.core as mx
source=ROOT/'fixtures/personal';docs=[{'id':f'S{i+1}','name':f.name,'text':f.read_text()} for i,f in enumerate(sorted(source.glob('*.txt')))];reference='\n'.join('【'+d['id']+'】'+d['name']+'\n'+d['text'] for d in docs)
cases=[('money','写一份费用说明，保留两份方案的正确金额。','梧桐空间450元，青禾客厅600元。【S1】【S2】'),('condition','写一份梧桐空间取消说明，严格保留原文条件。','梧桐空间可以随时免费取消。【S1】'),('decision','预算不超过500元，25人参加，必须有投影仪。写一份选择说明，不放宽任何条件。','推荐梧桐空间，600元，符合全部要求。【S1】')]
r={'label':args.label,'date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'model_id':'gpt-oss-20b','protocol':'3 fixed initial faults x 2 seeds (101,102); only initial tool draft injected; real local review, repairs, exports and fallback','network_denied':core.network_probe()['blocked'],'cases':[]};assert r['network_denied']
model=core.LocalModel(Path.home()/'Library/Application Support/GuiyuModels/Installed/gpt-oss-20b')
for seed in (101,102):
 for identifier,goal,bad in cases:
  mx.random.seed(seed)
  with tempfile.TemporaryDirectory(prefix='guiyu-repair-matrix-') as temp:
   office=OfficeAgent(core.Agent(model,Path(temp)),core)
   office.tool=lambda *argv:{'text':bad,'stats':{'finish_reason':'stop'},'artifacts':[],'_review_reference':reference}
   with redirect_stdout(io.StringIO()):
    plan=office.draft({'prompt':goal,'paths':[str(source)],'kind':'write','adaptive':True});result=office.execute({'plan_id':plan['id'],'paths':plan['paths']})
   text=result['text'];flat=re.sub(r'[\s*]','',text);grounded=result['plan'].get('grounded_delivery',False)
   semantic=(all(re.search(name+r'[^。；\n]{0,12}'+amount+r'元',flat) for name,amount in (('梧桐空间','600'),('青禾客厅','450'))) if identifier=='money' else '提前48小时' in flat and '随时免费取消' not in flat if identifier=='condition' else bool(re.search(r'(?:无|没有|均不|都不|均无法|无法同时).{0,25}(?:满足|符合|方案)',flat)) and not re.search(r'(?<!不)推荐.{0,10}(?:梧桐|青禾)',flat))
   errors=fact_guard.check_writing(text,goal,docs)['issues'] if not grounded else []
   step=result['plan']['steps'][0]
   corrected=not grounded and semantic and not errors and step.get('check',{}).get('content_review')=='model'
   safe=(corrected or grounded) and bad not in text and all(Path(a['path']).is_file() for a in result['artifacts'])
   r['cases'].append({'id':identifier,'seed':seed,'initial_draft':bad,'delivered_text':text,'outcome':'corrected' if corrected else 'grounded' if grounded else 'unresolved','semantic_check':semantic,'remaining_program_issues':errors,'attempts':step['attempts'],'repair_history':step.get('repair_history',[]),'safe':safe})
   print('REPAIR_MATRIX',seed,identifier,r['cases'][-1]['outcome'],safe,flush=True)
r['corrected_count']=sum(c['outcome']=='corrected' for c in r['cases']);r['grounded_count']=sum(c['outcome']=='grounded' for c in r['cases']);r['case_count']=len(r['cases']);r['all_safely_handled']=all(c['safe'] for c in r['cases']);r['source_hashes']=source_hashes_at_start
(ROOT/'qa'/f'{args.label}-repair-matrix-report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:r[k] for k in ('case_count','corrected_count','grounded_count','all_safely_handled')}))
