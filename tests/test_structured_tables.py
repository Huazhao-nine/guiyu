"""Fictional workbook regression for conversational row extraction and exported copies."""
import csv
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from openpyxl import Workbook, load_workbook
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import worker as core
from local_query import compile_query, apply_query, named_paths
from office_agent import OfficeAgent, read_structured, numeric_value
from structured_tables import resolve_query, output_columns, row_filter_goal
from request_router import RequestRouter

PROMPT='在我给你的工作簿 1 文件中，把计算技术研究所的同学的名单分离出来，发给我'

class SilentModel:
    info={'key':'test','name':'test'}
    def generate(self,*args,**kwargs):raise AssertionError('Literal extraction must not generate rows')

class StructuredTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.path=self.root/'工作簿1.xlsx'
        book=Workbook();book.active.title='说明';book.active.append(['使用说明']);book.active.append(['全部为虚构学生，禁止外传真实资料。'])
        first=book.create_sheet('一班');first.append(['研究生登记表']);first.append([]);first.append(['姓名','培养单位','学号'])
        first.append(['林晓','中国科学院计算技术研究所','00001']);first.append(['周宁','中国科学院软件研究所','00002']);first.append(['陈雨','计算技术研究所','00003'])
        second=book.create_sheet('二班');second.append(['学号','姓名','培养单位']);second.append(['00004','陈雨','中国科学院计算技术研究所']);second.append(['00005','赵安','计算机网络信息中心'])
        book.save(self.path);self.hash=core.digest(self.path)
        self.office=OfficeAgent(core.Agent(SilentModel(),self.root/'data'),core)
    def tearDown(self):self.tmp.cleanup()
    def run_task(self,prompt=PROMPT,parent=None):
        with redirect_stdout(io.StringIO()):
            plan=self.office.draft({'prompt':prompt,'paths':[str(self.path)],'parent_id':parent})
            return self.office.execute({'plan_id':plan['id'],'paths':plan['paths']})
    def test_natural_roster_request_exports_exact_rows_and_zero_padded_ids(self):
        result=self.run_task()
        self.assertEqual([s['tool'] for s in result['plan']['steps']],['filter'])
        self.assertEqual([r[2] for r in result['rows']],['00001','00003','00004'])
        self.assertIn('林晓',result['text']);self.assertIn('3 条记录',result['text'])
        self.assertIn('说明',result['text']);self.assertIn('二班',result['text'])
        self.assertEqual({a['type'] for a in result['artifacts']},{'xlsx','csv'})
        self.assertEqual(core.digest(self.path),self.hash);self.assertIsNone(result['transaction'])
        check=result['plan']['results']['step-1']['selection_check']
        self.assertEqual([r['row'] for r in check['locations']],[4,6,2])
        path=next(a['path'] for a in result['artifacts'] if a['type']=='xlsx')
        book=load_workbook(path,read_only=True);self.assertEqual(book.active['C2'].value,'00001');book.close()
    def test_projection_and_multiturn_keep_full_base_table(self):
        result=self.run_task(PROMPT+'，只保留姓名、学号')
        self.assertEqual(result['columns'],['姓名','学号'])
        following=self.run_task('那软件研究所的同学名单呢？',result['id'])
        self.assertEqual(following['rows'],[['周宁','中国科学院软件研究所','00002']])
    def test_zero_matches_never_export_everyone(self):
        result=self.run_task('筛选培养单位等于不存在研究所')
        self.assertEqual(result['rows'],[]);self.assertIn('没有符合条件',result['text'])
    def test_explicit_sheet_limits_scope(self):
        result=self.run_task(PROMPT+'，只用工作表“一班”')
        self.assertEqual([r[2] for r in result['rows']],['00001','00003'])
    def test_duplicate_people_are_preserved_not_deduplicated_by_name(self):
        result=self.run_task();self.assertEqual(sum(r[0]=='陈雨' for r in result['rows']),2)
    def test_same_basename_requires_clarification(self):
        with self.assertRaisesRegex(ValueError,'同名'):named_paths(PROMPT,['/a/工作簿1.xlsx','/b/工作簿 1.xlsx'])
    def test_named_file_does_not_match_workbook_10(self):
        self.assertEqual(named_paths(PROMPT,['/a/工作簿1.xlsx','/b/工作簿10.xlsx']),{'/a/工作簿1.xlsx'})
    def test_excluded_file_is_not_selected_when_switching_sources(self):
        self.assertEqual(named_paths('不要用“甲登记.txt”，改用乙登记.txt。',['/a/甲登记.txt','/a/乙登记.txt']),{'/a/乙登记.txt'})
        self.assertEqual(named_paths('不用甲登记.txt，只处理乙登记.txt。',['/a/甲登记.txt','/a/乙登记.txt']),{'/a/乙登记.txt'})
        self.assertEqual(named_paths('不要用工作簿1，改用工作簿2。',['/a/工作簿1.xlsx','/a/工作簿2.xlsx']),{'/a/工作簿2.xlsx'})
    def test_only_excluded_or_conflicting_source_mentions_require_clarification(self):
        for prompt in ['不要用甲登记.txt。','不要用甲登记.txt，又要读取甲登记.txt。']:
            with self.assertRaisesRegex(ValueError,'范围'):named_paths(prompt,['/a/甲登记.txt'])
    def test_not_only_one_file_preserves_both_named_sources(self):
        self.assertEqual(named_paths('不要只用甲登记.txt，要合并甲登记.txt与乙登记.txt。',['/a/甲登记.txt','/a/乙登记.txt']),{'/a/甲登记.txt','/a/乙登记.txt'})
    def test_missing_named_workbook_does_not_fall_back_to_another(self):
        with self.assertRaisesRegex(ValueError,'未找到'):named_paths('从工作簿2提取名单',['/a/工作簿1.xlsx'])
    def test_pure_filter_planner_cannot_add_an_unrequested_document(self):
        from agent_control import initial_recipe
        from office_agent import TOOLS
        class Model:
            def generate(self,system,user,**kw):
                payload=json.loads(user)
                self.offered=set(payload['工具'])
                return json.dumps({'title':'筛选名单','steps':[{'tool':'filter','instruction':'筛选'}]}),{}
        model=Model();initial_recipe(model,core.parse_json,PROMPT,[self.path],['filter'],TOOLS,{})
        self.assertEqual(model.offered,{'filter'})
    def test_row_review_does_not_confuse_independent_delivery_with_conditions(self):
        self.assertEqual(row_filter_goal('把计算技术研究所的同学名单分离出来，统计补助合计，只保留姓名、学号。'),'把计算技术研究所的同学名单分离出来')
        self.assertIn('只统计状态',row_filter_goal('只统计状态包含已确认的同学，导出Excel'))
    def test_scope_and_route_are_source_bound(self):
        router=RequestRouter(self.office.agent,core)
        self.assertEqual(router.decide({'prompt':PROMPT})['mode'],'workspace')
        other=self.root/'无关.csv';other.write_text('其他,字段\n甲,乙\n')
        with redirect_stdout(io.StringIO()):plan=self.office.draft({'prompt':PROMPT,'paths':[str(self.root)]})
        self.assertEqual(plan['paths'],[str(self.path)])
    def test_incompatible_sheets_are_not_silently_omitted(self):
        book=load_workbook(self.path);sheet=book.create_sheet('三班');sheet.append(['姓名','电话']);sheet.append(['许安','13800000000']);book.save(self.path);book.close()
        with self.assertRaisesRegex(ValueError,'表头不同'):self.run_task()
    def test_unknown_projection_does_not_return_unrequested_columns(self):
        with self.assertRaisesRegex(ValueError,'字段'):output_columns('只保留姓名、年龄',['姓名','学号'])
    def test_formula_strings_are_not_live_in_output(self):
        book=load_workbook(self.path);book['一班']['A4']='=1+1';book['一班']['A4'].data_type='s';book.save(self.path);book.close()
        result=self.run_task();path=next(a['path'] for a in result['artifacts'] if a['type']=='xlsx')
        book=load_workbook(path);self.assertNotEqual(book.active['A2'].data_type,'f');book.close()
    def test_model_query_rejects_invented_conditions(self):
        class Model:
            def generate(self,*a,**kw):return json.dumps({'filters':[{'column':'培养单位','operator':'eq','value':'凭空发明'}]}),{}
        with self.assertRaises(ValueError):resolve_query('挑出合适的同学名单',{'columns':['培养单位'],'rows':[['计算所']]},{},Model(),core.parse_json)
    def test_vertical_merged_institution_is_expanded_only_with_actual_merge(self):
        book=load_workbook(self.path);sheet=book['一班'];sheet['B5']='';sheet.merge_cells('B4:B5');book.save(self.path);book.close()
        result=self.run_task();self.assertEqual([r[2] for r in result['rows']],['00001','00002','00003','00004'])
    def test_uncached_formulas_stop_instead_of_losing_rows(self):
        book=load_workbook(self.path);book['一班']['B4']='="计算技术研究所"';book.save(self.path);book.close()
        with self.assertRaisesRegex(ValueError,'公式'):self.run_task()
    def test_id_columns_are_never_summed(self):
        from office_agent import compute_statistics
        result=compute_statistics({'columns':['学号','金额（元）'],'rows':[['00001','10'],['00003','20']]})
        self.assertEqual([r[0] for r in result['rows']],['金额（元）'])
    def test_statistics_audit_preserves_real_workbook_sheet_and_row(self):
        book=load_workbook(self.path)
        for sheet in (book['一班'],book['二班']):
            header=3 if sheet.title=='一班' else 1
            sheet.cell(header,4,'补助（元）')
            for row in range(header+1,sheet.max_row+1):sheet.cell(row,4,10)
        book.save(self.path);book.close()
        result=self.run_task(PROMPT+'，统计补助合计')
        path=next(a['path'] for a in result['artifacts'] if a['name']=='数值统计.xlsx')
        book=load_workbook(path,read_only=True)
        try:matrix=list(book['参与统计的数据'].iter_rows(values_only=True))
        finally:book.close()
        self.assertEqual(list(matrix[0][-3:]),['来源文件','来源工作表','原始数据行号'])
        self.assertEqual([r[-2:] for r in matrix[1:]],[('一班','4'),('一班','6'),('二班','2')])

if __name__=='__main__':unittest.main()
