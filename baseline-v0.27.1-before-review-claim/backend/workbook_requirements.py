"""Literal, source-bound arithmetic requirements; no business-default formulas."""
import re
from table_semantics import header_unit


def explicit_binary(goal, name, columns):
    """Bind a fully stated `new = left op right` clause to unique real fields.

    Compound arithmetic, ambiguous aliases and unspecified definitions remain
    with the planner.  A prefix of a longer formula is never compiled.
    """
    _,target=header_unit(name)
    target=target.strip()
    if not target:return None,None
    aliases={}
    for column in columns:
        _,stem=header_unit(column)
        for alias in (column,stem.strip()):
            if alias and not alias.isdigit():aliases.setdefault(alias.casefold(),set()).add(column)
    unique={k:next(iter(v)) for k,v in aliases.items() if len(v)==1}
    if not unique:return None,None
    fields='|'.join(re.escape(v) for v in sorted(unique,key=len,reverse=True))
    operator=r'减去?|加上?|乘以?|除以?|[+＋\-−×*÷/]|minus|plus|times|divided\s+by'
    boundary=r'(?:^|[，,。；;\n]|计算|求出|新增|其中|定义|令|设定|calculate\s+)\s*'
    pattern=boundary+re.escape(target)+r'\s*(?:按|为|是|等于|定义为|=|：|:)\s*(?P<a>'+fields+r')\s*(?P<op>'+operator+r')\s*(?P<b>'+fields+r')'
    matches=[]
    for match in re.finditer(pattern,goal,re.I):
        prefix=goal[max(0,match.start()-14):match.start()]
        if re.search(r'(?:不要|不必|不需要|不应|禁止|别|例如|比如|假设|举例).{0,8}$',prefix):continue
        later=re.split(r'[，,。；;\n]',goal[match.end():])[1:]
        if any(re.search(r'改为|改成|更正为|替换为',clause) and re.search(operator,clause,re.I)
               and len(list(re.finditer(fields,clause,re.I)))>=2 for clause in later):continue
        tail=re.split(r'[，,。；;\n]',goal[match.end():],maxsplit=1)[0].strip()
        tail=tail.rstrip('.!！').strip()
        if tail and not re.fullmatch(r'(?:计算|算出|得到|计算得到)(?:即可|就行)?',tail):continue
        token=match['op'].casefold()
        kind='subtract' if re.fullmatch(r'减去?|[-−]|minus',token) else 'add' if re.fullmatch(r'加上?|[+＋]|plus',token) else 'multiply' if re.fullmatch(r'乘以?|[×*]|times',token) else 'divide'
        expression={kind:[{'column':unique[match['a'].casefold()]},{'column':unique[match['b'].casefold()]}]}
        matches.append((expression,match.group().lstrip('，,。；;\n ')))
    if not matches or any(expr!=matches[0][0] for expr,_ in matches):return None,None
    return matches[0]


def raw_numeric_requirements(goal,source):
    """Only explicit single-record bounds on exact, unique source labels."""
    from workbook_intent import literal_numeric_requirements,compact
    candidates=[]
    for clause in re.split(r'[，,。；;\n]',goal):
        for name in source['columns']:
            _,stem=header_unit(name)
            if not stem:continue
            literal=re.escape(compact(stem.strip()))
            row_bound=re.search(r'(?:单[票笔条次个份]|每[票笔条次个份])'+literal+r'(?:须|需|必须|要|应|为|是|的)?(?:不少于|不超过|大于|小于|至少|至多|高于|低于|超过|不足|>=|<=|>|<|≥|≤)',compact(clause))
            if not row_bound:continue
            for requirement in literal_numeric_requirements(clause,source):
                if requirement['column']==name and requirement not in candidates:candidates.append(requirement)
    return candidates


def literal_empty_requirements(goal,source):
    """Only explicit blank/nonblank requirements on unique source labels.

    Disjunctions, examples and negated removals need semantic planning. This
    does not infer required contact fields or treat zero as a missing value.
    """
    aliases={}
    for name in source['columns']:
        _,stem=header_unit(name)
        for alias in {name,stem.strip()}:
            if alias:aliases.setdefault(alias,set()).add(name)
    result=[]
    for clause in re.split(r'[，,。；;\n]',goal):
        if re.search(r'或|除非|如果|假如|例如|比如',clause):continue
        for alias,names in aliases.items():
            if len(names)!=1:continue
            missing=r'(?:为?空(?:白|值)?|没(?:有)?填(?:写)?|未填(?:写)?|缺失)'
            patterns=[r'(?:剔除|排除|去掉|过滤掉|删除|不保留)\s*(?:所有)?\s*'+re.escape(alias)+r'\s*'+missing+r'(?:的|记录|行)*',
                      r'(?:剔除|排除|去掉|过滤掉|删除|不保留)[^，,。；;\n]{1,60}?(?:和|及|与|、)\s*'+re.escape(alias)+r'\s*'+missing+r'(?:的|记录|行)*',
                      r'(?:把|将)?\s*'+re.escape(alias)+r'\s*'+missing+r'(?:的|记录|行)*\s*(?:去掉|剔除|排除|不保留)']
            match=next((m for pattern in patterns if (m:=re.search(pattern,clause))),None)
            if match and re.search(r'(?:不(?:要|用|必|需|需要|应)|别|勿|禁止).{0,3}$',clause[:match.start()]):continue
            if match:operator='not_empty'
            else:
                match=re.search(re.escape(alias)+r'\s*'+missing,clause)
                if not match or re.search(r'(?:不(?:要|用|必|需|需要|应)|别|勿|禁止|排除|剔除|去掉).{0,3}$',clause[:match.start()]):continue
                if re.search(r'排除|剔除|去掉|过滤掉|不保留|不要|禁止',clause[:match.start()]):continue
                if re.match(r'(?:的|记录|行)*\s*(?:不要|不保留|去掉|剔除|排除)',clause[match.end():]):continue
                operator='is_empty'
            field_start=match.start()+match.group().find(alias)
            if any(len(other)>len(alias) and other.endswith(alias) and clause[:field_start+len(alias)].endswith(other)
                   for other in aliases):continue
            rule={'column':next(iter(names)),'operator':operator,'type':'text','quote':match.group()}
            if rule not in result:result.append(rule)
    # Separate empty/nonempty branches are not a single global source scope.
    return [r for r in result if len({x['operator'] for x in result if x['column']==r['column']})==1]


def literal_nonempty_requirements(goal,source):
    return [r for r in literal_empty_requirements(goal,source) if r['operator']=='not_empty']


def compile_empty_polarity(node,goal,source):
    """Repair only the truth direction of a quoted literal empty-cell test."""
    rules={r['column']:r for r in literal_empty_requirements(goal,source)};notes=[]
    def visit(value):
        if not isinstance(value,dict) or 'any' in value or 'not' in value:return
        if 'all' in value:
            for child in value['all']:visit(child)
            return
        rule=rules.get(value.get('column'))
        if not rule or 'value_column' in value:return
        operator=value.get('operator');v=value.get('value')
        blank=v=='' or (isinstance(v,str) and not v.strip()) or (isinstance(v,list) and len(v)==1 and isinstance(v[0],str) and not v[0].strip())
        if operator not in ('is_empty','not_empty') and not (blank and operator in ('eq','ne','in','not_in')):return
        after={k:v for k,v in rule.items() if k!='quote'}
        if value==after:return
        before=dict(value);value.clear();value.update(after)
        notes.append({'kind':'literal_empty_polarity','before':before,'after':dict(value),'quote':rule['quote']})
    visit(node);return notes


def qualifies_before_limit(goal,quote):
    """Keep explicit 'first N, then filter' requests in that stated scope."""
    position=goal.find(quote)
    if position<0:return False
    cutoff=re.search(r'(?:取|保留|只看|只要|选)?前\s*[0-9一二两三四五六七八九十]+\s*(?:条|笔|名|项|个|行)',goal)
    return cutoff is None or position<cutoff.start()


def result_ordering(graph,result):
    """Stable order along the delivered path, stopping at aggregation."""
    from table_program import TableError
    if not isinstance(graph,list) or len(graph)>16:raise TableError('历史处理图超过核对范围。')
    steps={step['id']:step for step in graph};keys=[];seen=set();cursor=result;visited=set()
    while cursor in steps:
        if cursor in visited:raise TableError('历史排序依赖存在循环，请从原始资料重新开始。')
        visited.add(cursor)
        step=steps[cursor];operation=step['operation']
        if operation['op']=='group':break
        if operation['op']=='sort':
            for key in operation['by']:
                if key['column'] not in seen:keys.append(dict(key));seen.add(key['column'])
        cursor=step['input']
    if len(keys)>8:raise TableError('结果排序超过8个字段，请明确简化排序要求。')
    return keys


def changes_ordering(goal):
    if re.search(r'(?:不|取消|无需|不要).{0,3}排序|升序|降序|逆序|反过来|倒过来|(?:从|由)(?:高到低|低到高|多到少|少到多|早到晚|晚到早|大到小|小到大|近到远|远到近)',goal):return True
    if re.search(r'按(?:原|上轮|之前|此前).{0,4}(?:排序|顺序)|(?:排序|顺序)(?:保持)?不变',goal):return False
    return bool(re.search(r'按[^，,。；;]{1,35}(?:排序|排列)',goal))
