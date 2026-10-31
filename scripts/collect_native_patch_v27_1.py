"""Inspect isolated fictional native results; never operate the UI or normal data."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from docx import Document
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def word_text(path):
    document=Document(path)
    return '\n'.join([p.text for p in document.paragraphs]+[
        ' | '.join(c.text for c in row.cells) for table in document.tables for row in table.rows])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finalize',action='store_true')
    args=parser.parse_args()
    private=ROOT/'qa/private/v0.27.1'
    setup=json.loads((private/'setup.json').read_text())
    assert setup['bundle_id']=='org.guiyu.qa.v271z'
    assert 'guiyu-native-v0.27-' in setup['data']
    workspace=Path(setup['data'])/'Workspaces'/setup['workspace_id']
    before=set(json.loads((private/'before-final-run.json').read_text())['before_ids'])
    history=[r for r in json.loads((workspace/'history.json').read_text()) if r['id'] not in before]
    expected=json.loads((ROOT/'qa/v0.27/native-retest/initial-evaluation.json').read_text())['cases']
    protocol=json.loads((ROOT/'qa/v0.27.1/protocol.json').read_text())
    assert setup['backend_hashes']==protocol['backend_hashes']=={p.name:sha(p) for p in (ROOT/'backend').glob('*.py')}
    cases=[]
    ids={}
    for prior in expected:
        name=prior['case']
        matches=[r for r in history if r['prompt']==prior['prompt']]
        if not matches:continue
        assert len(matches)==1,(name,'Multiple final-stage attempts must be reported separately.')
        record=matches[0];identifier=record['id'];ids[name]=identifier
        task=workspace/'Outputs'/identifier/'task.json'
        if not task.exists():continue
        result=json.loads(task.read_text())
        plan=result.get('plan') or {}
        if plan and plan.get('state')!='completed':
            cases.append({'case':name,'id':identifier,'passed':False,'state':plan['state']});continue
        sources=result.get('sources',[])
        for source in sources:
            path=Path(source['path'])
            assert sha(path)==sha(ROOT/'fixtures/submission_v27/workspace'/path.name)
        directory=ROOT/'qa/v0.27.1/outputs'/name
        directory.mkdir(parents=True,exist_ok=True)
        artifacts=[];words=[]
        for artifact in result.get('artifacts',[]):
            path=Path(artifact['path']);assert not path.is_symlink() and path.resolve().is_relative_to((workspace/'Outputs').resolve())
            target=directory/path.name
            if target.exists():assert sha(target)==sha(path),'Do not replace retained outputs.'
            else:shutil.copy2(path,target)
            artifacts.append({'name':path.name,'type':artifact['type'],'path':str(target.relative_to(ROOT)),'sha256':sha(target)})
            if artifact['type']=='docx':words.append(target)
        text='\n'.join(word_text(p) for p in words)
        checks={'completed':not plan or plan['state']=='completed','no_grounded_fallback':not plan.get('grounded_delivery'),
                'no_original_mutation':not result.get('transaction')}
        if plan:checks['completion_checked']=plan.get('completion_check',{}).get('state')=='passed'
        row={'case':name,'id':identifier,'prompt':prior['prompt'],'checks':checks,
             'rows':result.get('rows',[]),'columns':result.get('columns',[]),'seconds':result.get('stats',{}).get('seconds'),
             'source_parent_id':result.get('source_parent_id',plan.get('source_parent_id',result.get('parent_id'))),
             'conversation_parent_id':result.get('conversation_parent_id',plan.get('conversation_parent_id',result.get('parent_id'))),
             'source_count':len(sources),'tools':[s['tool'] for s in plan.get('steps',[])],
             'artifacts':artifacts,'word_text':text,'text':result.get('text',''),
             'repair_history':[s.get('repair_history',[]) for s in plan.get('steps',[]) if s.get('repair_history')],
             'producer_recoveries':[x for r in plan.get('results',{}).values() for x in r.get('producer_recoveries',[])],
             'review_history':[x for r in plan.get('results',{}).values() for x in r.get('review_history',[])]}
        if name in ('workbook','top_followup','return_word'):
            want=protocol['expected_workbook_rows'] if name=='workbook' else protocol['expected_top_row']
            checks['rows']=result.get('rows')==want
            columns=result.get('columns',[])
            bases=[re.sub(r'[（(][^()（）]+[)）]$','',str(c)) for c in columns]
            checks['columns']=bases==['Owner','累计时长','支出','记录数']
            checks['requested_units']=len(columns)==4 and '小时' in columns[1] and '万元' in columns[2]
            checks['word_presence']=bool(words)==(name!='top_followup')
            if words:checks['word_table']=all(' | '.join(r) in text for r in want)
            xlsx=next((ROOT/a['path'] for a in artifacts if a['type']=='xlsx'),None)
            checks['xlsx_exists']=bool(xlsx)
            if xlsx:
                book=load_workbook(xlsx,read_only=True,data_only=False)
                try:
                    sheet=book['处理结果'];cells=[[str(c.value) if c.value is not None else '' for c in r] for r in sheet]
                    checks['xlsx_rows']=cells[1:]==want
                finally:book.close()
            if name=='return_word':
                revision=plan.get('workbook',{}).get('flow',{}).get('contract',{}).get('delivery_revision',{})
                checks['exact_result_reuse']=revision.get('data_unchanged') is True
                row['delivery_revision']=revision
        elif name=='identity':
            checks.update(no_sources=not sources,no_tools=not plan.get('steps'),identity='归屿' in result.get('text',''))
        elif name=='office':
            numeric=re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))','',text)
            checks.update(word_exists=bool(words),numbers=all(re.search(r'(?<![\d.])'+n+r'(?:\.0+)?(?![\d.])',numeric) for n in ('974','826','364','400','210','200')),
                confirmation_date=bool(re.search(r'2028(?:年|[-/])0?7(?:月|[-/])13',text)),unpaid=bool(re.search(r'尚未(?:支付|付款)|未付款|未支付',text)),
                deposit_excluded=bool(re.search(r'不计入|不纳入|不包含|未计入',text)),sources='S1' in text and 'S2' in text,
                calendar_before_write='calendar' in row['tools'] and row['tools'].index('calendar')<row['tools'].index('write'))
        elif name=='share':
            fixture=next(c for c in json.loads((ROOT/'fixtures/submission_v27/tasks.json').read_text())['cases'] if c.get('kind')=='share')
            bodies=[(ROOT/a['path']).read_text() for a in artifacts if a['type'] in ('txt','md')]+[text]
            checks.update(privacy_checked=result.get('share_check',{}).get('state')=='passed',three_formats={a['type'] for a in artifacts}=={'txt','md','docx'},
                sensitive_values_absent=all(all(v not in b for v in fixture['sensitive_values']) for b in bodies),
                office_values_retained=all(all(v in b for v in fixture['retained_values']) for b in bodies))
            row['share_check']=result.get('share_check')
        row['passed']=all(bool(v) for v in checks.values());cases.append(row)
    lookup={x['case']:x for x in cases}
    if 'return_word' in lookup and 'identity' in lookup and 'top_followup' in lookup:
        c=lookup['return_word'];c['checks']['source_lineage']=c['source_parent_id']==ids['top_followup']
        c['checks']['conversation_lineage']=c['conversation_parent_id']==ids['identity']
        c['passed']=all(bool(v) for v in c['checks'].values())
    report={'version':'0.27.1','scope':'Actual native UI with six already-known fictional goals; repair verification, not unseen-data generalization.',
        'backend_hashes':protocol['backend_hashes'],'unit_tests':protocol['tests'],'passed':sum(c['passed'] for c in cases),'total':6,
        'cases':cases,'source_mutations':False,'normal_user_history_and_workspace_not_opened':True,
        'prior_failures_retained':['qa/v0.27/native-retest/initial-evaluation.json','qa/v0.27.1/native-review-format-failure.json','qa/v0.27.1/native-producer-stop-failure.json']}
    if args.finalize:
        assert len(cases)==6 and report['passed']==6,[(c['case'],c.get('checks')) for c in cases]
        (ROOT/'qa/v0.27.1/native-evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    else:(private/'collection-progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'observed':len(cases),'total':6,'cases':[(c['case'],c['passed'],c.get('checks')) for c in cases]},ensure_ascii=False))


if __name__=='__main__':main()
