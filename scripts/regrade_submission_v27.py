"""Normalize equivalent Gregorian date formats in preserved submission outputs.

No generation, backend change, expectation change or numeric regrading occurs.
"""
import hashlib,json,re
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def canonical_dates(text):
    def canonical(m):
        try:return date(int(m[1]),int(m[2]),int(m[3])).isoformat()
        except ValueError:return m[0]
    return re.sub(r'(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})\s*日?',canonical,text)

def main():
    assert canonical_dates('2034年2月3日')=='2034-02-03'
    assert canonical_dates('2034/02/04')=='2034-02-04'
    assert '2034-02-03' not in canonical_dates('2034年2月4日')
    source=ROOT/'qa/v0.27/reports/adapted-20261031T102446-2dcf4f.json'
    target=ROOT/'qa/v0.27/reports/adapted-date-formats.json'
    assert not target.exists()
    report=json.loads(source.read_text());suite=json.loads((ROOT/'fixtures/submission_v27/tasks.json').read_text());validation=json.loads((ROOT/'fixtures/submission_v27/validation.json').read_text());changes=[]
    from docx import Document
    for row in report['cases']:
        case=next(c for c in suite['cases'] if c['id']==row['id'])
        if case.get('kind')!='office' or 'word_text' not in row:continue
        raw=ROOT/'qa/private/v0.27/20261031T102446-2dcf4f'/(row['id']+'-result.json');result=json.loads(raw.read_text())
        words=[a for a in result['artifacts'] if a['type']=='docx']
        text='\n'.join(t for a in words for t in ([p.text for p in Document(a['path']).paragraphs]+[' | '.join(c.text for c in r.cells) for tb in Document(a['path']).tables for r in tb.rows]))
        assert text==row['word_text'],'Captured Word text differs; stop.'
        text=canonical_dates(text);old=dict(row['checks'])
        row['checks']['dates']=not case.get('dates') or any(canonical_dates(d) in text for d in case['dates'])
        row['checks']['all_required_dates']=all(re.search(canonical_dates(pat),text) for pat in validation.get(row['id'],{}).get('required_dates_all',[]))
        row['passed']=all(row['checks'].values())
        for k,v in row['checks'].items():
            if old[k]!=v:changes.append({'case':row['id'],'check':k,'before':old[k],'after':v})
    report['passed']=sum(c['passed'] for c in report['cases'])
    report['grading_correction']={'reason':'Accept equivalent YYYY年M月D日, YYYY/MM/DD and ISO date formats; actual Word reread and matched preserved text. Outputs, required dates, all other checks and backend hashes unchanged.','original_report':str(source.relative_to(ROOT)),'original_report_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'changes':changes,'no_model_regeneration':True,'grader_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(report['passed'],report['total'],target.relative_to(ROOT))

if __name__=='__main__':main()
