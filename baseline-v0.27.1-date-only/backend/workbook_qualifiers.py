"""Literal source qualifications with quoted scope and observed values.

Only explicit field=value atoms and unambiguous AND/OR joins are compiled.
Aliases, parentheses, hypothetical statements and mixed scopes stay with the
planner. No filename, example value, or expected answer is special-cased.
"""
from copy import deepcopy
import re
from table_program import TableError,column
from table_semantics import header_unit


def initial_distinct_keys(goal,columns):
    """Explicit 'first deduplicate source records', not a later dedup stage."""
    pattern=r'(?:首先|先)\s*按([^，,。；;\n]{1,80}?)(?:去重(?:并|、)?(?:保留)?|保留)\s*(?:(?:原表|原始|输入|表中|各表|每表)\s*)?(?:首次|最先|第一条)(?:出现的)?(?:记录|一条)?'
    for match in re.finditer(pattern,goal):
        prefix=goal[:match.start()]
        if re.search(r'不要|不必|不用|别|禁止|先筛|先排除|先剔除|先过滤|基于.{0,20}(?:结果|上轮)',prefix):continue
        label=match[1].strip()
        try:keys=[column(label,columns)]
        except TableError:
            try:keys=[column(part,columns) for part in re.split(r'[、和与及]',label) if part.strip()]
            except TableError:continue
        if keys and len(set(keys))==len(keys):return keys
    return None


def literal_boolean_rules(goal,source):
    aliases={};values={}
    for i,name in enumerate(source['columns']):
        if source.get('field_types',{}).get(name) not in ('text','boolean'):continue
        observed={str(row[i]).strip() for row in source['rows'] if str(row[i]).strip() and len(str(row[i]).strip())<=80}
        if not observed or len(observed)>40:continue
        values[name]={v.casefold():v for v in observed}
        for label in {name,header_unit(name)[1].strip()}:
            if label:aliases.setdefault(label.casefold(),set()).add(name)
    atoms=[]
    boundary=r'(?=的?(?:(?:原始)?(?:记录|登记|项目|数据|条目))?(?:\s|[，,。、;；。)]|且|并且|或者|或|而且|和|与|及|$))'
    for alias,names in aliases.items():
        if len(names)!=1:continue
        name=next(iter(names));options='|'.join(re.escape(v) for v in sorted(values[name],key=len,reverse=True))
        pattern=re.escape(alias)+r'\s*(?:为|是|等于|=)\s*[“"「]?(?P<value>'+options+r')[”"」]?'+boundary
        for match in re.finditer(pattern,goal,re.I):
            atom={'column':name,'operator':'eq','type':'text','value':values[name][match['value'].casefold()]}
            atoms.append((match.start(),match.end(),atom))
    owners={value:set() for observed in values.values() for value in observed}
    # Uniqueness also considers non-categorical text columns. A value shared
    # with a free-text column is not an unambiguous omitted-field reference.
    for i,name in enumerate(source['columns']):
        if source.get('field_types',{}).get(name) not in ('text','boolean'):continue
        for row in source['rows']:
            value=str(row[i]).strip().casefold()
            if value in owners:owners[value].add(name)
    for value,names in owners.items():
        if len(names)!=1:continue
        name=next(iter(names))
        pattern=r'(?:只看|只算|只统计|仅统计|保留|留下|筛选(?:出)?|或者|或|并且|且)\s*[“"「]?(?P<value>'+re.escape(value)+r')[”"」]?'+boundary
        for match in re.finditer(pattern,goal,re.I):
            atoms.append((match.start('value'),match.end(),{'column':name,'operator':'eq','type':'text','value':values[name][value]}))
    selected=[]
    for atom in sorted(atoms,key=lambda x:(x[0],-x[1])):
        if selected and atom[0]<selected[-1][1]:continue
        selected.append(atom)
    def connector(a,b):
        text=goal[a[1]:b[0]]
        text=re.sub(r'(?:的)?(?:记录|登记|项目|数据|条目)|的|[\s，,、“”「」"]','',text)
        if text in ('或','或者'):return 'or'
        if text in ('且','并且','而且','和','与','及','以及'):return 'and'
        return None
    groups=[];current=[];joins=[]
    for atom in selected:
        join=connector(current[-1],atom) if current else None
        if current and join is None:
            groups.append((current,joins));current=[];joins=[]
        if current:joins.append(join)
        current.append(atom)
    if current:groups.append((current,joins))
    rules=[]
    for members,joins in groups:
        if 'or' not in joins or not 2<=len(members)<=12:continue
        start,end=members[0][0],members[-1][1]
        left=max((goal.rfind(c,0,start) for c in '，,。；;\n'),default=-1)+1
        if re.search(r'不要|别|禁止|排除|剔除|如果|假如|例如|比如|除非|是否|能否',goal[left:start]):continue
        chunks=[[members[0][2]]]
        for join,atom in zip(joins,members[1:]):
            if join=='or':chunks.append([])
            chunks[-1].append(atom[2])
        predicate={'any':[chunk[0] if len(chunk)==1 else {'all':chunk} for chunk in chunks]}
        rules.append({'predicate':predicate,'quote':goal[start:end],'fields':sorted({m[2]['column'] for m in members})})
    # Two unrelated branches using the same field cannot be one global scope.
    return [r for i,r in enumerate(rules) if not any(i!=j and set(r['fields'])&set(other['fields']) for j,other in enumerate(rules))]


def compile_boolean_scope(node,rules):
    notes=[]
    def atoms(value):
        return [a for child in value['all'] for a in atoms(child)] if set(value)=={'all'} else [value]
    def leaves(value):
        if 'column' in value:return [value]
        if 'not' in value:return []
        return [leaf for key in ('all','any') for child in value.get(key,[]) for leaf in leaves(child)]
    for rule in rules:
        expected=rule['predicate'];allowed={}
        for leaf in leaves(expected):allowed.setdefault(leaf['column'],set()).add(leaf['value'])
        def belongs(child):
            subset=leaves(child)
            if not subset or 'not' in child:return False
            for leaf in subset:
                vals=leaf.get('value');vals=vals if isinstance(vals,list) else [vals]
                if leaf.get('operator') not in ('eq','in') or any(v not in allowed.get(leaf.get('column'),set()) for v in vals):return False
            return True
        original=atoms(node);positions=[i for i,child in enumerate(original) if belongs(child)]
        if not positions:continue
        new=[child for i,child in enumerate(original) if i not in positions]
        new.insert(min(positions),deepcopy(expected))
        after=new[0] if len(new)==1 else {'all':new}
        if node==after:continue
        before=deepcopy(node);node.clear();node.update(after)
        notes.append({'kind':'literal_boolean_scope','before':before,'after':deepcopy(after),'quote':rule['quote']})
    return notes
