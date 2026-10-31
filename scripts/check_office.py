"""Real-model office workflow checks on fictional inputs under OS network denial."""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time

root=Path(__file__).resolve().parents[1]
runtime=Path.home()/'Library/Application Support/GuiyuRuntime'
report={'version':'0.9.0','date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'hardware':'Apple M5 32 GB','fixture':'fictional office expenses','checks':{}}
started=time.perf_counter()
with tempfile.TemporaryDirectory(prefix='guiyu-office-') as temp:
    base=Path(temp);source=base/'expenses';shutil.copytree(root/'fixtures/office',source)
    worker=subprocess.Popen(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',str(runtime/'python/bin/python'),'-u',str(root/'backend/worker.py'),'--model',str(runtime/'model'),'--data',str(base/'data')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    events=queue.Queue()
    def read():
        for line in worker.stdout:
            try:events.put(json.loads(line))
            except ValueError:pass
        events.put({'event':'eof'})
    threading.Thread(target=read,daemon=True).start()
    def wait(kind):
        while True:
            event=events.get(timeout=120)
            if event['event'] in ('fatal','error','eof'):raise RuntimeError(event)
            if event['event']=='privacy':report['checks']['worker_network_denied']=event['blocked']
            if event['event']==kind:return event
    def send(value):worker.stdin.write(json.dumps(value,ensure_ascii=False)+'\n');worker.stdin.flush()
    def run(prompt,paths,kind='workflow',edits=None,history=None):
        send({'command':'plan','prompt':prompt,'paths':paths,'kind':kind,'history':history or []})
        plan=wait('plan')['plan'];report['checks']['draft_has_no_completed_steps']=all(s['state']=='pending' for s in plan['steps'])
        send({'command':'execute_plan','plan_id':plan['id'],'paths':plan['paths'],'steps':edits or []})
        return wait('complete')['result']
    try:
        wait('ready')
        result=run('查找这些费用资料，提取费用项目、金额和经办人成表格，统计金额的合计与平均值，再写一份报销简报。',[str(source)])
        steps=result['plan']['steps'];tools=[s['tool'] for s in steps]
        report['checks']['four_step_workflow']=tools==['search','table','statistics','write'] and all(s['state']=='completed' for s in steps)
        values=result['plan']['results']
        extracted=next(values[s['id']] for s in steps if s['tool']=='table')
        stats=next(values[s['id']] for s in steps if s['tool']=='statistics')
        report['checks']['three_original_records']=len(extracted['rows'])==3
        report['checks']['expense_sum_431_70']=any(row[2] in ('431.7','431.70') for row in stats['rows'])
        report['checks']['expense_mean_143_90']=any(row[3]=='143.90' for row in stats['rows'])
        report['checks']['writer_uses_verified_total']='431.7' in result['text'] or '431.70' in result['text']
        report['checks']['all_workflow_artifacts_exist']=len(result['artifacts'])==4 and all(Path(a['path']).is_file() for a in result['artifacts'])
        report['workflow']={'tools':tools,'steps':[{'tool':s['tool'],'seconds':s['seconds'],'summary':s['summary']} for s in steps], 'columns':extracted['columns'],'rows':extracted['rows'],'statistics':stats['rows'],'draft':result['text'],'artifacts':[a['name'] for a in result['artifacts']]}
        csv=base/'费用.csv';shutil.copy(root/'fixtures/statistics/费用明细.csv',csv)
        result=run('统计表格中的数值，核对合计与平均值。',[str(csv)])
        report['checks']['csv_statistics_without_extraction']=[s['tool'] for s in result['plan']['steps']]==['statistics']
        report['checks']['csv_sum_431_70']=any(r[2] in ('431.7','431.70') for r in result['rows'])
        report['csv']={'rows':result['rows'],'text':result['text']}
        result=run('帮我写一封礼貌的中文邮件，邀请同事周五参加30分钟的项目沟通会。地点和具体时间留为待补充。',[],kind='write')
        report['checks']['writing_without_sources']=len(result['artifacts'])==2 and '周五' in result['text'] and '待补充' in result['text']
        report['writing']={'text':result['text'],'artifacts':[a['name'] for a in result['artifacts']]}
    finally:
        worker.stdin.close()
        try:worker.wait(timeout=10)
        except subprocess.TimeoutExpired:worker.terminate();worker.wait(timeout=10)
report['wall_seconds']=round(time.perf_counter()-started,2)
report['all_checks_passed']=all(report['checks'].values())
(root/'qa/v0.9-office-integration-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'all_checks_passed':report['all_checks_passed'],'checks':report['checks'],'wall_seconds':report['wall_seconds']},ensure_ascii=False,indent=2))
raise SystemExit(0 if report['all_checks_passed'] else 1)
