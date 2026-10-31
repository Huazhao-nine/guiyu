"""Source-bound recovery checks for immutable local table views."""
import re
from table_program import TableError
from table_semantics import header_unit
from copy import deepcopy


def previous_scope_proof(flow):
    if not flow.verified_previous_scope or 'P0' not in flow.views:return None
    from workbook_flow import fingerprint
    return {'previous_result_hash':fingerprint(flow.views['P0']),'initial_distinct_keys':list(flow.previous_distinct_keys)}


def restore_previous_scope_proof(flow,config):
    proof=config.get('flow',{}).get('previous_scope_proof')
    if not proof:return
    from workbook_flow import fingerprint
    if (not isinstance(proof,dict) or set(proof)!={'previous_result_hash','initial_distinct_keys'}
        or 'P0' not in flow.views or proof['previous_result_hash']!=fingerprint(flow.views['P0'])
        or not isinstance(proof['initial_distinct_keys'],list) or any(not isinstance(k,str) for k in proof['initial_distinct_keys'])):
        raise TableError('已保存的上轮结果核对依据不一致，请重新规划。')
    flow.verified_previous_scope=True;flow.previous_distinct_keys=list(proof['initial_distinct_keys'])


def conjunction_atoms(node):
    if not isinstance(node,dict):return []
    if set(node)=={'all'}:return [a for child in node['all'] for a in conjunction_atoms(child)]
    if 'column' in node and 'value' in node:return [node]
    return []  # OR and NOT are not unconditional facts.


def calculation_still_valid(flow,step,key):
    """Do not reuse an old calculation after its input or result was replaced."""
    operation=step['operation'];watched={operation['name']}
    def references(node):
        if 'column' in node:watched.add(node['column'])
        for value in node.values():
            if isinstance(value,list):
                for child in value:references(child)
    references(operation['expression'])
    while key!=step['id'] and key in flow.parents:
        between=next(s for s in flow.graph if s['id']==key)['operation']
        if between['op']=='group' or (between['op']=='derive' and between['name'] in watched):return False
        key=flow.parents[key]
    return key==step['id']


def check_filter_ancestry(flow,key,where):
    from workbook_intent import check_predicate
    incoming=conjunction_atoms(where)
    if not incoming:return
    known=list(incoming);changed=set();cursor=key
    while cursor in flow.parents:
        step=next(s for s in flow.graph if s['id']==cursor);op=step['operation']
        if op['op']=='group':break
        if op['op']=='derive':changed.add(op['name'])
        if op['op']=='filter':
            facts=[a for a in conjunction_atoms(op['where']) if not ({a.get('column'),a.get('value_column')}&changed)]
            try:check_predicate({'all':known+facts})
            except TableError as exc:
                raise TableError(str(exc)+' 当前输入'+key+'已经受前序条件限制；请退回该筛选前仍保留的'+step['input']+'，依据原话修正后重建后续步骤，不要在已经排除的记录上继续筛。') from exc
            known.extend(facts)
        cursor=step['input']


def explicit_recompute(goal,name):
    """Only authorize a copied numeric field named in a positive user clause."""
    stem=header_unit(name)[1].strip()
    if len(stem)<2:return False
    for clause in re.split(r'[，,。；;\n]',goal):
        if re.search(r'不要|不必|无需|不需要|禁止|别|例如|比如|假设',clause):continue
        if re.search(r'(?:重算|重新(?:计算|核算|核对计算)|recompute|recalculate)\s*[“「\"]?'+re.escape(stem),clause,re.I):return True
        if re.search(re.escape(stem)+r'[”」\"]?\s*(?:需要|要|请)?\s*(?:重算|重新(?:计算|核算)|recompute|recalculate)',clause,re.I):return True
    return False


def check_aggregate_grain(flow,key,where):
    """A follow-up about previous groups must not filter homonymous raw rows."""
    if flow.shapes.get('P0')!='aggregate' or flow.shapes[key]!='detail':return
    from workbook_intent import literal_numeric_requirements,compact
    prior=flow.views['P0'];requirements=literal_numeric_requirements(flow.current_goal,prior)
    for bound in requirements:
        # Bind the scope suffix to the same metric clause, not a separate goal.
        quote=bound['quote'];text=compact(flow.current_goal);start=text.find(quote)
        if start<0:continue
        clause=re.split(r'[，,。；;\n]',text[start:],maxsplit=1)[0]
        if not re.search(r'(?:的(?:分组|组|类别|团队|部门)|分组结果|汇总结果)',clause):continue
        if re.search(r'每条|单条|单笔|每次|单次|原始记录|明细记录',clause):continue
        stem=compact(header_unit(bound['column'])[1])
        for atom in conjunction_atoms(where):
            if compact(header_unit(atom.get('column',''))[1])!=stem:continue
            raise TableError('原话“'+quote+'”限制的是上轮汇总后的组，不是单条记录。请直接在P0的已核对分组结果上筛选，或先完成group再筛；明细行上的同名字段不能代替累计值。')


def global_summary_recipes(graph,finish):
    """Retain only executed whole-detail summary definitions, never values."""
    steps={s['id']:s for s in graph};recipes=[]
    for key in finish.get('summaries',[]):
        while key in steps:
            step=steps[key];op=step['operation']
            if op['op']=='group':
                if not op['by'] and op not in recipes:recipes.append(deepcopy(op))
                break
            if op['op'] not in ('select','sort'):break
            key=step['input']
    return recipes[:3]


def restore_global_summaries(flow,contract,action):
    """Recompute a retained verified definition on this delivery's detail."""
    key=action.get('result');refs=action.get('summaries',[])
    if not contract.get('global_summary') or key not in flow.views or flow.shapes[key]!='detail':return False
    if refs and all(s in flow.views for s in refs):return False
    recipes=contract.get('retained_summary_recipes',[])
    if not recipes:return False
    from workbook_flow import execute_operation
    for op in recipes:execute_operation(flow.views[key],op)  # all validate before mutation
    restored=[]
    for op in recipes:
        existing=next((s['id'] for s in flow.graph if s['input']==key and s['operation']==op),None)
        restored.append(existing or flow.record(key,op)['view'])
    action['summaries']=restored
    contract['summary_dependency_repairs']=contract.get('summary_dependency_repairs',0)+1
    return True


def interpret_followup_delta(office,flow,contract):
    """Interpret just the new narrowing request against the verified result.

    This is model interpretation, not a literal business-rule compiler. Every
    action still passes normal field/type/grounding checks, then delivery review.
    Unsupported changes fall back to full source planning without mutation.
    """
    if not flow.verified_previous_scope or 'P0' not in flow.views:return None
    from workbook_flow import ask
    table=flow.views['P0'];fields=flow.fields(table)
    value=ask(office,'你只解释用户这一次对已完成结果的追问，不重新解释旧任务。上轮结果已经核对，原有条件继续成立。'
              '将这次新增的缩小范围、排序或选列要求映射到给出的真实字段。若“累计值达标的组”指上轮汇总，直接筛这个汇总。'
              '只用filter、sort、select、limit，不能算新列、重新分组、放宽或替换旧条件。若上轮汇总缺少本次需要的明细日期等字段，返回{"not_applicable":true,"narrows":true,"quote":"本轮进一步缩小记录范围的连续原话"}，后续会回原始明细处理。'
              '若需要改变统计定义、放宽旧条件、仅改变展示或无法确定含义，返回{"not_applicable":true}。'
              '可处理时只返回{"quote":"这次要求中对应新增操作的连续原话","actions":[{"tool":"filter","where":{"field":"真实字段名","op":"比较方式","value":"取值"}}]}。'
              '最多3个动作，不填input/result/summaries，不编造列、阈值或数据。只有文件导出要求而没有新增数据操作时返回not_applicable。',
              {'本轮追问':flow.current_goal,'已核对结果类型':flow.shapes['P0'],'实际字段':fields,
               '结果示例':{'columns':table['columns'],'rows':table['rows'][:8]},'记录数':len(table['rows'])},650)
    if value=={'not_applicable':True}:return None
    if set(value)=={'not_applicable','narrows','quote'} and value['not_applicable'] is True and value['narrows'] is True:
        quote=value['quote']
        if not isinstance(quote,str) or not 2<=len(quote)<=220 or quote not in flow.current_goal:raise TableError('追问范围解释缺少本轮原话依据。')
        contract['retained_scope']['mode']='subset'
        contract['scope_interpretation']={'quote':quote,'scope':'subset','source':'local model; original scope replay and source checks retained'}
        return None
    if set(value)!={'quote','actions'} or not isinstance(value['quote'],str) or len(value['quote'])<2 or value['quote'] not in flow.current_goal:raise TableError('追问解释缺少本轮原话依据。')
    actions=value['actions']
    if not isinstance(actions,list) or not 1<=len(actions)<=3 or any(not isinstance(a,dict) or a.get('tool') not in ('filter','sort','select','limit') or {'input','result','summaries'}&set(a) for a in actions):raise TableError('追问只能追加少量已支持的结果操作。')
    before=deepcopy(flow.__dict__)
    try:
        key='P0'
        for action in actions:key=flow.apply(dict(action,input=key))['view']
    except (ValueError,TypeError,KeyError):
        flow.__dict__.clear();flow.__dict__.update(before);raise
    contract['delta_interpretation']={'quote':value['quote'],'actions':deepcopy(actions),'base':'P0','source':'local model; normal typed checks and delivery review retained'}
    if any(action['tool'] in ('filter','limit') for action in actions):contract['retained_scope']['mode']='subset'
    office.workbook_metrics['focused_followup_actions']=len(actions)
    return {'tool':'finish','result':key,'summaries':[]}
