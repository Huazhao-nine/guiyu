"""Exercise comparison, writing, explicit preferences and grounded questions with real offline Qwen."""
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
report={'version':'0.9.0','date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'hardware':'Apple M5 32 GB','fixture':'fictional venue proposals and fictional person record','checks':{}}
started=time.perf_counter()
with tempfile.TemporaryDirectory(prefix='guiyu-personal-') as temp:
    base=Path(temp);source=base/'proposals';shutil.copytree(root/'fixtures/personal',source)
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
            event=events.get(timeout=180)
            if event['event'] in ('fatal','error','eof'):raise RuntimeError(event)
            if event['event']=='privacy':report['checks']['worker_network_denied']=event['blocked']
            if event['event']==kind:return event
    def send(value):worker.stdin.write(json.dumps(value,ensure_ascii=False)+'\n');worker.stdin.flush()
    def run(prompt,paths,parent=None,kind='auto',prefs=None):
        req={'command':'plan','prompt':prompt,'paths':paths,'kind':kind,'preferences':prefs or {}}
        if parent:req.update(parent_id=parent['id'],history=[{'role':'user','text':parent['prompt']},{'role':'assistant','text':parent['text']}])
        send(req);plan=wait('plan')['plan']
        send({'command':'execute_plan','plan_id':plan['id'],'paths':plan['paths']})
        return wait('complete')['result']
    try:
        ready=wait('ready');report['checks']['real_qwen_model_loaded']=ready['model_info']['architecture']=='qwen3'
        prefs={'enabled':True,'tone':'正式简洁','length':'简短','notes':'先给结论，使用清楚的中文，不要客套。'}
        result=run('对比这两份场地方案的费用、可用时间和设备，按维度保留原文出处，再写一份简短的选择说明。',[str(source)],prefs=prefs)
        plan=result['plan'];comparison=plan['results']['step-1']
        report['checks']['compare_then_write_plan']=[s['tool'] for s in plan['steps']]==['compare','write']
        evidence=comparison['comparison']['evidence'];docs={p.name:p.read_text() for p in source.glob('*.txt')}
        names={s['id']:s['name'] for s in result['sources']}
        report['checks']['every_comparison_quote_matches_source']=bool(evidence) and all(e['quote'] in docs[names[e['source_id']]] for e in evidence)
        report['checks']['comparison_has_fees_time_equipment']=len(comparison['rows'])==3 and '600' in comparison['text'] and '450' in comparison['text'] and '投影' in comparison['text'] and '14:00' in comparison['text'] and '09:00' in comparison['text']
        report['checks']['source_line_numbers_present']=all(e['line']>=2 for e in evidence) and '第' in comparison['text']
        report['checks']['write_uses_both_proposals']='600' in plan['results']['step-2']['text'] and '450' in plan['results']['step-2']['text']
        report['checks']['four_editable_artifacts']=len(result['artifacts'])==4 and all(Path(a['path']).is_file() for a in result['artifacts'])
        report['checks']['explicit_preferences_saved_in_plan']=plan['preferences']==prefs and plan['preference_summary']=='正式简洁 · 简短'
        revised=run('请修改上一轮文稿：只写一段不超过150字的选择说明，保留两份方案的费用和出处。',[str(source)],parent=result,kind='write',prefs=prefs)
        report['checks']['continue_original_task_keeps_thread']=revised['thread_id']==result['thread_id'] and revised['parent_id']==result['id']
        report['checks']['continued_draft_retains_facts']='600' in revised['text'] and '450' in revised['text'] and 'S1' in revised['text'] and 'S2' in revised['text']
        facts=base/'虚构人员.txt';facts.write_text('【虚构测试资料】\n姓名：周禾。\n任务：准备读书会资料。\n截止时间：10月24日。\n')
        answer=run('请详细说明周禾的任务与截止时间，只依据资料，不推断其他个人信息。',[str(facts)],kind='answer')
        ae=answer['plan']['results']['step-1']['evidence']
        report['checks']['source_answer_only_publishes_exact_quotes']=bool(ae) and all(e['quote'] in facts.read_text() for e in ae) and '10月24日' in answer['text']
        report['checks']['answer_has_no_inferred_background']=not any(s in answer['text'] for s in ['入学','硕士','导师','符合','预计'])
        report['checks']['no_sources_still_supports_general_writing']=bool(run('起草一封礼貌的中文邮件，邀请朋友周六一起读书，地点时间待补充。',[],kind='write',prefs=prefs)['artifacts'])
        report['comparison']={'columns':comparison['columns'],'rows':comparison['rows'],'evidence':evidence}
        report['writing']=plan['results']['step-2']['text'];report['continued_draft']=revised['text'];report['grounded_answer']=answer['text']
    finally:
        worker.stdin.close()
        try:worker.wait(timeout=10)
        except subprocess.TimeoutExpired:worker.terminate();worker.wait(timeout=10)
report['wall_seconds']=round(time.perf_counter()-started,2)
report['all_checks_passed']=all(report['checks'].values())
(root/'qa/v0.9-personal-integration-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'all_checks_passed':report['all_checks_passed'],'checks':report['checks'],'wall_seconds':report['wall_seconds']},ensure_ascii=False,indent=2))
raise SystemExit(0 if report['all_checks_passed'] else 1)
