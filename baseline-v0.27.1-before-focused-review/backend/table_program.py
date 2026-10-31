"""Typed local table operations. No generated Python, SQL, formulas or paths are executed."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_UP
from functools import cmp_to_key
import re
from local_query import normal

MAX_ROWS=5000
MAX_COLUMNS=40


class TableError(ValueError):
    pass


def fail(message):raise TableError(message)


def column(name, columns):
    if not isinstance(name,str):fail('字段必须是实际列名。')
    if name in columns:return name
    exact=[c for c in columns if normal(c)==normal(name)]
    if len(exact)==1:return exact[0]
    compact=lambda c:re.sub(r'\s+','',normal(c))
    spaced=[c for c in columns if compact(c)==compact(name)]
    if len(spaced)==1:return spaced[0]
    if len(spaced)>1:fail('去掉空格后字段不唯一，请使用完整实际列名：'+'、'.join(spaced))
    key=lambda c:re.sub(r'[\s（(].*?[)）]|\s','',normal(c))
    found=[c for c in columns if key(c)==key(name) or normal(c.split(' / ')[-1])==normal(name)]
    if len(found)==1:return found[0]
    fail('无法唯一确定字段“'+name+'”。实际字段：'+'、'.join(columns))


def number(value):
    text=normal(value).replace(',','').replace('，','').replace(' ','')
    if not text:return None
    match=re.fullmatch(r'([¥￥$]?)([+-]?(?:\d+(?:\.\d*)?|\.\d+))(万元|万|元|usd|cny|%|％|件|个|份|人|小时|天)?',text)
    if not match:fail('不是可计算的完整数值：'+str(value)[:60])
    result=Decimal(match[2])
    if match[3] in ('万元','万'):result*=10000
    if match[3] in ('%','％'):result/=100
    if not result.is_finite() or abs(result)>Decimal('1e30'):fail('数值超出计算范围。')
    return result


def calendar_date(value):
    if not str(value).strip():return None
    text=str(value).strip()
    if re.search(r'[T\s]\d{1,2}:\d{2}',text):
        normalized=re.sub(r'^(\d{4})[/年](\d{1,2})[/月](\d{1,2})日?',lambda m:f'{int(m[1]):04}-{int(m[2]):02}-{int(m[3]):02}',text)
        normalized=re.sub(r'([T\s])(\d):',r'\g<1>0\2:',normalized)
        try:return datetime.fromisoformat(normalized.replace('Z','+00:00')).date()
        except ValueError:fail('日期或时间格式无效：'+text[:40])
    text=text.split(' ')[0]
    match=re.fullmatch(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?',text)
    if not match:fail('日期需要完整的年、月、日：'+text[:40])
    try:return date(*(int(x) for x in match.groups()))
    except ValueError:fail('日期不存在：'+text)


def header_scale(c):
    return Decimal(10000) if '万元' in c else Decimal('0.01') if '%' in c or '％' in c else Decimal(1)


def cell_number(value,c):
    parsed=number(value)
    if parsed is None:return None
    explicit=bool(re.search(r'[¥￥$%％]|万元|元|万|usd|cny',normal(value)))
    return parsed if explicit else parsed*header_scale(c)


def calendar_text(value):
    """Normalize calendar dates, retaining meaningful timestamps verbatim."""
    text=str(value).strip()
    if not text:return ''
    if re.fullmatch(r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?|\d{4}-\d{2}-\d{2}[T\s]00:00(?::00(?:\.0+)?)?',text):return calendar_date(text).isoformat()
    return text


def numeric_column(c):
    return not re.search(r'编号|序号|编码|代码|代号|号码|学号|工号|账号|身份证|电话|手机|邮编|(^id$)|(^code$)|(^key$)',c,re.I)


def decimal_text(value, places=None):
    if value is None:return ''
    if places is not None:value=value.quantize(Decimal(1).scaleb(-places),rounding=ROUND_HALF_UP)
    text=format(value,'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def currency(column_name, cells):
    found=set()
    for text in [column_name]+[str(c) for c in cells if str(c).strip()]:
        if re.search(r'\$|USD|美元',text,re.I):found.add('USD')
        if re.search(r'¥|￥|人民币|CNY|元',text,re.I):found.add('CNY')
    if len(found)>1:fail('同一数值字段含不同货币，不能直接合并计算。')
    return next(iter(found),'')


def check_table(table):
    columns=table.get('columns');rows=table.get('rows')
    if not isinstance(columns,list) or not 1<=len(columns)<=MAX_COLUMNS or any(not isinstance(c,str) or not c for c in columns) or len(set(columns))!=len(columns):fail('表格字段无效或重复。')
    if not isinstance(rows,list) or len(rows)>MAX_ROWS or any(not isinstance(r,list) or len(r)!=len(columns) for r in rows):fail('表格行结构或数量无效。')
    return table


def test_condition(condition, row, columns, budget=None, depth=0):
    budget=budget if budget is not None else [64]
    budget[0]-=1
    if not isinstance(condition,dict) or budget[0]<0 or depth>6:fail('条件过多或嵌套过深。')
    if len(condition)==1 and next(iter(condition)) in ('all','any','not'):
        key=next(iter(condition));items=condition[key]
        if key=='not':return not test_condition(items,row,columns,budget,depth+1)
        if not isinstance(items,list) or not 1<=len(items)<=12:fail('组合条件不能为空，最多12项。')
        # Evaluate every condition even when an earlier branch decides the outcome:
        # malformed predicates must never hide behind Boolean short-circuiting.
        values=[test_condition(c,row,columns,budget,depth+1) for c in items]
        return all(values) if key=='all' else any(values)
    if set(condition)-{'column','operator','value','value_column','type','quote'} or not {'column','operator'}<=set(condition):fail('条件字段无效。')
    c=column(condition['column'],columns);cell=row[columns.index(c)]
    op=condition['operator'];value=condition.get('value');kind=condition.get('type','text')
    other=column(condition['value_column'],columns) if 'value_column' in condition else None
    if other:
        if 'value' in condition:fail('value和value_column只能选一个。')
        value=row[columns.index(other)]
    if kind not in ('text','number','date'):fail('条件类型只支持文字、数字或日期。')
    if op in ('is_empty','not_empty'):return (not str(cell).strip()) if op=='is_empty' else bool(str(cell).strip())
    if op not in ('eq','ne','contains','not_contains','in','not_in','gt','gte','lt','lte'):fail('不支持的比较方式。')
    if op in ('in','not_in'):
        if not isinstance(value,list) or not 1<=len(value)<=30:fail('集合条件需要1–30个值。')
        found=any([test_condition({'column':c,'operator':'eq','value':v,'type':kind},row,columns,budget,depth+1) for v in value])
        return found if op=='in' else not found
    if not isinstance(value,(str,int,float)) or isinstance(value,bool) or len(str(value))>200:fail('条件值无效。')
    if op in ('contains','not_contains'):
        if kind!='text':fail('包含比较只用于文字。')
        present=normal(value) in normal(cell)
        return present if op=='contains' else not present
    if kind=='number':
        if not numeric_column(c):fail('标识字段不能作为数值比较。')
        if str(cell).strip().endswith(('%','％')) and not other and not str(value).strip().endswith(('%','％')):
            fail('百分比列的条件值必须带%单位，例如90%，避免把90误当成比例90而非0.9。')
        a,b=cell_number(cell,c),cell_number(value,other or c)
    elif kind=='date':a,b=calendar_date(cell),calendar_date(value)
    else:
        if op in ('gt','gte','lt','lte'):fail('大小比较请指定数字或日期类型。')
        a,b=normal(cell),normal(value)
    if a is None or b is None:return False
    return {'eq':lambda:a==b,'ne':lambda:a!=b,'gt':lambda:a>b,'gte':lambda:a>=b,'lt':lambda:a<b,'lte':lambda:a<=b}[op]()


def validate_condition(condition,columns):
    # A nonempty sentinel validates syntax even for an empty input table.
    # Type conversion uses zero/date placeholders appropriate to each leaf.
    budget=[64]
    def walk(node,depth=0):
        budget[0]-=1
        if depth>6 or budget[0]<0 or not isinstance(node,dict):fail('组合条件无效或过多。')
        if len(node)==1 and next(iter(node)) in ('all','any','not'):
            k=next(iter(node));children=[node[k]] if k=='not' else node[k]
            if not isinstance(children,list) or not 1<=len(children)<=12:fail('组合条件不能为空。')
            for child in children:walk(child,depth+1)
        else:
            placeholder=['' for _ in columns]
            c=column(node.get('column'),columns)
            placeholder[columns.index(c)]='2000-01-01' if node.get('type')=='date' else '0'
            if node.get('value_column'):placeholder[columns.index(column(node['value_column'],columns))]=placeholder[columns.index(c)]
            test_condition(node,placeholder,columns)
    walk(condition)


def normalize_expression(expr,depth=0):
    if not isinstance(expr,dict) or depth>6:fail('派生表达式需要JSON对象，最多嵌套6层。')
    if expr.get('type')=='number' and len(expr)==2 and ('column' in expr or 'constant' in expr):expr={k:v for k,v in expr.items() if k!='type'}
    if len(expr)!=1:fail('表达式每个节点只能有column、constant或一个算术操作，不要添加type等其他参数。')
    k,v=next(iter(expr.items()))
    if k in ('column','constant'):return dict(expr)
    if k not in ('add','subtract','multiply','divide') or not isinstance(v,list) or len(v)!=2:
        fail('derive只支持add/subtract/multiply/divide两个操作数；文字排序直接用sort，计数用group或summary，不使用concat或类型转换表达式。')
    return {k:[normalize_expression(x,depth+1) for x in v]}


def evaluate_expression(expr,row,columns,depth=0):
    if depth>6 or not isinstance(expr,dict) or len(expr)!=1:fail('计算表达式无效。')
    op,arg=next(iter(expr.items()))
    if op=='column':
        c=column(arg,columns)
        if not numeric_column(c):fail('不能对标识字段计算。')
        return cell_number(row[columns.index(c)],c)
    if op=='constant':return number(arg)
    if op not in ('add','subtract','multiply','divide') or not isinstance(arg,list) or len(arg)!=2:fail('派生列只支持两项加减乘除。')
    a,b=[evaluate_expression(x,row,columns,depth+1) for x in arg]
    if a is None or b is None:return None
    if op=='divide' and b==0:fail('派生列出现除以零，请明确处理方式。')
    with localcontext() as ctx:
        ctx.prec=40
        value={'add':lambda:a+b,'subtract':lambda:a-b,'multiply':lambda:a*b,'divide':lambda:a/b}[op]()
    if abs(value)>Decimal('1e30'):fail('计算结果超出范围。')
    return value


def run_program(table, operations, emit=None):
    check_table(table)
    if not isinstance(operations,list) or len(operations)>10:fail('一次最多组合10个表格操作。')
    position=0
    def progress(index,entry):
        nonlocal position
        position=index+1
        if emit:emit(index,entry)
    try:return _run_program(table,operations,progress)
    except TableError as exc:
        if position>=len(operations):raise
        step=operations[position]
        op=step.get('op','unknown') if isinstance(step,dict) else 'unknown'
        error=TableError(f'操作index={position}（{op}）失败：{exc}')
        error.operation_index=position;error.operation=op
        raise error from exc


def _run_program(table, operations, emit=None):
    data=deepcopy(table);data.setdefault('provenance',[[i] for i in range(len(data['rows']))])
    if operations:data.pop('summaries',None)
    trace=[];notes=list(data.get('notes',[]));lost=set()
    for index,step in enumerate(operations):
        if not isinstance(step,dict) or not isinstance(step.get('op'),str):fail('表格操作无效。')
        op=step['op'];before=len(data['rows']);cols=data['columns'];rows=data['rows'];prov=data['provenance']
        allowed={'filter':{'op','where'},'select':{'op','columns'},'sort':{'op','by'},'limit':{'op','count','offset'},'distinct':{'op','columns','keep'},'group':{'op','by','metrics'},'summary':{'op','by','metrics'},'derive':{'op','name','expression','format','precision','replace'}}
        if op not in allowed or set(step)-allowed[op]:fail('未知操作或参数：'+op)
        if op=='summary':
            if len(data.get('summaries',[]))>=3:fail('一次最多保留3份附加汇总。')
            summary=run_program(data,[{**step,'op':'group'}])
            data.setdefault('summaries',[]).append({k:summary[k] for k in ('columns','rows','provenance','units') if k in summary})
            notes.extend(summary.get('notes',[]))
        elif op=='filter':
            validate_condition(step.get('where'),cols)
            keep=[i for i,r in enumerate(rows) if test_condition(step['where'],r,cols)]
            data['rows']=[rows[i] for i in keep];data['provenance']=[prov[i] for i in keep]
        elif op=='select':
            requested=step.get('columns')
            if not isinstance(requested,list) or not requested:fail('选择字段不能为空。')
            if any(c in lost and c not in cols for c in requested):fail('group已将明细折叠，不能再选择原明细字段。需要同时保留明细和合计时，把group改为summary；summary的by与metrics参数相同。')
            chosen=[column(c,cols) for c in requested]
            if len(set(chosen))!=len(chosen):fail('输出字段重复。')
            data['rows']=[[r[cols.index(c)] for c in chosen] for r in rows];data['columns']=chosen
        elif op=='sort':
            keys=step.get('by')
            if not isinstance(keys,list) or not 1<=len(keys)<=4:fail('排序需要1–4个字段。')
            prepared=[]
            for k in keys:
                if not isinstance(k,dict) or set(k)-{'column','direction','type'}:fail('排序参数无效。')
                c=column(k.get('column'),cols);kind=k.get('type','text');direction=k.get('direction','asc')
                if kind not in ('text','number','date') or direction not in ('asc','desc'):fail('排序类型或顺序无效。')
                if kind=='number' and not numeric_column(c):fail('标识字段请按文字排序。')
                parser=(lambda x,c=c:cell_number(x,c)) if kind=='number' else calendar_date if kind=='date' else lambda x:normal(x) or None
                prepared.append(([parser(r[cols.index(c)]) for r in rows],1 if direction=='asc' else -1))
            def compare(a,b):
                for values,direction in prepared:
                    x,y=values[a],values[b]
                    if x is None or y is None:
                        if x is y:continue
                        return 1 if x is None else -1  # blanks last in both directions
                    if x!=y:return direction*(1 if x>y else -1)
                return a-b
            order=sorted(range(len(rows)),key=cmp_to_key(compare));data['rows']=[rows[i] for i in order];data['provenance']=[prov[i] for i in order]
        elif op=='limit':
            count=step.get('count');offset=step.get('offset',0)
            if type(count)!=int or type(offset)!=int or not 0<=count<=MAX_ROWS or not 0<=offset<=MAX_ROWS:fail('取前几条的数量或起点无效。')
            data['rows']=rows[offset:offset+count];data['provenance']=prov[offset:offset+count]
        elif op=='distinct':
            if step.get('keep','first')!='first':fail('去重当前只支持保留first（首次）记录。')
            keys=step.get('columns')
            if not isinstance(keys,list) or not keys:fail('去重必须指定字段。')
            indices=[cols.index(column(c,cols)) for c in keys];seen={};keep=[]
            for i,row in enumerate(rows):
                key=tuple(normal(row[j]) for j in indices)
                if key not in seen:seen[key]=i;keep.append(i)
                else:prov[seen[key]]=sorted(set(prov[seen[key]]+prov[i]))
            data['rows']=[rows[i] for i in keep];data['provenance']=[prov[i] for i in keep]
        elif op=='derive':
            name=step.get('name');fmt=step.get('format','number');places=step.get('precision',2)
            replace=step.get('replace',False)
            if type(replace)!=bool or (replace and name not in cols):fail('重算字段必须是已存在的列。')
            if not isinstance(name,str) or not name.strip() or len(name)>80 or (name in cols and not replace) or (not replace and len(cols)>=MAX_COLUMNS):fail('派生字段名称无效或重复。')
            if fmt not in ('number','percent') or type(places)!=int or not 0<=places<=8:fail('派生字段显示格式无效。')
            expression=normalize_expression(step.get('expression'))
            def units(expr,depth=0):
                if depth>6 or not isinstance(expr,dict) or len(expr)!=1:fail('计算表达式无效。')
                k,v=next(iter(expr.items()))
                if k=='column':
                    c=column(v,cols)
                    if not numeric_column(c):fail('不能对标识字段计算。')
                    return data.get('units',{}).get(c) or currency(c,[r[cols.index(c)] for r in rows])
                if k=='constant':number(v);return ''
                if k not in ('add','subtract','multiply','divide') or not isinstance(v,list) or len(v)!=2:fail('计算表达式无效。')
                a,b=[units(x,depth+1) for x in v]
                if k in ('add','subtract') and a and b and a!=b:fail('不同货币不能直接相加减。')
                return '' if k=='divide' and a==b else a or b
            result_unit=units(expression)
            values=[evaluate_expression(expression,r,cols) for r in rows]
            # Validate an empty result's expression too.
            rendered=[('' if v is None else decimal_text(v*(100 if fmt=='percent' else 1/header_scale(name)),places)+('%' if fmt=='percent' else '')) for v in values]
            if replace:
                position=cols.index(name)
                data['rows']=[r[:position]+[v]+r[position+1:] for r,v in zip(rows,rendered)]
            else:
                data['rows']=[r+[v] for r,v in zip(rows,rendered)];data['columns']=cols+[name]
            data.setdefault('units',{})[name]=result_unit
            missing=sum(v is None for v in values)
            if missing:notes.append(f'{name}：{missing}行因原字段为空而未计算，未当作零。')
        else:
            by=step.get('by',[]);metrics=step.get('metrics')
            if not isinstance(by,list) or len(by)>3 or not isinstance(metrics,list) or not 1<=len(metrics)<=8:fail('分组或统计指标无效。')
            groups=[column(c,cols) for c in by];names=[];prepared=[];output_units={}
            for m in metrics:
                if not isinstance(m,dict) or set(m)-{'function','column','as','precision'}:fail('统计指标参数无效。')
                fn=m.get('function');name=m.get('as')
                if fn not in ('sum','mean','min','max','count','count_distinct') or not isinstance(name,str) or not 1<=len(name)<=80:fail('统计方式或结果字段名无效。')
                if name in groups+names:fail('统计结果字段重名。')
                c=column(m['column'],cols) if m.get('column') else None
                if fn not in ('count',) and c is None:fail('统计缺少字段。')
                if fn in ('sum','mean','min','max'):
                    if not numeric_column(c):fail('标识字段不能求和或平均。')
                    detected=currency(c,[r[cols.index(c)] for r in rows])
                    output_units[name]=data.get('units',{}).get(c) or detected
                places=m.get('precision',2)
                if type(places)!=int or not 0<=places<=8:fail('统计精度需要0–8位小数。')
                prepared.append((fn,c,name,places));names.append(name)
            buckets={}
            for i,r in enumerate(rows):buckets.setdefault(tuple(r[cols.index(c)] for c in groups),[]).append(i)
            if not groups and not rows:buckets[()]=[]
            out=[];out_prov=[]
            for key,indices in buckets.items():
                values=[]
                for fn,c,name,places in prepared:
                    cells=[rows[i][cols.index(c)] for i in indices] if c else []
                    if fn=='count':value=str(sum(bool(str(v).strip()) for v in cells)) if c else str(len(indices))
                    elif fn=='count_distinct':value=str(len({normal(v) for v in cells if str(v).strip()}))
                    else:
                        parsed=[cell_number(v,c) for v in cells];valid=[v for v in parsed if v is not None]
                        if len(valid)!=len(parsed):notes.append(f'{name}：{len(parsed)-len(valid)}个空值未参与计算。')
                        with localcontext() as ctx:
                            ctx.prec=40
                            aggregate=sum(valid,Decimal(0)) if fn=='sum' and valid else sum(valid,Decimal(0))/len(valid) if fn=='mean' and valid else min(valid) if fn=='min' and valid else max(valid) if fn=='max' and valid else None
                            value=decimal_text(aggregate/header_scale(name) if aggregate is not None else None,places if fn=='mean' else None)
                        if not valid:notes.append(f'{name}：没有有效数值，结果留空，未替换为零。')
                    values.append(value)
                out.append(list(key)+values);out_prov.append(sorted({p for i in indices for p in prov[i]}))
            lost.update(set(cols)-set(groups+names));data.update(columns=groups+names,rows=out,provenance=out_prov,units=output_units)
        check_table(data)
        entry={'operation':op,'input_rows':before,'output_rows':len(data['rows']),'columns':data['columns']}
        trace.append(entry)
        if emit:emit(index,entry)
    data.update(trace=trace,notes=list(dict.fromkeys(notes)))
    return data
