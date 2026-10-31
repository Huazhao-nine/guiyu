"""Behavioral checks for schema repair, delivery and source-bound revisions."""
import io,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stdout
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from table_program import TableError
from workbook_intent import repair_json_punctuation,json_scalar_sequence,normalize_action
from workbook_flow import TableFlow,fingerprint,freeze_finish,plan_actions
from workbook_agent import output_contract
from workbook_revision import try_revision

class Model:
    def __init__(self,answers):self.answers=list(answers);self.calls=[]
    def generate(self,system,user,**kw):
        self.calls.append(json.loads(user));value=self.answers.pop(0)
        return json.dumps(value,ensure_ascii=False),{'tokens':10,'seconds':.01,'input_tokens':25}

def office(answers=()):
    return SimpleNamespace(agent=SimpleNamespace(model=Model(answers)),core=SimpleNamespace(parse_json=json.loads,emit=lambda *a,**k:None),workbook_metrics={'tokens':0,'peak_memory_gb':0})

class SchemaRecoveryTests(unittest.TestCase):
    def test_whitespace_resolution_keeps_units_and_rejects_compact_collisions(self):
        from table_program import column
        fields=['阶段A / 实际（元）','阶段A / 实际（美元）']
        self.assertEqual(column('阶段 A/实际（元）',fields),fields[0])
        fields=['a b','ab']
        self.assertEqual(column('a b',fields),'a b')
        with self.assertRaises(TableError):column('a  b',fields)
        with self.assertRaises(TableError):column('实际', ['阶段A / 实际','阶段B / 实际'])
    def test_compact_field_reference_can_drive_a_real_calculation(self):
        source={'columns':['本期 / 收入（元）','本期 / 支出（元）'],'rows':[['1900','600']],'provenance':[[0]],'notes':[]}
        flow=TableFlow(source,'计算本期差额')
        flow.apply({'tool':'derive','name':'差额','formula':'[本 期/收入（元）]-[本 期/支出（元）]'})
        self.assertEqual(flow.views[flow.last]['rows'][0][-1],'1300')
    def test_column_scope_error_precedes_invalid_numeric_value_without_changing_rows(self):
        source={'columns':['地区','阶段A / 数量','阶段B / 数量'],'rows':[['甲','5','7']],'provenance':[[0]],'notes':[]}
        flow=TableFlow(source,'只统计阶段A，排除阶段B。')
        with self.assertRaises(TableError) as raised:
            flow.apply({'tool':'filter','where':{'field':'阶段 B/数量','op':'eq','value':None}})
        self.assertEqual(getattr(raised.exception,'error_code',None),'column_scope')
        self.assertEqual(flow.last,'V0');self.assertEqual(flow.graph,[])
        allowed=TableFlow(source,'排除阶段B数量等于0的行。')
        allowed.apply({'tool':'filter','where':{'field':'阶段B / 数量','op':'ne','value':0}})
        self.assertEqual(len(allowed.views[allowed.last]['rows']),1)
    def test_missing_object_close_keeps_money_and_calendar_predicates(self):
        raw='{"tool":"filter","where":[{"field":"日期","op":"gte","value":"2027-02-01"},{"field":"金额","op":"gte","value":1700],"logic":"all"}]'
        repaired=repair_json_punctuation(raw)
        self.assertEqual(json_scalar_sequence(raw),json_scalar_sequence(repaired))
        action=normalize_action(json.loads(repaired));self.assertEqual(len(action['where']['all']),2)
        self.assertEqual(action['where']['all'][1]['value'],1700)
    def test_punctuation_cannot_supply_missing_value_or_merge_two_actions(self):
        for raw in ('{"tool":"filter","input":}', '{"tool":"sort","tool":"filter"}'):
            with self.assertRaises((ValueError,TableError)):repair_json_punctuation(raw)
    def test_result_alias_never_introduces_a_path_or_conflicting_input(self):
        self.assertEqual(normalize_action({'tool':'select','result':'V4','fields':['Ref']})['input'],'V4')
        for v in ({'tool':'select','result':'/tmp/source'},{'tool':'select','result':'V4','input':'V3'}):
            with self.assertRaises(TableError):normalize_action(v)
    def test_logic_sentinel_has_owner_and_does_not_drop_date_or_money(self):
        a={'field':'日期','op':'gte','value':'2027-02-01'};b={'field':'金额','op':'gte','value':1700}
        action=normalize_action({'tool':'filter','where':[a,b,{'logic':'all'}]})
        self.assertEqual(action['where'],{'all':[a,b]})
        self.assertEqual(normalize_action({'tool':'filter','where':[a,b],'logic':'or'})['where'],{'any':[a,b]})
        with self.assertRaises(TableError):normalize_action({'tool':'filter','where':[a,b,{'logic':'or'}],'logic':'all'})
    def test_logic_leaf_is_explicit_single_condition_not_a_new_comparison(self):
        a={'field':'日期','op':'lte','value':'2027-02-28','logic':'all'}
        out=normalize_action({'tool':'filter','where':a})['where'];self.assertEqual(out,{'all':[{'field':'日期','op':'lte','value':'2027-02-28'}]})

class OutputRecoveryTests(unittest.TestCase):
    def test_abbreviated_numeric_field_is_bound_to_unique_real_quantity(self):
        source={'columns':['单号','报销金额（元）'],'rows':[['A','40'],['B','90']],'provenance':[[0],[1]],'notes':[]}
        f=TableFlow(source,'只要报销不少于75元的记录。')
        with self.assertRaises(TableError) as raised:f.finish({'result':'V0'},{'deliver':'detail'})
        self.assertEqual(raised.exception.repair_predicate['column'],'报销金额（元）');self.assertEqual(raised.exception.repair_predicate['value'],'75')
    def test_shared_abbreviation_does_not_guess_a_measure_or_currency(self):
        source={'columns':['报销金额','报销数量'],'rows':[['40','1']],'provenance':[[0]],'notes':[]}
        f=TableFlow(source,'报销不少于75。')
        self.assertEqual(f.finish({'result':'V0'},{'deliver':'detail'})['rows'],[['40','1']])
        f=TableFlow({'columns':['报销金额（元）'],'rows':[['40']],'provenance':[[0]],'notes':[]},'报销不少于75美元。')
        self.assertEqual(f.finish({'result':'V0'},{'deliver':'detail'})['rows'],[['40']])
    def test_abbreviation_does_not_retarget_unknown_or_disjunctive_conditions(self):
        source={'columns':['报销金额（元）'],'rows':[['40']],'provenance':[[0]],'notes':[]}
        for goal in ['预算不少于75元。','报销不少于75元或其他条件满足。','不要报销不少于75元的记录。','别保留报销不少于75元的记录。','不允许保留报销不少于75元的记录。']:
            f=TableFlow(source,goal);self.assertEqual(f.finish({'result':'V0'},{'deliver':'detail'})['rows'],[['40']])
    def test_quantity_alias_is_not_cut_out_of_a_longer_unknown_concept(self):
        source={'columns':['编号','发货数量'],'rows':[['A','5'],['B','20']],'provenance':[[0],[1]],'notes':[]}
        for word in ['待发货','未发货','总发货']:
            f=TableFlow(source,'只保留'+word+'不少于10件的记录。')
            self.assertEqual(f.finish({'result':'V0'},{'deliver':'detail'})['rows'],[['A','5'],['B','20']])
        for prefix in ['不希望保留','无需保留','别再保留']:
            f=TableFlow(source,prefix+'发货不少于10件的记录。')
            self.assertEqual(f.finish({'result':'V0'},{'deliver':'detail'})['rows'],[['A','5'],['B','20']])
        for prefix in ['', '挑出', '只保留']:
            f=TableFlow(source,prefix+'发货不少于10件的记录。')
            with self.assertRaises(TableError) as raised:f.finish({'result':'V0'},{'deliver':'detail'})
            self.assertEqual(raised.exception.repair_predicate['column'],'发货数量')
    def test_projection_ignores_only_known_non_delivered_format_fields(self):
        source={'columns':['编号','预算（元）','已用（元）'],'rows':[['A','3000','1000']],'provenance':[[0]],'notes':[]}
        f=TableFlow(source,'统一为元，只保留编号与已用。')
        value=f.finish({'result':'V0','fields':['编号','已用（元）'],'display_units':{'已用（元）':'元','预算（元）':'元'}},{'deliver':'detail'})
        self.assertEqual(value['columns'],['编号','已用（元）']);self.assertEqual(value['rows'],[['A','1000']])
        with self.assertRaises(TableError):f.finish({'result':'V0','fields':['编号'],'display_units':{'不存在':'元'}},{'deliver':'detail'})
    def test_calendar_preview_and_export_share_date_text_without_losing_timestamps(self):
        from table_semantics import canonical_table
        from workbook_export import typed_value,display
        data={'columns':['截止日期'],'rows':[['2027-02-01 00:00:00'],['2027-02-28T00:00:00']],'provenance':[[0],[1]],'notes':[]}
        result=canonical_table(data);self.assertEqual(result['rows'],[['2027-02-01'],['2027-02-28']]);self.assertEqual(canonical_table(result),result)
        for row in result['rows']:
            value,fmt=typed_value(row[0],'截止日期','date',lambda s:s);self.assertEqual(display(value,fmt),row[0])
        for text in ('2027-02-01 14:30:00','2027-02-01T14:30:00+08:00','2027-02-01 尚未确认'):
            result=canonical_table(dict(data,rows=[[text]],provenance=[[0]]));self.assertEqual(result['rows'],[[text]])
            self.assertEqual(typed_value(text,'截止日期','date',lambda s:s),(text,None))
    def test_declared_count_is_not_part_of_last_field(self):
        for suffix in ('三列','3列','共三个字段'):
            value=output_contract(office(),'只要编码、金额、日期'+suffix+'。',{'columns':['编码','金额（元）','日期'],'rows':[]},{})
            self.assertEqual(value,['编码','金额（元）','日期'])
        with self.assertRaisesRegex(TableError,'列数'):output_contract(office(),'只要编码、金额三列。',{'columns':['编码','金额'],'rows':[]},{})
    def test_mapping_retries_only_correspondence_and_caches_success(self):
        bad={'bindings':[{'requested':'小组','column':'Team'},{'requested':'人数','column':'Team'},{'requested':'工时','column':'Hours'}]}
        good={'bindings':[{'requested':'小组','column':'Team'},{'requested':'人数','column':'People'},{'requested':'工时','column':'Hours'}]}
        o=office([bad,good]);cache={};audit={};table={'columns':['Team','People','Hours'],'rows':[]}
        self.assertEqual(output_contract(o,'只要小组、人数、工时三列。',table,{},cache=cache,audit=audit),table['columns'])
        self.assertEqual(len(o.agent.model.calls),2);self.assertIn('上次映射问题',o.agent.model.calls[1])
        self.assertEqual(output_contract(o,'只要小组、人数、工时三列。',table,{},cache=cache),table['columns']);self.assertEqual(len(o.agent.model.calls),2)
        self.assertEqual(audit['declared_count'],3)
    def test_chinese_connector_inside_a_word_is_not_split_into_fake_fields(self):
        good={'bindings':[{'requested':'参与者姓名','column':'Person'},{'requested':'联系方式','column':'Email'}]}
        self.assertEqual(output_contract(office([good]),'只保留参与者姓名和联系方式两列。',{'columns':['Person','Email'],'rows':[]},{}),['Person','Email'])

class LiteralRevisionTests(unittest.TestCase):
    def make(self):
        source={'columns':['Ref','Cap（元）','Paid（元）','Due'],'rows':[['A','6000','1000','2027-02-01'],['B','3000','1000','2027-02-28'],['C','1800','500','2027-03-01']],'provenance':[[0],[1],[2]],'notes':[]}
        f=TableFlow(source,'计算剩余额度，筛选不少于3000元。')
        f.apply({'tool':'derive','name':'Balance','formula':'[Cap（元）]-[Paid（元）]'})
        f.apply({'tool':'filter','where':{'field':'Balance（元）','op':'gte','value':3000}})
        contract={'deliver':'detail','docx':True,'write':'写说明并导出Word。','column_bindings':[{'requested':'剩余额度','column':'Balance（元）'},{'requested':'截止日期','column':'Due'}]}
        finish=freeze_finish(f,{'result':f.last,'fields':['Ref','Balance（元）','Due']});result=f.finish(finish,contract)
        cfg={'mode':'flow','flow':{'graph':f.graph,'finish':finish,'contract':contract,'expected':fingerprint(result)}}
        return source,{'id':'old','prompt':'筛选剩余额度','workbook':cfg}
    def test_relaxation_recovers_rows_without_model_and_preserves_export(self):
        source,parent=self.make();o=office()
        result=try_revision(o,source,'把余额门槛放宽到1300元，其余筛选条件、排序和输出字段保持不变。',parent,{'goal':'上轮'})
        self.assertIsNotNone(result);self.assertEqual(result[3]['rows'],[['A','5000','2027-02-01'],['B','2000','2027-02-28'],['C','1300','2027-03-01']])
        self.assertEqual(len(o.agent.model.calls),0);self.assertTrue(result[1]['docx']);self.assertTrue(result[1]['revision']['literal_compiler'])
    def test_zero_matches_is_valid_data_not_a_reason_to_replan(self):
        source,parent=self.make();o=office()
        result=try_revision(o,source,'把剩余额度门槛改成不少于99999元，其他要求不变。',parent,{'goal':'上轮'})
        self.assertEqual(result[3]['rows'],[]);self.assertEqual(len(o.agent.model.calls),0)
    def test_date_endpoint_edit_preserves_other_conditions(self):
        source,parent=self.make();o=office()
        first=try_revision(o,source,'把余额门槛放宽到1300元，其他要求不变。',parent,{'goal':'上轮'})
        flow,contract,finish,result,_=first
        parent={'id':'second','prompt':'更新余额','workbook':{'mode':'flow','flow':{'graph':flow.graph,'contract':contract,'finish':finish,'expected':fingerprint(result)}}}
        result=try_revision(o,source,'把截止日期改成不晚于2027-02-28，其他要求不变。',parent,{'goal':'上轮'})
        self.assertIsNotNone(result);self.assertEqual([r[0] for r in result[3]['rows']],['A','B'])
        self.assertEqual(len(o.agent.model.calls),0)
    def test_explicit_inconsistent_relaxation_does_not_change_operator(self):
        from workbook_edits import literal_edits
        from workbook_revision import build_flow
        source,parent=self.make();cfg=parent['workbook'];flow=build_flow(source,cfg,'')
        self.assertIsNone(literal_edits(flow,cfg['flow']['finish'],cfg['flow']['contract'],'把余额门槛放宽到7000元，其他要求不变。'))
        self.assertIsNone(literal_edits(flow,cfg['flow']['finish'],cfg['flow']['contract'],'把预算门槛改成不少于1300元，其他要求不变。'))

class PipelineConstraintRepairTests(unittest.TestCase):
    def test_bypassed_distinct_is_reconnected_before_group_and_dependent_sort(self):
        source={'columns':['联系方式','组别','工时'],'rows':[['a','甲','2'],['a','甲','9'],['b','甲','3']],'provenance':[[0],[1],[2]],'notes':[]}
        o=office([{'title':'工时','deliver':'aggregate','detail_request':''},
                  {'tool':'distinct','input':'V0','fields':['联系方式']},
                  {'tool':'group','input':'V0','by':['组别'],'metrics':[{'function':'count','name':'人数'},{'function':'sum','field':'工时','name':'合计'}]},
                  {'tool':'sort','input':'V2','by':[{'field':'合计','direction':'desc'}]},
                  {'tool':'finish','result':'V3'},{'state':'passed'}])
        with redirect_stdout(io.StringIO()):flow,contract,_,result,_=plan_actions(o,source,'同一联系方式只留首次，按组别汇总人数和工时，合计从高到低。')
        self.assertEqual(result['rows'],[['甲','2','5']]);self.assertEqual(flow.graph[1]['input'],'V1')
        self.assertEqual(contract['constraint_repairs'][0]['dependency']['keys'],['联系方式'])
        self.assertEqual(source['rows'][1][-1],'9')
    def test_distinct_on_delivery_path_is_valid_despite_merged_source_provenance(self):
        source={'columns':['账号','金额'],'rows':[['a','10'],['a','90']],'provenance':[[0],[1]],'notes':[]}
        f=TableFlow(source,'同一账号只留首次，汇总金额。')
        f.apply({'tool':'distinct','fields':['账号']});f.apply({'tool':'group','by':[],'metrics':[{'function':'sum','field':'金额','name':'合计'}]})
        result=f.finish({'result':f.last},{'deliver':'aggregate'})
        self.assertEqual(result['rows'],[['10']]);self.assertEqual(result['provenance'],[[0,1]])
    def test_unrelated_deduplication_cannot_supply_a_missing_dependency(self):
        source={'columns':['账号','金额'],'rows':[['a','10'],['a','90']],'provenance':[[0],[1]],'notes':[]}
        f=TableFlow(source,'同一账号只留首次，汇总金额。')
        f.record('V0',{'op':'filter','where':{'column':'金额','operator':'gt','value':50,'type':'number'}})
        f.apply({'tool':'distinct','fields':['账号']})
        f.apply({'tool':'group','input':'V0','by':[],'metrics':[{'function':'sum','field':'金额','name':'合计'}]})
        with self.assertRaises(TableError) as raised:f.finish({'result':f.last},{'deliver':'aggregate'})
        self.assertEqual(raised.exception.error_code,'dependency_scope');self.assertIsNone(getattr(raised.exception,'repair_dependency',None))
    def test_optional_sibling_distinct_does_not_change_an_ordinary_raw_summary(self):
        source={'columns':['账号','金额'],'rows':[['a','10'],['a','90']],'provenance':[[0],[1]],'notes':[]}
        f=TableFlow(source,'汇总全部原始金额，不要去重。')
        f.record('V0',{'op':'distinct','columns':['账号']})
        f.apply({'tool':'group','input':'V0','by':[],'metrics':[{'function':'sum','field':'金额','name':'合计'}]})
        self.assertEqual(f.finish({'result':f.last},{'deliver':'aggregate'})['rows'],[['100']])
    def test_column_scope_feedback_allows_tool_switch_instead_of_repeating_filter(self):
        source={'columns':['地区','阶段A / 数量','阶段B / 数量'],'rows':[['甲','5','7'],['甲','8','2']],'provenance':[[0],[1]],'notes':[]}
        o=office([{'title':'汇总','deliver':'aggregate','detail_request':''},
                  {'tool':'filter','where':{'field':'阶段B / 数量','op':'eq','value':None}},
                  {'tool':'group','input':'V0','by':['地区'],'metrics':[{'function':'sum','field':'阶段A / 数量','name':'合计'}]},
                  {'tool':'finish','result':'V1'},{'state':'passed'}])
        with redirect_stdout(io.StringIO()):flow,_,_,result,failures=plan_actions(o,source,'按地区汇总阶段A数量，排除阶段B。')
        self.assertEqual(result['rows'],[['甲','13']]);self.assertEqual(len(flow.graph),1)
        self.assertEqual(failures[0]['error_code'],'column_scope')
        feedback=o.agent.model.calls[2]
        self.assertIn('纠正方向',feedback);self.assertNotIn('条件JSON结构示例',feedback)
    def test_plain_negative_writing_keeps_a_table_only_contract(self):
        for denial in ('不写文稿。','不用写说明。','不导出Word。'):
            o=office([{'title':'资料','deliver':'detail','detail_request':''},{'tool':'finish','result':'V0'},{'state':'passed'}])
            source={'columns':['编号'],'rows':[['A']],'provenance':[[0]],'notes':[]}
            with redirect_stdout(io.StringIO()):_,contract,_,_,_=plan_actions(o,source,'只要明细表，'+denial)
            self.assertEqual(contract['write'],'')
    def test_omitted_numeric_condition_rebuilds_detail_and_existing_summary(self):
        source={'columns':['编号','金额（元）'],'rows':[['A','200'],['B','500'],['C','900']],'provenance':[[0],[1],[2]],'notes':[]}
        o=office([{'title':'金额','deliver':'both','detail_request':'每条明细保留'},
                  {'tool':'group','input':'V0','by':[],'metrics':[{'function':'sum','field':'金额（元）','name':'合计'},{'function':'count','name':'条数'}]},
                  {'tool':'finish','result':'V0','summaries':['V1']},{'state':'passed'}])
        with redirect_stdout(io.StringIO()):flow,contract,_,result,_=plan_actions(o,source,'金额不少于500元，每条明细保留，另外给这批金额合计和条数。')
        self.assertEqual(result['rows'],[['B','500'],['C','900']]);self.assertEqual(result['summaries'][0]['rows'],[['1400','2']])
        self.assertEqual(len(contract['constraint_repairs']),1);self.assertEqual(len(o.agent.model.calls),4)
        self.assertEqual(source['rows'][0],['A','200'])
    def test_explicit_category_dates_and_amount_are_repaired_without_new_model_steps(self):
        source={'columns':['编号','日期','金额（元）','状态'],'rows':[['A','2027-02-01','500','有效'],['B','2027-02-28','1200','有效'],['C','2027-03-01','5000','有效'],['D','2027-02-03','10000','作废'],['E','2027-01-31','10000','有效'],['F','2027-01-01','300','有效']],'provenance':[[i] for i in range(6)],'notes':[]}
        o=office([{'title':'日期核对','deliver':'detail','detail_request':''},
                  {'tool':'sort','by':[{'field':'日期','direction':'asc'}]}, {'tool':'finish','result':'V1'},{'state':'passed'}])
        goal='只看有效合同，日期在2027-02-01至2027-02-28（含两端），金额不少于500元，按日期排序，只保留编号、日期、金额。'
        with redirect_stdout(io.StringIO()):_,contract,_,result,_=plan_actions(o,source,goal)
        self.assertEqual(result['rows'],[['A','2027-02-01','500'],['B','2027-02-28','1200']])
        # One source condition can also remove rows violating another; check
        # bounded, quoted repairs and exact delivery rather than repair order.
        self.assertLessEqual(len(contract['constraint_repairs']),4)
        self.assertTrue(all(r['quote'] in goal for r in contract['constraint_repairs']))
        self.assertEqual(len(o.agent.model.calls),4)

if __name__=='__main__':unittest.main()
