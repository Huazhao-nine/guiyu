"""Grounded data briefs: the local model selects facts; code renders their values."""
import json
import re
from pathlib import PurePath


def _explicit_title(goal):
    """Copy a requested title; quoted source names and model titles are not requests."""
    if not isinstance(goal,str):return None
    label=r'(?:(?:文稿|文章|报告|说明|邮件|通知|简报|Word)?(?:的)?标题|邮件(?:的)?主题)'
    assignment=r'(?:改成|改为|换成|换为|设为|定为|写成|用|叫|为|是|[:：])'
    marker=label+r'\s*(?:请|就|要)?\s*'+assignment+r'?\s*[:：]?\s*'
    quoted=r'(?:“([^”\r\n]{1,200})”|「([^」\r\n]{1,200})」|《([^》\r\n]{1,200})》|"([^"\r\n]{1,200})"|‘([^’\r\n]{1,200})’)'
    quoted_spans=[(match.start(),match.end()) for match in re.finditer(quoted,goal)]
    def unavailable(start):
        if any(begin<start<end for begin,end in quoted_spans):return True
        prefix=re.split(r'[，,。；;\n]',goal[:start])[-1]
        prefix=re.split(r'而且|并且|但是|不过|但|且|并',prefix)[-1]
        return bool(re.search(r'不要|不用|不叫|不是|不应|避免|而非|例如|比如|示例|样例',prefix))
    found=[]
    for pattern in (marker+quoted,r'(?:以|用|采用|使用)\s*'+quoted+r'\s*(?:作为|作|做|为)\s*'+label):
        for match in re.finditer(pattern,goal):
            if unavailable(match.start()):continue
            found.append((match.start(),next(v for v in match.groups() if v is not None).strip()))
    # Unquoted titles require an assignment word/colon and end at a clause boundary.
    direct=label+r'\s*(?:请|就|要)?\s*'+assignment+r'\s*[:：]?\s*([^，,。；;\r\n“”「」《》"‘’]{1,80})'
    for match in re.finditer(direct,goal):
        if unavailable(match.start()):continue
        title=re.split(r'(?:并|然后|同时)(?:导出|保存|生成|写|保留)',match[1])[0].strip()
        if not title or re.search(r'^(?:不变|保持|沿用|简短|简洁|自动|合适|恰当|中文|根据|依据|基于|按|由|请)|(?:即可|就好|一下)$',title):continue
        found.append((match.start(),title))
    return max(found,key=lambda item:item[0])[1] if found else None


def _writing_goals(plan):
    """Read only the task lineage already attached to this checked workbook plan."""
    current=plan.get('prompt','')
    from workbook_intent import retains_delivery
    flow=plan.get('workbook',{}).get('flow',{})
    revision=isinstance(flow.get('contract',{}).get('revision'),dict)
    retained=retains_delivery(current) or revision or bool(re.search(r'(?:其他|其它|其余)[^，,。；;\n]{0,32}不变|沿用(?:上轮|上次|刚才|原有)(?:的)?(?:条件|要求|设置|格式)',current))
    switched=re.search(r'(?:改用|换|切换|改为处理)[^，,。；;\n]{0,100}(?:文件|工作簿|\.(?:xlsx|csv)\b)|另一份',current,re.I)
    inherit=retained and not switched and not re.search(r'不要沿用|原标题.{0,5}(?:不用|不要)',current)
    prior=flow.get('goals',[]) if inherit else []
    goals=[g for g in prior if isinstance(g,str) and g!=current] if isinstance(prior,list) else []
    return goals+[current]


def writing_title(plan,table):
    """Resolve headings from explicit user text or verified source identity, without a model."""
    goals=_writing_goals(plan)
    for goal in reversed(goals):
        title=_explicit_title(goal)
        if title:return title,{'source':'explicit_request' if goal==plan.get('prompt','') else 'retained_explicit_request','basis':goal}
    # locations/inputs come from the selected source tables, even when no rows match.
    # Do not use plan.title, workbook tool prose, or prior model-written headings.
    names=list(dict.fromkeys(loc['file'] for loc in table.get('locations',[]) if isinstance(loc,dict) and isinstance(loc.get('file'),str)))
    if not names:names=list(dict.fromkeys(label.split(' / ')[0].split(' · 表头')[0] for label in table.get('inputs',[]) if isinstance(label,str)))
    if not names:names=list(dict.fromkeys(n for n in plan.get('source_names',[]) if isinstance(n,str)))
    style=plan.get('workbook',{}).get('program',{}).get('write','')
    suffix=next((word for word in ('通知','简报','报告','总结','摘要') if re.search(r'(?:写|起草|撰写|制作|生成|做)[^，,。；;\n]{0,12}'+word,style)), '情况说明')
    if len(names)==1:
        name=PurePath(names[0].replace('\\','/')).name
        topic=re.sub(r'\.(?:xlsx|csv)$','',name,flags=re.I).strip()
        generic=re.fullmatch(r'(?:book|workbook|sheet|data|export|工作簿|数据|表格|新建工作簿|未命名)[ _-]*\d*',topic,re.I)
        if PurePath(name).suffix.lower() in ('.xlsx','.csv') and 1<=len(topic)<=40 and re.search(r'[\w\u4e00-\u9fff]',topic) and not generic and not re.search(r'[\r\n\t#*|<>]|[\x00-\x1f]',topic):
            title=topic if topic.endswith(suffix) else topic+suffix
            return title,{'source':'verified_source','basis':name}
    return ('工作簿'+suffix if suffix!='情况说明' else '工作簿处理说明'),{'source':'neutral','basis':'multiple_sources' if len(names)>1 else 'no_unambiguous_topic'}


def fact_catalog(table,source_rows):
    def cell_fact(c,v,units):
        unit=units.get(c,'')
        suffix='元' if unit=='CNY' and not re.search(r'元|%|％',str(v)) and '万元' not in c else 'USD' if unit=='USD' and 'USD' not in str(v) else ''
        return c+'：'+(str(v)+suffix if str(v).strip() else '未填写')
    facts={'COUNT':f'本次按要求从{source_rows}条原始记录中整理出{len(table["rows"])}条结果。'}
    for i,summary in enumerate(table.get('summaries',[]),1):
        for j,row in enumerate(summary['rows'],1):facts[f'S{i}_{j}']='；'.join(cell_fact(c,v,summary.get('units',{})) for c,v in zip(summary['columns'],row))+'。'
    for i,row in enumerate(table['rows'][:20],1):facts['R'+str(i)]='；'.join(cell_fact(c,v,table.get('units',{})) for c,v in zip(table['columns'],row))+'。'
    return facts


def write_from_results(office,context,plan,child):
    from office_agent import export_docx
    from personal_tools import markdown_table
    data=next(r for name,r in context['results'] if name=='workbook')
    table=data['result_table'];catalog=fact_catalog(table,data['workbook_check']['source_rows'])
    title,title_check=writing_title(plan,table)
    selected=[];stats={};origin='local_model'
    system=('你是中文办公文稿编辑。事实已由本地工具核对，不能改写数值或重新算数。'
            '只选择最能满足写作要求的事实编号，返回JSON，不写正文、不产生新事实。'
            '可以优先选汇总，再选明细，细节表格由程序自动附上。COUNT是记录数，S是已核对汇总，R是按最终顺序排列的记录。'
            '标题已经由程序按用户要求与实际资料确定，不能另拟标题、引入其他业务或改变任务主题。'
            '格式：{"facts":["COUNT"]}。')
    for attempt in range(2):
        try:
            raw,stats=office.agent.model.generate(system,json.dumps({'用户完整目标':'\n'.join(_writing_goals(plan)),'本步写作要求':plan['workbook']['program']['write'],'已确定标题':title,'可用事实':catalog},ensure_ascii=False),max_tokens=500)
            value=office.core.parse_json(raw)
            if stats.get('finish_reason')=='length' or not isinstance(value,dict) or set(value)-{'title','facts'}:raise ValueError('文稿事实选择格式无效。')
            ids=value.get('facts')
            if not isinstance(ids,list) or not ids or len(ids)>24 or any(not isinstance(k,str) or k not in catalog for k in ids):raise ValueError('引用了不存在的事实编号。')
            # Accept and ignore a legacy title field; it cannot cost a retry or affect the document.
            selected=list(dict.fromkeys(ids))
            break
        except (ValueError,TypeError,KeyError):continue
    if not selected:selected=['COUNT']+[k for k in catalog if k.startswith('S')];origin='safe_default'
    # Required counts and aggregate facts are never lost to editorial selection.
    required=['COUNT']+[k for k in catalog if k.startswith('S')]
    chosen=list(dict.fromkeys(required+selected))
    # Row references follow the actual final sort, even if the editor selects in a different order.
    chosen=[k for k in chosen if not k.startswith('R')]+sorted((k for k in chosen if k.startswith('R')),key=lambda k:int(k[1:]))
    brief='\n\n'.join(catalog[k] for k in chosen if not k.startswith('R'))
    if re.search(r'邮件',plan['workbook']['program']['write']):brief='您好：\n\n'+brief+'\n\n以下为本次整理的明细，供核对。'
    text='# '+title+'\n\n'+brief
    if table['rows']:
        text+='\n\n## 明细\n\n'+markdown_table(table['columns'],table['rows'][:200])
        if len(table['rows'])>200:text+='\n\n文稿展示前200条，完整数据保存在本轮Excel与CSV副本。'
    else:text+='\n\n本轮没有符合条件的记录。'
    for summary in table.get('summaries',[]):text+='\n\n## 汇总\n\n'+markdown_table(summary['columns'],summary['rows'])
    if table.get('notes'):text+='\n\n## 数据说明\n\n'+'\n'.join(table['notes'])
    folder=office.core.secure_dir(office.agent.data/'Outputs'/child)
    word=folder/'工作簿说明.docx';markdown=folder/'工作簿说明.md';paths=[markdown]
    if plan['workbook'].get('flow',{}).get('contract',{}).get('docx',True):export_docx(text,word,context['docs']);paths.insert(0,word)
    markdown.write_text(text);markdown.chmod(0o600)
    return {'text':text,'summary':'已根据核对结果生成文稿，数值、记录顺序与汇总由程序填入。','artifacts':[{'name':p.name,'path':str(p),'type':p.suffix[1:]} for p in paths],
            'stats':stats,'checked_fact_rendering':True,'writing_check':{'state':'passed','method':'verified_fact_blocks','editor':origin,'selected_facts':chosen,'summary_count':len(table.get('summaries',[])),'title':title,'title_check':title_check}}
