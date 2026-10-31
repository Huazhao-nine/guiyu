"""Conservative checks for explicit instructions, independent of workbook examples."""
import re
from table_program import TableError, number, calendar_date
from table_semantics import header_unit, quantity


def compact(text):
    return re.sub(r'\s|[「」“”"`]', '', str(text)).lower()


def check_predicate(node):
    """Reject provably contradictory conjunctions before they erase the source."""
    if not isinstance(node, dict):
        return
    for key in ('all', 'any'):
        for child in node.get(key, []):
            check_predicate(child)
    if 'not' in node:
        check_predicate(node['not'])
    if 'all' not in node:
        return
    leaves=[]
    def flatten(value):
        if 'all' in value:
            for child in value['all']: flatten(child)
        elif 'column' in value and 'value' in value and not isinstance(value['value'], list):
            leaves.append(value)
    flatten(node)
    for i,a in enumerate(leaves):
        for b in leaves[i+1:]:
            if (a['column'],a.get('type')) != (b['column'],b.get('type')):
                continue
            av,bv=a['value'],b['value']
            if a.get('type')=='number':
                av,bv=number(av),number(bv)
            elif a.get('type')=='date':
                av,bv=calendar_date(av),calendar_date(bv)
            else:
                av,bv=compact(av),compact(bv)
            ops={a.get('operator'),b.get('operator')}
            impossible=(av==bv and ops in ({'eq','ne'},{'gt','lte'},{'gte','lt'})) or (av!=bv and ops=={'eq'})
            if av is not None and bv is not None and a.get('type') in ('number','date'):
                compare={'eq':lambda x,y:x==y,'ne':lambda x,y:x!=y,'gt':lambda x,y:x>y,
                         'gte':lambda x,y:x>=y,'lt':lambda x,y:x<y,'lte':lambda x,y:x<=y}
                ao,bo=a.get('operator'),b.get('operator')
                if ao=='eq' and bo in compare:impossible|=not compare[bo](av,bv)
                if bo=='eq' and ao in compare:impossible|=not compare[ao](bv,av)
                lower,upper=(a,b) if ao in ('gt','gte') and bo in ('lt','lte') else ((b,a) if bo in ('gt','gte') and ao in ('lt','lte') else (None,None))
                if lower:
                    lv,uv=(av,bv) if lower is a else (bv,av)
                    impossible|=lv>uv or (lv==uv and ('gt'==lower['operator'] or 'lt'==upper['operator']))
            if impossible:
                raise TableError('条件在同一个“且”中互相矛盾：'+a['column']+'。请依据用户原话修正，不要把工具条件错误当作没有符合条件的资料。')


def explicit_keys(goal,columns):
    """Compile only literal, unambiguous keys; aliases still require the model."""
    goal,_=positive_intent(goal)
    contracts=[]
    from workbook_qualifiers import initial_distinct_keys
    initial=initial_distinct_keys(goal,columns)
    if initial:contracts.append(initial)
    phrases=list(re.finditer(r'按([^，,。；;\n]{1,120}?)(?:去重|去除重复|消除重复)',goal))
    phrases+=list(re.finditer(r'([^，,。；;\n]{1,100}?)相同.{0,12}?只(?:留|保留)',goal))
    phrases+=list(re.finditer(r'同一([^，,。；;\n]{1,80}?)只(?:留|保留)',goal))
    for m in phrases:
        phrase=re.sub(r'^(?:同一|先|再)+','',compact(m[1]));matches=[]
        for c in sorted(columns,key=len,reverse=True):
            key=compact(c)
            if key and key in phrase:
                matches.append(c);phrase=phrase.replace(key,'',1)
        if not matches or re.sub(r'[、,，/及和与]|字段|进行|先|再','',phrase):
            continue
        contracts.append(matches)
    if contracts and any(set(keys)!=set(contracts[0]) for keys in contracts[1:]):
        raise TableError('用户指定了不同的去重键，不能自动选择其中一组。请确认这次以哪些字段判断重复。')
    return contracts[0] if contracts else None


def check_explicit_keys(operation,goal,columns,repair=False):
    if operation['op']!='distinct':return []
    keys=explicit_keys(goal,columns)
    if not keys or set(operation['columns'])==set(keys):return []
    if not repair:
        raise TableError('去重键与用户明确指定的字段不一致，应仅使用：'+'、'.join(keys)+'。分组字段不能擅自加入去重键。')
    before=list(operation['columns']);operation['columns']=keys
    return [{'kind':'literal_dedup_keys','before':before,'after':list(keys),'evidence':'explicit user key clause matched actual columns'}]


BOUNDARIES={'不少于':'gte','不低于':'gte','至少':'gte','不超过':'lte','至多':'lte',
            '大于':'gt','超过':'gt','高于':'gt','小于':'lt','少于':'lt','低于':'lt','不足':'lt','等于':'eq'}


def compile_column_comparisons(node,goal,view):
    """Repair only AND leaves bound to the same literal pair of real columns.

    A shorter left label may be an unambiguous suffix of one actual field;
    the right label must be exact. Arithmetic phrases are never shortened.
    """
    text=compact(goal)
    markers=r'找出|筛选|筛出|保留|只看|选出|并且|且|同时满足|满足'
    negative=r'(?:不(?:想|要|用|应当|应该|应|必|需(?:要)?|得|能)?|别|莫|勿|请勿|无需|无须|禁止|避免|未)'
    if re.search(negative+r'(?:再|继续|仅|只|直接|自行)*(?:'+markers+r')',text):return []
    if re.search(r'或|任意|任一|除非|假如|如果|例如|比如|否则|排除|不要|剔除|去掉|不选|不取|不满足|并非|不是',text):return []
    aliases={}
    for name in view['columns']:
        if view.get('field_types',{}).get(name) not in ('number','percent','date'):continue
        labels={name,header_unit(name)[1].strip()}
        original=view.get('unit_ledger',{}).get(name,{}).get('source_column')
        if original:labels.update((original,header_unit(original)[1].strip()))
        aliases[name]={compact(label) for label in labels if compact(label)}
    operators=dict(BOUNDARIES,**{'不大于':'lte','不小于':'gte','不早于':'gte','不晚于':'lte','早于':'lt','晚于':'gt',
                               '>=':'gte','<=':'lte','>':'gt','<':'lt','≥':'gte','≤':'lte','==':'eq','=':'eq'})
    pattern='|'.join(re.escape(word) for word in sorted(operators,key=len,reverse=True))
    # Denial can include arbitrary auxiliaries (e.g. 不允许再保留). Inspect the
    # local prefix of each syntax marker, rather than enumerating every verb.
    for raw_clause in re.split(r'[，,。；;\n]',goal):
        clause=compact(raw_clause);start=0
        for marker in re.finditer(markers,clause):
            prefix=clause[start:marker.start()];start=marker.end()
            if not re.search(pattern,prefix) and re.search(r'[不别勿未非无禁]|避免',prefix):return []
    reverse={'gt':'lt','gte':'lte','lt':'gt','lte':'gte','eq':'eq','ne':'ne'}
    def signature(left,operator,right):
        return (left,operator,right) if left<right else (right,reverse[operator],left)
    claims={}
    for raw_clause in re.split(r'[，,。；;\n]',goal):
        clause=compact(raw_clause)
        for match in re.finditer(pattern,clause):
            before=clause[:match.start()];after=clause[match.end():]
            right_matches={name for name,labels in aliases.items() for label in labels if after.startswith(label) and
                           (not after[len(label):] or re.match(r'的|且|并且|以及|同时|而且',after[len(label):]))}
            if len(right_matches)!=1:continue
            right=next(iter(right_matches))
            exact={name for name,labels in aliases.items() if before in labels}
            if not exact:
                cuts=list(re.finditer(markers,before));phrase=before[cuts[-1].end():] if cuts else before
                exact={name for name,labels in aliases.items() if phrase in labels}
                if not exact:
                    phrase=re.sub(r'(?:必须|需要|须|需|应|要)$','',phrase)
                    exact={name for name,labels in aliases.items() if phrase in labels}
                if not exact and phrase:
                    exact={name for name,labels in aliases.items() if name!=right and any(label.endswith(phrase) for label in labels)}
            if len(exact)!=1:continue
            left=next(iter(exact))
            if left==right:continue
            operator=operators[match[0]];key=frozenset((left,right))
            claims.setdefault(key,{})[signature(left,operator,right)]={'column':left,'operator':operator,'value_column':right,'quote':raw_clause.strip()}
    corrections=[]
    def visit(value):
        if not isinstance(value,dict):return
        if set(value)=={'all'}:
            for child in value['all']:visit(child)
            return
        if 'any' in value or 'not' in value:return
        left=value.get('column');right=value.get('value_column');operator=value.get('operator')
        if value.get('type') not in ('number','date') or not left or not right or operator not in reverse:return
        bound=claims.get(frozenset((left,right)),{})
        if len(bound)!=1:return
        expected=next(iter(bound.values()))
        def dimension(name):return 'ratio' if view.get('field_types',{}).get(name)=='percent' else view.get('units',{}).get(name,'')
        if dimension(left)!=dimension(right):raise TableError('用户比较的两字段单位维度不同，不能直接比较：'+left+'、'+right+'。')
        if signature(left,operator,right) in bound:return
        before=dict(value)
        value.update({key:expected[key] for key in ('column','operator','value_column')})
        corrections.append({'kind':'literal_column_comparison','before':before,'after':dict(value),
                            'quote':expected['quote'],'evidence':'literal comparison bound to the same actual column pair'})
    visit(node)
    return corrections


def check_explicit_boundaries(node,goal,view):
    if not isinstance(node,dict):return
    for key in ('all','any'):
        for child in node.get(key,[]):check_explicit_boundaries(child,goal,view)
    if 'not' in node:return  # Negated wording requires semantic interpretation.
    if node.get('type')!='number' or 'value' not in node or isinstance(node['value'],list):return
    name=node['column'];_,stem=header_unit(name)
    aliases=[stem.strip()]
    original=view.get('unit_ledger',{}).get(name,{}).get('source_column')
    if original:aliases.append(header_unit(original)[1].strip())
    text=compact(goal)
    for alias in aliases:
        if not alias:continue
        pattern=re.escape(compact(alias))+r'(?:须|需|必须|要|应|为|是|在|达到|的|金额|数值|门槛)*('+ '|'.join(BOUNDARIES)+r')([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:万元|千元|元|千美元|万美元|USD|CNY|kg|千克|克|g|小时|分钟|[%％])?)'
        m=re.search(pattern,text,re.I)
        if not m:continue
        if re.search(r'(?:不要|排除|剔除|去掉)[^，,。；;]{0,4}$',text[:m.start()]):continue
        try:expected,_=quantity(m[2]);actual=number(node['value'])
        except TableError:continue
        if expected==actual and node.get('operator')!=BOUNDARIES[m[1]]:
            raise TableError('条件边界与用户原话“'+m[1]+'”不一致：'+name+'应使用'+BOUNDARIES[m[1]]+'，不能遗漏或加入边界记录。')


def explicit_division(goal,divisor):
    """A user-specified allocation/division is arithmetic, even at a unit ratio."""
    from fractions import Fraction
    from general_assistant import numbers
    operators=r'除以?|[/÷]|分给|分摊|均分|平分|分配|缩小|(?i:divided?\s+by|split|allocate)'
    text=re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))','',goal)
    for clause in re.split(r'[，,。；;\n]',text):
        if Fraction(divisor) not in numbers(clause):continue
        if re.search(r'换算|转换|转成|转为|换成|显示|展示|表示|输出单位',clause):continue
        for match in re.finditer(operators,clause):
            if not re.search(r'(?:不要|不必|无需|不用|不需要|别|不能|不应).{0,6}$',clause[:match.start()]):return True
    return False


def literal_numeric_requirements(goal,view):
    """Gate detail delivery on explicit, field-bound AND comparisons.

    Only exact observed field labels and explicit numbers/units are compiled.
    Disjunctions, exclusions, hypothetical examples and ambiguous field aliases
    stay with semantic planning. The canonical view is checked before display
    conversion or projection, so office-unit presentation cannot change facts.
    """
    text=compact(goal);claims={}
    from table_semantics import UNITS,unit_definition
    units='|'.join(re.escape(u) for u in sorted(UNITS,key=len,reverse=True))
    number_pattern=r'[+-]?(?:\d+(?:,\d{3})*(?:\.\d*)?|\.\d+)'
    for name in view['columns']:
        if view.get('field_types',{}).get(name) not in ('number','percent'):continue
        default,stem=header_unit(name);literal_aliases={compact(stem.strip())}
        original=view.get('unit_ledger',{}).get(name,{}).get('source_column')
        if original:literal_aliases.add(compact(header_unit(original)[1].strip()))
        aliases=set(literal_aliases)
        # Ordinary requests often omit a measure noun. Bind only a complete
        # retained stem; claims shared by multiple real fields stay ambiguous.
        shortened=re.sub(r'(?:金额|数额|数量)$','',compact(stem.strip()))
        if len(shortened)>=2:aliases.add(shortened)
        for alias in aliases:
            if not alias:continue
            pattern=re.escape(alias)+r'(?:须|需|必须|要|应|为|是|在|达到|的|金额|数值|门槛)*('+ '|'.join(BOUNDARIES)+')('+number_pattern+r'(?:'+units+r')?)'
            for match in re.finditer(pattern,text,re.I):
                left=max((text.rfind(c,0,match.start()) for c in '，,。；;\n'),default=-1)+1
                prefix=text[left:match.start()]
                if re.search(r'不|别|勿|未|禁止|避免|无需|无须',prefix):continue
                if alias not in literal_aliases:
                    if prefix and not re.search(r'(?:挑出|找出|筛选出|筛出|筛选|只要|只看|仅保留|保留|且|并且|而且|同时|要求|满足)[“「\"]?$',prefix):continue
                ends=[p for c in '，,。；;\n' if (p:=text.find(c,match.end()))>=0]
                clause=text[left:min(ends) if ends else len(text)]
                if re.search(r'或|任意|除非|假如|如果|例如|比如|排除|不要|剔除|不选|不取|不只|不限制|别|勿|禁止|避免|不允许|不能|不应|不用|不需要|不保留|不满足|未满足',clause):continue
                try:expected,_=quantity(match[2],default)
                except TableError:continue
                key=(match.start(),match.end(),BOUNDARIES[match[1]],expected)
                claims.setdefault(key,{})[name]=match[0]
    result=[]
    for (_,_,op,expected),fields in claims.items():
        if len(fields)!=1:continue
        name,quote=next(iter(fields.items()))
        result.append({'column':name,'operator':op,'value':expected,'quote':quote})
    return result


def check_literal_numeric_bounds(goal,view):
    comparisons={'gte':lambda a,b:a>=b,'gt':lambda a,b:a>b,'lte':lambda a,b:a<=b,'lt':lambda a,b:a<b,'eq':lambda a,b:a==b}
    for requirement in literal_numeric_requirements(goal,view):
        name,op,expected,quote=(requirement[k] for k in ('column','operator','value','quote'))
        index=view['columns'].index(name)
        for row in view['rows']:
            try:value=number(row[index])
            except TableError:value=None
            if value is None or not comparisons[op](value,expected):
                exc=TableError('交付仍有记录不满足用户明确条件“'+quote+'”。请在明细视图对“'+name+'”落实'+op+' '+str(expected)+'的筛选，并更新相关汇总后再finish。')
                exc.repair_predicate={'column':name,'operator':op,'type':'number','value':str(expected)};exc.repair_quote=quote
                raise exc


def literal_calendar_requirements(goal,view,bindings=()):
    """Bind complete ISO/Chinese ranges, inheriting only an explicit year/month.

    Ambiguous fields, disjunctions and exclusive endpoints need normal semantic
    planning. No current year, cross-year rollover or business calendar is guessed.
    """
    from table_program import calendar_date
    aliases={c:{header_unit(c)[1].strip()} for c in view['columns'] if view.get('field_types',{}).get(c)=='date'}
    for binding in bindings:
        if binding.get('column') in aliases:aliases[binding['column']].add(binding['requested'])
    iso=r'(?P<sy>\d{4})-(?P<sm>\d{1,2})-(?P<sd>\d{1,2})\s*(?:至|到|–|~|～|—)\s*(?P<ey>\d{4})-(?P<em>\d{1,2})-(?P<ed>\d{1,2})'
    chinese=r'(?P<sy>\d{4})年(?P<sm>\d{1,2})月(?P<sd>\d{1,2})日?\s*(?:至|到|–|~|～|—)\s*(?:(?P<ey>\d{4})年)?(?:(?P<em>\d{1,2})月)?(?P<ed>\d{1,2})日'
    claims={}
    for name,labels in aliases.items():
        for label in labels:
            for dates in (iso,chinese):
                pattern=re.escape(label)+r'(?:的)?(?:在|为|是|范围为)?\s*'+dates
                for match in re.finditer(pattern,goal,re.I):
                    left=max((goal.rfind(c,0,match.start()) for c in '，,。；;\n'),default=-1)+1
                    end=re.search(r'[，,。；;\n]',goal[match.end():]);clause=goal[left:match.end()+end.start() if end else len(goal)]
                    if re.search(r'排除|不要|例如|比如|或者|或|假如|如果|不只|不限制|不含|不包括|不包含|不计',clause):continue
                    if re.match(r'[\s，,;；（()）]*(?:但)?(?:不含|不包含|不包括)(?:结束日|截止日|最后一天|两端|起止日|开始日)',goal[match.end():]):continue
                    start=calendar_date(f"{match['sy']}-{int(match['sm']):02}-{int(match['sd']):02}")
                    end=calendar_date(f"{match['ey'] or match['sy']}-{int(match['em'] or match['sm']):02}-{int(match['ed']):02}")
                    if start>end:raise TableError('日期范围的开始晚于结束，不能自动交换或猜跨年。')
                    claims.setdefault((match.start(),match.end(),start,end),{})[name]=match.group()
    # A full calendar month is an exact interval. Only bind a named date field
    # or the single date field actually present; never choose among dates.
    import calendar
    for match in re.finditer(r'(?P<year>\d{4})年\s*(?P<month>\d{1,2})月\s*(?:整月|全月|整个月)',goal):
        left=max((goal.rfind(c,0,match.start()) for c in '，,。；;\n'),default=-1)+1
        end=re.search(r'[，,。；;\n]',goal[match.end():]);clause=goal[left:match.end()+end.start() if end else len(goal)]
        if re.search(r'排除|不要|例如|比如|或者|或|假如|如果|不只|不限制|不含|不包括|不包含|不计',clause):continue
        if re.match(r'[\s，,;；（()）]*(?:但)?(?:不含|不包含|不包括)(?:月初|月底|两端|起止日)',goal[match.end():]):continue
        names=[name for name,labels in aliases.items() if any(re.search(re.escape(label)+r'(?:的)?(?:在|为|是|范围为)?\s*$',goal[left:match.start()],re.I) for label in labels)]
        if not names and len(aliases)==1:names=list(aliases)
        if len(names)!=1:continue
        year,month=int(match['year']),int(match['month'])
        if not 1<=month<=12:raise TableError('月份应在1至12之间。')
        start=calendar_date(f'{year:04}-{month:02}-01')
        stop=calendar_date(f'{year:04}-{month:02}-{calendar.monthrange(year,month)[1]:02}')
        claims[(match.start(),match.end(),start,stop)]={names[0]:match.group()}
    result=[]
    for (_,_,start,end),fields in claims.items():
        if len(fields)!=1:continue
        name,quote=next(iter(fields.items()))
        result.extend({'column':name,'operator':operator,'type':'date','value':limit.isoformat(),'quote':quote}
                      for operator,limit in [('gte',start),('lte',end)])
    return result


def check_literal_calendar_bounds(goal,view,bindings=()):
    from table_program import calendar_date
    from workbook_requirements import qualifies_before_limit
    for bound in literal_calendar_requirements(goal,view,bindings):
        index=view['columns'].index(bound['column']);limit=calendar_date(bound['value'])
        if any(not row[index] or (calendar_date(row[index])<limit if bound['operator']=='gte' else calendar_date(row[index])>limit) for row in view['rows']):
            exc=TableError('交付仍有记录不满足明确日期范围“'+bound['quote']+'”。')
            exc.repair_predicate={k:v for k,v in bound.items() if k!='quote'};exc.repair_quote=bound['quote'];exc.repair_before_limits=qualifies_before_limit(goal,bound['quote']);raise exc


def compile_calendar_month_bounds(node,goal,view):
    """Correct AND date endpoints only for a uniquely bound complete month.

    Calendar arithmetic supplies the endpoint, not the rows that happened to be
    observed. Additional explicit date comparisons, OR and NOT remain semantic
    planning tasks; they must not be widened by this check.
    """
    from table_program import calendar_date
    bounds=[b for b in literal_calendar_requirements(goal,view)
            if re.search(r'整月|全月|整个月',b['quote'])]
    if not bounds:return []
    if re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}月\s*\d{1,2}日|早于|晚于|之前|之后',goal):return []
    changes=[]
    def visit(value):
        if 'all' in value:
            for child in value['all']:visit(child)
            return
        if 'any' in value or 'not' in value or value.get('type')!='date':return
        operator=value.get('operator')
        bound=next((b for b in bounds if b['column']==value.get('column') and
                    ((operator in ('gte','gt') and b['operator']=='gte') or
                     (operator in ('lte','lt') and b['operator']=='lte'))),None)
        if not bound:return
        date=calendar_date(value['value']);expected=calendar_date(bound['value'])
        from datetime import timedelta
        effective=date+(timedelta(days=1) if operator=='gt' else -timedelta(days=1) if operator=='lt' else timedelta())
        if effective==expected:return
        before=dict(value)
        value.update(operator=bound['operator'],value=bound['value'])
        changes.append({'kind':'calendar_month_endpoint','before':before,'after':dict(value),
                        'quote':bound['quote'],'evidence':'Exact Gregorian month endpoints from the explicit year, month and real date field.'})
    visit(node)
    return changes


def check_literal_inclusions(goal,view,source=None):
    """A unique observed category may be selected by an explicit positive clause."""
    values={};source=source or view
    for i,name in enumerate(source['columns']):
        if name not in view['columns']:continue
        if view.get('field_types',{}).get(name)!='text':continue
        for row in source['rows']:
            value=str(row[i])
            if 2<=len(value)<=40 and value in goal:values.setdefault(value,set()).add(name)
    for value,fields in values.items():
        if len(fields)!=1:continue
        match=re.search(r'(?:只看|只要|只处理|仅处理|仅统计|只统计|仅保留|只保留)\s*[“「\"]?'+re.escape(value)+
                        r'|'+re.escape(value)+r'[”」\"]?\s*(?:的(?:记录|数据|结果))?\s*单独(?:列出|列出来|查看|统计|保留|展示|显示)',goal)
        if not match or re.search(r'(?:不|不要|不必|不是|不需要|不用|无需|别)\s*(?:把|将)?\s*$',goal[:match.start()]):continue
        # A comma can separate two branches of the same OR requirement. A
        # single-value shortcut cannot narrow that whole sentence to branch A.
        left=max((goal.rfind(c,0,match.start()) for c in '。；;\n'),default=-1)+1
        end=re.search(r'[。；;\n]',goal[match.end():]);clause=goal[left:match.end()+end.start() if end else len(goal)]
        if re.search(r'或|例如|比如|如果|假如',clause):continue
        name=next(iter(fields));index=view['columns'].index(name)
        if any(str(row[index])!=value for row in view['rows']):
            exc=TableError('交付仍包含用户明确选择“'+value+'”之外的类别。')
            exc.repair_predicate={'column':name,'operator':'eq','type':'text','value':value};exc.repair_quote=match[0];raise exc


def needs_global_summary(goal):
    return bool(re.search(r'(?:这批|本批|本次|整批|全部结果|所有结果|总体|整体).{0,24}(?:合计|总计|总额|总数)|(?:总金额|总成本|总费用|总人数|总条数)',goal))


def positive_intent(goal):
    negative=set();text=goal
    verbs={'distinct':r'去重|去除重复|消除重复','sort':r'排序|升序|降序|[从由](?:高到低|低到高|多到少|少到多|早到晚|晚到早)',
           'group':r'分组|汇总|统计','derive':r'计算'}
    prefix=r'(?:不要|不需要|不必|无需|不用|不)(?:再|自行|额外|进行)?(?:按[^，,。；;\n]{1,40}?)?'
    for tool,words in verbs.items():
        def remove(match):negative.add(tool);return ''
        text=re.sub(prefix+'(?:'+words+')',remove,text)
    return text,negative


def required_operations(goal):
    """An early handoff hint only; the separate semantic review still decides."""
    goal,_=positive_intent(goal)
    words={
        'filter':r'筛|挑出|找出|只看|排除|剔除|低于|不足|大于|小于|不少于|不超过',
        'derive':r'计算|[=＝]|(?:减|乘|除以).{0,15}(?:算|金额|数量)',
        'group':r'汇总|合计|总计|平均|统计.{0,15}(?:数|金额|费用|工时)|种数|条数',
        'distinct':r'去重|去除重复|消除重复|相同.{0,10}只留',
        'sort':r'升序|降序|[从由](?:高到低|低到高|多到少|少到多|晚到早|早到晚)',
        'limit':r'前\s*[0-9一二三四五六七八九十]+(?:条|笔|名|项|个)',
    }
    return {tool for tool,pattern in words.items() if re.search(pattern,goal)}


def check_forbidden_tool(tool,goal):
    positive,negative=positive_intent(goal)
    if tool in negative and tool not in required_operations(positive):raise TableError('用户已明确要求不执行'+tool+'，请保留该限制并交付已有正确结果。')


def enforced_restrictions(goal):
    positive,negative=positive_intent(goal)
    return sorted(negative-required_operations(positive))


def check_excluded_column_scope(node,goal):
    """Header partitions excluded from metrics must not become invented row tests."""
    if not isinstance(node,dict):return
    for key in ('all','any'):
        for child in node.get(key,[]):check_excluded_column_scope(child,goal)
    if 'not' in node:check_excluded_column_scope(node['not'],goal)
    name=node.get('column','');parts=re.split(r'\s+/\s+|\s*/\s*',name)
    if len(parts)<2:return
    for label in parts[:-1]:
        if not label or len(label)>80:continue
        for clause in re.split(r'[，,。；;\n]',goal):
            match=re.search(r'(?:不要|不应|不需|无需|不把|不含|排除|忽略|不计|不包括|剔除).{0,16}?'+re.escape(label),clause)
            if not match:continue
            after=clause[match.end():match.end()+35]
            if re.search(r'(?:等于|大于|小于|高于|低于|不足|至少|至多|超过|为|是)\s*(?:[+-]?\d|零)|为空|空白|缺失',after):continue
            exc=TableError('用户排除“'+label+'”的是统计列范围，不能把该列为空或等于某值当作行条件。请保留原始行，从未受这个条件影响的视图继续，仅选择用户指定列参与汇总。')
            exc.error_code='column_scope'
            raise exc


def verified_calendar_row_clause(clause,source_scope):
    """Distinguish an already executed date constraint from an output label."""
    if not source_scope:return False
    source,verified=source_scope
    bounds=literal_calendar_requirements(clause,source)
    if not bounds or len({b['column'] for b in bounds})!=1:return False
    name=bounds[0]['column'];stem=header_unit(name)[1].strip();text=compact(clause)
    label=compact(stem)
    if not text.startswith(label):return False
    text=text[len(label):]
    for quote in {b['quote'] for b in bounds}:text=text.replace(compact(quote),'')
    if re.sub(r'范围|记录|数据|明细|结果|在|为|是|的|从|至|到|起|内|中','',text):return False
    return all(verified({k:v for k,v in bound.items() if k!='quote'}) for bound in bounds)


def literal_exclusions(goal,source,inherited=()):
    """Bind explicit excluded values only to a unique, observed text field."""
    candidates={}
    for i,c in enumerate(source['columns']):
        if source.get('field_types',{}).get(c) not in ('text','boolean'):continue
        for value in set(r[i] for r in source['rows']):
            value=str(value)
            if 2<=len(value)<=80 and value in goal:candidates.setdefault(value,set()).add(c)
    fresh=[]
    prefix=r'(?:排除|不含|不包含|不包括|剔除|去掉|除去|不要包含|不要包括)'
    for value,fields in candidates.items():
        if len(fields)!=1:continue
        c=next(iter(fields));label=re.escape(c)
        pattern=prefix+r'\s*(?:(?:所有|全部|其中的|被标记为|状态为|状态是|标记为|'+label+r'(?:为|是)?)\s*)?[“「\"]?'+re.escape(value)
        match=re.search(pattern,goal) or re.search(r'(?:^|[，,。；;\n])\s*(?:(?:先|再)\s*)?(?:把|将)?[“「\"]?'+re.escape(value)+r'[”」\"]?(?:的|记录|项目|条目|数据|人员|合同|报名记录)*\s*(?:去掉|剔除|排除|不算)',goal)
        if not match or re.search(r'(?:不要|不必|无需|不用|不需要|不)(?:再|自行|额外)?$',goal[:match.start()]):continue
        fresh.append({'field':c,'value':value,'quote':match[0]})
    rules={(r['field'],r['value']):r for r in fresh}
    for r in inherited:
        if not isinstance(r,dict) or not {'field','value','quote'}<=set(r) or r['field'] not in source['columns']:continue
        value=re.escape(str(r['value']))
        included=re.search(r'(?:^|[，,。；;])\s*(?:也|并)?(?:包括|包含|纳入|算上).{0,4}?'+value+'|'+value+r'(?:也|都)?(?:算上|纳入)',goal)
        if not included:rules.setdefault((r['field'],r['value']),dict(r))
    return list(rules.values())


def positive_category_scope(goal,source,field):
    """Do not broaden a user-requested positive scope while compiling exclusions."""
    index=source['columns'].index(field)
    values={str(row[index]) for row in source['rows'] if row[index] is not None}
    prefixes=r'(?:只看|只要|只统计|仅统计|仅保留|只保留|状态(?:为|是)|'+re.escape(field)+r'(?:为|是|等于))\s*[“「\"]?'
    for item in values:
        if not item:continue
        for match in re.finditer(prefixes+re.escape(item),goal):
            if not re.search(r'不要|不应|别|排除',goal[max(0,match.start()-4):match.start()]):return True
    return False


def compile_exclusion_scope(node,goal,source):
    """Correct an invented include-set only inside a plain conjunction.

    This does not invent a missing filter. Every correction quotes a unique
    observed field/value requested for exclusion, preserving other predicates.
    OR/NOT or positive selections require normal semantic replanning.
    """
    rules=literal_exclusions(goal,source);by_field={};notes=[]
    for rule in rules:by_field.setdefault(rule['field'],[]).append(rule)
    def visit(value):
        if not isinstance(value,dict) or 'any' in value or 'not' in value:return
        if 'all' in value:
            for child in value['all']:visit(child)
            return
        field=value.get('column');bound=by_field.get(field,[])
        if not bound or value.get('operator') not in ('eq','in') or positive_category_scope(goal,source,field):return
        before=dict(value);excluded=[r['value'] for r in bound]
        value['operator']='ne' if len(excluded)==1 else 'not_in'
        value['value']=excluded[0] if len(excluded)==1 else excluded
        notes.append({'kind':'literal_category_exclusion','before':before,'after':dict(value),'quotes':[r['quote'] for r in bound]})
    visit(node)
    return notes


def check_exclusion_scope(node,goal,source):
    """An explicit categorical exclusion cannot become an invented include set."""
    rules=literal_exclusions(goal,source);fields={r['field'] for r in rules}
    def visit(value):
        if not isinstance(value,dict):return
        for key in ('all','any'):
            for child in value.get(key,[]):visit(child)
        if 'not' in value:return
        if value.get('column') not in fields or value.get('operator') not in ('eq','in'):return
        selected=value.get('value');selected=selected if isinstance(selected,list) else [selected]
        for item in selected:
            match=re.search(r'(?:只看|只要|只统计|仅统计|仅保留|只保留|状态(?:为|是))\s*[“「\"]?'+re.escape(str(item)),goal)
            if match and not re.search(r'不要|不应|别',goal[max(0,match.start()-4):match.start()]):continue
            raise TableError('用户只要求排除'+'、'.join(r['value'] for r in rules if r['field']==value['column'])+'，不能擅自把“'+value['column']+'”收窄为只包括'+str(item)+'。请使用排除条件，保留其他类别。')
    visit(node)


def verify_literal_exclusions(result,source,rules):
    if not rules:return
    locations={}
    for row,origins in zip(source['rows'],source['provenance']):
        for origin in origins:locations[origin]=row
    origins={origin for view in [result]+result.get('summaries',[]) for group in view.get('provenance',[]) for origin in group}
    for rule in rules:
        i=source['columns'].index(rule['field'])
        if any(origin in locations and compact(locations[origin][i])==compact(rule['value']) for origin in origins):
            exc=TableError('原话“'+rule['quote']+'”尚未落实：结果或汇总仍包含'+rule['field']+'为“'+rule['value']+'”的来源行。请从完整原始数据排除这些行，再重建后续结果；现有正确的行内计算可以复用。')
            exc.repair_predicate={'column':rule['field'],'operator':'ne','type':'text','value':rule['value']};exc.repair_quote=rule['quote'];exc.repair_shape='detail'
            raise exc


ACTION_FIELDS={
 'filter':{'where','fields','columns','sort','select'},'derive':{'name','formula','expression','format','precision','fields','display_units','where'},
 'group':{'by','metrics'},'distinct':{'fields','columns','by','keep'},'sort':{'by'},
 'limit':{'count','offset'},'select':{'fields','columns'},'inspect':{'fields'},
 'finish':{'result','summaries','fields','display_units'},
 'present':{'units'},
}


def validate_action(action,default=None):
    if not isinstance(action,dict):raise TableError('工具动作需要对象。')
    tool=action.get('tool',default)
    if tool not in ACTION_FIELDS:raise TableError('没有这个工具，请使用列出的工具。')
    unexpected=set(action)-ACTION_FIELDS[tool]-{'tool','input','purpose','output'}
    if unexpected:
        raise TableError('工具'+tool+'不接受参数'+','.join(sorted(unexpected))+'；多个筛选条件写入where的all/any，写作和文件交付由程序在finish后完成。')
    if 'output' in action and (tool in ('inspect','finish','present') or not isinstance(action['output'],str) or not re.fullmatch(r'V[1-9][0-9]?',action['output'])):
        raise TableError('output只能是下一项新结果的V编号；文件与结果编号由程序分配。')
    for a,b in (('fields','columns'),('formula','expression')):
        if a in action and b in action and action[a]!=action[b]:raise TableError('工具参数'+a+'和'+b+'互相冲突。')
    if tool=='derive' and 'fields' in action:
        if 'where' in action:raise TableError('批量derive与where的依赖关系不明确，请拆成独立动作。')
        if set(action)-{'tool','input','purpose','output','fields','display_units'} or not isinstance(action['fields'],list) or not 1<=len(action['fields'])<=4:
            raise TableError('批量derive使用fields数组，按依赖顺序给1–4个name/formula对象，不同时提供单列参数。')
        for field in action['fields']:
            if not isinstance(field,dict) or set(field)-{'name','formula','expression','format','precision','display_units'}:raise TableError('每个计算字段仅提供name、formula和可选format/precision/display_units。')
            validate_action(dict(field,tool='derive'))
            if not {'name'}<=set(field) or not ('formula' in field or 'expression' in field):raise TableError('每个计算字段需要name和formula。')
    if 'display_units' in action and (not isinstance(action['display_units'],dict) or len(action['display_units'])>40 or any(not isinstance(k,str) or not isinstance(v,str) for k,v in action['display_units'].items())):
        raise TableError('display_units需要字段到明确单位的对象。')
    if tool=='present' and (not isinstance(action.get('units'),list) or not 1<=len(action['units'])<=12 or
            any(not isinstance(v,dict) or set(v)!={'field','unit'} or not isinstance(v['field'],str) or not isinstance(v['unit'],str) for v in action['units'])):
        raise TableError('显示单位需要1–12个明确的field/unit对象。')
    if tool=='sort' and (not isinstance(action.get('by'),list) or any(not isinstance(v,dict) for v in action['by'])):
        raise TableError('sort.by需要字段与方向组成的对象数组。')
    if tool=='filter':
        if 'sort' in action:
            sort=action['sort']
            if isinstance(sort,dict):
                if set(sort)!={'by'}:raise TableError('组合sort只接受by，不接受输入、路径或其他动作。')
                sort=sort['by']
            if not isinstance(sort,list) or not sort or any(not isinstance(key,dict) or not key or set(key)-{'field','direction','order','ascending'} for key in sort):raise TableError('组合sort需要明确的排序键数组。')
            for key in sort:
                if not isinstance(key.get('field'),str) or not key['field']:raise TableError('组合sort需要实际排序字段。')
                directions=[key[name] for name in ('direction','order') if name in key]
                if any(direction not in ('asc','desc') for direction in directions):raise TableError('排序方向只能是asc或desc。')
                if 'ascending' in key:
                    if type(key['ascending'])!=bool:raise TableError('ascending需要布尔值。')
                    directions.append('asc' if key['ascending'] else 'desc')
                if len(set(directions))>1:raise TableError('组合sort的排序方向参数冲突。')
        if 'select' in action:
            selected=action['select']
            if isinstance(selected,dict):
                if len(selected)!=1 or next(iter(selected)) not in ('fields','columns'):raise TableError('组合select只接受fields或columns。')
                selected=next(iter(selected.values()))
            if not isinstance(selected,list) or not selected or any(not isinstance(field,str) or not field for field in selected):raise TableError('组合select需要明确字段数组。')


def normalize_continuity(goal):
    """Canonicalize explicit unchanged processing rules without changing user data."""
    rule=r'(?:(?:业务|筛选|统计|计算|处理)?(?:口径|标准|规则)|筛选条件|输出字段|输出列|字段|排序|汇总|明细|条件|要求|设置|安排|列)'
    return re.sub(r'((?:其他|其它|其余)(?:的)?)'+rule+r'(?:(?:和|与|及|、|以及)'+rule+r')*(?:均|都)?(?:保持)?(?:不变|照旧)',r'\1条件不变',goal)


def retains_delivery(goal):
    return bool(re.search(r'(?:其他|其它|其余)(?:的)?(?:要求|设置|安排|条件)(?:均|都)?(?:保持)?不变|(?:交付|输出|导出)(?:要求|格式)(?:保持)?不变',normalize_continuity(goal)))


def writing_intent(goal):
    """Separate positive writing requests from plain-language cancellations."""
    negative=r'(?:不要|无需|不必|不需要|不用|别|不)(?:再|额外)?'
    denied=bool(re.search(negative+r'(?:写(?:任何)?(?:文稿|说明|报告|邮件|文字)?|起草)(?=[，,。；;！!\s]|$|只|仅|就)',goal,re.I))
    denied=denied or bool(re.search(r'(?:只(?:需要|要)|仅(?:需要|要))\s*(?:表格|明细表|Excel|CSV)',goal,re.I))
    no_word=bool(re.search(negative+r'(?:导出|生成|保存|另存|写|出|保留)?\s*(?:Word|DOCX)|(?:Word|DOCX)(?:这次)?(?:不用|不要|不必|不需要)(?:了)?',goal,re.I))
    pattern=r'(?:导出|另存|生成|保存|给我|写)[^，,。；;\n]{0,12}(?:Word|DOCX)|(?:写|起草|撰写|制作|做)[^，,。；;\n]{0,16}(?:说明|简报|文稿|报告|邮件|总结|摘要)'
    positive=next((m for m in re.finditer(pattern,goal,re.I) if not re.search(negative+r'\s*$',goal[:m.start()])),None)
    if denied and positive is None and re.search(r'(?:只(?:需要|要)|仅(?:需要|要))\s*(?:表格|明细表|Excel|CSV)',goal,re.I):no_word=True
    return positive,denied,no_word


def strict_action_json(text):
    import json
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                hint='一次derive只能生成一个字段；先算依赖字段，下一轮再算另一个字段，name和formula各只能有一个。' if key in ('name','formula','expression') else '每次只做一个动作；多个条件用all/any装入独立对象，每个对象内的参数只能有一个值。'
                raise TableError('参数“'+str(key)[:40]+'”重复。'+hint)
            result[key]=value
        return result
    start=text.find('{')
    if start<0:raise TableError('动作没有完整JSON对象。')
    value,end=json.JSONDecoder(object_pairs_hook=unique).raw_decode(text,start)
    if re.search(r'"tool"\s*:',text[end:]):raise TableError('每轮只能给一个工具动作，不能串接多个动作。')
    return value


def json_scalar_sequence(text):
    """Lex values independently of punctuation; never infer missing values."""
    import json
    start,end=text.find('{'),text.rfind('}')
    if start<0 or end<start or end-start>6000:raise TableError('格式修订范围不完整。')
    body=text[start:end+1];decoder=json.JSONDecoder();values=[];i=0
    while i<len(body):
        if body[i].isspace() or body[i] in '{}[],:':i+=1;continue
        if body[i]=='"':
            value,end=decoder.raw_decode(body,i)
            if not isinstance(value,str):raise TableError('字符串边界不完整。')
            values.append(('string',value));i=end;continue
        match=re.match(r'-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null',body[i:])
        if not match:raise TableError('无法无损确定格式错误中的字段和数值。')
        values.append(('literal',match[0]));i+=len(match[0])
    return values


def remove_stray_json_closers(text):
    """Drop only closing delimiters with no possible opening delimiter."""
    import json
    start,end=text.find('{'),text.rfind('}')
    if start<0 or end<start or end-start>6000:raise TableError('格式修订范围不完整。')
    body=text[start:end+1];decoder=json.JSONDecoder();out=[];stack=[];i=0
    while i<len(body):
        ch=body[i]
        if ch=='"':
            _,last=decoder.raw_decode(body,i);out.append(body[i:last]);i=last;continue
        if ch in '{[':stack.append(ch)
        elif ch in '}]':
            opening={'}':'{',']':'['}[ch]
            if stack and stack[-1]==opening:stack.pop()
            elif opening not in stack:i+=1;continue
            else:
                # A duplicated closer crossing an object/array end is uniquely
                # removable when the matching closer follows that end as well.
                expected='}' if stack[-1]=='{' else ']'
                if re.match(r'\s*'+re.escape(expected)+r'\s*'+re.escape(ch),body[i+1:]):i+=1;continue
                raise TableError('括号层级不明确，不能直接修订。')
        out.append(ch);i+=1
    candidate=''.join(out)
    if json_scalar_sequence(candidate)!=json_scalar_sequence(body):raise TableError('格式修订改变了原字段或数值。')
    strict_action_json(candidate)
    return candidate


def repair_json_punctuation(text):
    """Recover delimiter errors without changing, adding or dropping scalar tokens.

    A small JSON grammar supplies only expected punctuation. It cannot invent
    an object key, a value, a tool or a business condition. Duplicate keys still
    fail the strict decoder. Ambiguous token roles stop rather than guess.
    """
    import json
    before=json_scalar_sequence(text);start,end=text.find('{'),text.rfind('}')
    body=text[start:end+1];decoder=json.JSONDecoder();out=[];stack=[];i=0;done=False
    def close_top():
        kind,state=stack[-1]
        if state not in (('value','after') if kind=='[' else ('key','after')):
            raise TableError('缺少字段值，不能靠标点补造。')
        if kind=='{' and state=='value':raise TableError('缺少字段值，不能靠标点补造。')
        if out and out[-1]==',':out.pop()
        out.append('}' if kind=='{' else ']');stack.pop()
    def value_start():
        if not stack:
            if done:raise TableError('只能修订一个完整JSON对象。')
            return
        kind,state=stack[-1]
        if kind=='{':
            if state=='colon':out.append(':');state='value'
            if state!='value':raise TableError('字段名不明确，不能推测标点关系。')
        elif state=='after':out.append(',')
        stack[-1][1]='after'
    while i<len(body):
        ch=body[i]
        if ch.isspace():i+=1;continue
        if ch in '{[':
            value_start();out.append(ch);stack.append([ch,'key' if ch=='{' else 'value']);i+=1;continue
        if ch in '}]':
            wanted='{' if ch=='}' else '['
            if not any(s[0]==wanted for s in stack):i+=1;continue
            while stack and stack[-1][0]!=wanted:close_top()
            close_top();done=not stack;i+=1;continue
        if ch==',':
            if not stack: i+=1;continue
            kind,state=stack[-1]
            if state=='after':out.append(',');stack[-1][1]='key' if kind=='{' else 'value'
            elif state not in ('key','value'):raise TableError('缺少字段值，不能修订。')
            i+=1;continue
        if ch==':':
            if not stack or stack[-1]!=['{','colon']:raise TableError('冒号缺少明确字段名。')
            out.append(':');stack[-1][1]='value';i+=1;continue
        value,last=decoder.raw_decode(body,i)
        if isinstance(value,(dict,list)):raise TableError('未识别的容器边界。')
        token=body[i:last]
        if not stack:raise TableError('JSON对象之外出现值。')
        kind,state=stack[-1]
        if kind=='{' and state in ('key','after'):
            if not isinstance(value,str):raise TableError('字段名必须是原有字符串。')
            if state=='after':out.append(',')
            stack[-1][1]='colon'
        else:value_start()
        out.append(token);i=last
    while stack:close_top()
    candidate=''.join(out)
    if json_scalar_sequence(candidate)!=before:raise TableError('标点修订改变了原字段或数值。')
    strict_action_json(candidate)
    return candidate


def normalize_predicate_shape(node):
    """Give logical selectors an explicit owner, retaining every predicate."""
    operators={'and':'all','all':'all','or':'any','any':'any','not':'not'}
    if isinstance(node,list):
        if not 1<=len(node)<=16:raise TableError('条件列表需要1–16项；任一满足使用any。')
        selectors=[];children=[]
        for child in node:
            if isinstance(child,dict) and child and set(child)<= {'logic','type'}:
                values=[operators.get(v) for v in child.values()]
                if not values or None in values or len(set(values))!=1 or values[0]=='not':raise TableError('条件列表的逻辑选择不明确。')
                selectors.append(values[0])
            else:children.append(normalize_predicate_shape(child))
        if len(set(selectors))>1 or not children:raise TableError('条件列表为空或包含冲突逻辑。')
        return {(selectors or ['all'])[0]:children}
    if not isinstance(node,dict):return node
    node=dict(node)
    if 'logic' in node and ('field' in node or 'column' in node):
        logic=operators.get(node.pop('logic'))
        if logic not in ('all','any'):raise TableError('单个字段条件的逻辑不明确。')
        return {logic:[normalize_predicate_shape(node)]}
    for key in ('all','any','and','or'):
        if key in node and isinstance(node[key],list):node[key]=[normalize_predicate_shape(c) for c in node[key]]
    if 'not' in node:node['not']=normalize_predicate_shape(node['not'])
    return node


def normalize_action(action):
    """Accept common argument envelopes, retaining all conflict/allowlist checks."""
    if not isinstance(action,dict):return action
    action=dict(action)
    for key in ('arguments','parameters','params','action'):
        if key not in action:continue
        params=action.pop(key)
        if not isinstance(params,dict):raise TableError('工具参数封装需要一个对象，一次只执行一个动作。')
        for name,value in params.items():
            if name in action and action[name]!=value:raise TableError('内外层工具参数“'+str(name)[:40]+'”冲突。')
            action[name]=value
    def unit_list(value):
        if not isinstance(value,list):return value
        if len(value)>40:raise TableError('显示单位列表最多40项。')
        from table_semantics import unit_definition
        result={}
        for item in value:
            if not isinstance(item,dict) or set(item)!={'field','unit'} or not isinstance(item['field'],str) or not item['field'] or not isinstance(item['unit'],str) or unit_definition(item['unit']) is None:
                raise TableError('显示单位列表只接受明确的field与已知unit。')
            if item['field'] in result and unit_definition(result[item['field']])!=unit_definition(item['unit']):raise TableError('同一字段的显示单位互相冲突。')
            result.setdefault(item['field'],item['unit'])
        return result
    if 'display_units' in action:action['display_units']=unit_list(action['display_units'])
    if action.get('tool')=='derive':
        def recover(parameters,name):
            value=dict(parameters)
            if isinstance(value.get('summaries'),list) and not value['summaries']:value.pop('summaries')
            if isinstance(value.get('display_units'),str):
                from table_semantics import unit_definition
                unit=value['display_units']
                if unit_definition(unit) is None:raise TableError('输出单位未识别：'+unit)
                if not isinstance(name,str) or not name.strip():raise TableError('标量display_units只能绑定到一个明确的计算字段name；多字段上层须提供字段到单位的映射。')
                value['display_units']={name:unit}
            return value
        fields=action.get('fields')
        if isinstance(fields,list):
            fields=[recover(dict(field,display_units=unit_list(field['display_units'])) if 'display_units' in field else field,field.get('name')) if isinstance(field,dict) else field for field in fields]
            action['fields']=fields
            name=fields[0].get('name') if len(fields)==1 and isinstance(fields[0],dict) else None
        else:name=action.get('name') if 'fields' not in action else None
        action=recover(action,name)
    if action.get('tool')!='finish' and 'result' in action:
        value=action.pop('result')
        if not isinstance(value,str) or not re.fullmatch(r'V\d{1,2}|P0',value):raise TableError('输入结果只能引用已有视图编号。')
        if 'input' in action and action['input']!=value:raise TableError('input与result引用不同视图，不能猜测输入。')
        action['input']=value
    if action.get('tool')=='filter':
        if 'logic' in action:
            logic=action.pop('logic');logic={'and':'all','or':'any','all':'all','any':'any'}.get(logic)
            if not logic or 'where' not in action:raise TableError('筛选逻辑需要明确的where条件。')
            if isinstance(action['where'],list):
                sentinels=[c.get('logic',c.get('type')) for c in action['where'] if isinstance(c,dict) and c and set(c)<= {'logic','type'}]
                if any({'and':'all','or':'any'}.get(v,v)!=logic for v in sentinels):raise TableError('筛选动作与条件列表的逻辑冲突。')
                children=[c for c in action['where'] if not (isinstance(c,dict) and c and set(c)<= {'logic','type'})]
                action['where']={logic:children}
            else:action['where']={logic:[action['where']]}
        logical=[k for k in ('all','and','any','or','not') if k in action]
        if len(logical)>1:raise TableError('筛选动作的外层逻辑有冲突，请合并到一个where条件树。')
        if logical:
            key=logical[0];value=action.pop(key);canonical={'and':'all','or':'any'}.get(key,key)
            if 'where' in action:
                if canonical=='not':raise TableError('not与where的关系不明确，请显式写入条件树。')
                if not isinstance(value,list):raise TableError('all/any的条件需要数组。')
                value=[action['where']]+value
            action['where']={canonical:value}
    if action.get('tool') in ('filter','derive') and 'where' in action:action['where']=normalize_predicate_shape(action['where'])
    return action


def explicit_percent(value,goal):
    """Infer a numeric tool argument's scale only from explicit user percentages."""
    if str(value).endswith(('%','％')):return str(value)
    from decimal import Decimal,InvalidOperation
    try:n=Decimal(str(value))
    except InvalidOperation:raise TableError('百分比参数需要数值或明确百分号。')
    if not n.is_finite():raise TableError('百分比参数必须是有限数值。')
    matches=set()
    for token in re.findall(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*[%％]',goal):
        ratio=Decimal(re.sub(r'\s|[%％]','',token))/100
        if n in (ratio,ratio*100):matches.add(ratio)
    if len(matches)!=1:raise TableError('百分比条件值需明确带%，或唯一对应用户已指定的百分比；不能猜测比例尺度。')
    from table_program import decimal_text
    return decimal_text(matches.pop()*100)+'%'
