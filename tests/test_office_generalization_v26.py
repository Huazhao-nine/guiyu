"""Office behavior independent of the frozen model-evaluation workbooks."""
import io,json,sys,tempfile,unittest,zipfile
from copy import deepcopy
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import worker as core
from document_tables import native_table,extract_result,protect_tables,table_markers
from workbook_flow import TableFlow,requested_units,plan_actions
from workbook_intent import retains_delivery
from local_query import named_paths
from structured_tables import workbook_layout
from office_agent import OfficeAgent,export_docx

class Selector:
    info={'name':'unit','key':'unit'}
    def __init__(self,value):self.value=value;self.calls=[]
    def generate(self,system,user,**kw):self.calls.append((system,user));return json.dumps(self.value,ensure_ascii=False),{}

class NativeDocumentTests(unittest.TestCase):
    def setUp(self):
        from docx import Document
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        path=self.root/'资料.docx';d=Document();t=d.add_table(rows=1,cols=3)
        for c,v in zip(t.rows[0].cells,['序号','材料名称','件数']):c.text=v
        for row in [('A01','样品甲','2'),('A02','样品乙','0'),('A03','样品丙','15')]:
            for c,v in zip(t.add_row().cells,row):c.text=v
        d.save(path);self.docs=[{'id':'S1','name':path.name,'path':str(path),'text':core.read_document(path)}]
        self.choice={'table_id':'S1-T1','columns':['材料名称','件数'],'quote':'材料名称及件数'}
    def test_copies_all_rows_and_zero_from_native_cells(self):
        n=native_table(self.docs,'提取材料名称及件数',Selector(self.choice),json.loads)
        self.assertEqual(n['rows'],[['样品甲','2'],['样品乙','0'],['样品丙','15']])
        result=extract_result(n,self.docs,self.root,'child',core)
        from openpyxl import load_workbook
        b=load_workbook(next(a['path'] for a in result['artifacts'] if a['type']=='xlsx'),data_only=True)
        self.assertEqual(b['处理结果']['B3'].value,0);self.assertEqual(b['处理结果'].max_row,4);b.close()
    def test_model_cannot_supply_rows_or_select_unknown_columns(self):
        for change in [dict(self.choice,rows=[['编造',8]]),dict(self.choice,columns=['不存在']),dict(self.choice,table_id='S2-T1'),dict(self.choice,quote='无关的原话')]:
            with self.subTest(change=change),self.assertRaises(ValueError):native_table(self.docs,'提取清单中逐项的名称和个数',Selector(change),json.loads)
    def test_two_literal_headers_select_without_model_and_copy_all_rows(self):
        model=Selector({'table_id':None})
        n=native_table(self.docs,'整理所有材料和件数，保留零值。',model,json.loads)
        self.assertFalse(model.calls);self.assertEqual(len(n['rows']),3)
        self.assertEqual(n['columns'],['材料名称','件数'])
    def test_partial_scope_uses_existing_filter_workflow(self):
        model=Selector(self.choice)
        self.assertIsNone(native_table(self.docs,'只保留件数大于1的材料',model,json.loads));self.assertFalse(model.calls)
    def test_step_boilerplate_does_not_override_user_scope(self):
        n=native_table(self.docs,'先提取全部，再筛选；不得重复计算合计',Selector(self.choice),json.loads,goal='提取材料名称及件数')
        self.assertEqual(len(n['rows']),3)
    def test_word_inserts_all_verified_rows_and_is_idempotent(self):
        n=native_table(self.docs,'提取材料名称及件数',Selector(self.choice),json.loads)
        context={'docs':self.docs,'results':[('table',{'native_table':n})],'query':{}}
        self.assertIn('{{SOURCE_TABLE_1}}',table_markers(context))
        value=protect_tables('# 材料情况\n\n{{SOURCE_TABLE_1}}',context)
        self.assertEqual(value,protect_tables(value,context));self.assertNotIn('{{SOURCE',value)
        path=self.root/'结果.docx';export_docx(value,path,self.docs)
        from docx import Document
        d=Document(path);self.assertEqual(len(d.tables[0].rows),4)
        self.assertEqual(d.tables[0].rows[-1].cells[0].text,'样品丙')
    def test_excluded_sources_and_filtered_rows_are_not_reintroduced(self):
        n=native_table(self.docs,'提取材料名称及件数',Selector(self.choice),json.loads)
        context={'docs':[],'results':[('table',{'native_table':n})],'query':{}}
        self.assertEqual(protect_tables('正文',context),'正文')
        context.update(docs=self.docs,query={'filters':[{'column':'件数','operator':'gt','value':'1'}]},table={'columns':['材料名称','件数'],'rows':[['样品丙','15']]})
        text=protect_tables('正文',context);self.assertIn('样品丙',text);self.assertNotIn('样品甲',text);self.assertNotIn('样品乙',text)
    def test_full_native_table_keeps_paragraph_budget_but_filtered_table_does_not(self):
        from fact_guard import check_writing,evidence_sheet
        n=native_table(self.docs,'提取材料名称及件数',Selector(self.choice),json.loads)
        self.docs[0]['text']='预算：2.6万元。\n'+self.docs[0]['text']
        result=extract_result(n,self.docs,self.root,'child',core)
        table={k:result[k] for k in ('columns','rows')};results=[('table',result)]
        self.assertFalse(check_writing('预算为26000元。','提取预算和清单',self.docs,table,results)['issues'])
        self.assertIn('2.6万元',evidence_sheet('提取预算和清单',self.docs,table,results))
        table=deepcopy(table);table['rows']=table['rows'][1:]
        self.assertTrue(check_writing('预算为26000元。','提取清单',self.docs,table,results)['issues'])

class OfficeContinuityTests(unittest.TestCase):
    def test_processing_and_output_conditions_remain_a_delivery_contract(self):
        for goal in ['其他规则和输出列不变','其余计算标准、排序和字段都保持不变','其他筛选条件及汇总照旧']:
            self.assertTrue(retains_delivery(goal))
        self.assertFalse(retains_delivery('其他规则改变，输出列另定'))
    def test_keeps_summary_after_narrowing_and_recomputes_count(self):
        class Model:
            def __init__(self):self.actions=iter([
                {'tool':'filter','where':{'field':'余额（元）','op':'ne','value':0}},
                {'tool':'group','input':'V1','by':[],'metrics':[{'function':'sum','field':'余额（元）','name':'总额'},{'function':'count','name':'条数'}]},
                {'tool':'finish','result':'V1','summaries':['V2']}])
            def generate(self,system,user,**kw):
                if system.startswith('只确定输出视图'):value={'title':'余额','deliver':'detail','detail_request':''}
                elif '当前只核对数据处理' in system:value={'state':'passed'}
                else:value=next(self.actions)
                return json.dumps(value,ensure_ascii=False),{}
        o=SimpleNamespace(agent=SimpleNamespace(model=Model()),core=SimpleNamespace(parse_json=json.loads,emit=lambda *a,**kw:None),workbook_metrics={'tokens':0,'peak_memory_gb':0})
        source={'columns':['项目','余额（元）'],'rows':[['甲','0'],['乙','20'],['丙','5']],'provenance':[[0],[1],[2]],'notes':[]}
        contract={'deliver':'both','preserve_detail':True,'global_summary':True,'docx':False,'write':''}
        flow,c,finish,result,_=plan_actions(o,source,'余额为0的去掉，其他规则和输出列不变，只要表格。',previous_goal='保留明细并附总额和条数。',previous_contract=contract)
        self.assertTrue(c['preserve_detail']);self.assertEqual(result['rows'],[['乙','20'],['丙','5']]);self.assertEqual(result['summaries'][0]['rows'],[['25','2']])
    def test_parallel_units_are_applied_to_the_delivered_values(self):
        self.assertEqual(requested_units('时长用小时、重量以kg、金额用万元显示。'),{'duration':'小时','mass':'kg','CNY':'万元'})
        source={'columns':['时间（分钟）','重量（g）','金额（元）'],'rows':[['150','1200','5000']],'provenance':[[0]],'notes':[]}
        f=TableFlow(source,'时长用小时、重量以kg、金额用万元显示。');result=f.finish({'result':'V0'},{'deliver':'detail'})
        self.assertEqual(result['rows'],[['2.5','1.2','0.5']]);self.assertEqual(f.views['V0']['rows'],[['150','1200','5000']])

class ScopeAndCacheTests(unittest.TestCase):
    def test_coordinated_short_title_resolves_existing_unique_sibling(self):
        files=['/scope/研讨会通知.md','/scope/研讨会补充说明.txt','/scope/其他补充说明.txt']
        self.assertEqual(named_paths('查找研讨会通知和补充说明，以最新内容为准。',files),set(files[:2]))
        self.assertEqual(named_paths('研讨会通知和人数分析。',files),{files[0]})
        with self.assertRaisesRegex(ValueError,'多份'):named_paths('研讨会通知和补充说明。',files+['/scope/研讨会通知补充说明.txt'])
    def test_empty_string_cache_is_not_an_unknown_numeric_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'表.xlsx';ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            def create(kind):
                with zipfile.ZipFile(path,'w') as z:
                    z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
                    z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="数据" r:id="r1"/></sheets></workbook>')
                    z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}"><sheetData><row><c r="A1" {kind}><f>IF(B1="","",B1*2)</f></c></row></sheetData></worksheet>')
            create('t="str"');self.assertEqual(workbook_layout(path),{'数据':[]})
            create('t="n"')
            with self.assertRaisesRegex(ValueError,'缓存'):workbook_layout(path)
    def test_independent_searches_accumulate_only_in_authorized_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);agent=OfficeAgent(core.Agent(Selector({}),root/'data'),core)
            docs=[{'id':'S1','name':'甲.txt','path':str(root/'甲.txt'),'text':'登记进度'}, {'id':'S2','name':'乙.txt','path':str(root/'乙.txt'),'text':'版本变更'}]
            context={'docs':docs,'scope_docs':docs,'table':None,'query':{},'results':[]};plan={'prompt':'查找两份资料','paths':[]}
            with redirect_stdout(io.StringIO()):
                first=agent.tool({'tool':'search','instruction':'登记进度'},context,plan,'search-a');context['results'].append(('search',first))
                second=agent.tool({'tool':'search','instruction':'版本变更'},context,plan,'search-b')
            self.assertEqual(set(second['query_matched_ids']),{'S2'});self.assertEqual(set(second['matched_ids']),{'S1','S2'});self.assertEqual(len(context['docs']),2)
            context['docs']=[docs[0]]
            with redirect_stdout(io.StringIO()):agent.tool({'tool':'search','instruction':'其中版本变更'},context,plan,'search-c')
            self.assertFalse(any(d['id']=='S2' for d in context['docs']))

if __name__=='__main__':unittest.main()
