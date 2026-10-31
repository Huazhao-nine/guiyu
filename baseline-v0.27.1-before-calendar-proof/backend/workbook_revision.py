"""Narrow revisions of a verified data plan; no file names or business aliases.

The model maps a quoted new boundary to a real column. Code changes only that
boundary, preserves all other operations, replays from the same source snapshot,
and rebuilds every dependent detail/summary. Ambiguous edits use normal planning.
"""
from copy import deepcopy
import re
from table_program import TableError


def eligible(goal):
    return bool(re.search(r'改|调整|放宽|收紧|门槛|边界|不少于|不超过|不早于|不晚于',goal) and
                re.search(r'不变|保持|沿用|刚才|上轮|上次|原始|这批',goal) and
                not re.search(r'基于.{0,30}(?:结果|明细)|只在.{0,30}结果|换.{0,6}(?:文件|工作簿)|另一份|不要沿用',goal))


def covered_request(goal,quotes,column_count=None):
    """Only recognize explicit unchanged/context/export clauses outside edits."""
    from workbook_intent import normalize_continuity
    text=normalize_continuity(goal)
    from general_assistant import chinese_integer
    for match in re.finditer(r'([0-9零一二两三四五六七八九十]+)列',text):
        count=int(match[1]) if match[1].isdigit() else chinese_integer(match[1])
        if column_count is None or count!=column_count:return False
    for quote in sorted(quotes,key=len,reverse=True):
        if not isinstance(quote,str) or not quote or quote not in goal:return False
        if re.search(r'分组|排序|去重|导出|Word|[加乘除]|另外|同时|并且|按.{0,30}(?:汇总|统计)',quote,re.I):return False
        text=text.replace(quote,'',1)
    patterns=[r'(?:其他|其它|其余)(?:的)?(?:筛选条件|条件|要求|设置)(?:[、和与及](?:排序|输出字段|输出列|字段|列|条件|要求|设置|汇总|明细)){0,6}(?:均|都)?(?:保持)?不变',
              r'回到(?:刚才|上次|上轮)(?:的)?[^，,。；;\n]{0,24}?(?:工作簿|表格|资料|任务)',
              r'从原始(?:记录|数据|明细)(?:重新)?(?:重算|计算|处理)',
              r'沿用[^，,。；;\n]{1,80}(?:条件|要求|设置)',
              r'(?:其他|其它|其余)(?:的)?(?:要求|条件|设置|安排)?(?:保持)?不变',
              r'(?:[0-9零一二两三四五六七八九十]+列|原有列|输出列|输出字段|字段|排序|筛选条件|金额合计|合计|条数|明细|汇总)(?:和|、|与|及|都|继续|保持|不变|照旧|保留|输出列|金额合计|合计|条数|明细|汇总)*',
              r'(?:这次)?只(?:需要|要)(?:表格|Excel|CSV)',
              r'(?:不要|无需|不需要)(?:再)?(?:导出)?\s*(?:Word|DOCX)',
              r'(?:继续|仍然)?(?:导出|保留)\s*(?:Word|DOCX)',r'原文件不(?:改动|变)']
    for _ in range(2):
        for pattern in patterns:text=re.sub(pattern,'',text,flags=re.I)
    return not re.sub(r'[\s，,。；;！!？?、和与及请把将再也的]','',text)


def build_flow(source,config,goal):
    from workbook_flow import TableFlow,execute_operation
    from table_semantics import describe
    flow=TableFlow(source,goal,config.get('previous_result'),previous_shape=config.get('previous_shape'))
    from workbook_recovery import restore_previous_scope_proof
    restore_previous_scope_proof(flow,config)
    graph=config['flow']['graph']
    if not isinstance(graph,list) or len(graph)>16:raise TableError('已保存步骤超出复用范围。')
    for item in graph:
        name,key,op=item['id'],item['input'],item['operation']
        if name in flow.views or key not in flow.views:raise TableError('已保存步骤引用无效。')
        value=execute_operation(flow.views[key],op)
        flow.views[name]=value;flow.parents[name]=key
        flow.shapes[name]='aggregate' if op['op']=='group' else flow.shapes[key]
        describe(value,flow.registry);flow.graph.append(deepcopy(item));flow.last=name
    return flow


def delivery_only_request(goal,row_count):
    """Recognize a fully covered export request, never a new data operation."""
    from workbook_intent import normalize_continuity,writing_intent
    from general_assistant import chinese_integer
    text=normalize_continuity(goal)
    writing,denied,no_word=writing_intent(text)
    if not (writing or no_word or denied):return False
    if re.search(r'另外|另一份|换.{0,8}(?:文件|资料|工作簿)|不要沿用|不沿用|取消.{0,8}(?:条件|筛选)',text):return False
    # A reference to the already singular result is metadata, not permission
    # to choose the first row out of a larger result.
    for m in list(re.finditer(r'(?:只要|只留|给)?(?:前([0-9零一二两三四五六七八九十]+)名|第([0-9零一二两三四五六七八九十]+)名)(?:的)?(?:结果)?',text))[::-1]:
        n=int(m[1] or m[2]) if (m[1] or m[2]).isdigit() else chinese_integer(m[1] or m[2])
        if not n==row_count==1:return False
        text=text[:m.start()]+text[m.end():]
    text=re.sub(r'回到(?:刚才|上次|上轮)(?:的)?[^，,。；;\n]{0,24}?(?:汇总|结果|表格|数据|明细|工作簿)(?=[，,。；;\n])','',text)
    text=re.sub(r'(?:其他|其它|其余)(?:的)?条件不变','',text)
    text=re.sub(r'(?:上轮|上次|刚才|当前|这个|这份|这些|原来|原有)(?:的)?(?:结果|汇总|明细|表格|数据)','',text)
    text=re.sub(r'(?:不要|不用|无需|不必|不需要)(?:再)?(?:导出|另存|生成|保存|写|给我)?\s*(?:一份|一版|一个)?\s*(?:Word|DOCX)','',text,flags=re.I)
    text=re.sub(r'(?:导出|另存|生成|保存|给我|写)(?:为|成|一份|一版|一个|成一份|为一份|成一个|为一个|成一版|为一版)?\s*(?:Word|DOCX)(?:文档|文稿|副本|文件)?','',text,flags=re.I)
    return not re.sub(r'[\s，,。；;！!？?、请把将给我再也的]','',text)


def try_delivery_reuse(source,goal,parent,old):
    """Replay a checked final view when only its Word delivery changes.

    The caller admits old state only for the unchanged source snapshot. Every
    old operation and prior-result proof is replayed before reusing its result.
    """
    if not old or not parent or old.get('snapshot')!=parent.get('snapshot'):return None
    previous=old.get('result_table') or {}
    if not delivery_only_request(goal,len(previous.get('rows',[]))):return None
    config=parent.get('workbook') or {}
    if config.get('mode')!='flow' or not config.get('flow'):return None
    from workbook_flow import fingerprint,freeze_finish
    from workbook_intent import writing_intent
    try:
        flow=build_flow(source,config,goal)
        finish=deepcopy(config['flow']['finish']);contract=deepcopy(config['flow']['contract'])
        result=flow.finish(finish,contract,check_intent=False)
        if fingerprint(result)!=config['flow']['expected'] or fingerprint(result)!=fingerprint(previous):return None
        writing,denied,no_word=writing_intent(goal)
        contract.update(docx=bool(writing and not no_word),write=goal[writing.start():] if writing and not no_word else '')
        contract['requirements']=list(dict.fromkeys(list(contract.get('requirements',[]))+[goal]))[-16:]
        contract['delivery_revision']={'parent_id':parent['id'],'data_unchanged':True,'proof':'Exact previous final view and typed graph replayed from unchanged sources before changing export only.'}
        result=flow.finish(finish,contract)
        return flow,contract,freeze_finish(flow,finish),result,[]
    except (ValueError,TypeError,KeyError,StopIteration):return None


def retained_scope_flow(source,goal,parent,previous,previous_goal):
    """Replay a verified detail scope for an explicit keep-filters follow-up.

    Start from the unchanged authorized source, retaining its typed conditions
    and row calculations. Do not rely on a summary of earlier chat messages.
    """
    clause=r'(?:保留|沿用)(?:上轮|上次|刚才|原有|之前)?(?:的)?筛选条件'
    from workbook_intent import normalize_continuity
    normalized=normalize_continuity(goal)
    unchanged=r'(?:其他|其它|其余)(?:的)?(?:条件|要求|设置|安排)(?:均|都)?(?:保持)?不变'
    if not parent or not (re.search(clause,normalized) or re.search(unchanged,normalized)) or re.search(r'取消|清除|全部记录|放宽|收紧|门槛.{0,8}改|不要沿用',goal):return None
    config=parent.get('workbook') or {}
    if config.get('mode')!='flow' or not config.get('flow'):return None
    from workbook_flow import TableFlow,fingerprint
    try:
        baseline=build_flow(source,config,goal)
        prior=baseline.finish(deepcopy(config['flow']['finish']),config['flow']['contract'],check_intent=False)
        if fingerprint(prior)!=config['flow']['expected']:return None
        key=config['flow']['finish']['result']
        while baseline.shapes[key]=='aggregate':key=baseline.parents[key]
        while key in baseline.parents:
            item=next(s for s in baseline.graph if s['id']==key)
            if item['operation']['op'] not in ('sort','select'):break
            key=item['input']
        path=[];cursor=key
        while cursor in baseline.parents:
            item=next(s for s in baseline.graph if s['id']==cursor);path.append(item);cursor=item['input']
        if cursor!='V0' or not path or len(path)>12:return None
        flow=TableFlow(source,goal+'\n'+previous_goal,previous,current_goal=goal,previous_shape='detail' if baseline.shapes[config['flow']['finish']['result']]=='detail' else 'aggregate')
        flow.verified_previous_scope=True
        flow.previous_distinct_keys=list(config['flow']['contract'].get('initial_distinct_keys') or [])
        for item in reversed(path):flow.record(flow.last,deepcopy(item['operation']))
        remaining=re.sub(clause+'|'+unchanged,'',normalized)
        remaining=re.sub(r'(?:这次)?只(?:需要|要)(?:表格|Excel|CSV)','',remaining,flags=re.I)
        restricts=bool(re.search(r'那[^，,。；;？?\n]{1,40}呢|筛|排除|剔除|只看|只要|单列|单独(?:列出|查看|统计|保留|展示|显示)|至少|至多|不少于|不超过|大于|小于|低于|高于|前\s*[0-9一二三四五六七八九十]+|去重|去掉',remaining))
        note={'parent_id':parent['id'],'input':flow.last,'rows':len(flow.views[flow.last]['rows']),
              'origins':sorted(flow.origins(flow.views[flow.last])),'mode':'subset' if restricts else 'equal',
              'proof':'Previous typed detail scope replayed from the unchanged source; no hidden chat inference.'}
        return flow,note
    except (ValueError,TypeError,KeyError,StopIteration):return None


def leaf_references(node):
    if not isinstance(node,dict):return []
    if 'column' in node:return [node]
    return [leaf for key in ('all','any','not') for child in (node.get(key,[]) if isinstance(node.get(key),list) else [node.get(key)]) for leaf in leaf_references(child)]


def repair_delivery_dependency(flow,finish,dependency):
    """Reconnect only an already verified deduplication of the same input."""
    graph=deepcopy(flow.graph)
    step=next(s for s in graph if s['id']==dependency['step'])
    through=next(s for s in graph if s['id']==dependency['through'])
    if step['operation']['op']!='group' or step['input']!=dependency['from'] or through['input']!=step['input'] or through['operation']['op']!='distinct' or set(through['operation']['columns'])!=set(dependency['keys']) or graph.index(through)>=graph.index(step):
        raise TableError('无法唯一恢复已验证的处理依赖，请重新核对目标。')
    step['input']=through['id']
    config={'previous_result':flow.views.get('P0'),'previous_shape':flow.shapes.get('P0'),'flow':{'graph':graph}}
    from workbook_recovery import previous_scope_proof
    config['flow']['previous_scope_proof']=previous_scope_proof(flow)
    rebuilt=build_flow(flow.views['V0'],config,flow.current_goal)
    rebuilt.goal=flow.goal;rebuilt.recipes=deepcopy(flow.recipes);rebuilt.presentation_units=deepcopy(flow.presentation_units);rebuilt.presentation_fields=deepcopy(flow.presentation_fields)
    return rebuilt,deepcopy(finish)


def repair_delivery_filter(flow,finish,condition,shape,before_limits=False):
    """Insert a source-quoted constraint and rebuild all dependent outputs."""
    fields={p['column'] for p in leaf_references(condition)}
    def ancestors(key):
        result=[key]
        while key in flow.parents:key=flow.parents[key];result.append(key)
        return result
    targets=[finish['result']]+finish.get('summaries',[]);chains=[ancestors(k) for k in targets]
    shared=next((k for k in chains[0] if flow.shapes[k]==shape and fields<=set(flow.views[k]['columns']) and all(k in c for c in chains[1:])),None)
    if shared is None or len(flow.graph)>=16:raise TableError('未找到可同时更新明细与汇总的条件位置。')
    if before_limits:
        upstream=set(ancestors(shared))
        limits=[s for s in flow.graph if s['id'] in upstream and s['operation']['op']=='limit']
        if limits:
            candidate=limits[0]['input']
            if flow.shapes[candidate]!=shape or not fields<=set(flow.views[candidate]['columns']):
                raise TableError('取前几条之前缺少筛选所需字段，请先在完整明细计算条件字段再排序截取；不能只过滤已经截取的结果。')
            shared=candidate
    graph=deepcopy(flow.graph);position=0 if shared in ('V0','P0') else next(i+1 for i,s in enumerate(graph) if s['id']==shared)
    marker='delivery-condition'
    for item in graph:
        if item['input']==shared:item['input']=marker
    graph.insert(position,{'id':marker,'input':shared,'operation':{'op':'filter','where':deepcopy(condition)}})
    mapping={'V0':'V0','P0':'P0'};renamed=[]
    for i,item in enumerate(graph,1):
        name='V'+str(i);renamed.append(dict(item,id=name,input=mapping[item['input']]));mapping[item['id']]=name
    action=deepcopy(finish);action['result']=mapping[marker] if finish['result']==shared else mapping[finish['result']]
    action['summaries']=[mapping[marker] if k==shared else mapping[k] for k in finish.get('summaries',[])]
    config={'previous_result':flow.views.get('P0'),'previous_shape':flow.shapes.get('P0'),'flow':{'graph':renamed}}
    from workbook_recovery import previous_scope_proof
    config['flow']['previous_scope_proof']=previous_scope_proof(flow)
    rebuilt=build_flow(flow.views['V0'],config,flow.current_goal)
    rebuilt.goal=flow.goal;rebuilt.recipes=deepcopy(flow.recipes);rebuilt.presentation_units=deepcopy(flow.presentation_units);rebuilt.presentation_fields=deepcopy(flow.presentation_fields)
    return rebuilt,action


def update_graph(flow,finish,condition,shape=None):
    """Replace one unique comparable boundary, or add one shared detail filter."""
    field=condition['column'];op=condition['operator']
    shape=shape or flow.shapes[finish['result']]
    family=lambda p:'lower' if p in ('gt','gte') else 'upper' if p in ('lt','lte') else p
    targets=[finish['result']]+finish.get('summaries',[])
    def ancestors(key):
        chain=[key]
        while key in flow.parents:key=flow.parents[key];chain.append(key)
        return chain
    active={key for target in targets for key in ancestors(target)}
    candidates=[]
    for item in flow.graph:
        if item['id'] not in active or item['operation']['op']!='filter':continue
        if flow.shapes[item['input']]!=shape:continue
        def conjunction(node):
            if set(node)=={'all'}:return [leaf for child in node['all'] for leaf in conjunction(child)]
            if 'column' in node:return [node]
            if any(leaf.get('column')==field for leaf in leaf_references(node)):raise TableError('该边界位于或/否定组合中，需要重新规划。')
            return []
        for leaf in conjunction(item['operation']['where']):
            if leaf.get('column')==field and family(leaf.get('operator'))==family(op) and 'value' in leaf:
                candidates.append(leaf)
    identities={(leaf['operator'],str(leaf['value']),leaf['type']) for leaf in candidates}
    if len(identities)>1:raise TableError('同一字段有多个不同边界，请明确要修改哪一个。')
    if candidates:
        for leaf in candidates:
            leaf.clear();leaf.update(deepcopy(condition))
        return deepcopy(flow.graph),deepcopy(finish),{'kind':'replace_boundary','occurrences':len(candidates)}
    chains=[ancestors(key) for key in targets]
    shared=next((key for key in chains[0] if all(key in chain for chain in chains[1:]) and flow.shapes[key]==shape and field in flow.views[key]['columns']),None)
    if shared is None:raise TableError('未找到所有明细与汇总共享的筛选位置。')
    graph=deepcopy(flow.graph);marker='revision-filter'
    index=0 if shared in ('V0','P0') else next(i+1 for i,s in enumerate(graph) if s['id']==shared)
    for item in graph:
        if item['input']==shared:item['input']=marker
    graph.insert(index,{'id':marker,'input':shared,'operation':{'op':'filter','where':deepcopy(condition)}})
    result=deepcopy(finish)
    if result['result']==shared:result['result']=marker
    if len(graph)>16:raise TableError('修改后超过数据步骤上限。')
    # Stable topological V identifiers keep the existing protocol and exports.
    mapping={'V0':'V0','P0':'P0'};renamed=[]
    for i,item in enumerate(graph,1):
        name='V'+str(i);renamed.append(dict(item,id=name,input=mapping[item['input']]))
        mapping[item['id']]=name
    result['result']=mapping[result['result']];result['summaries']=[mapping[s] for s in result.get('summaries',[])]
    return renamed,result,{'kind':'add_shared_filter','input':shared}


def covered_raw_revision(goal,rules,baseline,column_count):
    """Allow only a literal record bound plus provably unchanged grouping."""
    from table_program import column
    text=goal
    for rule in rules:
        quote=rule['quote']
        if quote not in text:return False
        text=re.sub(r'(?:(?:只|仅)(?:统计|处理|看|要))?\s*(?:单[票笔条次个份]|每[票笔条次个份])\s*(?='+re.escape(quote)+')','',text)
        text=re.sub(re.escape(quote)+r'(?:的)?(?:原始|源)?(?:登记|记录|明细)',quote,text)
    groups=[s['operation']['by'] for s in baseline.graph if s['operation']['op']=='group' and s['operation']['by']]
    for match in list(re.finditer(r'(?:仍|继续|照旧)(?:然)?按([^，,。；;\n]{1,80}?)(?:分组)?(?:汇总|统计)',text))[::-1]:
        label=match[1]
        try:keys=[column(label,baseline.views['V0']['columns'])]
        except TableError:
            try:keys=[column(p,baseline.views['V0']['columns']) for p in re.split(r'[、和与及]',label) if p.strip()]
            except TableError:return False
        if not keys or not any(set(keys)==set(group) for group in groups):return False
        text=text[:match.start()]+text[match.end():]
    return covered_request(text,[r['quote'] for r in rules],column_count)


def try_revision(office,source,goal,parent,old):
    if not old or not parent or not eligible(goal):return None
    config=parent.get('workbook') or {}
    if config.get('mode')!='flow' or not config.get('flow'):return None
    from workbook_flow import ask,fingerprint,freeze_finish
    from workbook_agent import check_grounding
    from workbook_intent import check_explicit_boundaries,check_predicate
    try:
        baseline=build_flow(source,config,goal)
        # P0 can already have narrower filters from an earlier task. It cannot
        # prove complete raw-source coverage for a relaxed boundary.
        if any(item['input']=='P0' for item in baseline.graph):return None
        prior=baseline.finish(deepcopy(config['flow']['finish']),config['flow']['contract'],check_intent=False)
        if fingerprint(prior)!=config['flow']['expected']:return None
        office.core.emit('progress',step=1,detail='正在沿用已核对步骤，调整这次的条件')
        from workbook_edits import literal_edits
        from workbook_requirements import raw_numeric_requirements
        raw=raw_numeric_requirements(goal,baseline.views['V0'])
        record_mode=bool(1<=len(raw)<=2 and covered_raw_revision(goal,raw,baseline,len(prior['columns'])))
        compiled=[{'field':r['column'],'op':r['operator'],'value':str(r['value']),'quote':r['quote']} for r in raw] if record_mode else literal_edits(baseline,config['flow']['finish'],config['flow']['contract'],goal)
        decision={'mode':'boundaries','edits':compiled} if compiled else ask(office,'只识别这次明确修改的一到两个数值或日期边界。其他步骤保持原样，不重新规划、不写文稿。JSON：{"mode":"boundaries","edits":[{"field":"实际列名","op":"gte","value":50,"quote":"当前目标中完整的改条件短语"}]}。quote逐字摘自当前目标，包含字段含义、比较词和新值。只是明确改门槛/起止日期才可使用boundaries；换分组、列、算法、数据源或其他要求用{"mode":"replan"}。field必须来自实际字段；数值已经统一基础单位。',
                     {'当前目标':goal,'上一轮目标':parent['prompt'],'实际字段':baseline.context()['fields'],'上次明细列':prior['columns']},450)
        if decision.get('mode')!='boundaries' or set(decision)!={'mode','edits'}:return None
        edits=decision['edits']
        if not isinstance(edits,list) or not 1<=len(edits)<=2:return None
        if not record_mode and not covered_request(goal,[e.get('quote') for e in edits if isinstance(e,dict)],len(prior['columns'])):return None
        changed=deepcopy(config);audit=[];fields=set()
        for edit in edits:
            if not isinstance(edit,dict) or set(edit)!={'field','op','value','quote'}:return None
            if edit['op'] not in ('gt','gte','lt','lte','eq'):return None
            main=baseline.views[changed['flow']['finish']['result']]
            probes=[baseline.views['V0']] if record_mode else [main] if baseline.shapes[changed['flow']['finish']['result']]=='aggregate' else reversed(list(baseline.views.values()))
            probe=next((v for v in probes if edit['field'] in v['columns'] and v.get('field_types',{}).get(edit['field']) in ('number','percent','date')),None)
            if probe is None:return None
            condition=baseline.predicate({k:v for k,v in edit.items() if k!='quote'},probe)
            if condition['column'] in fields:return None
            fields.add(condition['column'])
            if 'value' not in condition or isinstance(condition['value'],list):return None
            from workbook_intent import BOUNDARIES
            words=BOUNDARIES|{'不高于':'lte','不早于':'gte','不晚于':'lte'}
            operators=[words[m[0]] for m in re.finditer('|'.join(re.escape(w) for w in sorted(words,key=len,reverse=True)),edit['quote'])]
            if operators and (len(set(operators))!=1 or condition['operator']!=operators[0]):return None
            if not operators and not compiled:return None
            if condition['type']=='date' and str(condition['value']) not in edit['quote']:return None
            from fractions import Fraction
            from table_semantics import explicit_quantities,UNITS,quantity,unit_definition
            evidence={Fraction(value) for _,value,_ in explicit_quantities(edit['quote'])}
            if condition['type']=='number':
                from general_assistant import numbers
                from table_program import number
                if Fraction(number(condition['value'])) not in numbers(edit['quote'])|evidence:return None
                dimensions={declared[0] for _,value,declared in explicit_quantities(edit['quote']) if declared[0] and Fraction(value)==Fraction(number(condition['value']))}
                actual_dimension=(unit_definition(baseline.field(probe,condition['column'])['unit']) or ('',))[0]
                if len(dimensions)==1 and actual_dimension not in dimensions:return None
                boundary=re.search('|'.join(re.escape(w) for w in sorted(words,key=len,reverse=True)),edit['quote'])
                tokens='|'.join(re.escape(u) for u in sorted(UNITS,key=len,reverse=True))
                literal=re.match(r'\s*([+-]?\d+(?:\.\d+)?\s*(?:'+tokens+r')?)',edit['quote'][boundary.end():],re.I) if boundary else None
                if literal:
                    expected,_=quantity(literal[1],unit_definition(baseline.field(probe,condition['column'])['unit']))
                    if Fraction(number(condition['value']))!=Fraction(expected):return None
            check_grounding({'operations':[{'op':'filter','where':condition}]},edit['quote'],extra_numbers=evidence)
            check_explicit_boundaries(condition,edit['quote'],probe);check_predicate(condition)
            graph,finish,note=update_graph(baseline,changed['flow']['finish'],condition,shape='detail' if record_mode else None)
            changed['flow']['graph']=graph;changed['flow']['finish']=finish
            audit.append(dict(note,condition=condition,quote=edit['quote']))
            baseline=build_flow(source,changed,goal)
        contract=deepcopy(changed['flow']['contract'])
        contract.pop('retained_scope',None)  # The verified boundary edit defines the new scope; other operations are unchanged.
        from workbook_intent import writing_intent
        writing,denied,no_word=writing_intent(goal)
        if no_word:contract.update(write=goal[writing.start():] if writing else '' if denied else contract.get('write',''),docx=False)
        elif denied and not writing:contract.update(write='',docx=False)
        elif re.search(r'(?:继续|仍然)?(?:导出|保留)\s*(?:Word|DOCX)',goal,re.I):contract.update(write=contract.get('write') or '根据核对结果写简短说明并导出Word。',docx=True)
        contract['requirements']=[goal];contract['revision']={'parent_id':parent['id'],'edits':audit,'literal_compiler':bool(compiled),'record_granularity':record_mode,'proof':'Only explicit boundaries changed; all other typed operations retained and replayed.'}
        finish=changed['flow']['finish'];result=baseline.finish(finish,contract)
        # No semantic re-review of unchanged requirements: the edit is structurally
        # restricted and the entire old/new dependency graph has been replayed.
        return baseline,contract,freeze_finish(baseline,finish),result,[]
    except (ValueError,TypeError,KeyError,StopIteration):
        return None
