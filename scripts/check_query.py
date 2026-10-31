"""Actual offline-model checks for search scope, predicates, grouping and follow-ups."""
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
report={'version':'0.9.0','date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'hardware':'Apple M5 32 GB','fixture':'fictional query ledger and office expenses','checks':{}}
started=time.perf_counter()
with tempfile.TemporaryDirectory(prefix='guiyu-query-') as temp:
    base=Path(temp);source=base/'office';shutil.copytree(root/'fixtures/office',source)
    ledger=base/'台账.csv';shutil.copy(root/'fixtures/query/社区费用台账.csv',ledger)
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
    def run(prompt,paths,parent=None,kind='auto',query=None,history=None):
        request={'command':'plan','prompt':prompt,'paths':paths,'kind':kind}
        if parent:request['parent_id']=parent['id']
        if query is not None:request['query']=query
        if history is not None:request['history']=history
        send(request);plan=wait('plan')['plan']
        send({'command':'execute_plan','plan_id':plan['id'],'paths':plan['paths']})
        return wait('complete')['result']
    try:
        ready=wait('ready');report['model']={k:v for k,v in ready['model_info'].items() if k!='path'}
        report['checks']['actual_local_model_identified']=ready['model_info']['architecture']=='qwen3'
        found=run('查找“交通”相关资料，列出原文与出处。',[str(source)],kind='search')
        report['checks']['search_only_matching_document']=len(found['search_hits'])==1 and found['search_hits'][0]['name']=='03_交通费用.txt'
        search_followup=run('把找到的资料写成一段不超过100字的说明，保留出处。',[str(source)],found,kind='write')
        report['checks']['search_scope_survives_followup']=len(search_followup['sources'])==1 and search_followup['sources'][0]['name']=='03_交通费用.txt' and '43.2' in search_followup['text'] and '260' not in search_followup['text']
        absent=run('查找“完全不存在的词”相关资料。',[str(source)],kind='search')
        report['checks']['zero_search_has_no_fallback']=absent['search_hits']==[] and '没有匹配' in absent['text']
        scoped=run('查找“交通”相关资料，提取费用项目、金额和经办人成表格，统计金额合计。',[str(source)])
        report['checks']['search_limits_later_tools']=len(scoped['plan']['query_state']['base_table']['rows'])==1 and '43.2' in scoped['text'] and '431.7' not in scoped['text']
        first=run('只统计状态包含待报销且金额大于100元，按经办人分组统计。',[str(ledger)])
        report['checks']['two_filtered_rows']=len(first['plan']['results']['step-1']['rows'])==2
        report['checks']['grouped_exact_sums']=sorted(r[3] for r in first['rows'])==['128.5','180']
        second=run('那陈雨呢？',[str(ledger)],first)
        report['checks']['followup_reuses_raw_table']=second['plan']['reused_table'] and len(second['plan']['query_state']['base_table']['rows'])==6
        report['checks']['followup_preserves_other_conditions']=len(second['plan']['query']['filters'])==3 and len(second['rows'])==1 and second['rows'][0][3]=='180'
        third=run('清除筛选，取消分组，统计全部记录。',[str(ledger)],second)
        report['checks']['reset_restores_all_rows']=third['rows'][0][2]=='709'
        report['checks']['thread_identity_preserved']=first['thread_id']==second['thread_id']==third['thread_id']
        empty=run('只统计金额大于9999元。',[str(ledger)],third)
        report['checks']['zero_filtered_rows_are_explicit']=empty['rows']==[] and '没有匹配记录' in empty['text']
        old_history=[{'role':'user','text':first['prompt']},{'role':'assistant','text':first['text']},{'role':'user','text':third['prompt']},{'role':'assistant','text':third['text']}]
        written=run('把本轮筛选与统计结果写成一段不超过200字的费用说明，附出处。',[str(ledger)],second,kind='write',history=old_history)
        report['checks']['write_uses_current_filtered_result']='180' in written['text'] and len(written['artifacts'])==2
        report['checks']['old_turn_numbers_excluded_from_draft']='林晓' not in written['text'] and '709' not in written['text'] and '128.5' not in written['text']
        answer=run('这笔费用由谁经办，金额多少？给出出处。',[str(ledger)],written,kind='answer')
        report['checks']['followup_answer_uses_active_rows']='陈雨' in answer['text'] and '180' in answer['text'] and 'S1' in answer['text']
        explicit=run('按设置的条件统计。',[str(ledger)],query={'filters':[{'column':'经办人','operator':'eq','value':'林晓'}],'group_by':[],'match':'all','metrics':['金额（元）']})
        report['checks']['panel_query_is_applied']=explicit['rows'][0][2]=='225.8'
        report['checks']['query_artifacts_created']=all(Path(a['path']).is_file() for result in (first,second,third,empty,written) for a in result['artifacts'])
        report['results']={'search':[{'name':h['name'],'line':h['line'],'snippet':h['snippet']} for h in found['search_hits']], 'filtered':first['rows'],'followup':second['rows'],'all_rows':third['rows'],'zero':empty['text'],'writing':written['text'],'answer':answer['text'],'panel':explicit['rows']}
    finally:
        worker.stdin.close()
        try:worker.wait(timeout=10)
        except subprocess.TimeoutExpired:worker.terminate();worker.wait(timeout=10)
report['wall_seconds']=round(time.perf_counter()-started,2)
report['all_checks_passed']=all(report['checks'].values())
(root/'qa/v0.9-query-integration-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'all_checks_passed':report['all_checks_passed'],'checks':report['checks'],'wall_seconds':report['wall_seconds']},ensure_ascii=False,indent=2))
raise SystemExit(0 if report['all_checks_passed'] else 1)
