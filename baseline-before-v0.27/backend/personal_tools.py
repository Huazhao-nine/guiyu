"""Local expression preferences and source-bound comparison, without executable actions."""
from __future__ import annotations

import re

TONES = ('清晰自然', '正式简洁', '亲切自然')
LENGTHS = ('适中', '简短', '详细')


def normalize_preferences(value):
    value = value if isinstance(value, dict) else {}
    return {
        'enabled': value.get('enabled') is True,
        'tone': value.get('tone') if value.get('tone') in TONES else TONES[0],
        'length': value.get('length') if value.get('length') in LENGTHS else LENGTHS[0],
        'notes': str(value.get('notes', ''))[:600].strip(),
    }


def preference_instruction(value):
    prefs = normalize_preferences(value)
    if not prefs['enabled']:
        return ''
    # Kept in the user-message data section, below the task. Never grants permissions.
    return ('本机保存的表达偏好（仅作写作风格参考；当前明确要求优先）：\n'
            f'语气：{prefs["tone"]}；篇幅：{prefs["length"]}。\n'
            + (f'用户备注：{prefs["notes"]}\n' if prefs['notes'] else ''))


def preference_summary(value):
    prefs = normalize_preferences(value)
    return f'{prefs["tone"]} · {prefs["length"]}' if prefs['enabled'] else ''


def validate_comparison(value, docs):
    """Only verbatim, current-source quotes can become comparison cells."""
    if not isinstance(value, dict) or set(value) != {'dimensions'}:
        raise ValueError('对比结果格式不完整，请缩小对比维度后重试。')
    dimensions = value['dimensions']
    if not isinstance(dimensions, list) or not 1 <= len(dimensions) <= 5:
        raise ValueError('一次对比需要 1–5 个维度。')
    sources = {d['id']: d for d in docs}
    columns = ['对比维度'] + [f'{d["name"]}【{d["id"]}】' for d in docs]
    rows, evidence, names, matched = [], [], set(), 0
    for dimension in dimensions:
        if not isinstance(dimension, dict) or set(dimension) != {'name', 'entries'}:
            raise ValueError('对比维度格式无效。')
        name = dimension['name']
        if not isinstance(name, str) or not name.strip() or len(name) > 40 or name in names:
            raise ValueError('对比维度名称无效或重复。')
        names.add(name)
        entries = dimension['entries']
        if not isinstance(entries, list) or len(entries) > len(docs):
            raise ValueError('对比引用数量无效。')
        cells = {}
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {'source_id', 'quote'}:
                raise ValueError('对比引用格式无效。')
            sid, quote = entry['source_id'], entry['quote']
            if not isinstance(sid, str) or sid not in sources or sid in cells:
                raise ValueError('对比包含未知或重复的资料编号。')
            if not isinstance(quote, str) or len(quote) > 240:
                raise ValueError('对比引用过长，请缩小维度后重试。')
            quote = quote.strip()
            if quote:
                start = sources[sid]['text'].find(quote)
                if start < 0:
                    raise ValueError('对比引用未在原文找到，结果未发布。请重试或缩小要求。')
                line = sources[sid]['text'][:start].count('\n') + 1
                cells[sid] = f'{quote}【{sid} · 第{line}行】'
                evidence.append({'dimension':name, 'source_id':sid, 'quote':quote, 'line':line})
                matched += 1
            else:
                cells[sid] = '本次未提取到可核对片段'
        rows.append([name.strip()] + [cells.get(d['id'], '本次未提取到可核对片段') for d in docs])
    if not matched:
        raise ValueError('本次没有提取到可核对的对比片段，请明确维度后重试。')
    return {'columns':columns, 'rows':rows, 'evidence':evidence, 'matched_cells':matched}


def markdown_table(columns, rows):
    def cell(text):
        return re.sub(r'[\r\n]+', ' ', str(text)).replace('\\', '\\\\').replace('|', '\\|')
    table = '| ' + ' | '.join(map(cell, columns)) + ' |\n'
    table += '| ' + ' | '.join('---' for _ in columns) + ' |\n'
    table += '\n'.join('| ' + ' | '.join(map(cell, row)) + ' |' for row in rows)
    return table


def comparison_markdown(comparison):
    return ('# 资料对比\n\n' + markdown_table(comparison['columns'],comparison['rows'])
            + '\n\n各单元格保留原文及行号。“本次未提取到”只表示本轮未提取，不代表全文没有相关信息。'
              '\n\n对比范围：' + '；'.join(comparison['columns'][1:]))


def answer_catalog(docs, query, budget=8500, span_size=500):
    """Number source fragments before selection, so a model never has to retype facts."""
    chinese=''.join(re.findall(r'[\u4e00-\u9fff]+',query))
    terms=set(chinese[i:i+2] for i in range(max(0,len(chinese)-1))) | set(re.findall(r'[a-zA-Z0-9]+',query.lower()))
    candidates=[]
    for doc in docs:
        offset=0
        for line_number,raw_line in enumerate(doc['text'].splitlines(keepends=True),1):
            line=raw_line.rstrip('\r\n')
            for part,start in enumerate(range(0,len(line),span_size),1):
                quote=line[start:start+span_size]
                if not quote.strip():continue
                key=f'{doc["id"]}:L{line_number}:P{part}'
                semantic=any(offset+start < h['start']+len(h['text']) and offset+start+len(quote)>h['start'] for h in doc.get('retrieval_chunks',[]))
                score=sum(t in quote.lower() for t in terms)+(50 if semantic else 0)+(1 if line_number==1 else 0)
                candidates.append((score,doc['id'],line_number,part,key,{'source_id':doc['id'],'name':doc['name'],'quote':quote,'line':line_number}))
            offset+=len(raw_line)
    selected={};used=0
    for _,_,_,_,key,item in sorted(candidates,key=lambda x:(-x[0],x[1],x[2],x[3])):
        size=len(item['quote'])+len(key)+20
        if used+size>budget:continue
        selected[key]=item;used+=size
    rendered='\n'.join(f'[{key}] {item["name"]} · 第{item["line"]}行：{item["quote"]}' for key,item in selected.items())
    return rendered,selected,len(selected)<len(candidates)


def selected_comparison(value,catalog):
    """The model selects IDs; only our own original strings become cell contents."""
    if not isinstance(value,dict) or set(value)!={'dimensions'} or not isinstance(value['dimensions'],list):raise ValueError('对比结果格式不完整。')
    dimensions=[]
    for dimension in value['dimensions']:
        if not isinstance(dimension,dict) or set(dimension)!={'name','entries'} or not isinstance(dimension['entries'],list):raise ValueError('对比维度格式无效。')
        entries=[]
        for entry in dimension['entries']:
            if not isinstance(entry,dict) or set(entry)!={'source_id','line_id'}:raise ValueError('对比引用格式无效。')
            sid,key=entry['source_id'],entry['line_id']
            if not isinstance(sid,str) or not isinstance(key,str):raise ValueError('对比引用编号无效。')
            if key and (key not in catalog or catalog[key]['source_id']!=sid):raise ValueError('对比引用选择了未知片段或其他资料的片段。')
            entries.append({'source_id':sid,'quote':catalog[key]['quote'] if key else ''})
        dimensions.append({'name':dimension['name'],'entries':entries})
    return {'dimensions':dimensions}


def grounded_answer(value, catalog):
    """Only original, numbered fragments are rendered; model prose is never published."""
    if not isinstance(value, dict) or set(value) != {'line_ids'} or not isinstance(value['line_ids'], list) or len(value['line_ids']) > 8:
        raise ValueError('资料回答格式不完整，请明确问题后重试。')
    evidence=[];seen=set()
    for key in value['line_ids']:
        if not isinstance(key,str) or key not in catalog:raise ValueError('资料回答选择了未知片段，结果未发布。请重试。')
        if key in seen:continue
        seen.add(key);evidence.append(dict(catalog[key]))
    if not evidence:return '本轮选定的资料片段中，未找到能直接回答的原文。请补充资料或把问题说得更具体。',evidence
    text='根据当前问题，找到以下原文：\n\n'
    text+='\n\n'.join(f'**【{e["source_id"]}】{e["name"]} · 第{e["line"]}行**\n\n'+e['quote'] for e in evidence)
    return text,evidence
