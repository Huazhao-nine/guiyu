"""Real local model repairs three injected bad drafts; separate from raw-model scores."""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
if '--isolated' not in sys.argv:
    result=subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),'--isolated'])
    raise SystemExit(result.returncode)

sys.path.insert(0,str(ROOT/'backend'))
import worker
import agent_control as control
import fact_guard
from office_agent import OfficeAgent
docs=[{'id':f'S{i+1}','name':p.name,'text':p.read_text()} for i,p in enumerate(sorted((ROOT/'fixtures/personal').glob('*.txt')))]
original={d['name']:hashlib.sha256(d['text'].encode()).hexdigest() for d in docs}
reference='\n\n'.join('【'+d['id']+'】'+d['name']+'\n'+d['text'] for d in docs)
cases=[
    {'id':'swapped_money','goal':'写一份简短费用说明，保留两份方案的正确金额。','bad':'梧桐空间450元，青禾客厅600元。【S1】【S2】'},
    {'id':'omitted_condition','goal':'写一份梧桐空间的取消说明，严格保留原文条件。','bad':'梧桐空间可以随时免费取消。【S1】'},
    {'id':'budget_conclusion','goal':'预算不超过500元，25人参加，必须有投影仪。写一份不放宽条件的选择说明。','bad':'推荐梧桐空间，600元，符合全部硬性要求。【S1】'},
]
report={'version':'0.9.0','date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'model_id':'gpt-oss-20b','fixture':'three explicitly injected incorrect fictional drafts','checks':{},'cases':[]}
report['checks']['network_denied']=worker.network_probe()['blocked'];assert report['checks']['network_denied']
model=worker.LocalModel(Path.home()/'Library/Application Support/GuiyuModels/Installed/gpt-oss-20b')
for case in cases:
    initial=fact_guard.check_writing(case['bad'],case['goal'],docs)
    assert initial['issues']
    with tempfile.TemporaryDirectory(prefix='guiyu-repair-') as temp:
        office=OfficeAgent(worker.Agent(model,Path(temp)),worker)
        # Inject only the initial tool draft. The actual controller, repair model,
        # validators, exports and evidence fallback execute without replacement.
        office.tool=lambda *args:{'text':case['bad'],'stats':{'finish_reason':'stop'},'artifacts':[],'_review_reference':reference}
        with redirect_stdout(io.StringIO()):
            plan=office.draft({'prompt':case['goal'],'paths':[str(ROOT/'fixtures/personal')],'kind':'write','adaptive':True})
            result=office.execute({'plan_id':plan['id'],'paths':plan['paths']})
        fixed=result['text'];grounded=result['plan'].get('grounded_delivery',False)
        artifacts=bool(result['artifacts']) and all(Path(a['path']).is_file() for a in result['artifacts'])
        step=result['plan']['steps'][0];events=result['plan']['events']
    final=fact_guard.check_writing(fixed,case['goal'],docs) if not grounded else {'issues':[]}
    compact=re.sub(r'\s','',fixed)
    independent=(('600' in fixed and '450' in fixed and '梧桐空间450元' not in compact and '青禾客厅600元' not in compact) if case['id']=='swapped_money' else ('提前48小时' in compact and '随时免费取消' not in compact) if case['id']=='omitted_condition' else any(s in fixed for s in ('均不满足','均不符合','均未能','无法同时','均不能','没有同时','无任何方案','没有方案','两份方案都不')) and not re.search(r'(?<!不)推荐(?:选择)?[**\s]*(?:梧桐|青禾)',fixed))
    passed=not final['issues'] and (grounded or independent) and case['bad'] not in fixed and artifacts and 2<=step['attempts']<=3
    report['cases'].append({'id':case['id'],'bad_draft':case['bad'],'initial_issues':initial['issues'],'delivered_text':fixed,'remaining_issues':final['issues'],'outcome':'grounded' if grounded else 'corrected','independent_check':independent,'attempts':step['attempts'],'check':step.get('check'),'activity':events,'artifacts_created':artifacts,'passed':passed})
    print('REPAIR',case['id'],passed,flush=True)
report['checks']['all_three_detected_and_safely_handled']=all(c['passed'] for c in report['cases'])
report['corrected_count']=sum(c['outcome']=='corrected' and c['passed'] for c in report['cases']);report['grounded_count']=sum(c['outcome']=='grounded' and c['passed'] for c in report['cases'])
report['checks']['fixture_hashes_unchanged']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'fixtures/personal').glob('*.txt')}==original
report['all_checks_passed']=all(report['checks'].values())
(ROOT/'qa/v0.9-repair-integration-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'all_checks_passed':report['all_checks_passed'],'checks':report['checks']},ensure_ascii=False))
raise SystemExit(0 if report['all_checks_passed'] else 1)
