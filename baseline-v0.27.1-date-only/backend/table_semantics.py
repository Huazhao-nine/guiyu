"""Local, idempotent quantity normalization and source-backed field descriptions."""
from copy import deepcopy
from decimal import Decimal
import re
from table_program import TableError, decimal_text, numeric_column, calendar_date,calendar_text

# Fixed unit definitions, independent from files, field names and evaluation cases.
UNITS={
    '元':('CNY',Decimal(1),'元'), 'cny':('CNY',Decimal(1),'元'), 'rmb':('CNY',Decimal(1),'元'),
    '千元':('CNY',Decimal(1000),'元'), '万元':('CNY',Decimal(10000),'元'),
    '美元':('USD',Decimal(1),'USD'), 'usd':('USD',Decimal(1),'USD'),
    '千美元':('USD',Decimal(1000),'USD'), '万美元':('USD',Decimal(10000),'USD'),
    'kusd':('USD',Decimal(1000),'USD'), '10kcny':('CNY',Decimal(10000),'元'),
    'cny10k':('CNY',Decimal(10000),'元'), 'kcny':('CNY',Decimal(1000),'元'),
    '千克':('mass',Decimal(1000),'g'), 'kg':('mass',Decimal(1000),'g'),
    '克':('mass',Decimal(1),'g'), 'g':('mass',Decimal(1),'g'),
    '小时':('duration',Decimal(60),'分钟'), '分钟':('duration',Decimal(1),'分钟'),
    '%':('ratio',Decimal('.01'),'%'), '％':('ratio',Decimal('.01'),'%'),
    '人':('',Decimal(1),'人'),'条':('',Decimal(1),'条'),'笔':('',Decimal(1),'笔'),
    '件':('',Decimal(1),'件'),'个':('',Decimal(1),'个'),'份':('',Decimal(1),'份'),
}
BASE={'CNY':'元','USD':'USD','mass':'g','duration':'分钟','ratio':'%'}


def unit_definition(text):
    key=re.sub(r'\s','',str(text)).lower()
    return UNITS.get(key)


def explicit_quantities(goal):
    tokens='|'.join(re.escape(s) for s in sorted(UNITS,key=len,reverse=True))
    return [(m,quantity(m[0])[0],unit_definition(m[2])) for m in re.finditer(r'([+-]?\d+(?:\.\d+)?)\s*('+tokens+r')',goal,re.I)]


def grounded_quantity(value,goal,dimension,default=None):
    """Resolve an omitted parameter unit only from a unique explicit user value."""
    result,unit=quantity(value,default)
    if not dimension or unit_definition(str(value)) or re.search(r'[A-Za-z%％\u4e00-\u9fff]',str(value)):return result
    raw,_=quantity(value)
    matches=set()
    for m,parsed,declared in explicit_quantities(goal):
        if declared[0]!=dimension:continue
        if raw in (Decimal(m[1]),parsed):matches.add(parsed)
    if len(matches)>1:raise TableError('数值对应了多个单位含义，请明确参数单位。')
    return next(iter(matches)) if matches else result


def header_unit(name):
    for m in re.finditer(r'[（(\[]([^）)\]]+)[）)\]]',name):
        definition=unit_definition(m[1])
        if definition:return definition,name[:m.start()]+name[m.end():]
    for token in sorted(UNITS,key=len,reverse=True):
        if token in ('g','kg','rmb','cny','usd','kusd','kcny','cny10k','10kcny'):
            match=re.search(r'(?i)(?:[ _/]+|\b)'+re.escape(token)+r'$',name)
        else:match=re.search(re.escape(token)+r'$',name)
        if match:return UNITS[token],name[:match.start()]
    return None,name


def quantity(value,default=None):
    if isinstance(value,bool):raise TableError('布尔状态不能当作数值。')
    text=str(value).strip().replace(',','').replace('，','').replace(' ','')
    if not text:return None,default
    m=re.fullmatch(r'([¥￥$]?)([+-]?(?:\d+(?:\.\d*)?|\.\d+))(.*)',text)
    if not m:raise TableError('需要完整数值或带明确单位的数值。')
    explicit=unit_definition(m[3]) if m[3] else None
    if m[3] and explicit is None:raise TableError('数值包含未识别的单位或其他文字。')
    symbol=UNITS['元'] if m[1] in ('¥','￥') else UNITS['usd'] if m[1]=='$' else None
    if explicit and symbol and explicit[0]!=symbol[0]:raise TableError('同一数值的货币标记冲突。')
    definition=explicit or symbol or default
    if default and definition and default[0]!=definition[0]:raise TableError('字段中混用了不同维度或货币，不能直接计算。')
    result=Decimal(m[2])*(definition[1] if definition else 1)
    if not result.is_finite() or abs(result)>Decimal('1e30'):raise TableError('数值超出计算范围。')
    return result,definition


def identifier(name,values):
    return (not numeric_column(name) or
            bool(re.search(r'编号|证件号|订单号|(?i:(^|[_\s])(?:id|code|phone|mobile|postcode|no|number)($|[_\s]))',name) or re.search(r'[a-z](?:Id|ID|Code|No|Number)$',name)) or
            any(re.fullmatch(r'0\d+',str(v).strip()) for v in values if str(v).strip()))


def canonical_table(source):
    """Every numeric value uses a declared base unit. Reapplying is a no-op."""
    table=deepcopy(source);columns=[];rows=[list(r) for r in source['rows']]
    units={};hints={};ledger={};notes=list(source.get('notes',[]));issues={}
    for i,original in enumerate(source['columns']):
        cells=[r[i] for r in source['rows']];present=[str(v).strip() for v in cells if str(v).strip()]
        definition,stem=header_unit(original)
        hint=source.get('units',{}).get(original)
        if definition is None and hint in BASE:definition=(hint,Decimal(1),BASE[hint])
        name=original;kind=source.get('field_types',{}).get(original,'text') if not present else 'text';converted=None
        if identifier(original,present):kind='identifier'
        elif present and all(v.lower() in ('true','false') for v in present):
            kind='boolean';converted=[str(v).lower() if str(v).strip() else '' for v in cells]
        else:
            parsed=[];detected=definition
            try:
                for v in cells:
                    n,u=quantity(v,definition)
                    if u and detected and u[0]!=detected[0]:raise TableError('同列混合单位维度。')
                    if u:detected=u
                    parsed.append(n)
                if present or definition:
                    dimension=detected[0] if detected else ''
                    if dimension:
                        name=stem.strip(' /_')+'（'+BASE[dimension]+'）'
                        units[name]='' if dimension=='ratio' else dimension
                    converted=[decimal_text(n*100)+'%' if dimension=='ratio' and n is not None else decimal_text(n) for n in parsed]
                    kind='percent' if dimension=='ratio' else 'number'
                    if name!=original or any(str(a)!=str(b) for a,b in zip(cells,converted)):
                        notes.append(original+'：按单元格显式单位优先、表头单位兜底，统一为'+(BASE.get(dimension,'原数值'))+'；未改变原文件。')
                    definition=detected
            except TableError as exc:
                if definition or detected:
                    issues[original]='单位或数值不一致，按原文字保留，不可直接计算：'+str(exc)
                    notes.append(original+'：'+issues[original]);kind='text';converted=None;name=original
                    units.pop(name,None)
                if present:
                    try:
                        for v in present:calendar_date(v)
                        kind='date';converted=[calendar_text(v) if str(v).strip() else '' for v in cells]
                    except TableError:pass
        if converted is not None:
            for r,v in zip(rows,converted):r[i]=v
        if name in columns:
            name=stem.strip(' /_')+'〔原列'+str(i+1)+'〕'+('（'+BASE[definition[0]]+'）' if definition else '')
            notes.append(original+'：单位统一后存在同名字段，用原列位置区分，原表头保留在字段说明中。')
            if definition:units[name]='' if definition[0]=='ratio' else definition[0]
        columns.append(name);hints[name]=kind
        old=source.get('unit_ledger',{}).get(original,{})
        ledger[name]=old or {'source_column':original,'canonical_unit':BASE.get(definition[0],definition[2]) if definition else ''}
    table.update(columns=columns,rows=rows,units=units,field_types=hints,unit_ledger=ledger,field_issues=issues,notes=list(dict.fromkeys(notes)))
    return table


def describe(table,registry):
    from workbook_data import profile
    result=profile(table);fields=[]
    for field in result['fields']:
        name=field['column']
        if name not in registry:registry[name]='F'+str(len(registry)+1)
        hint=table.get('field_types',{}).get(name)
        field={**field,'id':registry[name],'type':hint or field['type'],'unit':table.get('unit_ledger',{}).get(name,{}).get('canonical_unit') or table.get('units',{}).get(name,'')}
        original=table.get('unit_ledger',{}).get(name,{}).get('source_column')
        if original and original!=name:field['source_column']=original
        if name in table.get('field_issues',{}):field['issue']=table['field_issues'][name]
        fields.append(field)
    return {**result,'fields':fields}
