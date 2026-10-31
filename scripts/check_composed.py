"""Frozen mixed local retrieval/calculation/calendar/writing development cases."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import io
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--isolated',action='store_true');args=parser.parse_args()
    if not args.isolated:
        raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),'--isolated']).returncode)
    sys.path.insert(0,str(ROOT/'backend'))
    import worker as core
    from office_agent import OfficeAgent
    from workspace_index import WorkspaceIndex
    from bge_embedding import LocalEmbedder
    import mlx.core as mx
    suite_path=ROOT/'fixtures/composed/tasks.json';suite=json.loads(suite_path.read_text())
    run=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
    private=ROOT/'qa/private/v0.13'/run;private.mkdir(parents=True)
    report={'version':'0.13.0','date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'run':run,'hardware':'Apple M5 32 GB; standard16 GB policy, not16 GB hardware validation','model':'qwen3.5-9b','network_denied':core.network_probe()['blocked'],'fixture_sha256':core.digest(suite_path),'source_hashes':{p.name:core.digest(p) for p in (ROOT/'backend').glob('*.py')},'cases':[]}
    assert report['network_denied']
    output=ROOT/'qa/v0.13-composed-report.json'
    if output.exists():shutil.copy2(output,private/'previous-report.json')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    model=core.LocalModel(Path.home()/'Library/Application Support/GuiyuModels/Installed/qwen3.5-9b')
    original=model.generate;current=''
    def generate(system,user,**kw):
        value=original(system,user,**kw)
        with (private/'model-trace.jsonl').open('a') as f:f.write(json.dumps({'case':current,'system':system,'user':user,'output':value[0],'stats':value[1]},ensure_ascii=False)+'\n')
        return value
    model.generate=generate
    embed=LocalEmbedder(Path.home()/'Library/Application Support/GuiyuModels/Installed/bge-small-zh-v1.5',ROOT/'packaging/model-catalog.json')
    report['runtime_policy']=model.policy.object()
    for case in suite['cases']:
        current=case['id'];mx.random.seed(91);case_dir=private/current;case_dir.mkdir();workspace=case_dir/'workspace';workspace.mkdir()
        for name in case['files']:shutil.copy2(ROOT/'fixtures/composed/workspace'/name,workspace/name)
        frozen={str(p.relative_to(workspace)):core.digest(p) for p in workspace.iterdir()}
        office=OfficeAgent(core.Agent(model,case_dir/'data'),core);index=WorkspaceIndex(workspace,case_dir/'index',embed)
        row={'id':current,'prompt':case['prompt'],'checks':{}};started=time.perf_counter()
        try:
            with redirect_stdout(io.StringIO()):
                found=index.retrieve({'query':case['prompt'],'kind':'auto'})
                plan=office.draft({'prompt':case['prompt'],'paths':found['paths'],'workspace_root':str(workspace),'retrieval':found,'kind':'auto','adaptive':True})
                plan['clock']['today']=suite['clock'];office.save(plan)
                result=office.execute({'plan_id':plan['id'],'paths':plan['paths'],'workspace_root':str(workspace)})
            (case_dir/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            from docx import Document
            docx=[a for a in result['artifacts'] if a['type']=='docx']
            text='\n'.join(p.text for a in docx for p in Document(a['path']).paragraphs)
            numeric_text=re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))','',text)
            tools=[s['tool'] for s in result['plan']['steps'] if s['state']=='completed']
            row['checks']={'completed':result['plan']['state']=='completed','no_grounded_fallback':not result['plan'].get('grounded_delivery'),'all_required_tools':set(case['tools'])<=set(tools),'word_delivered':len(docx)>=case['minimum_docx'],'verified_numbers_in_word':all(re.search(r'(?<![\d.])'+re.escape(n)+r'(?:\.0+)?(?![\d.])',numeric_text) for n in case['numbers']),'date_in_word':any(d in re.sub(r'\s','',text) for d in case['dates']),'condition_preserved':not case.get('required_condition') or any(c in text for c in case['required_condition']) or bool(re.search(r'(?:尚未|未|不表示|不代表)[^。；\n]{0,10}(?:付款|支付)',text)),'delivery_check_passed':result['plan'].get('completion_check',{}).get('state')=='passed','no_original_file_transaction':not result.get('transaction'),'original_files_unchanged':all(core.digest(workspace/p)==h for p,h in frozen.items()),'bounded_steps':len(result['plan']['steps'])<=8}
            row.update(tools=tools,planner=result['plan'].get('planner_source'),steps=[{'tool':s['tool'],'state':s['state'],'adaptive_added':s.get('adaptive_added',False),'summary':s['summary']} for s in result['plan']['steps']],text=result['text'],word_text=text,source_names=[s['name'] for s in result['sources']],events=result['plan'].get('events',[]))
            row['passed']=all(row['checks'].values())
        except Exception as e:
            row.update(passed=False,error=str(e)[:700]);(case_dir/'error.txt').write_text(str(e))
        row['seconds']=round(time.perf_counter()-started,2);report['cases'].append(row)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(current,row['passed'],row.get('error',''),flush=True)
    report.update(passed=sum(r['passed'] for r in report['cases']),total=len(report['cases']),peak_mlx_gb=round(mx.get_peak_memory()/1e9,3),peak_process_rss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,3),source_hashes_unchanged=all(core.digest(ROOT/'backend'/name)==h for name,h in report['source_hashes'].items()),limits='Three fixed developer tasks, no held-out benchmark,16GB device or real user study. Model traces and generated files preserved privately.')
    report['all_checks_passed']=report['passed']==report['total'] and report['source_hashes_unchanged']
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');(private/'report.json').write_text(output.read_text())
    print(json.dumps({k:report[k] for k in ('passed','total','peak_mlx_gb','all_checks_passed')}))
    raise SystemExit(0 if report['all_checks_passed'] else 1)


if __name__=='__main__':main()
