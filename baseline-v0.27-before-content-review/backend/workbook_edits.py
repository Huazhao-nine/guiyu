"""Source-bound literal edits of saved table plans, independent of business schemas."""
import re
from table_semantics import header_unit,quantity,unit_definition,explicit_quantities,describe
from table_program import TableError,number
from workbook_intent import BOUNDARIES


def literal_edits(flow,finish,contract,goal):
    """Return edits only when clause, field, comparison and value are grounded.

    Exact saved user-to-column bindings and compatible output units can resolve
    short references. A relaxed/tightened boundary retains its old operator.
    New grouping/projection/source requests still use full planning.
    """
    main=finish['result'];view=flow.views[main];shape=flow.shapes[main]
    fields={f['column']:f for f in describe(view,flow.registry)['fields'] if f['type'] in ('number','percent','date')}
    projected=set()
    for name in finish.get('fields',view['columns']):
        try:projected.add(flow.resolve(view,name))
        except (ValueError,TypeError):pass
    clauses=[c.strip() for c in re.split(r'[，,。；;\n]',goal) if c.strip()]
    words=BOUNDARIES|{'不高于':'lte','不早于':'gte','不晚于':'lte'}
    operators='|'.join(re.escape(w) for w in sorted(words,key=len,reverse=True))
    pattern=re.compile(r'('+operators+r'|放宽到|放宽至|收紧到|收紧至|改成|改为|调整到|调整为)\s*(\d{4}-\d{2}-\d{2}|[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*(?:万元|千元|元|小时|分钟|千克|kg|克|g|USD|CNY|%|％)?)',re.I)
    requested=[(c,list(pattern.finditer(c))) for c in clauses if pattern.search(c)]
    if not 1<=len(requested)<=2 or any(len(ms)!=1 for _,ms in requested):return None
    active=set();cursor=main
    while cursor in flow.parents:active.add(cursor);cursor=flow.parents[cursor]
    def leaves(n):
        if 'all' in n:return [x for child in n['all'] for x in leaves(child)]
        if 'column' in n:return [n]
        return []
    old=[]
    for item in flow.graph:
        if item['id'] in active and item['operation']['op']=='filter' and flow.shapes[item['input']]==shape:
            old.extend(leaves(item['operation']['where']))
    aliases={name:{header_unit(name)[1].strip()} for name in fields}
    for binding in contract.get('column_bindings',[]):
        try:name=flow.resolve(view,binding['column'])
        except (ValueError,TypeError,KeyError):continue
        if name in aliases:aliases[name].add(header_unit(binding['requested'])[1].strip())
    edits=[]
    for clause,matches in requested:
        match=matches[0];phrase=match[1];literal=match[2];is_date=bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}',literal))
        noun=re.sub(r'把|将|只保留|仅保留|只看|门槛|边界|改成|改为|调整到|调整为|放宽到|放宽至|收紧到|收紧至|的|\s','',clause[:match.start()])
        candidates=[]
        for name,labels in aliases.items():
            for label in labels:
                compact=re.sub(r'\s','',label)
                shorter=re.sub(r'金额$','',compact)
                if (compact and compact in clause) or (len(shorter)>=2 and shorter in clause) or (len(noun)>=2 and noun in compact):candidates.append(name);break
        quantities=explicit_quantities(literal);dimension=quantities[0][2][0] if quantities else None
        compatible=[name for name,f in fields.items() if (f['type']=='date' if is_date else f['type']!='date' and (dimension is None or (unit_definition(f['unit']) or ('',))[0]==dimension))]
        candidates=list(dict.fromkeys(candidates))
        if candidates and any(c not in compatible for c in candidates):return None
        selected=[name for name in compatible if name in projected]
        if not candidates and not noun and len(selected)==1:candidates=selected
        if not candidates and not noun and len(compatible)==1:candidates=compatible
        if len(candidates)!=1:return None
        name=candidates[0];f=fields[name]
        value=literal if is_date else str(quantity(literal,unit_definition(f['unit']))[0])
        op=words.get(phrase)
        if op is None:
            bounds={(p['operator'],str(p.get('value'))) for p in old if p['column']==name and p.get('operator') in ('gt','gte','lt','lte','eq') and 'value' in p}
            if len(bounds)!=1:return None
            op,prior=next(iter(bounds))
            if phrase.startswith(('放宽','收紧')):
                a,b=(value,prior) if is_date else (number(value),number(prior))
                lower=op in ('gt','gte');upper=op in ('lt','lte')
                if not lower and not upper:return None
                if (phrase.startswith('放宽') and (a>b if lower else a<b)) or (phrase.startswith('收紧') and (a<b if lower else a>b)):return None
        edits.append({'field':name,'op':op,'value':value,'quote':clause})
    return edits
