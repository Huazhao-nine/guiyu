import io
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import fact_guard as guard
import agent_control as control
import test_agent_control as controller_fixtures


DOCS=[{'id':'S1','name':'01_梧桐空间.txt','text':'方案名称：梧桐空间\n场地费用：600元/半天。\n取消规则：提前48小时可免费取消。'},
      {'id':'S2','name':'02_青禾客厅.txt','text':'方案名称：青禾客厅\n场地费用：450元/半天。\n取消规则：预订确认后取消收取100元。'}]


class FactChecks(unittest.TestCase):
    def test_unpaid_status_does_not_authorize_a_new_payment_timeline(self):
        issues=guard.calendar_and_refund_issues('确认后将按流程支付。','需提前三天确认，费用尚未支付。')
        self.assertTrue(any('付款时间条件' in v for v in issues))

    def test_explicit_source_payment_timeline_is_preserved(self):
        self.assertEqual(guard.calendar_and_refund_issues('审批完成后付款。','费用审批完成后付款。'),[])

    def test_payment_timing_question_can_remain_explicitly_unconfirmed(self):
        self.assertEqual(guard.calendar_and_refund_issues('是否确认后付款，待确认。','费用尚未支付。'),[])

    def issues(self,text,instruction='写一份场地说明。',**kwargs):return guard.check_writing(text,instruction,DOCS,**kwargs)['issues']
    def test_chinese_adjacent_amount_and_decimal_normalization(self):
        self.assertEqual([(x['value'],x['unit']) for x in guard.amounts('合计为1,200.00元及0.5万元，另有$2.5')],[(1200,'元'),(5000,'元'),(2.5,'USD')])
    def test_unknown_amount_is_rejected(self):self.assertTrue(self.issues('预计需支付650元。【S1】'))
    def test_amount_assigned_to_wrong_entity_is_rejected(self):
        self.assertTrue(self.issues('梧桐空间为450元，青禾客厅为600元。'))
    def test_correct_amount_binding_is_accepted(self):self.assertFalse(self.issues('梧桐空间为600.00元，青禾客厅为450元。【S1】【S2】'))
    def test_parenthetical_comparison_is_not_a_second_entity_assignment(self):
        self.assertFalse(self.issues('青禾客厅费用更低（450元 vs 600元）。'))
        self.assertTrue(self.issues('青禾客厅费用600元 vs 450元。'))
    def test_budget_in_user_request_is_not_invented_source_fact(self):
        self.assertFalse(self.issues('你的预算上限是500元。','我的预算上限500元，写说明。'))
        self.assertTrue(self.issues('梧桐空间收费500元。','我的预算上限500元，写说明。'))
    def test_currency_is_not_interchangeable(self):self.assertTrue(self.issues('梧桐空间收费600美元。'))
    def test_wrong_cheaper_heading_is_rejected(self):self.assertTrue(self.issues('**费用更低**：梧桐空间600元，青禾客厅450元。'))
    def test_correct_cheaper_heading_is_accepted(self):self.assertFalse(self.issues('**费用更低**：青禾客厅450元，梧桐空间600元。'))
    def test_omitted_cancellation_condition_is_rejected(self):self.assertTrue(self.issues('梧桐空间可以免费取消。'))
    def test_exact_cancellation_condition_is_accepted(self):self.assertFalse(self.issues('梧桐空间提前48小时可免费取消。【S1】'))
    def test_condition_cannot_be_assigned_to_other_venue(self):self.assertTrue(self.issues('青禾客厅需提前48小时取消。'))
    def test_explicit_budget_cap_is_retained_in_conclusion(self):self.assertTrue(self.issues('推荐梧桐空间，600元，符合要求。','预算不超过500元，必须有投影仪，写一份选择说明。'))
    def test_explicit_over_budget_alternative_is_marked(self):self.assertFalse(self.issues('如果提高预算，可选择梧桐空间，600元。','预算不超过500元。'))
    def test_admitting_violation_does_not_make_positive_recommendation_valid(self):
        self.assertTrue(self.issues('推荐梧桐空间，费用600元，超出预算上限，无法满足硬性要求。','预算不超过500元，不放宽条件。'))
        self.assertFalse(self.issues('不推荐梧桐空间，600元，超出预算。','预算不超过500元，不放宽条件。'))
        self.assertTrue(self.issues('如果提高预算，可选择梧桐空间，600元。','预算不超过500元，不放宽条件。'))
    def test_no_relaxation_also_blocks_generic_advice_after_correct_conclusion(self):
        goal='预算不超过500元，25人参加，必须有投影仪，不放宽任何条件。'
        self.assertTrue(self.issues('当前没有合格方案。如果必须选择，建议权衡，或考虑调整人数/预算。',goal))
        self.assertTrue(self.issues('两份方案都不满足。请考虑调整预算、人数或投影仪需求。',goal))
        self.assertTrue(self.issues('两份方案均不满足。若必须使用投影仪且人数足够，需接受超预算。',goal))
        self.assertFalse(self.issues('两份方案均不满足。无需接受超预算，继续寻找合格方案。',goal))
        self.assertFalse(self.issues('两份方案都不满足。不要考虑调整预算，请寻找同时满足全部条件的新方案。',goal))
        self.assertFalse(self.issues('两份方案都不满足。可以不调整预算，继续寻找新方案。',goal))
    def test_budget_first_cannot_select_more_expensive_option(self):self.assertTrue(self.issues('预算优先，建议选择梧桐空间，600元。','预算优先时选更便宜的场地。'))
    def test_cheaper_option_does_not_bypass_capacity_or_equipment(self):
        docs=[dict(DOCS[0],text=DOCS[0]['text']+'\n容量：最多30人。\n设备：提供投影仪。'),dict(DOCS[1],text=DOCS[1]['text']+'\n容量：最多20人。\n设备：不提供投影仪。')]
        issues=guard.check_writing('推荐青禾客厅450元，符合全部要求。','预算不超过500元，25人参加，必须有投影仪。',docs)['issues']
        self.assertTrue(any('容量' in x for x in issues));self.assertTrue(any('投影仪' in x for x in issues))
    def test_unconditional_claim_is_rejected_even_with_condition_elsewhere(self):self.assertTrue(self.issues('梧桐空间提前48小时可免费取消，也可随时免费取消。'))
    def test_negative_warning_is_not_a_positive_promise(self):self.assertFalse(self.issues('不能承诺梧桐空间可以免费取消。'))
    def test_unknown_source_reference_is_rejected(self):self.assertTrue(self.issues('可对照资料确认。【S7】'))
    def test_filtered_out_money_does_not_authorize_new_draft(self):
        table={'columns':['项目','金额（元）','经办人'],'rows':[['设备','180.00','陈雨']]}
        self.assertTrue(self.issues('陈雨的金额为260元。',table=table))
        self.assertFalse(self.issues('陈雨的金额为180元。',table=table))
    def test_amount_in_another_active_row_cannot_change_owner(self):
        table={'columns':['项目','金额（元）','经办人'],'rows':[['设备','180','陈雨'],['资料','128.5','林晓']]}
        self.assertTrue(self.issues('陈雨为128.5元。',table=table))
    def test_scoped_result_cannot_be_presented_as_entire_workspace(self):
        self.assertTrue(self.issues('整个工作区支出600元。',query={'filters':[{'column':'状态'}]}))
    def test_program_computed_total_is_permitted(self):
        self.assertFalse(self.issues('本轮合计1050元。',results=[('statistics',{'text':'本轮合计1050元。'})]))
    def test_program_average_and_group_total_keep_currency_provenance(self):
        stats={'text':'已计算分组结果','columns':['经办人','字段','有效数值数','合计','平均值','最小值','最大值','单位','未参与行数'],
               'rows':[['陈雨','金额（元）','2','460','230.00','180','280','元','0'],['林晓','金额（元）','1','128.5','128.50','128.5','128.5','元','0']]}
        table={'columns':['经办人','金额（元）'],'rows':[['陈雨','180'],['陈雨','280'],['林晓','128.5']]}
        self.assertFalse(self.issues('陈雨平均230元，本轮总合计588.5元。',table=table,results=[('statistics',stats)]))
        self.assertTrue(self.issues('陈雨平均231元。',table=table,results=[('statistics',stats)]))
        self.assertTrue(self.issues('本轮总合计128.5元。',table=table,results=[('statistics',stats)]))
    def test_old_statistics_cannot_authorize_current_money(self):
        self.assertTrue(self.issues('本轮合计999元。',results=[('statistics',{'text':'旧合计999元'}),('statistics',{'text':'当前合计600元'})]))
    def test_explicit_filter_threshold_is_not_invented_money(self):
        self.assertFalse(self.issues('筛选条件为金额大于100元。','只统计金额大于100元。'))
    def test_cross_month_rows_cannot_be_called_this_month(self):
        table={'columns':['日期','金额（元）'],'rows':[['2026-09-28','180'],['2026-10-20','280']]}
        self.assertTrue(self.issues('本月费用合计460元。',table=table))
    def test_exclusive_date_bound_is_explicit_when_range_mentions_it(self):
        query={'filters':[{'column':'日期','operator':'lt','value':'2026-11-01'}]}
        self.assertTrue(self.issues('日期范围为2026‑10‑01至2026‑11‑01。',query=query))
        self.assertFalse(self.issues('日期范围为2026-10-01至2026-11-01（不含上限日）。',query=query))
        self.assertFalse(self.issues('日期范围为2026年10月1日至2026年10月31日。',query=query))
    def test_price_difference_is_computed_and_labelled(self):
        self.assertFalse(self.issues('梧桐空间600元，青禾客厅450元，相差150元。'))
        self.assertTrue(self.issues('梧桐空间150元，青禾客厅450元。'))
        self.assertTrue(self.issues('梧桐空间600元，青禾客厅450元，相差200元。'))
        self.assertFalse(self.issues('青禾客厅比梧桐空间便宜150元。'))
        self.assertTrue(self.issues('青禾客厅价格低至150元。'))
    def test_different_price_bases_cannot_authorize_a_difference(self):
        docs=[dict(DOCS[0],text=DOCS[0]['text'].replace('半天','天')),dict(DOCS[1],text=DOCS[1]['text'].replace('半天','小时'))]
        self.assertTrue(guard.check_writing('梧桐空间600元/天，青禾客厅450元/小时，相差150元。','比较价格',docs)['issues'])
    def test_extracted_amount_requires_its_own_source(self):
        result={'columns':['金额（元）','出处'],'rows':[['450','S1']]}
        self.assertTrue(guard.table_money_issues(result,DOCS))
    def test_grounded_brief_does_not_reuse_failed_drafts(self):
        from personal_tools import answer_catalog
        text=guard.grounded_brief('写说明',DOCS,None,[('write',{'text':'未知费用999元，随时免费取消。'})],answer_catalog)
        self.assertNotIn('999',text);self.assertIn('提前48小时',text);self.assertIn('待确认',text)
    def test_standalone_constraint_fallback_retains_both_short_proposals(self):
        from personal_tools import answer_catalog
        folder=Path(__file__).resolve().parents[1]/'fixtures/personal'
        docs=[{'id':f'S{i+1}','name':p.name,'text':p.read_text()} for i,p in enumerate(sorted(folder.glob('*.txt')))]
        text=guard.grounded_brief('预算不超过500元，25人参加，必须有投影仪，不放宽条件。',docs,None,[],answer_catalog)
        for phrase in ('最多30人','最多20人','不提供投影仪','600元','450元','取消收取100元'):
            self.assertIn(phrase,text)
    def test_known_source_fields_cannot_be_called_missing(self):
        docs=[dict(d,text=d['text']+'\n可用时间：周六下午。\n容量：30人。') for d in DOCS]
        self.assertTrue(guard.check_writing('缺失信息：可用时间、容量等待补充。','写说明',docs)['issues'])
        self.assertTrue(guard.check_writing('（待补充：可用时间、容量）','写说明',docs)['issues'])


class PatchChecks(unittest.TestCase):
    def claim_review(self,verdict):
        import json
        class Model:
            supports_structured_output=True
            def generate(self,system,user,**kwargs):
                if '审查意见核验器' in system:
                    return json.dumps(verdict,ensure_ascii=False),{'finish_reason':'stop'}
                return json.dumps({'action':'revise','reason':'草稿未列出明细。','quote':'材料费37元，共6份。'},ensure_ascii=False),{'finish_reason':'stop'}
        return control.review_writing(Model(),json.loads,'列出费用明细。','材料费37元，共6份。','材料费37元，共6份。')

    def test_unsupported_edit_claim_keeps_existing_draft_and_audit(self):
        result=self.claim_review({'verdict':'unsupported','reason':'草稿中已列出明细，意见不成立。'})
        self.assertEqual(result['action'],'accept')
        self.assertEqual(result['claim_review']['original_reason'],'草稿未列出明细。')

    def test_supported_claim_still_requires_revision(self):
        result=self.claim_review({'verdict':'supported','reason':'还缺原文明确要求的另一项。'})
        self.assertEqual(result['action'],'revise')

    def test_invalid_claim_adjudication_cannot_release_revision(self):
        result=self.claim_review({'action':'accept'})
        self.assertEqual(result['action'],'revise')

    def test_calendar_false_alarm_requires_replayed_target_and_correct_weekday(self):
        from general_tools import run_tool
        args={'operation':'date_shift','date':'2032-02-09','days':3}
        data=run_tool('calendar',args)['data']
        proof={'verified_tool_calendars':[{'arguments':args,'data':data}]}
        text=f"确认日期：{data['date']}（{data['weekday']}）。"
        review={'reason':f"最晚确认日期计算错误，应为{data['date']}。",'quote':text}
        self.assertTrue(control.proven_calendar_criticism(review,text,proof))
        self.assertFalse(control.proven_calendar_criticism(review,text.replace(data['weekday'],'星期一'),proof))
        self.assertFalse(control.proven_calendar_criticism(review,'确认日期：2032-02-13。',proof))

    def test_calendar_proof_never_overrules_source_or_business_day_error(self):
        from general_tools import run_tool
        args={'operation':'date_shift','date':'2032-02-09','days':3}
        proof={'verified_tool_calendars':[{'arguments':args,'data':run_tool('calendar',args)['data']}]}
        for reason in ('日期计算错误，应按最新版本。','日期计算错误，起始日期选错。','日期计算错误，应按工作日。'):
            self.assertFalse(control.proven_calendar_criticism({'reason':reason,'quote':'2032-02-12'},'2032-02-12',proof))

    def test_calendar_review_replay_rejects_tampered_and_clock_relative_results(self):
        from general_tools import run_tool
        args={'operation':'date_shift','date':'2032-02-09','days':3}
        result=run_tool('calendar',args)
        call={'tool':'calendar','state':'completed','arguments':args,'result':result}
        self.assertEqual(len(guard.tool_calendars([('calendar',{'tool_calls':[call]})])),1)
        result['data']['date']='2032-02-15'
        self.assertEqual(guard.tool_calendars([('calendar',{'tool_calls':[call]})]),[])
        call.update(arguments={'operation':'date_shift','days':3},result=run_tool('calendar',{'operation':'date_shift','days':3}))
        self.assertEqual(guard.tool_calendars([('calendar',{'tool_calls':[call]})]),[])

    def test_arithmetic_false_alarm_requires_matching_verified_equation(self):
        proof={'verified_tool_equations':[{'expression':'37*6','result':'222'}]}
        review={'reason':'费用计算错误，乘积需要核对。','quote':'* **材料费**：37元/份 × 6份 = 222元'}
        self.assertTrue(control.proven_arithmetic_criticism(review,proof))
        self.assertFalse(control.proven_arithmetic_criticism(dict(review,quote='37元/份 × 6份 = 223元'),proof))
        self.assertFalse(control.proven_arithmetic_criticism(review,{}))

    def test_correct_arithmetic_never_overrules_source_unit_or_scope_errors(self):
        proof={'verified_tool_equations':[{'expression':'37*6','result':'222'}]}
        for reason in ('计算错误，单价应采用最新通知。','计算错误，计入了排除项目。','计算错误，单位换算不正确。','合计错误，遗漏另一项费用。'):
            self.assertFalse(control.proven_arithmetic_criticism({'reason':reason,'quote':'37*6=222'},proof))

    def test_review_reuse_reexecutes_tool_equations_and_ignores_tampering(self):
        from general_tools import run_tool
        good=run_tool('calculate',{'expression':'37*6'})
        results=[('calculate',{'tool_calls':[{'tool':'calculate','state':'completed','arguments':{'expression':'37*6'},'result':good}],
            'verified_subtotals':[{'expression':'30+2','value':'999'}]})]
        self.assertEqual(guard.tool_equations(results),[{'expression':'37*6','result':'222'}])
        good['data']['result']='999'
        self.assertEqual(guard.tool_equations(results),[])

    def test_review_grammar_only_allows_quotes_from_current_draft(self):
        import json
        from structured_output import JSONGrammar
        grammar=JSONGrammar(control.writing_review_schema('交通费用128.50元。\n\n付款状态待确认。'))
        self.assertEqual(grammar.status('{"action":"accept"}'),(True,True))
        self.assertEqual(grammar.status(json.dumps({'action':'revise','reason':'需核对','quote':'付款状态待确认。'},ensure_ascii=False)),(True,True))
        self.assertFalse(grammar.status(json.dumps({'action':'revise','reason':'需核对','quote':'不存在的句子'},ensure_ascii=False))[0])

    def test_capable_local_model_receives_constrained_deterministic_review(self):
        import json
        calls=[]
        class Model:
            supports_structured_output=True
            def generate(self,system,user,**kwargs):
                calls.append(kwargs);return '{"action":"accept"}',{'finish_reason':'stop'}
        self.assertEqual(control.review_writing(Model(),json.loads,'写说明','原文摘录。','原文摘录。'),{'action':'accept'})
        self.assertEqual(calls[0]['temperature'],0)
        self.assertIn('oneOf',calls[0]['response_schema'])

    def test_optional_omission_cannot_add_unrequested_requirements(self):
        review={'reason':'草稿未标注缺失的容量与可用时间信息，请补充。'}
        self.assertTrue(control.optional_omission(review,'对比费用与设备，核对取消规则并写说明。'))
        self.assertFalse(control.optional_omission(review,'比较费用、容量与可用时间。'))
        self.assertFalse(control.optional_omission({'reason':'草稿金额错误，且缺少容量。'},'写说明'))
    def patch(self,draft,edits):
        import json
        class Model:
            def generate(self,*args,**kwargs):return json.dumps({'edits':edits}),{'finish_reason':'stop'}
        return control.repair_writing(Model(),json.loads,draft,'金额错误','费用128元','写说明')[0]
    def test_exact_patch_preserves_unrelated_text(self):
        self.assertEqual(self.patch('费用999元。下句保留。',[{'old':'费用999元。','new':'费用128元。'}]),'费用128元。下句保留。')
    def test_ambiguous_and_overlapping_patches_are_rejected(self):
        for draft,edits in [('金额，金额',[{'old':'金额','new':'费用'}]),('费用999元',[{'old':'费用999元','new':'费用128元'},{'old':'999元','new':'128元'}])]:
            with self.assertRaises(control.OutputCheckError):self.patch(draft,edits)
    def test_patch_cannot_include_executable_fields(self):
        with self.assertRaises(control.OutputCheckError):self.patch('费用999元',[{'old':'费用999元','new':'费用128元','path':'outside'}])
    def test_block_id_resolves_repeated_paragraph_without_fuzzy_matching(self):
        self.assertEqual(self.patch('费用999元\n\n费用999元',[{'block_id':'B2','new':'费用128元'}]),'费用999元\n\n费用128元')
    def test_block_id_unknown_and_duplicate_edits_are_rejected(self):
        for edits in ([{'block_id':'B3','new':'改写'}],[{'block_id':'B1','new':'甲'},{'block_id':'B1','new':'乙'}]):
            with self.assertRaises(control.OutputCheckError):self.patch('原句',edits)
    def test_fact_sheet_current_rows_excludes_old_assistant_claims(self):
        text=guard.evidence_sheet('写说明',DOCS,{'columns':['金额（元）'],'rows':[['128.5']]},[('write',{'text':'旧合计999元'})])
        self.assertIn('128.5',text);self.assertNotIn('999',text);self.assertNotIn('600',text)
    def test_fact_sheet_explicitly_marks_no_eligible_option(self):
        import json
        docs=[dict(DOCS[0],text=DOCS[0]['text']+'\n容量：30人。\n设备：投影仪。'),dict(DOCS[1],text=DOCS[1]['text']+'\n容量：20人。\n设备：不提供投影仪。')]
        facts=json.loads(guard.evidence_sheet('对比，预算不超过500元，25人参加，必须有投影仪。',docs))
        self.assertTrue(facts['程序硬条件核对']['当前均不合格'])


class RecoveryChecks(unittest.TestCase):
    setUp=controller_fixtures.ControllerTests.setUp
    tearDown=controller_fixtures.ControllerTests.tearDown
    plan=controller_fixtures.ControllerTests.plan
    execute=controller_fixtures.ControllerTests.execute
    def test_bad_amount_is_repaired_before_publication(self):
        self.agent.model.responses=[('交通费用999元。【S1】','stop'),('交通费用128.50元。【S1】','stop')]
        result=self.execute(self.plan('写一份说明。',kind='write'))
        self.assertNotIn('999',result['text']);self.assertEqual(result['plan']['steps'][0]['attempts'],2)
    def test_repeated_bad_amount_delivers_evidence_without_bad_draft(self):
        self.agent.model.responses=[('交通费用999元。','stop')]*3
        result=self.execute(self.plan('写一份说明。',kind='write'))
        self.assertNotIn('999',result['text']);self.assertTrue(result['plan']['grounded_delivery'])
        self.assertEqual(result['plan']['steps'][0]['check']['content_review'],'grounded')
        self.assertEqual(len(result['artifacts']),2)
    def test_grounded_delivery_preserves_computed_results_and_prior_steps(self):
        self.agent.model.responses=[('错误合计999元。','stop')]*3
        result=self.execute(self.plan())
        self.assertTrue(result['plan']['grounded_delivery'])
        self.assertNotIn('999',result['text']);self.assertIn('0.3',result['text'])
        self.assertEqual([s['attempts'] for s in result['plan']['steps']],[1,1,3])
    def test_third_attempt_rebuild_can_resolve_incomplete_patch(self):
        self.agent.model.responses=[('交通费用999元。','stop'),('交通费用999元。','stop'),('交通费用128.50元。【S1】','stop')]
        result=self.execute(self.plan('写一份说明。',kind='write'))
        self.assertEqual(result['plan']['steps'][0]['attempts'],3)
        self.assertFalse(result['plan'].get('grounded_delivery',False));self.assertNotIn('999',result['text'])

    def test_valid_patch_gets_a_second_local_patch_instead_of_full_rewrite(self):
        self.agent.model.responses=[('交通费用999元。','stop'),('交通费用128.50元。','stop'),('交通费用128.50元。【S1】','stop')]
        self.agent.model.draft_checks=[{'action':'accept'},
            {'action':'revise','reason':'当前要求需要出处','quote':'交通费用128.50元。'}, {'action':'accept'}]
        result=self.execute(self.plan('写一份带出处的说明。',kind='write'))
        step=result['plan']['steps'][0]
        self.assertEqual(step['attempts'],3)
        self.assertEqual([r['strategy'] for r in step['repair_history']],['draft','patch'])
        self.assertFalse(result['plan'].get('grounded_delivery',False))
        self.assertIn('128.50',result['text'])


if __name__=='__main__':unittest.main()
