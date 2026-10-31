"""Canonical, typed generation forms derived from the current local schema."""
from copy import deepcopy
import json


def obj(properties, optional=()):
    return {'type':'object', 'properties':properties,
            'required':[key for key in properties if key not in optional], 'additionalProperties':False}


def array(items, minimum=0, maximum=16):
    return {'type':'array', 'items':items, 'minItems':minimum, 'maxItems':maximum}


def text(maximum=80):
    return {'type':'string', 'maxLength':maximum}


def enum(values):
    unique=[];seen=set()
    for value in values:
        key=json.dumps(value,ensure_ascii=False,sort_keys=True)
        if key not in seen:unique.append(value);seen.add(key)
    return {'enum':unique}


def _view_schema(flow, key, prefix, contract=None):
    """Only one primitive dialect is generated; legacy saved forms still load."""
    from table_semantics import UNITS, unit_definition
    from general_assistant import numbers
    from table_program import decimal_text
    from decimal import Decimal
    contract=contract or {}
    summaries=[k for k in flow.views if flow.shapes[k]=='aggregate' and flow.initial_scope_satisfied([k],contract.get('initial_distinct_keys'))]
    preserve=contract.get('preserve_detail',contract.get('deliver')=='both')
    fields = {f['id']:f for f in flow.fields(flow.views[key])}
    refs = enum(fields)
    # A new label and an existing field reference are different parameters.
    # Reserve registry identifiers while leaving business labels open-ended.
    label = {'type':'string','minLength':1,'maxLength':80,
             'not':{'enum':['F'+str(i) for i in range(1,len(flow.registry)+18)]}}
    numeric = enum(k for k,f in fields.items() if f['type'] in ('number','percent'))
    scalar = {'oneOf':[text(240), {'type':'number'}, {'type':'boolean'}]}
    leafs = [obj({'field':refs, 'op':enum(['is_empty','not_empty'])}),
             obj({'field':refs, 'op':enum(['eq','ne','contains','not_contains','gt','gte','lt','lte']), 'value':scalar}),
             obj({'field':refs, 'op':enum(['in','not_in']), 'value':array(scalar,1,16)}),
             obj({'field':refs, 'op':enum(['eq','ne','gt','gte','lt','lte']), 'other':refs})]
    constants = sorted({decimal_text(Decimal(v.numerator)/Decimal(v.denominator))
                        for v in numbers(flow.goal)} | {'0','1'})
    defs = {'C0':{'oneOf':leafs}, 'E0':{'oneOf':[obj({'column':numeric}), obj({'constant':enum(constants)})]}}
    for i in range(1,7):
        child = {'$ref':'#/$defs/C'+str(i-1)}
        defs['C'+str(i)] = {'oneOf':leafs+[obj({'all':array(child,1,16)}), obj({'any':array(child,1,16)}), obj({'not':child})]}
        expression = {'$ref':'#/$defs/E'+str(i-1)}
        defs['E'+str(i)] = {'oneOf':deepcopy(defs['E0']['oneOf'])+
                          [obj({key:array(expression,2,2)}) for key in ('add','subtract','multiply','divide')]}
    inp = {'const':key}
    def action(tool,props,optional=()):
        return obj({'tool':{'const':tool},'input':inp,**props}, optional)
    count_metric = obj({'function':{'const':'count'},'name':label}, ())
    metric = obj({'function':enum(['sum','mean','min','max','count_distinct']), 'field':refs, 'name':label})
    # Per-field display commands choose only compatible, known unit spellings.
    presentation = []
    for identifier,f in fields.items():
        if f['type'] not in ('number','percent'):
            continue
        dimensions = {flow.views[key].get('units',{}).get(f['column'],'')}
        if f['type']=='percent':dimensions.add('ratio')
        units = [key for key in UNITS if unit_definition(key)[0] in dimensions and unit_definition(key)[0]]
        if units:presentation.append(obj({'field':{'const':identifier},'unit':enum(units)}))
    branches = [action('filter',{'where':{'$ref':'#/$defs/C6'}}),
                action('derive',{'name':label,'formula':{'$ref':'#/$defs/E6'},'format':enum(['number','percent']),'precision':{'enum':list(range(9))}},('precision',)),
                action('group',{'by':array(refs,0,6),'metrics':array({'oneOf':[count_metric,metric]},1,8)}),
                action('distinct',{'fields':array(refs,1,12)}),
                action('sort',{'by':array(obj({'field':refs,'direction':enum(['asc','desc'])}),1,8)}),
                action('select',{'fields':array(refs,1,40)}),
                action('limit',{'count':{'type':'integer'},'offset':{'type':'integer'}},('offset',)),
                action('inspect',{'fields':array(refs,1,6)}),
                ]
    def global_summary(key):
        steps={s['id']:s for s in flow.graph}
        while key in steps:
            op=steps[key]['operation']
            if op['op']=='group':return not op['by']
            key=steps[key]['input']
        return False
    can_finish=(not preserve or (flow.shapes[key]=='detail' and bool(summaries))) and (not contract.get('global_summary') or any(global_summary(k) for k in summaries))
    can_finish=can_finish and flow.initial_scope_satisfied([key],contract.get('initial_distinct_keys'))
    if can_finish:
        summary_array=array(enum(summaries),1 if preserve else 0,min(3,len(summaries)))
        branches.append(obj({'tool':{'const':'finish'},'result':inp,'summaries':summary_array,'fields':array(refs,1,min(40,len(fields)))},('fields',)))
    if presentation:
        branches.insert(-1,action('present',{'units':array({'oneOf':presentation},1,12)}))
    # Namespaces let every input bind its own field enum.  A grouped view
    # cannot request a date or status field that only exists in raw data.
    def namespace(value):
        if isinstance(value,list):return [namespace(v) for v in value]
        if not isinstance(value,dict):return value
        return {k:(v.replace('#/$defs/','#/$defs/'+prefix) if k=='$ref' else namespace(v)) for k,v in value.items()}
    return namespace(branches),{prefix+name:namespace(value) for name,value in defs.items()}


def action_schema(flow,contract=None):
    branches=[];definitions={}
    for index,key in enumerate(flow.views):
        actions,defs=_view_schema(flow,key,'V'+str(index)+'_',contract)
        branches.extend(actions);definitions.update(defs)
    branches.append(obj({'clarify':text(220)}))
    return {'oneOf':branches,'$defs':definitions}


def selection_schema(tables):
    choices=[]
    for table in tables:
        maximum=min(20,table['row_count'])
        headers=[list(range(start,start+count)) for start in range(1,maximum+1) for count in (1,2,3) if start+count-1<=maximum]
        choices.append(obj({'id':{'const':table['id']},'header_rows':enum(headers),'exclude_summary':{'type':'boolean'}}))
    return {'oneOf':[obj({'tables':array({'oneOf':choices},1,min(12,len(tables)))}),
        obj({'clarify':text(220)})]}
