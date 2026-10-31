"""Deterministic checks for explicit amounts, entity bindings and stated conditions.

This is deliberately narrower than a semantic correctness or legal-validity proof.
Only current authorized sources and program-computed results are evidence.
"""
from decimal import Decimal
from pathlib import Path
import re

MONEY=re.compile(r'(?<![0-9A-Za-z_.])(?:(?P<prefix>[¥￥$])\s*)?(?P<number>[+-]?\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<unit>万元|美元|人民币|元|USD|CNY)?',re.I)
CITATION=re.compile(r'【(S\d+)(?:[^】]*)】')


def amounts(text):
    result=[]
    for match in MONEY.finditer(text):
        if not (match['prefix'] or match['unit']):continue
        unit=match['unit'] or ('USD' if match['prefix']=='$' else '元')
        unit='USD' if unit.lower() in ('usd','美元') else '元'
        value=Decimal(match['number'].replace(',',''))
        if match['unit']=='万元':value*=10000
        result.append({'value':value,'unit':unit,'start':match.start(),'end':match.end(),'literal':match[0]})
    return result


def names(doc):
    values=[]
    for line in doc['text'].splitlines():
        match=re.match(r'\s*(?:方案名称|场地名称|项目名称|供应商|客户名称|姓名|名称)[：:]\s*([^，。；\n]{2,30})\s*$',line)
        if match:values.append(match[1].strip())
    stem=re.sub(r'^\d+[ _.-]*','',Path(doc['name']).stem)
    if 2<=len(stem)<=30:values.append(stem)
    return list(dict.fromkeys(values))


def prices(doc):
    return {(a['value'],a['unit']) for line in doc['text'].splitlines() if re.search(r'费用|价格|单价|租金|报价',line) and not re.search(r'取消|违约|押金',line) for a in amounts(line)}


def price_basis(doc):
    bases=set()
    for line in doc['text'].splitlines():
        if not re.search(r'费用|价格|单价|租金|报价',line) or re.search(r'取消|违约|押金',line):continue
        for amount in amounts(line):
            match=re.match(r'\s*/\s*([^，。；\s]{1,8})',line[amount['end']:])
            bases.add(match[1] if match else '')
    return next(iter(bases)) if len(bases)==1 else None


def native_scope_documents(docs,table,results):
    """Unfiltered native-cell extraction retains same-document paragraph facts.

    A filtered/projection table is not proof of the original scope. Require an
    exact match to every native row, including source IDs, before adding facts.
    """
    if table is None:return []
    allowed=set()
    for tool,result in results:
        native=result.get('native_table') if tool=='table' else None
        if not native:continue
        expected_columns=native['columns']+['出处','核对提示']
        expected_rows=[row+[native['source_id'],'Word表格原文'] for row in native['rows']]
        if table.get('columns')==expected_columns and table.get('rows')==expected_rows:allowed.add(native['source_id'])
    return [doc for doc in docs if doc['id'] in allowed]


def extraction_scope_documents(docs,table,results):
    """Retain paragraphs from the same unfiltered text-document extraction.

    This establishes the document scope, not extraction completeness. Once
    filtering/projection changes the table, these source facts stop applying.
    """
    if table is None:return []
    import hashlib
    allowed=set()
    for tool,result in results:
        scope=result.get('unfiltered_document_scope') if tool=='table' else None
        if not isinstance(scope,dict) or result.get('partial') or result.get('skipped'):continue
        if result.get('columns')!=table.get('columns') or result.get('rows')!=table.get('rows'):continue
        for doc in docs:
            if scope.get(doc['id'])==hashlib.sha256(doc['text'].encode()).hexdigest():allowed.add(doc['id'])
    return [doc for doc in docs if doc['id'] in allowed]


def current_evidence(docs,table,results):
    """Filtered rows replace whole-document numeric evidence, including on follow-ups."""
    if table is not None:
        groups={}
        for row in table['rows']:
            cells=[]
            for column,value in zip(table['columns'],row):
                text=str(value)
                if '元' in column and re.fullmatch(r'[+-]?\d+(?:\.\d+)?',text):text+='元'
                cells.append(f'{column}：{text}')
            owner=next((str(row[table['columns'].index(c)]) for c in ('经办人','姓名','项目','名称') if c in table['columns']),'本轮匹配记录')
            groups.setdefault(owner,[]).append('；'.join(cells))
        # Labels from excluded rows must never authorize an amount in a new draft.
        source_docs=[{'id':f'R{i}','name':owner,'text':'\n'.join(lines)} for i,(owner,lines) in enumerate(groups.items())]
        source_docs+=native_scope_documents(docs,table,results)
        present={d['id'] for d in source_docs}
        source_docs += [d for d in extraction_scope_documents(docs,table,results) if d['id'] not in present]
    else:source_docs=docs
    latest=[r for tool,r in results if tool=='statistics'][-1:]
    lines=[]
    for result in latest:
        lines.append(result['text'])
        cols=result.get('columns',[]);totals={}
        if not all(c in cols for c in ('字段','合计','平均值','最小值','最大值','单位')):continue
        for row in result.get('rows',[]):
            unit=row[cols.index('单位')]
            if unit not in ('元','USD'):continue
            field=row[cols.index('字段')];owner=' / '.join(row[:cols.index('字段')])
            values='，'.join(f'{label}{row[cols.index(label)]}{unit}' for label in ('合计','平均值','最小值','最大值'))
            lines.append(f'{owner} · {field}：{values}')
            key=(field,unit);totals.setdefault(key,[]).append(Decimal(row[cols.index('合计')]))
        for (field,unit),values in totals.items():
            if values:lines.append(f'当前全部分组 · {field}：总合计{sum(values,Decimal(0))}{unit}')
    for tool,result in results:
        if tool in ('calculate','calendar'):
            lines.append(result['text'])
            unit=result.get('calculation_unit')
            if tool=='calculate' and unit in ('元','USD'):
                owner=' / '.join(result.get('calculation_sources',[]))
                prefix=(owner+' · ') if owner else ''
                for call in result.get('tool_calls',[]):
                    if call.get('state')=='completed' and call.get('tool')=='calculate' and not call.get('output','').endswith('%'):
                        lines.append(prefix+'本轮工具计算：'+call['result']['data']['result']+unit)
                for subtotal in result.get('verified_subtotals',[]):
                    if subtotal['unit']==unit:
                        lines.append(prefix+'同一算式的中间金额核对：'+subtotal['expression']+' = '+subtotal['value']+unit)
    computed='\n'.join(lines)
    return source_docs,computed


def table_money_issues(result,docs):
    columns=result.get('columns',[])
    if '出处' not in columns:return []
    index=columns.index('出处');sources={d['id']:d for d in docs};issues=[]
    for row in result.get('rows',[]):
        doc=sources.get(row[index])
        if not doc:continue
        known={(a['value'],a['unit']) for a in amounts(doc['text'])}
        for column,cell in zip(columns,row):
            value=str(cell)
            if re.fullmatch(r'[+-]?\d+(?:\.\d+)?',value) and re.search(r'金额|费用|价格|单价',column):
                unit='USD' if re.search(r'USD|美元',column,re.I) else '元' if re.search(r'元|人民币',column) else None
                if unit:value+=unit
            for amount in amounts(value):
                if (amount['value'],amount['unit']) not in known:issues.append(f'{doc["name"]}提取的“{column}：{cell}”未找到对应原文金额。')
    return issues[:8]


def calendar_and_refund_issues(text,reference=''):
    """Check adjacent weekday claims and unsupported refund event conditions."""
    from datetime import date
    issues=[]
    plain=re.sub(r'\*\*','',text)
    for m in re.finditer(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?\s*[（(]?\s*(?:星期|礼拜|周)([一二三四五六日天])',plain):
        try:day=date(int(m[1]),int(m[2]),int(m[3]))
        except ValueError:
            issues.append(f'日期“{m[0]}”无效，请按资料核对。');continue
        actual='一二三四五六日'[day.weekday()]
        if m[4] not in (actual,'天' if actual=='日' else actual):
            issues.append(f'{day.isoformat()}实际为星期{actual}，草稿写成星期{m[4]}，请修正日期和星期的对应关系。')
    phases=r'(?:活动|会议|培训|服务|项目)(?:结束|完成)|验收通过|交接完成|合同终止'
    refund_reference='\n'.join(c for c in re.split(r'[。；\n]',reference) if re.search(r'退还|退款|可退|押金',c))
    for clause in re.split(r'[。；\n]',plain):
        if not re.search(r'退还|退款',clause) or re.search(r'是否|待确认|待补充|建议.{0,10}(?:询问|确认)|需.{0,5}核实',clause):continue
        for event in re.findall(phases,clause):
            if event not in refund_reference:issues.append(f'退还条件“{event}”未在当前退款或押金依据中找到，不能自行补写退还时间；请只保留已有性质与条件。')
    payment_reference='\n'.join(c for c in re.split(r'[。；\n]',reference) if re.search(r'支付|付款|结算',c))
    payment_events=r'(?:完成确认|确认|审批|签约|验收(?:通过)?|活动结束|提交资料|收到发票)(?:完成)?后'
    for clause in re.split(r'[。；\n]',plain):
        if not re.search(r'支付|付款|结算',clause) or re.search(r'是否|待确认|待补充|建议.{0,10}(?:询问|确认)|需.{0,5}核实',clause):continue
        for event in re.findall(payment_events,clause):
            if event not in payment_reference:issues.append(f'付款时间条件“{event}”没有当前依据，不能从尚未付款自行补出后续付款流程。')
    return issues


def check_writing(text,instruction,docs,table=None,results=(),query=None):
    source_docs,computed=current_evidence(docs,table,results)
    known={(a['value'],a['unit']) for d in source_docs for a in amounts(d['text'])}
    known|={(a['value'],a['unit']) for a in amounts(computed)}
    grand_totals={(a['value'],a['unit']) for line in computed.splitlines() if line.startswith('当前全部分组') for a in amounts(line)}
    requested={(a['value'],a['unit']) for a in amounts(instruction)}
    aliases={alias:d for d in source_docs for alias in names(d)}
    price_docs=[(d,next(iter(values))) for d in source_docs if len(values:=prices(d))==1]
    differences={(abs(av-bv),au) for a,(av,au) in price_docs for b,(bv,bu) in price_docs if au==bu and av!=bv and price_basis(a) is not None and price_basis(a)==price_basis(b)}
    calculations=[{'higher':names(a)[0] if names(a) else a['name'],'lower':names(b)[0] if names(b) else b['name'],'difference':str(av-bv),'currency':au,'basis':price_basis(a)} for a,(av,au) in price_docs for b,(bv,bu) in price_docs if au==bu and av>bv and price_basis(a) is not None and price_basis(a)==price_basis(b)][:12]
    issues=[]
    def add(message):
        if message not in issues:issues.append(message)
    for message in calendar_and_refund_issues(text,instruction+'\n'+'\n'.join(d['text'] for d in source_docs)):
        add(message)
    if re.search(r'(?:不|不要|不得|不能)[^。；\n]{0,8}放宽',instruction):
        if re.search(r'(?<!不)(?<!无)(?:需|须|只能|可以)(?:要)?(?:接受|允许|容忍)(?:超出预算|超预算|超过预算|放宽条件)',text):
            add('原目标明确不放宽条件，不能要求用户接受超预算或放宽条件；应明确当前没有满足全部要求的方案。')
        advice=r'(?P<verb>建议|考虑|可以|请)(?P<between>[^。；\n]{0,80}?)(?:调整|放宽|降低|提高|增加|减少)(?:当前|原有|现有)?(?:预算|人数|条件|要求)'
        for match in re.finditer(advice,text):
            if re.search(r'(?:不|不要|不能|不应)\s*$',text[:match.start()]):continue
            if re.search(r'(?:不|无需|不必|不要)\s*$',match['between']):continue
            add('原目标明确不放宽条件，不能以建议调整预算、人数或要求代替符合全部条件的结论；可明确当前无合格方案并继续寻找。')
    paragraphs=re.split(r'\n\s*\n',text)
    for paragraph in paragraphs:
        for amount in amounts(paragraph):
            key=(amount['value'],amount['unit'])
            before=paragraph[:amount['start']]
            clause=re.split(r'[。；\n]',before)[-1]
            derived=key in differences and bool(re.search(r'(?:相差|差价|差额|节省|节约|多付|少付|高出|便宜了?|贵了?|低|高)[\s*]*$',before))
            if derived:continue
            if key not in known:
                if key in requested and re.search(r'预算|要求|不超过|上限|阈值|目标|条件|筛选|大于|小于|不少于',clause):continue
                add(f'金额“{amount["literal"]}”没有当前资料或计算依据。');continue
            if re.search(r'(?:^|[，,：:])\s*(?:本轮|当前|各组|整体)(?:的|全部分组)?(?:费用)?(?:总合计|合计|总计|总额)\s*$',clause) and grand_totals:
                if key not in grand_totals:add(f'本轮总合计“{amount["literal"]}”与程序当前分组总额不一致。')
                continue
            previous_amounts=amounts(before)
            if previous_amounts and re.search(r'\bvs\.?\b|相比|低于|高于|对比',before[previous_amounts[-1]['end']:],re.I):continue
            # Bind an amount to the closest explicitly named entity, not just any file.
            matches=[(m.start(),name) for name in aliases for m in re.finditer(re.escape(name),before)]
            if matches:
                position,name=max(matches)
                between=before[position+len(name):]
                if len(between)<=60 and not re.search(r'[。；\n]',between):
                    allowed={(a['value'],a['unit']) for a in amounts(aliases[name]['text'])}
                    allowed|={(a['value'],a['unit']) for line in computed.splitlines() if name in line for a in amounts(line)}
                    if key not in allowed:add(f'“{name}”与金额“{amount["literal"]}”不对应，请按原文修正。')
        # A cheaper/more expensive heading must describe the actual named option.
        for match in re.finditer(r'(?:费用|价格|单价|成本)(?:\s|\*|[：:])*?(更低|更高|更便宜|更贵|最低|最高)',paragraph):
            mentioned=sorted((paragraph.find(name),name) for name in aliases if name in paragraph)
            if not mentioned:continue
            prior=[item for item in mentioned if item[0]<match.start()]
            name=(prior[-1] if prior else mentioned[0])[1]
            connector=list(re.finditer(r'相较于|相比|比',paragraph[:match.start()]))
            if connector:
                subjects=[item for item in prior if item[0]<connector[-1].start()]
                if subjects:name=subjects[-1][1]
            own=aliases[name]
            price=prices(own);others=set().union(*(prices(d) for d in source_docs if d is not own))
            if len(price)==1:
                value,unit=next(iter(price));rivals=[v for v,u in others if u==unit]
                if rivals and ((match[1] in ('更低','更便宜','最低') and value>min(rivals)) or (match[1] in ('更高','更贵','最高') and value<max(rivals))):add(f'“{name}”的费用高低结论与原始金额不一致，请修改理由标题与结论。')
        for condition in re.finditer(r'提前\s*\d+\s*(?:个)?(?:小时|天|工作日)',paragraph):
            before=paragraph[:condition.start()]
            mentioned=[(m.start(),name) for name in aliases for m in re.finditer(re.escape(name),before)]
            if not mentioned:continue
            position,name=max(mentioned);between=before[position+len(name):]
            if len(between)>60 or re.search(r'[。；\n]|无需|不必|不要求',between):continue
            if re.search(r'取消|退款|手续费',paragraph[condition.end():condition.end()+25]):
                if re.sub(r'\s','',condition[0]) not in re.sub(r'\s','',aliases[name]['text']):add(f'“{name}”的“{condition[0]}”取消条件未在对应原文找到，不能套用其他方案的条件。')
        for clause in re.split(r'[。；\n]',paragraph):
            recommended=re.search(r'(?:建议|推荐|选择|选用|选)[^。；\n]{0,15}',clause)
            if not recommended:continue
            # A warning elsewhere in the sentence does not cancel a positive
            # recommendation ("推荐A，超出预算"). Only negate the actual verb.
            prefix=clause[:recommended.start()]
            if re.search(r'(?:不|不可|不能|无法|不应|不宜|不要|不再)\s*$',prefix):continue
            conditional_change=re.search(r'(?:如果|若|如需|在)[^。；\n]{0,12}(?:提高|增加|放宽|调整)预算',prefix)
            if conditional_change and not re.search(r'不放宽|不得放宽|不能放宽|严格|硬性',instruction):continue
            selected=next((name for _,name in sorted((clause.find(name,recommended.start()),name) for name in aliases if clause.find(name,recommended.start())>=0)),None)
            if not selected:continue
            candidate=aliases[selected]
            required_people=re.search(r'(\d+)\s*人(?:参加|参会)|(?:至少|容纳|人数(?:为|是)?)\s*(\d+)\s*人',instruction)
            if required_people:
                people=int(next(x for x in required_people.groups() if x is not None))
                capacity=re.search(r'(?:容量|容纳)[^。；\n]{0,8}?(\d+)\s*人',candidate['text'])
                if capacity and int(capacity[1])<people:add(f'“{selected}”容量仅{capacity[1]}人，不能作为满足{people}人硬性要求的选择。')
            for equipment in re.findall(r'必须(?:要|有|提供|配备|使用)?(?:有|提供|配备|使用)?(投影仪|麦克风|白板|无线网络|WiFi)',instruction,re.I):
                negative=re.search(r'(?:不提供|没有|不配备|不支持|无)[^，,。；\n]{0,15}'+re.escape(equipment),candidate['text'],re.I)
                if negative or equipment.lower() not in candidate['text'].lower():add(f'“{selected}”未满足必须有{equipment}的硬性要求，不能因价格较低而推荐为合格方案。')
            own_prices=prices(aliases[selected])
            if len(own_prices)!=1:continue
            price,unit=next(iter(own_prices))
            for maximum in re.finditer(r'预算[^。；\n]{0,10}?(?:不超过|上限(?:为|是)?|最多|限制为)\s*([\d,.]+)\s*元',instruction):
                if unit=='元' and price>Decimal(maximum[1].replace(',','')):add(f'“{selected}”费用超过原目标的预算上限，不能作为满足硬性要求的选择。')
            if re.search(r'预算(?:优先|为主|最重要)',instruction) and re.search(r'预算(?:优先|为主|最重要)',clause):
                rivals=[v for d in source_docs for v,u in prices(d) if u==unit]
                if rivals and price>min(rivals):add(f'预算优先的建议选择了更贵的“{selected}”，请按费用修正或明确其他必要条件。')
        for doc in source_docs:
            own_names=names(doc)
            if any(name in paragraph for name in aliases) and not any(name in paragraph for name in own_names):continue
            for line in doc['text'].splitlines():
                conditions=re.findall(r'(?:至少)?提前\s*\d+\s*(?:个)?(?:小时|天|工作日)|满\s*\d+(?:\.\d+)?\s*元',line)
                for effect in ('免费取消','全额退款','免手续费','可报销','可以报销'):
                    if effect not in line or not conditions or effect not in paragraph:continue
                    if re.search(r'(?:不能|不支持|并非|不代表|无法保证).{0,8}'+effect,paragraph):continue
                    normalized=re.sub(r'\s','',paragraph)
                    if any(re.sub(r'\s','',c) not in normalized for c in conditions):add(f'“{effect}”缺少原文限定条件“{"、".join(conditions)}”，请保留条件。')
                    if re.search(r'(?:随时|无条件|任何时间).{0,8}'+effect,paragraph):add(f'原文对“{effect}”有限定，不能写成随时或无条件。')
    known_ids={d['id'] for d in docs}
    if set(CITATION.findall(text))-known_ids:add('文稿包含无法对应本轮资料的出处编号。')
    if query and query.get('filters') and re.search(r'所有记录|全体记录|整个工作区|全工作区|全部资料',text):add('本轮已筛选记录，不能把小计写成所有资料或整个工作区的结论。')
    normalized_dates=re.sub(r'[\s*]','',re.sub(r'[\u2010-\u2015\u2212]','-',text))
    for rule in (query or {}).get('filters',[]):
        if rule.get('operator')!='lt' or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',rule.get('value','')):continue
        year,month,day=map(int,rule['value'].split('-'))
        variants=(rule['value'],f'{year}年{month}月{day}日',f'{month}月{day}日')
        for variant in variants:
            for match in re.finditer(re.escape(variant),normalized_dates):
                nearby=normalized_dates[max(0,match.start()-28):match.end()+18]
                if not re.search(r'不含|不包含|小于(?!等于)|早于|之前|(?<![<=>])<(?![=])',nearby) and not normalized_dates[match.end():].startswith('前'):
                    add(f'日期条件为小于{rule["value"]}，该上限日期不包含在内；请明确“不含该日”或写成前一天截止，避免变成包含上限。')
    if table is not None:
        date_columns=[i for i,c in enumerate(table['columns']) if re.search(r'日期',c)]
        months={str(row[i])[:7] for row in table['rows'] for i in date_columns if re.match(r'\d{4}-\d{2}-\d{2}$',str(row[i]))}
        if len(months)>1 and re.search(r'本月|当月',text):add('当前匹配记录跨多个月，不能把结果写成本月或当月；请保留实际日期范围与筛选口径。')
        if not any('预算' in d['text'] for d in source_docs) and re.search(r'符合.{0,12}预算|预算.{0,8}(?:充足|足够|无超支)',text):add('本轮有效资料未提供预算依据，不能声称费用符合预算或没有超支。')
    if table is None:
        for display,label in (('可用时间','可用时间'),('容量','容量'),('取消规则','取消规则'),('场地费用','场地费用')):
            if all(re.search(re.escape(label)+r'[：:]',d['text']) for d in docs) and re.search(r'(?:缺失信息|待补充信息|待补充[：:]|未提供)[^。\n]{0,45}'+re.escape(display)+r'|'+re.escape(display)+r'[^。\n]{0,12}(?:待补充|未提供)',text):add(f'原文已提供“{display}”，不能标作资料缺失；用户自己的活动安排可以另行确认。')
    return {'issues':issues[:8],'amounts_checked':len(amounts(text)),'condition_rules':sum(bool(re.search(r'提前\s*\d+|满\s*\d+',d['text'])) for d in source_docs),'verified_calculations':calculations}


def grounded_brief(instruction,docs,table,results,catalog_builder):
    """Useful evidence survives an unsuccessful generative repair; no invented conclusion."""
    pieces=['# 资料说明（依据版）','本轮文稿未通过完整检查，已整理可核对的依据。选择建议与最终结论待确认。']
    included=False
    for tool,result in results:
        if tool in ('compare','answer','statistics','calculate','calendar'):
            pieces.append(result['text']);included=True
    if table is not None:
        from personal_tools import markdown_table
        pieces.extend(['## 本轮匹配记录',markdown_table(table['columns'],table['rows'][:20])])
        if len(table['rows'])>20:pieces.append(f'预览前20行，共{len(table["rows"])}行；完整记录见本轮表格。')
    elif not included:
        _,catalog,_=catalog_builder(docs,instruction)
        pieces.append('## 当前资料中的原文')
        for item in list(catalog.values())[:24]:pieces.append(f'【{item["source_id"]}】{item["name"]} · 第{item["line"]}行\n\n{item["quote"]}')
    return '\n\n'.join(pieces)


def tool_equations(results):
    """Re-execute local tool calculations and subtotals before review reuse."""
    from general_tools import run_tool
    from decimal import Decimal,InvalidOperation
    equations=[];seen=set()
    for name,result in results:
        if name!='calculate' or not isinstance(result,dict):continue
        candidates=[]
        for call in result.get('tool_calls',[])[:4]:
            if call.get('state')=='completed' and call.get('tool')=='calculate':
                candidates.append((call.get('arguments',{}),call.get('result',{}).get('data',{}).get('result')))
        candidates += [({'expression':v.get('expression')},v.get('value')) for v in result.get('verified_subtotals',[])[:12] if isinstance(v,dict)]
        for arguments,value in candidates:
            try:
                actual=run_tool('calculate',arguments)['data']['result']
                expression=arguments['expression']
                if Decimal(actual)!=Decimal(str(value)) or expression in seen:continue
            except (ValueError,TypeError,KeyError,InvalidOperation):continue
            equations.append({'expression':expression,'result':actual});seen.add(expression)
            if len(equations)>=16:return equations
    return equations


def tool_calendars(results):
    """Only expose calendar results that reproduce exactly from actual calls."""
    from general_tools import run_tool
    verified=[]
    for name,result in results:
        if name!='calendar' or not isinstance(result,dict):continue
        for call in result.get('tool_calls',[])[:4]:
            if call.get('state')!='completed' or call.get('tool')!='calendar':continue
            arguments=call.get('arguments',{})
            # Relative clock calls need their original reference. Do not replay
            # them against the current clock or turn an inferred date into fact.
            if not any(k in arguments for k in ('date','start')):continue
            try:actual=run_tool('calendar',arguments)['data']
            except (ValueError,TypeError):continue
            if actual!=call.get('result',{}).get('data'):continue
            verified.append({'arguments':arguments,'data':actual})
            if len(verified)>=8:return verified
    return verified


def evidence_sheet(instruction,docs,table=None,results=()):
    """Compact current-source facts for generation/repair; never prior assistant prose."""
    facts=check_writing('',instruction,docs,table,results)
    if table is not None:
        _,computed=current_evidence(docs,table,results)
        evidence={'本轮数据':{'columns':table['columns'],'rows':table['rows']},'程序统计':computed}
        native_docs=native_scope_documents(docs,table,results)
        native_docs += [d for d in extraction_scope_documents(docs,table,results) if d['id'] not in {x['id'] for x in native_docs}]
        if native_docs:evidence['同一未筛选原文的段落事实']=[{'source_id':d['id'],'name':d['name'],'clauses':[line for line in d['text'].splitlines() if line.strip()][:18]} for d in native_docs]
    else:
        evidence={'原文事实':[{ 'source_id':d['id'],'name':d['name'],'clauses':[line for line in d['text'].splitlines() if line.strip()][:18]} for d in docs[:8]],'程序差价':facts['verified_calculations']}
    maximum=re.search(r'预算[^。；\n]{0,10}?(?:不超过|上限(?:为|是)?|最多)\s*([\d,.]+)\s*元',instruction)
    required=re.search(r'(\d+)\s*人(?:参加|参会)|(?:至少|容纳|人数(?:为|是)?)\s*(\d+)\s*人',instruction)
    equipment=re.findall(r'必须(?:要|有|提供|配备|使用)?(?:有|提供|配备|使用)?(投影仪|麦克风|白板|无线网络|WiFi)',instruction,re.I)
    if table is None and maximum and any(x in instruction for x in ('对比','比较','选择')):
        options=[]
        for doc in docs:
            own=prices(doc)
            if len(own)!=1:continue
            price,unit=next(iter(own))
            if unit!='元':continue
            checks={'预算':price<=Decimal(maximum[1].replace(',',''))}
            capacity=re.search(r'(?:容量|容纳)[^。；\n]{0,8}?(\d+)\s*人',doc['text'])
            if required:
                people=int(next(v for v in required.groups() if v is not None));checks['人数']=int(capacity[1])>=people if capacity else None
            for item in equipment:
                negative=re.search(r'(?:不提供|没有|不配备|不支持|无)[^，,。；\n]{0,15}'+re.escape(item),doc['text'],re.I)
                checks[item]=False if negative else True if item.lower() in doc['text'].lower() else None
            options.append({'source_id':doc['id'],'名称':names(doc)[0] if names(doc) else doc['name'],'条件':checks,'合格':False if False in checks.values() else True if None not in checks.values() else None})
        if options:evidence['程序硬条件核对']={'方案':options,'当前均不合格':all(o['合格'] is False for o in options)}
    import json
    return json.dumps(evidence,ensure_ascii=False)[:14000]
