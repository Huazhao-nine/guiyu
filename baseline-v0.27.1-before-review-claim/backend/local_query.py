"""Local literal retrieval and a typed, deterministic table query language."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import re
import unicodedata

OPS={'eq':'等于','ne':'不等于','contains':'包含','not_contains':'不包含','gt':'大于','gte':'不少于','lt':'小于','lte':'不超过'}
ROW_INTENT=r'名单|名册|分离出来|挑出|抽出|单独.{0,8}(?:列出|提取|导出)|列出.{0,12}(?:同学|人员|学生)|提取.{0,12}(?:同学|人员|学生)'
RESET=r'清除筛选|清除条件|取消筛选|全部记录|所有记录|全部资料'

def normal(value):return unicodedata.normalize('NFKC',str(value)).casefold().strip()

def named_paths(prompt, paths):
    """Resolve names only within an already authorized scope, including 工作簿 1."""
    text=re.sub(r'\s+','',normal(prompt))
    paths=list(dict.fromkeys(str(p) for p in paths));matches=[];excluded=set()
    for path in paths:
        from pathlib import Path
        stem=re.sub(r'\s+','',normal(Path(path).stem))
        full=re.sub(r'\s+','',normal(Path(path).name))
        if len(stem)<3 and full not in text:continue
        ending=r'(?![a-z0-9])' if re.search(r'[a-z0-9]$',stem) else ''
        occurrences=list(re.finditer(re.escape(stem)+ending,text))
        rejected=[m for m in occurrences if re.search(r'(?:不要用|别用|不用|不读|别读|不使用|不要使用|不读取|不要读取|不采用|排除|忽略)[“「《\"\']?$',text[max(0,m.start()-20):m.start()])]
        if rejected and len(rejected)!=len(occurrences):raise ValueError('同一文件同时被要求使用和排除，请明确本次资料范围。')
        if rejected:excluded.add(stem)
        elif occurrences:matches.append((stem,str(path)))
    # Coordinated abbreviated titles can share an already named prefix, e.g.
    # "研讨会通知和补充说明". Resolve only a unique existing sibling title;
    # this never constructs a path or picks between ambiguous documents.
    from pathlib import Path
    existing=list(matches)
    for stem,_ in existing:
        for match in re.finditer(re.escape(stem)+r'(?:以及|和|与|及|、)([^，,。；;\n]{2,30})',text):
            short=match[1].strip('“”「」《》\"\'')
            candidates=[]
            for path in paths:
                title=re.sub(r'\s+','',normal(Path(path).stem))
                if title in excluded or title==stem or not title.endswith(short):continue
                prefix=title[:-len(short)]
                if len(prefix)>=2 and stem.startswith(prefix):candidates.append((title,path))
            if len(candidates)>1:raise ValueError('简称“'+short+'”对应多份资料，请写完整文件名。')
            matches.extend(candidates)
    matches=list(dict.fromkeys(matches))
    if excluded and not matches:raise ValueError('当前只指定了要排除的文件，请说明要使用的资料范围。')
    # A shared basename from two folders needs clarification, never an arbitrary choice.
    for stem in {m[0] for m in matches}:
        if sum(m[0]==stem for m in matches)>1:raise ValueError('有多个同名文件，请在“我的资料”选择具体文件后再试。')
    result={path for stem,path in matches if not any(stem!=other and stem in other for other,_ in matches)}
    required=re.findall(r'工作簿\s*\d+',normal(prompt))
    for title in required:
        key=re.sub(r'\s+','',title)
        if key in excluded:continue
        if not any(re.sub(r'\s+','',normal(__import__('pathlib').Path(p).stem))==key for p in result):
            raise ValueError('授权范围内未找到“'+title+'”，请添加或选择这份工作簿。')
    return result

def resolve_column(value,columns):
    key=normal(value).strip('「」【】"\' ')
    exact=[c for c in columns if normal(c)==key]
    if len(exact)==1:return exact[0]
    matches=[c for c in columns if re.split(r'[（(]',normal(c))[0]==key]
    if len(matches)==1:return matches[0]
    raise ValueError(f'无法确定字段“{value}”，请选择表格中完整的列名。')

def validate_query(spec,columns):
    if not isinstance(spec,dict) or set(spec)-{'filters','match','group_by','metrics'}:raise ValueError('筛选格式无效。')
    result={'filters':[],'match':spec.get('match','all'),'group_by':[],'metrics':[]}
    if result['match'] not in ('all','any'):raise ValueError('条件组合只支持“全部满足”或“任一满足”。')
    rules=spec.get('filters',[])
    if not isinstance(rules,list) or len(rules)>8:raise ValueError('一次最多设置八个筛选条件。')
    for rule in rules:
        if not isinstance(rule,dict) or set(rule)!={'column','operator','value'} or rule.get('operator') not in OPS:raise ValueError('筛选条件无效。')
        value=str(rule['value']).strip()
        if not value or len(value)>120:raise ValueError('每个条件需要不超过120字的值。')
        result['filters'].append({'column':resolve_column(rule['column'],columns),'operator':rule['operator'],'value':value})
    for key,limit in (('group_by',2),('metrics',12)):
        values=spec.get(key,[])
        if not isinstance(values,list) or len(values)>limit:raise ValueError('分组或统计字段过多。')
        result[key]=list(dict.fromkeys(resolve_column(v,columns) for v in values))
    return result

def describe_query(spec):
    filters=[f'{r["column"]} {OPS[r["operator"]]} {r["value"]}' for r in spec.get('filters',[])]
    body=('；或 '.join(filters) if spec.get('match')=='any' else '；且 '.join(filters)) or '全部记录'
    if spec.get('group_by'):body+=' · 按'+'、'.join(spec['group_by'])+'分组'
    if spec.get('metrics'):body+=' · 统计'+'、'.join(spec['metrics'])
    return body

def query_text(prompt):
    text=re.sub(r'(?:不超过|不少于|至少|至多|大于|小于)\s*\d+\s*(?:字|段|句|页)','',unicodedata.normalize('NFKC',prompt))
    text=re.sub(r'筛选(?:与统计)?结果|筛选后(?:的)?','结果',text)
    return text

def wants_query(prompt):
    prompt=query_text(prompt)
    return bool(re.search(r'筛选|只看|仅看|只统计|仅统计|大于|小于|不少于|不超过|至少|至多|>=|<=|[><=]|按.+?(?:分组|汇总|统计)|那.{1,30}呢|'+RESET,prompt) or re.search(ROW_INTENT,prompt))

def compile_query(prompt,table,inherited=None):
    """Compile only supported literal predicates; never silently discard a condition."""
    columns=table['columns'];text=query_text(prompt)
    spec=validate_query(deepcopy(inherited or {}),columns)
    if re.search(RESET,text):spec['filters']=[]
    if re.search(r'取消分组|不分组|合并分组',text):spec['group_by']=[]
    group=re.search(r'按[「“"\s]*([^，,。；;]+?)[」”"\s]*(?:分组|汇总|分别统计|统计)',text)
    if group:spec['group_by']=[resolve_column(group[1].strip('「」“”" '),columns)]
    op_pattern=r'不包含|不等于|不少于|不超过|大于等于|小于等于|至少|至多|大于|小于|等于|包含|>=|<=|!=|==|>|<|=|为|是'
    mapping={'不包含':'not_contains','不等于':'ne','不少于':'gte','不超过':'lte','大于等于':'gte','小于等于':'lte','至少':'gte','至多':'lte','大于':'gt','小于':'lt','等于':'eq','包含':'contains','>=':'gte','<=':'lte','!=':'ne','==':'eq','>':'gt','<':'lt','=':'eq','为':'eq','是':'eq'}
    aliases=[]
    for col in columns:
        aliases.extend((col,re.split(r'[（(]',col)[0]))
    aliases=sorted(set(aliases),key=len,reverse=True)
    pattern=r'[「“"]?('+ '|'.join(re.escape(unicodedata.normalize('NFKC',c)) for c in aliases)+r')[」”"]?\s*('+op_pattern+r')\s*(?:[「“"]([^」”"]+)[」”"]|([^，,；;。\n且]+))'
    found=[];matched_ranges=[]
    for match in re.finditer(pattern,text):
        col=resolve_column(match[1],columns);value=(match[3] or match[4]).strip()
        value=re.split(r'\s*(?:并且|且|然后|再|按|并写|并统计|的(?:记录|费用|项目|数据|资料|同学|学生|人员|名单|名册)|进行|求合计|求平均)',value)[0].strip()
        value=re.sub(r'(?:的)?(?:合计|平均值|总额|汇总|统计)$','',value).strip()
        if not value:raise ValueError('条件缺少值，请打开“按条件统计”补全。')
        found.append({'column':col,'operator':mapping[match[2]],'value':value});matched_ranges.append(match.span())
    # Resolve literal names / status fragments from the actual table, without inventing values.
    for index,column in enumerate(columns):
        if any(r['column']==column for r in found) or re.search(r'出处|证据|核对|来源|编号|日期|时间',column):continue
        values={str(r[index]).strip() for r in table['rows'] if index<len(r)}
        candidates=set()
        for value in values:
            if 2<=len(value)<=30 and not re.fullmatch(r'[\d.,+\- 元¥￥$]+',value):
                candidates.add(value)
                if re.search(r'状态|类别|分类',column):candidates.update(x for x in re.split(r'[，,、;； ]+',value) if len(x)>=2)
        if re.search(r'状态',column):candidates.update(v for v in ('已垫付','待报销','待付款','已报销','未付款','未报销','已付款') if any(v in x for x in values))
        if re.search(r'学院|院所|单位|部门|机构|研究所|学校',column):
            for value in values:
                compact=normal(value)
                for end in re.finditer(r'研究所|大学|学院|公司|中心|部门',compact):
                    for start in range(max(0,end.end()-40),end.start()):
                        fragment=compact[start:end.end()]
                        if len(fragment)>=5 and fragment in normal(text):candidates.add(fragment)
        hits=sorted((v for v in candidates if v in text or normal(v) in normal(text)),key=len,reverse=True)
        if hits and wants_query(text):
            if len([h for h in hits if not any(h!=v and h in v for v in hits)])>1:
                raise ValueError('同一字段有多个值，请用“按条件统计”明确设置任一满足或全部满足。')
            value=hits[0]
            op='contains' if any(value!=v and value in v for v in values) else 'eq'
            found.append({'column':column,'operator':op,'value':value})
    if found:
        changed={r['column'] for r in found}
        spec['filters']=[r for r in spec['filters'] if r['column'] not in changed]+found
        if re.search(r'或者|或',text):
            if '且' in text:raise ValueError('混合“且/或”的条件请拆开处理，或在条件面板中设置。')
            spec['match']='any'
        elif '且' in text or '并且' in text:spec['match']='all'
    # Conditions the compiler cannot interpret must not fall through to whole-table statistics.
    explicit=bool(re.search(ROW_INTENT,text) or re.search(r'筛选|只看|仅看|只统计|仅统计|大于|小于|不少于|不超过|>=|<=|[><=]|那.{1,30}呢',text))
    metric_only=any(re.search(r'(?:只统计|仅统计)\s*'+re.escape(re.split(r'[（(]',c)[0])+r'(?:的)?(?:合计|平均|总额|[，,。]|$)',text) for c in columns)
    condition=re.search(r'(?:只看|仅看|只统计|仅统计|筛选出?)\s*([^，,；;。\n]+)',text)
    if condition and not metric_only:
        for clause in re.split(r'并且|且|或者|或',condition[1]):
            if not any(r['value'] in clause for r in found) and not re.search(RESET,clause):
                raise ValueError(f'还不能确定条件“{clause.strip()}”，请用字段、比较方式和具体值填写。')
    if explicit and not found and not re.search(RESET,text) and not metric_only and not re.search(r'取消分组|不分组',text):
        raise ValueError('还不能确定筛选条件。请写成“金额大于100元”“状态包含待报销”，或打开“按条件统计”选择字段。')
    for forbidden in ('最近一周','上周','昨天','今天','前五','前十','最大的','最小的'):
        if forbidden in text:raise ValueError('相对日期与排名条件请改成明确的日期或数值范围。')
    # Detect a second comparator without a named field instead of silently omitting it.
    rest=text
    for a,b in reversed(matched_ranges):rest=rest[:a]+rest[b:]
    if re.search(r'且\s*(?:大于|小于|不少于|不超过|>=|<=|[><])',rest):raise ValueError('每个数值条件都需写明字段，例如“金额大于100且金额小于300”。')
    return validate_query(spec,columns)

def apply_query(table,spec,numeric_value):
    spec=validate_query(spec,table['columns']);indices={c:i for i,c in enumerate(table['columns'])}
    def compare(cell,rule):
        raw=normal(cell);target=normal(rule['value']);op=rule['operator']
        if op=='contains':return target in raw
        if op=='not_contains':return target not in raw
        left,right=numeric_value(cell),numeric_value(rule['value'])
        if left is not None and right is not None:
            header_unit=re.search(r'[（(](元|USD|CNY|人|份|次|件|小时|分钟|天|个|笔|GB|MB)[)）]',rule['column'],re.I)
            unit=left[1] or (header_unit[1] if header_unit else '')
            if unit=='CNY':unit='元'
            if unit and right[1] and unit!=right[1]:raise ValueError('筛选数值与数据单位不同，请统一单位。')
            a,b=left[0],right[0]
        elif re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',target):
            a,b=date.fromisoformat(raw),date.fromisoformat(target)
        elif op in ('gt','gte','lt','lte'):
            # Missing / nonnumeric rows are excluded, never compared lexicographically.
            if right is None and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',target):raise ValueError('大小比较需要数值或 YYYY-MM-DD 日期。')
            return False
        else:a,b=raw,target
        return {'eq':lambda:a==b,'ne':lambda:a!=b,'gt':lambda:a>b,'gte':lambda:a>=b,'lt':lambda:a<b,'lte':lambda:a<=b}[op]()
    rows=[];row_indices=[];locations=[]
    for number,row in enumerate(table['rows']):
        matches=[compare(row[indices[r['column']]],r) for r in spec['filters']]
        if not matches or (all(matches) if spec['match']=='all' else any(matches)):rows.append(row);row_indices.append(number+2);locations.extend(table.get('row_locations',[])[number:number+1])
    result={**table,'rows':rows,'query':spec,'source_row_numbers':row_indices,'unfiltered_count':len(table['rows']),'row_locations':locations}
    return result

def grouped_statistics(table,spec,compute):
    columns=table['columns'];metrics=spec.get('metrics',[])
    if metrics:
        indices=[columns.index(c) for c in metrics]
        target={'columns':metrics,'rows':[[r[i] for i in indices] for r in table['rows']]}
    else:target=table
    if not table['rows']:return {'columns':['字段','有效数值数','合计','平均值','最小值','最大值','单位','未参与行数'],'rows':[],'notes':[],'input_rows':0}
    group_by=spec.get('group_by',[])
    if not group_by:return compute(target)
    groups={}
    for index,row in enumerate(table['rows']):groups.setdefault(tuple(row[columns.index(c)] for c in group_by),[]).append(target['rows'][index])
    result=None
    for key,rows in groups.items():
        metric=compute({'columns':target['columns'],'rows':rows})
        if result is None:result={'columns':group_by+metric['columns'],'rows':[],'notes':[],'input_rows':len(table['rows'])}
        result['rows'].extend([list(key)+r for r in metric['rows']]);result['notes'].extend(metric['notes'])
    return result

def search_query(prompt):
    clause=re.split(r'[，,；;\n]',prompt)[0]
    quoted=re.findall(r'[“"「]([^”"」]{1,80})[”"」]',clause)
    if quoted:return ' '.join(quoted)
    clause=re.sub(r'^.*?(?:查找|检索|搜索|找出|找一下|搜一下|搜一搜)\s*','',clause)
    clause=re.sub(r'^(?:包含|提到|有关|关于|这些|所有|全部|一下|一下子)\s*','',clause)
    clause=re.sub(r'(?:相关|有关)?(?:的)?(?:资料|文件|内容|记录).*?$','',clause).strip(' ：:。?？')
    return clause[:120]

def search_documents(documents,query):
    terms=[normal(x) for x in re.split(r'[\s、]+',query) if x.strip()]
    if not terms:raise ValueError('请写出要查找的词，例如：查找“交通”相关资料。')
    hits=[]
    for doc in documents:
        name=normal(doc['name']);body=normal(doc['text'])
        if not all(t in name or t in body for t in terms):continue
        lines=doc['text'].splitlines() or [doc['text']]
        ranked=[(sum(normal(line).count(t) for t in terms),i,line) for i,line in enumerate(lines)]
        _,line_number,_=max(ranked,key=lambda x:(x[0],-x[1]))
        snippet='\n'.join(lines[max(0,line_number-1):line_number+3])[:500]
        score=sum(body.count(t)+3*name.count(t) for t in terms)
        hits.append({'id':doc['id'],'name':doc['name'],'path':doc['path'],'snippet':snippet,'line':line_number+1,'score':score})
    return sorted(hits,key=lambda h:(-h['score'],h['name']))
