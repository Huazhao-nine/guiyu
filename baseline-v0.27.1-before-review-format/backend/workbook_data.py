"""Inspect workbook structure before selecting tables; retain source cells and provenance."""
import csv
import io
import re
from pathlib import Path
from copy import deepcopy
from table_program import MAX_ROWS, MAX_COLUMNS, TableError, number, calendar_date, numeric_column
from local_query import normal


def inspect_documents(documents,core):
    tables=[];total=0
    for doc in sorted(documents,key=lambda d:d['path']):
        path=Path(doc['path'])
        if path.suffix.lower() not in ('.xlsx','.csv'):continue
        core.read_document(path)  # Source archive/expansion checks, no model access.
        matrices=[]
        if path.suffix.lower()=='.csv':
            for encoding in ('utf-8-sig','gb18030','utf-16'):
                try:text=path.read_bytes().decode(encoding);break
                except UnicodeError:continue
            else:raise ValueError('无法识别CSV编码。')
            matrix=[];limited=False
            for row in csv.reader(io.StringIO(text)):
                if len(matrix)>=MAX_ROWS+20:limited=True;break
                matrix.append(row)
            matrices=[('',matrix,[],limited,'')]
        else:
            from openpyxl import load_workbook
            from structured_tables import workbook_layout
            book=load_workbook(path,read_only=True,data_only=True,keep_links=False)
            try:
                if len(book.sheetnames)>30:raise ValueError('一次最多检查30个工作表。')
                for sheet in book:
                    matrix=[];limited=False;error=''
                    if sheet.max_column and sheet.max_column>MAX_COLUMNS:
                        matrices.append((sheet.title,[],[],True,'工作表超过40列，请缩小范围。'));continue
                    for row in sheet.iter_rows(values_only=True):
                        if len(matrix)>=MAX_ROWS+20:limited=True;break
                        matrix.append(['' if x is None else str(x) for x in row])
                    try:merges=workbook_layout(path,{sheet.title}).get(sheet.title,[])
                    except ValueError as exc:merges=[];error=str(exc)
                    matrices.append((sheet.title,matrix,merges,limited,error))
            finally:book.close()
        for sheet,matrix,merges,limited,error in matrices:
            total+=sum(len(r) for r in matrix)
            if total>400000:raise ValueError('工作簿结构检查超过40万个单元格，请选择更小的范围。')
            while matrix and not any(str(x).strip() for x in matrix[-1]):matrix.pop()
            width=max((len(r) for r in matrix if any(str(x).strip() for x in r)),default=0)
            if width>MAX_COLUMNS:error='表格超过40列，请缩小范围。'
            matrix=[[str(x) for x in r]+['']*(width-len(r)) for r in matrix]
            while width and all(not r[width-1].strip() for r in matrix):
                width-=1;matrix=[r[:width] for r in matrix]
            nonempty=[i+1 for i,r in enumerate(matrix) if any(v.strip() for v in r)]
            candidates=[]
            for n in nonempty[:20]:
                r=matrix[n-1]
                if sum(bool(v.strip()) for v in r)>=2 and all(not v.strip() or len(v)<=100 for v in r):
                    candidates.append(n)
            tables.append({'id':'T'+str(len(tables)+1),'file':doc['name'],'path':doc['path'],'sheet':sheet,
                           'matrix':matrix,'merges':merges,'row_count':len(matrix),'width':width,
                           'candidate_header_rows':candidates[:8],'limited':limited,'error':error})
            if len(tables)>40:raise ValueError('一次最多检查40个表区域，请限定文件。')
    if not tables:raise ValueError('没有可处理的CSV或Excel工作簿。')
    return tables


def overview(tables):
    result=[];budget=11000
    for table in tables:
        matrix=table['matrix'];rows=[]
        for i,r in enumerate(matrix[:12]):
            if not any(v.strip() for v in r):continue
            values=[v[:75] for v in r]
            size=sum(len(v) for v in values)
            if size>budget:break
            rows.append({'row':i+1,'cells':values});budget-=size
        tail=[{'row':i+1,'cells':[v[:60] for v in r]} for i,r in enumerate(matrix) if i>=len(matrix)-2 and i>=12]
        result.append({k:table[k] for k in ('id','file','sheet','row_count','width','candidate_header_rows','limited','error')}|{'first_rows':rows,'last_rows':tail,'merges':table['merges'][:20]})
    return result


def automatic_append(tables,goal):
    """Prepare explicitly named simple books when their headers are unique.

    This never selects a business subset, guesses a join, or chooses between
    different possible headers.  Ambiguous structures go to the planner.
    """
    clauses=[]
    for clause in re.split(r'[，,。；;\n]',goal):
        match=re.search(r'合并|纵向追加|拼接',clause)
        if match and not re.search(r'不要|不必|不需要|不应|禁止|别',clause[:match.start()]):clauses.append(clause)
    if not clauses or not 2<=len(tables)<=12:return None
    files=[t['file'] for t in tables]
    if len(set(files))!=len(files):return None  # multi-sheet selection is semantic
    named=' '.join(clauses)
    stems=[Path(name).stem for name in files];mentioned=set();positions={}
    if len({name.casefold() for name in stems})!=len(stems):return None
    names='|'.join(re.escape(name) for name in sorted(stems,key=len,reverse=True))
    for match in re.finditer('(?:'+names+r')(?:\.(?:xlsx|csv))?',named,re.I):
        left=named[:match.start()];right=named[match.end():].lstrip('”"」')
        if left and not re.search(r'(?:[\s“"「、，,(（]|合并|追加|拼接|把|将|和|与|及|以及)$',left):continue
        sheets='|'.join(re.escape(t['sheet']) for t in tables if t.get('sheet'))
        if right and not re.match(r'[\s、，,)）]|和|与|及|的(?:工作簿|工作表|数据|记录|资料|表|'+(sheets or r'(?!)')+r')|里|内|中|纵向|合并|拼接|追加|一起',right):continue
        stem=re.sub(r'\.(?:xlsx|csv)$','',match.group(),flags=re.I).casefold()
        mentioned.add(stem);positions.setdefault(stem,match.start())
    if {name.casefold() for name in stems}!=mentioned:return None
    selection=[]
    for table in sorted(tables,key=lambda t:positions[Path(t['file']).stem.casefold()]):
        candidates={}
        for index,row in enumerate(table['matrix'][:20]):
            if len(row)!=table['width'] or not all(str(v).strip() and len(str(v))<=160 for v in row):continue
            if len(set(map(normal,row)))!=len(row):continue
            textual=True
            for value in row:
                try:number(value);textual=False;break
                except TableError:pass
                try:calendar_date(value);textual=False;break
                except TableError:pass
            if textual:candidates.setdefault(tuple(row),index+1)
        if len(candidates)!=1:return None
        header=next(iter(candidates.values()))
        if any(int(re.search(r'\d+',merge)[0])==header for merge in table['merges']):return None
        selection.append({'id':table['id'],'header_rows':[header],'exclude_summary':True})
    if re.search(r'(?:保留|包括|包含|计入).{0,4}(?:合计|汇总|总计)行',goal):return None
    try:source=prepare_table(tables,selection)
    except TableError:return None
    return selection,source


def prepare_table(tables,selection):
    if not isinstance(selection,list) or not 1<=len(selection)<=12:raise TableError('需选择1–12张数据表。')
    seen=set();columns=None;rows=[];locations=[];inputs=[];notes=[];units={};ledger={};issues={}
    for choice in selection:
        if not isinstance(choice,dict) or set(choice)-{'id','header_rows','exclude_summary'} or not {'id','header_rows'}<=set(choice):raise TableError('表结构选择无效。')
        table=next((t for t in tables if t['id']==choice['id']),None)
        if table is None or table['id'] in seen:raise TableError('工作表标识不存在或重复。')
        seen.add(table['id'])
        if table['error']:raise TableError(table['file']+' / '+table['sheet']+'：'+table['error'])
        if table['limited']:raise TableError('所选工作表未完整读取，不能交付部分结果。请缩小范围。')
        headers=choice['header_rows']
        if not isinstance(headers,list) or not 1<=len(headers)<=3 or any(type(n)!=int or not 1<=n<=min(20,len(table['matrix'])) for n in headers) or headers!=list(range(min(headers),max(headers)+1)):raise TableError('表头需要是前20行内连续的1–3行。')
        if type(choice.get('exclude_summary',True))!=bool:raise TableError('合计行选择无效。')
        matrix=deepcopy(table['matrix']);width=table['width']
        from openpyxl.utils.cell import range_boundaries
        for merge in table['merges']:
            c1,r1,c2,r2=range_boundaries(merge)
            if not (1<=r1<=r2<=len(matrix) and 1<=c1<=c2<=width):continue
            value=matrix[r1-1][c1-1]
            for r in range(r1-1,r2):
                for c in range(c1-1,c2):
                    if (r+1 in headers or c1==c2) and not matrix[r][c]:matrix[r][c]=value
        own=[]
        for c in range(width):
            names=list(dict.fromkeys(matrix[n-1][c].strip() for n in headers if matrix[n-1][c].strip()))
            own.append(' / '.join(names))
        if not own or any(not x or len(x)>160 for x in own) or len(set(map(normal,own)))!=len(own):raise TableError('选定表头为空、重复或过长，请重新选择表头行。')
        excluded=[];own_rows=[];own_locations=[]
        for n in range(max(headers)+1,len(matrix)+1):
            row=matrix[n-1]
            if not any(v.strip() for v in row):continue
            if [v.strip() for v in row]==own or [v.strip() for v in row]==[matrix[headers[-1]-1][c].strip() for c in range(width)]:continue
            first=next((v.strip() for v in row if v.strip()),'')
            if choice.get('exclude_summary',True) and re.fullmatch(r'合计|总计|小计|汇总|total|subtotal',first,re.I):excluded.append(n);continue
            own_rows.append(list(row));own_locations.append({'table_id':table['id'],'file':table['file'],'sheet':table['sheet'],'row':n})
            if len(rows)+len(own_rows)>MAX_ROWS:raise TableError('所选数据合并超过5,000行，请缩小范围。')
        label=table['file']+(' / '+table['sheet'] if table['sheet'] else '')
        # Convert each source independently. Applying the first table's scale
        # to the appended rows would silently misvalue other source units.
        from table_semantics import canonical_table
        canonical=canonical_table({'columns':own,'rows':own_rows,'notes':[]})
        if len(selection)>1 and any('〔原列' in c for c in canonical['columns']):
            raise TableError('单位统一后有同名字段，无法唯一确定多表对应，请明确字段。')
        if columns is None:
            columns=list(canonical['columns']);units=dict(canonical['units']);ledger=deepcopy(canonical['unit_ledger'])
        if set(canonical['columns'])!=set(columns) or any(canonical['units'].get(c,'')!=units.get(c,'') for c in columns):
            raise TableError('选中的数据表字段不同或单位量纲不同；不猜测缺失单位、汇率或跨表关联。')
        indices=[canonical['columns'].index(c) for c in columns]
        rows.extend([[row[i] for i in indices] for row in canonical['rows']]);locations.extend(own_locations)
        notes.extend(label+'：'+note for note in canonical['notes'])
        issues.update(canonical.get('field_issues',{}))
        inputs.append(label+' · 表头'+','.join(map(str,headers))+'行')
        if excluded:notes.append(label+'：排除标为合计/总计/小计的行 '+','.join(map(str,excluded))+'，避免与明细重复计算。')
    if columns is None:raise TableError('未选定可处理的数据表。')
    return {'columns':columns,'rows':rows,'locations':locations,'provenance':[[i] for i in range(len(rows))],
            'inputs':inputs,'notes':notes,'units':units,'unit_ledger':ledger,'field_issues':issues}


def profile(table):
    fields=[];budget=6500
    for i,c in enumerate(table['columns']):
        cells=[r[i] for r in table['rows']];present=[v for v in cells if v.strip()]
        numeric=0;dates=0
        for v in present:
            try:number(v);numeric+=1
            except TableError:pass
            try:calendar_date(v);dates+=1
            except TableError:pass
        identifier=any(re.fullmatch(r'0\d+',v.strip()) for v in present)
        kind='number' if present and numeric==len(present) and numeric_column(c) and not identifier else 'date' if present and dates==len(present) else 'text'
        examples=[]
        for v in dict.fromkeys(present):
            text=v[:100]
            if len(examples)>=8 or len(text)>budget:break
            examples.append(text);budget-=len(text)
        fields.append({'column':c,'type':kind,'empty':len(cells)-len(present),'distinct':len(set(map(normal,present))),'examples':examples})
    return {'row_count':len(table['rows']),'fields':fields,'inputs':table.get('inputs',[]),'notes':table.get('notes',[]),
            'summaries':[{'columns':s['columns'],'rows':s['rows'][:8]} for s in table.get('summaries',[])]}
