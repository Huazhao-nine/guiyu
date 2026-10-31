"""Run actual local-model integration on disposable fictional documents."""
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import shutil
import re
import subprocess
import tempfile
import time
import unittest

root=Path(__file__).resolve().parents[1]
runtime=Path.home()/'Library/Application Support/GuiyuRuntime'
report={'schema':1,'version':'0.9.0','date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'fixture':'fictional community activities','hardware':'Apple M5 32 GB','tests':{}}
started=time.time()
python=runtime/'python/bin/python'
probe=subprocess.run([str(python),str(root/'backend/worker.py'),'--model',str(runtime/'model'),'--data',str(root/'qa/private/unisolated'),'--probe-only'],capture_output=True,text=True,timeout=10)
report['tests']['fail_closed_without_sandbox']=probe.returncode==2 and 'fatal' in probe.stdout
native=subprocess.run([str(root/'dist/Guiyu.app/Contents/MacOS/Guiyu'),'--privacy-probe'],capture_output=True,text=True,timeout=10)
report['native_network_probe']=json.loads(native.stdout)
report['tests']['native_network_denied']=native.returncode==0
suite=subprocess.run([str(python),'-m','unittest','discover','-s',str(root/'tests'),'-v'],capture_output=True,text=True,timeout=30)
report['tests']['unit_suite']=suite.returncode==0
count=re.search(r'Ran (\d+) tests?',suite.stderr)
report['unit_test_count']=int(count[1]) if count else None
with tempfile.TemporaryDirectory(prefix='guiyu-integration-') as temp:
    data=Path(temp)
    selected=data/'selected'
    shutil.copytree(root/'fixtures/demo',selected)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in selected.iterdir()}
    worker=subprocess.Popen(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',str(python),'-u',str(root/'backend/worker.py'),'--model',str(runtime/'model'),'--data',str(data/'data')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    def event_until(kind):
        while True:
            line=worker.stdout.readline()
            if not line:raise RuntimeError('worker stopped')
            event=json.loads(line)
            if event['event'] in ('fatal','error'):raise RuntimeError(event)
            if event['event']==kind:return event
    def send(command):
        worker.stdin.write(json.dumps(command,ensure_ascii=False)+'\n');worker.stdin.flush()
    try:
        while True:
            e=json.loads(worker.stdout.readline())
            if e['event']=='privacy':report['worker_network_probe']=e;report['tests']['worker_network_denied']=e['blocked']
            if e['event']=='ready':break
            if e['event']=='fatal':raise RuntimeError(e)
        results={}
        for kind,prompt in [('table','把活动名称、时间、地点和负责人整理为表格，附出处。'),('summary','汇总活动安排、待办和明确待定的事项，附出处。'),('organize','按内容分类，起容易查找的中文文件名，先给方案。'),('answer','摄影志愿者要在什么时候落实？给出资料出处。')]:
            send({'command':'run','id':'integration-'+kind,'kind':kind,'paths':[str(selected)],'prompt':prompt})
            result=event_until('complete')['result'];results[kind]=result
            report[kind]={'stats':result['stats'],'text':result['text'],'rows':result['rows'],'columns':result['columns'],'artifacts':[a['name'] for a in result['artifacts']]}
        rows=results['table']['rows']
        report['tests']['table_two_events']=len(rows)==2 and all(any(name in str(row) for row in rows) for name in ['秋日社区读书会','数字生活公益工作坊'])
        report['tests']['table_artifact_created']=all(Path(a['path']).is_file() for a in results['table']['artifacts'])
        report['tests']['summary_artifact_created']=all(Path(a['path']).is_file() for a in results['summary']['artifacts'])
        report['tests']['answer_deadline_and_citation']='22' in results['answer']['text'] and 'S3' in results['answer']['text']
        tx=results['organize']['transaction']
        send({'command':'apply','transaction_id':tx['id'],'paths':[str(selected)]})
        applied=event_until('transaction')['transaction']
        report['tests']['organize_applied']=applied['state']=='applied' and all(Path(m['destination']).is_file() for m in applied['moves'])
        send({'command':'undo','transaction_id':tx['id']})
        undone=event_until('transaction')['transaction']
        after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in selected.iterdir() if p.is_file()}
        report['tests']['organize_undo_hashes']=undone['state']=='undone' and before==after
        report['organize']['categories']=[m['category'] for m in tx['moves']]
    finally:
        worker.stdin.close()
        try:worker.wait(timeout=10)
        except subprocess.TimeoutExpired:worker.terminate();worker.wait(timeout=5)
report['wall_seconds']=round(time.time()-started,2)
report['all_checks_passed']=all(report['tests'].values())
path=root/'qa/v0.9-direct-integration-report.json'
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'all_checks_passed':report['all_checks_passed'],'checks':report['tests'],'wall_seconds':report['wall_seconds']},ensure_ascii=False,indent=2))
raise SystemExit(0 if report['all_checks_passed'] else 1)
