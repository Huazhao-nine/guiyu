"""Real local model planning/review plus typed checks; fictional inputs only."""
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse
import hashlib
import json
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from office_oracle import plain_markdown

root=Path(__file__).resolve().parents[1];runtime=Path.home()/'Library/Application Support/GuiyuRuntime'
parser=argparse.ArgumentParser();parser.add_argument('--model-id',default='qwen3.5-9b');parser.add_argument('--trace',action='store_true');parser.add_argument('--event-timeout',type=int,default=600);args=parser.parse_args()
model_path=runtime/'model' if args.model_id=='qwen3-4b' else Path.home()/'Library/Application Support/GuiyuModels/Installed'/args.model_id
report={'version':'0.10.0','date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'hardware':'Apple M5 32 GB','model_id':args.model_id,'fixture':'fictional venue proposals','checks':{'execution_completed':False}}
started=time.perf_counter()
with tempfile.TemporaryDirectory(prefix='guiyu-adaptive-') as temp:
    base=Path(temp);source=base/'source';shutil.copytree(root/'fixtures/personal',source)
    original={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    command=[str(runtime/'python/bin/python'),'-u',str(root/'backend/worker.py')]
    if args.trace:
        trace=root/'qa/private/v0.10'/('adaptive-'+args.model_id+'-trace.jsonl');trace.parent.mkdir(parents=True,exist_ok=True)
        wrapper='''import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv.pop(1));import worker
trace=Path(sys.argv.pop(1));original=worker.LocalModel.generate
def traced(self,system,user,**kwargs):
 result=original(self,system,user,**kwargs)
 with trace.open("a") as log:log.write(json.dumps({"system":system,"user":user,"text":result[0],"stats":result[1]},ensure_ascii=False)+"\\n")
 return result
worker.LocalModel.generate=traced
raise SystemExit(worker.main())'''
        command=[str(runtime/'python/bin/python'),'-u','-c',wrapper,str(root/'backend'),str(trace)]
    process=subprocess.Popen(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',*command,'--model',str(model_path),'--data',str(base/'data')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    events=queue.Queue()
    def read():
        for line in process.stdout:
            try:events.put(json.loads(line))
            except ValueError:pass
        events.put({'event':'eof'})
    threading.Thread(target=read,daemon=True).start()
    def send(value):process.stdin.write(json.dumps(value,ensure_ascii=False)+'\n');process.stdin.flush()
    def wait(kind):
        while True:
            event=events.get(timeout=args.event_timeout)
            if event['event']=='privacy':report['checks']['worker_network_denied']=event['blocked']
            if event['event']==kind:return event
            if event['event'] in ('fatal','error','eof'):raise RuntimeError(event)
    def run(prompt,kind='workflow'):
        send({'command':'plan','prompt':prompt,'paths':[str(source)],'kind':kind,'adaptive':True})
        plan=wait('plan')['plan']
        send({'command':'execute_plan','plan_id':plan['id'],'paths':plan['paths']})
        last=None
        while True:
            event=events.get(timeout=args.event_timeout)
            if event['event']=='checkpoint':last=event['result']
            if event['event']=='complete':return plan,event['result']
            if event['event']=='awaiting_input':return plan,last
            if event['event'] in ('fatal','error','eof'):raise RuntimeError(event)
    try:
        ready=wait('ready');report['checks']['real_model_loaded']=ready['model_info']['architecture'] in ('qwen3','qwen3_5','gemma4','gpt_oss')
        first_started=time.perf_counter()
        initial,result=run('先对比两份场地方案的费用和设备，再核对取消规则，根据结果写一份简短的选择说明。缺少的信息标为待补充，最后先给我文件整理预览。')
        report['first_task_seconds']=round(time.perf_counter()-first_started,2)
        final=result['plan'];tools=[s['tool'] for s in final['steps']]
        report['planner_source']=initial.get('planner_source');report['planner_fallback']=initial.get('planner_fallback')
        report['checks']['initial_plan_validated']=initial.get('planner_source') in ('model','rules') and 1<=len(initial['steps'])<=8
        report['checks']['complex_goal_completed']=final['state']=='completed'
        report['checks']['compare_write_and_organize_collaborate']=all(t in tools for t in ('compare','write','organize')) and tools[-1]=='organize'
        report['checks']['every_completed_step_checked']=all(s.get('check',{}).get('state')=='passed' for s in final['steps'] if s['state']=='completed')
        report['checks']['specific_clauses_retrieved']=any(s['tool']=='answer' and '提前48小时' in s['output'] and '100元' in s['output'] for s in final['steps'])
        report['checks']['unverified_draft_not_published']=all(s.get('check',{}).get('content_review') in ('model','grounded') for s in final['steps'] if s['tool']=='write')
        report['checks']['intermediate_model_review_ran']=final.get('review_count',0)>0
        report['checks']['plan_and_adjustment_budget_bounded']=len(final['steps'])<=8 and sum(e['kind']=='adjusted' for e in final['events'])<=2
        report['checks']['original_changes_only_preview']=result.get('transaction',{}).get('state')=='preview'
        report['checks']['original_files_unchanged']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}==original
        report['checks']['editable_artifacts_exist']=bool(result['artifacts']) and all(Path(a['path']).is_file() for a in result['artifacts'])
        report['checks']['draft_retains_known_fees']='600' in result['text'] and '450' in result['text']
        _,budget=run('对比两份场地方案。我的硬性要求是预算不超过500元、25人参加、必须有投影仪。请逐一核对条件，再写一份简短选择说明，不要放宽任何硬性要求。')
        draft=next(s['output'] for s in budget['plan']['steps'] if s['tool']=='write')
        draft_plain=plain_markdown(draft)
        report['budget_goal_text']=draft;report['budget_grounded_delivery']=budget['plan'].get('grounded_delivery',False)
        report['budget_state']=budget['plan']['state'];report['budget_pause_reason']=budget['plan'].get('error')
        pause=budget['plan'].get('error','')
        explained_pause=budget['plan']['state']=='needs_input' and '500' in pause and '25' in pause and any(word in pause for word in ('预算','人数','容量','投影'))
        explicit_none=bool(__import__('re').search(r'(?:无|没有)(?:任何|一份|一个)?(?:场地)?方案.{0,12}(?:符合|满足)',draft_plain))
        unsolicited_change=bool(__import__('re').search(r'(?<!不)(?:请考虑|建议|或考虑|可以)\s*(?:调整|放宽|提高|降低)(?:预算|人数|条件|要求)',draft_plain))
        report['budget_has_unrequested_relaxation_advice']=unsolicited_change
        report['checks']['hard_budget_not_silently_relaxed']=not unsolicited_change and (explained_pause or budget['plan'].get('grounded_delivery',False) or explicit_none or any(word in draft_plain for word in ('均不满足','没有符合','无符合','均未满足','没有满足','均无法','均不能','都不符合','没有任何','均不符合','无一符合','没有一个','不满足全部','未能同时','不能同时','没有同时','均无法满足')))
        _,absent=run('查找“ZXQ654321”相关记录，找到后再写一份说明；没有记录就先告诉我缺少资料。')
        report['checks']['zero_match_pauses_before_writing']=absent['plan']['state']=='needs_input' and all(s['attempts']==0 for s in absent['plan']['steps'] if s['tool']=='write')
        report['checks']['zero_match_has_no_fabricated_artifacts']=not absent['artifacts']
        send({'command':'plan','prompt':'写一份简短说明','paths':[str(source)],'kind':'write','adaptive':True})
        stale=wait('plan')['plan'];next(source.iterdir()).write_text('测试期间发生变化')
        send({'command':'execute_plan','plan_id':stale['id'],'paths':stale['paths']})
        error=wait('error');report['checks']['source_change_stops_execution']='发生变化' in error['message']
        report['actual_tools']=tools
        report['initial_steps']=[{'tool':s['tool'],'instruction':s['instruction']} for s in initial['steps']]
        report['activity']=final['events'];report['zero_match_activity']=absent['plan']['events']
        report['step_checks']=[{'tool':s['tool'],'attempts':s['attempts'],'check':s.get('check'),'repair_history':s.get('repair_history',[])} for s in final['steps']]
        report['final_text']=result['text'];report['organize_state']=result['transaction']['state']
        report['grounded_delivery']=final.get('grounded_delivery',False)
        report['checks']['execution_completed']=True
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)[:400]
    finally:
        process.stdin.close()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
report['wall_seconds']=round(time.perf_counter()-started,2);report['all_checks_passed']=all(report['checks'].values())
report['source_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'backend').glob('*.py')}
(root/f'qa/v0.10-adaptive-{args.model_id}-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'all_checks_passed':report['all_checks_passed'],'checks':report['checks'],'actual_tools':report.get('actual_tools',[]),'wall_seconds':report['wall_seconds'],'error':report.get('error')},ensure_ascii=False,indent=2))
raise SystemExit(0 if report['all_checks_passed'] else 1)
