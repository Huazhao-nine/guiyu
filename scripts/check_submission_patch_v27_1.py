"""Route, retrieve, plan, execute and inspect new local-office deliveries.

No grader values are supplied to any model or product tool. All stages keep
immutable reports and raw traces in independent fictional workspaces.
"""
import argparse,csv,hashlib,io,json,re,resource,shutil,subprocess,sys,time,uuid
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from check_primary_model_v25 import equal_rows
from regrade_submission_v27 import canonical_dates
ROOT=Path(__file__).resolve().parents[1]

def client_followup(prompt,parent):
    # Same existing client contract as WorkbookFollowupIntent.requiresSource.
    if not parent or not any(s.get('tool')=='workbook' for s in parent.get('plan',{}).get('steps',[])):return False
    if re.search(r'另外|另一个|另一份|换.{0,4}(文件|工作簿|资料|数据源)|不沿用|不要沿用',prompt):return False
    return bool(re.search(r'(其他|其它|其余|原有|原来).{0,30}(不变|照旧|保持)|(上轮|上次|刚才|这批|这些|当前).{0,8}(结果|筛选|明细|条件|表格|工作簿|资料)|原始(数据|明细|记录).{0,4}(重算|重做)|沿用.{0,4}(上轮|原有|之前)',prompt) and re.search(r'改|调整|放宽|收紧|保留|筛|排序|分组|汇总|统计|导出|加上|去掉|去重|只留|只要|选择|重算|重做',prompt))

def main():
    p=argparse.ArgumentParser();p.add_argument('--isolated',action='store_true');p.add_argument('--group',choices=['submission'],default='submission');p.add_argument('--label',required=True);p.add_argument('--case',choices=['transfer_office_notice'],default='transfer_office_notice');args=p.parse_args()
    assert re.fullmatch(r'[a-z0-9-]{1,50}',args.label)
    if not args.isolated:
        raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),'--isolated','--group',args.group,'--label',args.label,'--case',args.case]).returncode)
    sys.path.insert(0,str(ROOT/'backend'));import worker as core
    from office_agent import OfficeAgent
    from request_router import RequestRouter
    from workspace_index import WorkspaceIndex
    from bge_embedding import LocalEmbedder
    from workbook_export import read_cells
    from openpyxl import load_workbook
    from docx import Document
    import mlx.core as mx
    mx.random.seed(20261030)
    source=ROOT/'fixtures/submission_v27';suite=json.loads((source/'tasks.json').read_text());cases=[c for c in suite['cases'] if c['group']==args.group and c['id']==args.case]
    names={n for c in cases for n in c.get('files',[])} | {'支持日志.xlsx','客户跟进纪要.md'}
    stamp=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6];run=ROOT/'qa/private/v0.27.1'/stamp;workspace=run/'workspace';workspace.mkdir(parents=True)
    for n in names:shutil.copy2(source/'workspace'/n,workspace/n)
    frozen={n:core.digest(workspace/n) for n in names};target=ROOT/'qa/v0.27.1/reports'/f'{args.label}-{stamp}.json';target.parent.mkdir(parents=True,exist_ok=True)
    report={'version':'0.27.1','label':args.label,'group':args.group,'hardware':'Apple M5 32GB','model':'qwen3.6-35b-a3b','seed':20261030,'network_denied':core.network_probe()['blocked'],'backend_hashes':{p.name:core.digest(p) for p in (ROOT/'backend').glob('*.py')},'runner_sha256':core.digest(Path(__file__)),'client_contract_sha256':core.digest(ROOT/'Sources/Guiyu/AgentModels.swift'),'fixture_hashes':frozen,'tasks_sha256':core.digest(source/'tasks.json'),'cases':[]}
    validation=json.loads((source/'validation.json').read_text()) if (source/'validation.json').exists() else {}
    report['validation_sha256']=core.digest(source/'validation.json') if validation else None
    assert report['network_denied'];started=time.perf_counter();model=core.LocalModel(Path.home()/'Library/Application Support/GuiyuModels/Research/qwen3.6-35b-a3b');report['load_seconds']=round(time.perf_counter()-started,2);report['runtime_policy']=model.policy.object()
    embed=LocalEmbedder(Path.home()/'Library/Application Support/GuiyuModels/Installed/bge-small-zh-v1.5',ROOT/'packaging/model-catalog.json')
    office=OfficeAgent(core.Agent(model,run/'data'),core);router=RequestRouter(office.agent,core);index=WorkspaceIndex(workspace,run/'index',embed)
    original=model.generate;current='';calls=[];saved={}
    def generate(system,user,**kw):
        result=original(system,user,**kw);calls.append({'case':current,'stats':result[1]})
        with (run/'model-trace.jsonl').open('a') as f:f.write(json.dumps({'case':current,'system':system,'user':user,'kwargs':kw,'output':result[0],'stats':result[1]},ensure_ascii=False)+'\n')
        return result
    model.generate=generate
    for case in cases:
        current=case['id'];t=time.perf_counter();begin=len(calls);row={'id':current,'prompt':case['prompt']};parent=saved.get(case.get('parent'));conversation=saved.get(case.get('conversation_parent')) or parent;events=io.StringIO()
        try:
            if case.get('parent') and not parent:raise ValueError('Parent task failed; no fabricated source lineage.')
            history=[]
            if parent:history+=[{'role':'user','text':parent['prompt'][:1500]},{'role':'assistant','text':parent['text'][:2500]}]
            if conversation and conversation!=parent:history+=[{'role':'user','text':conversation['prompt']},{'role':'assistant','text':conversation['text']}]
            request={'id':str(uuid.uuid4()),'prompt':case['prompt'],'kind':'auto','history':history,'workspace_available':True,'files_selected':False,'adaptive':True,'workbook_mode':'flow','workspace_root':str(workspace)}
            if parent:request.update(thread_id=parent['thread_id'],parent_id=parent['id'],previous_source={'prompt':parent['prompt'],'query':parent.get('query_summary','')})
            if conversation:request['conversation_parent_id']=conversation['id']
            with redirect_stdout(events):
                decision={'mode':'workspace','use_previous':True,'source':'native_workbook_followup'} if client_followup(case['prompt'],parent) else router.decide(request)
                row['routing']=decision
                if case.get('chat'):
                    if decision['mode']!='chat':raise ValueError('Source-free conversation was not routed to chat.')
                    result=router.chat(request)
                else:
                    if decision['mode']!='workspace':raise ValueError('Source task routed to '+decision['mode'])
                    retrieval_request={'query':case['prompt'],'kind':'auto'}
                    if parent and decision['use_previous']:
                        prior=office.get(parent['plan']['id']);retrieval_request.update(previous={'snapshots':prior['snapshot'],'retrieval':prior.get('retrieval') or {'query':prior['prompt']}},continue_previous=True)
                    else:request.pop('parent_id',None)
                    found=index.retrieve(retrieval_request);request.update(paths=found['paths'],retrieval=found,source_required=True,privacy={'detector':'astrlink-guard'})
                    if not found.get('reuse'):request.pop('parent_id',None)
                    plan=office.draft(request);result=office.execute({'plan_id':plan['id'],'paths':plan['paths'],'workspace_root':str(workspace)})
            (run/(current+'-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');saved[current]=result
            if case.get('chat'):
                checks={'chat_route':decision['mode']=='chat','no_sources':not result['sources'],'nonempty':len(result['text'].strip())>4};row['text']=result['text']
            else:
                words=[a for a in result['artifacts'] if a['type']=='docx'];word_text='\n'.join(t for a in words for t in ([p.text for p in Document(a['path']).paragraphs]+[' | '.join(c.text for c in r.cells) for tb in Document(a['path']).tables for r in tb.rows]));numeric=re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))','',word_text)
                checks={'completed':result['plan']['state']=='completed','checked':result['plan'].get('completion_check',{}).get('state')=='passed','no_grounded_fallback':not result['plan'].get('grounded_delivery'),'word_requested':not case.get('word') or bool(words),'no_unrequested_word':case.get('word') or not words,'no_original_mutation':not result.get('transaction'),'originals_unchanged':all(core.digest(workspace/n)==h for n,h in frozen.items())}
                row.update(word_text=word_text,tools=[s['tool'] for s in result['plan']['steps']],source_names=[s['name'] for s in result['sources']])
                if case.get('kind')=='share':
                    bodies=[Path(a['path']).read_text() for a in result['artifacts'] if a['type'] in ('txt','md')]+[word_text]
                    checks.update(privacy_passed=result.get('share_check',{}).get('state')=='passed',all_three_formats={a['type'] for a in result['artifacts']}=={'txt','md','docx'},sensitive_values_absent=all(all(v not in body for v in case['sensitive_values']) for body in bodies),office_values_retained=all(all(v in body for v in case['retained_values']) for body in bodies),checked_source_count=result.get('share_check',{}).get('source_count')==len(result['sources']))
                    row['share_check']=result.get('share_check')
                elif case.get('kind')=='office':
                    checks.update(numbers=all(re.search(r'(?<![\d.])'+re.escape(n)+r'(?:\.0+)?(?![\d.])',numeric) for n in case.get('numbers',[])),dates=not case.get('dates') or any(canonical_dates(d) in canonical_dates(word_text) for d in case['dates']),patterns=all(re.search(pat,word_text) for pat in case.get('patterns',[])),condition=not case.get('required_condition') or any(p in word_text for p in case['required_condition']))
                else:
                    data=next(r for r in result['plan']['results'].values() if 'workbook_check' in r);xlsx=next(a['path'] for a in data['artifacts'] if a['type']=='xlsx');b=load_workbook(xlsx,read_only=True,data_only=False)
                    try:matrix=read_cells(b,'处理结果')
                    finally:b.close()
                    csvpath=next(a['path'] for a in data['artifacts'] if a['type']=='csv')
                    with open(csvpath,encoding='utf-8-sig',newline='') as f:csvmatrix=list(csv.reader(f))
                    summary=data['result_table'].get('summaries',[]);values=[str(v) for s in summary for r in s['rows'] for v in r]
                    checks.update(expected_rows=equal_rows(matrix[1:],case['rows']),expected_columns=[re.sub(r'[（(][^）)]*[）)]|\s','',c) for c in matrix[0]]==case['columns'],preview_matches_xlsx=matrix==[data['columns']]+data['rows'],csv_matches_xlsx=csvmatrix==matrix,summary_values=all(str(v) in values for v in case.get('summary_values',[])),word_values=all(re.search(r'(?<![\d.])'+re.escape(str(v))+r'(?:\.0+)?(?![\d.])',numeric) for v in case.get('word_numbers',[])))
                    row.update(rows=matrix[1:],columns=matrix[0],summaries=summary,graph=result['plan']['workbook']['flow']['graph'],repairs=result['plan']['workbook']['repairs'],revision=result['plan']['workbook']['flow']['contract'].get('revision'))
            checks['all_required_dates']=all(re.search(canonical_dates(pat),canonical_dates(word_text)) for pat in validation.get(case['id'],{}).get('required_dates_all',[])) if not case.get('chat') else True
            row.update(checks=checks,passed=all(checks.values()))
        except Exception as exc:row.update(passed=False,error=str(exc)[:1400],dependency_blocked=bool(case.get('parent') and not parent))
        (run/(current+'-events.jsonl')).write_text(events.getvalue());row.update(seconds=round(time.perf_counter()-t,2),model_calls=len(calls)-begin,model_executed=len(calls)>begin);report['cases'].append(row);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(current,row['passed'],row.get('error',''),flush=True)
    report.update(passed=sum(c['passed'] for c in report['cases']),total=len(cases),peak_mlx_gb=round(mx.get_peak_memory()/1e9,3),peak_process_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,3),backend_unchanged=all(core.digest(ROOT/'backend'/n)==h for n,h in report['backend_hashes'].items()),limits='Developer-authored tasks using public structures and fictional records; all fictional source documents. Separate routing, BGE retrieval and typed tools. Native followup client contract mirrored and hashed. No GUI execution or real-user validation.')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');(run/'report.json').write_text(target.read_text());print(json.dumps({'passed':report['passed'],'total':report['total'],'report':str(target.relative_to(ROOT))}));raise SystemExit(0 if report['passed']==report['total'] and report['backend_unchanged'] else 1)

if __name__=='__main__':main()
