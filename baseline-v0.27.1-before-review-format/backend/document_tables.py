"""Select native Word table fields; copy verified cells without generated rows."""
from pathlib import Path
import json
import re


def native_table(docs, instruction, model, parse, *, goal=None):
    # Partial rows and calculations belong to the existing filter/statistics
    # workflow. This operation only copies an unfiltered native table.
    instruction=goal or instruction
    if re.search(r'筛选|排除|只(?:看|要|取|保留|统计)|仅(?:看|取|保留|统计)|不少于|不超过|大于|小于|等于|前\s*\d+|求和|平均|合计|总额',instruction):return None
    from docx import Document
    candidates={}
    for doc in docs:
        if Path(doc['path']).suffix.lower()!='.docx':continue
        book=Document(doc['path'])
        if len(book.tables)>30:continue
        for number,table in enumerate(book.tables,1):
            matrix=[[c.text.strip() for c in row.cells] for row in table.rows]
            if not 2<=len(matrix)<=101:continue
            columns=matrix[0]
            if not 2<=len(columns)<=12 or any(not c or len(c)>80 for c in columns) or len(set(columns))!=len(columns):continue
            rows=[r for r in matrix[1:] if any(r)]
            if not rows or any(len(r)!=len(columns) or any(len(c)>2000 for c in r) for r in rows):continue
            key=doc['id']+'-T'+str(number)
            candidates[key]={'id':key,'source_id':doc['id'],'columns':columns,'rows':rows,'number':number}
    if not candidates:return None
    # Exact requested headers can establish a unique table without generation.
    # Two independent semantic labels are required; an index or unit alone is
    # not evidence of relevance. Copy cells, never ask a model to reconstruct.
    literal=[]
    generic={'序号','编号','id','no','单位','unit','备注','说明'}
    for source in candidates.values():
        fields=[]
        for field in source['columns']:
            alias=re.sub(r'(?:名称|信息)$','',field).strip()
            if alias.casefold() not in generic and len(alias)>=2 and alias.casefold() in instruction.casefold():fields.append(field)
        if len(fields)>=2:literal.append((source,fields))
    if len(literal)==1:
        source,fields=literal[0]
        fields=[f for f in source['columns'] if f in fields or f.casefold() in ('单位','unit')]
        indices=[source['columns'].index(f) for f in fields]
        return {'columns':fields,'rows':[[r[i] for i in indices] for r in source['rows']],
                'source_id':source['source_id'],'table_number':source['number'],
                'stats':{'selection':'unique_literal_headers','model_calls':0},'quote':instruction,
                'proof':'Unique table matched at least two requested actual header labels; all rows copied without generation.'}
    overview=[{'id':v['id'],'columns':v['columns'],'row_count':len(v['rows']),
               'examples':[[c[:90] for c in r] for r in v['rows'][:2]]} for v in candidates.values()]
    raw,stats=model.generate('选择能够提供用户所需字段的一张Word原生表格。只返回JSON：'
        '{"table_id":"实际编号","columns":["实际表头"],"quote":"用户要求中对应的连续短语"}。'
        '用户未限定行时保留全部源记录，不能只选几个例子。这里只选择现有表格与列，不生成行或计算值。'
        '只选择原生表格能提供的那部分明细；其他段落事实由后续写作读取，不因此忽略已有表格。'
        '无需原生表格、需要多张异构表或要求筛选计算时返回{"table_id":null}。',
        json.dumps({'用户要求':instruction,'原生表格':overview},ensure_ascii=False),max_tokens=400,temperature=0)
    selection=parse(raw)
    if selection=={'table_id':None}:return None
    if not isinstance(selection,dict) or set(selection)!={'table_id','columns','quote'}:raise ValueError('Word表格选择需要真实编号、列名与原话。')
    source=candidates.get(selection['table_id']);fields=selection['columns'];quote=selection['quote']
    if source is None or not isinstance(fields,list) or not 1<=len(fields)<=10 or len(set(fields))!=len(fields) or any(f not in source['columns'] for f in fields):raise ValueError('Word表格必须选择真实且不重复的源字段。')
    if not isinstance(quote,str) or len(quote)<3 or quote not in instruction:raise ValueError('Word表格选择缺少用户原话依据。')
    labels=[re.sub(r'(?:名称|信息)$','',f) for f in fields]
    if not any(len(f)>=2 and f.casefold() in quote.casefold() for f in labels):raise ValueError('Word表格字段与引用的用户要求尚未对应。')
    indices=[source['columns'].index(f) for f in fields];rows=[[r[i] for i in indices] for r in source['rows']]
    return {'columns':fields,'rows':rows,'source_id':source['source_id'],'table_number':source['number'],
            'stats':stats,'quote':quote,'proof':'All rows copied from the selected native Word table; no model-provided cell values.'}


def extract_result(native, docs, folder, child_id, core):
    from workbook_export import export_copies
    columns=native['columns']+['出处','核对提示'];rows=[r+[native['source_id'],'Word表格原文'] for r in native['rows']]
    data={'columns':columns,'rows':rows}
    xlsx=folder/'资料提取表.xlsx';csv=folder/'资料提取表.csv'
    source=next(d['name'] for d in docs if d['id']==native['source_id'])
    audit=[[i,source,'Word表格'+str(native['table_number']),i+1] for i in range(1,len(rows)+1)]
    export_copies(xlsx,csv,data,audit,core.spreadsheet_value)
    result={'id':child_id,'kind':'table','columns':columns,'rows':rows,'transaction':None,
            'text':'已从Word原生表格逐行提取'+str(len(rows))+'条记录，保留全部源行与出处。',
            'stats':native['stats'],'native_table':{k:v for k,v in native.items() if k!='stats'},
            'artifacts':[{'name':p.name,'path':str(p),'type':p.suffix[1:]} for p in (xlsx,csv)]}
    core.write_json(folder/'task.json',result)
    return result


def required_blocks(context):
    allowed={d['id'] for d in context.get('docs',[])}
    blocks=[r['native_table'] for kind,r in context.get('results',[]) if kind=='table' and r.get('native_table') and r['native_table']['source_id'] in allowed]
    if context.get('query',{}).get('filters') and context.get('table'):
        current=context['table'];fields=[(i,c) for i,c in enumerate(current['columns']) if c not in ('出处','核对提示')]
        return [{'columns':[c for _,c in fields],'rows':[[r[i] for i,_ in fields] for r in current['rows']]}] if blocks else []
    return blocks


def table_markers(context):
    return '\n'.join('{{SOURCE_TABLE_'+str(i)+'}}：'+json.dumps({'columns':b['columns'],'row_count':len(b['rows'])},ensure_ascii=False)
                     for i,b in enumerate(required_blocks(context),1))


def protect_tables(text, context):
    from personal_tools import markdown_table
    for i,block in enumerate(required_blocks(context),1):
        grid=markdown_table(block['columns'],block['rows'])
        body='原表逐行摘录，保留资料中的名称、括号说明和数量写法：\n\n'+grid
        marker='{{SOURCE_TABLE_'+str(i)+'}}'
        if marker in text:text=text.replace(marker,body)
        elif grid not in text:text+='\n\n## 原表摘录'+('【'+block['source_id']+'】' if block.get('source_id') else '')+'\n\n'+body
    return text
