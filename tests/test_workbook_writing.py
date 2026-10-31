import io,json,sys,tempfile,unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import worker as core
from workbook_writing import fact_catalog,write_from_results,writing_title
from types import SimpleNamespace
from docx import Document

TABLE={'columns':['物料编号','补货成本'],'rows':[['I02','300'],['I04','30'],['I01','20']],'units':{'补货成本':'CNY'},
       'summaries':[{'columns':['补货成本合计','物料种数'],'rows':[['350','3']],'units':{'补货成本合计':'CNY'}}]}


class Editor:
 def __init__(self,value):self.value=value;self.calls=[]
 def generate(self,system,user,**kw):
  self.calls.append((system,json.loads(user),kw))
  return json.dumps(self.value,ensure_ascii=False),{'tokens':10,'seconds':.01}


def writing_plan(prompt,write='写一段简短情况说明并导出Word。',goals=(),source_names=()):
 return {'prompt':prompt,'source_names':list(source_names),'title':'不可信的模型任务名',
         'workbook':{'program':{'write':write},'flow':{'goals':list(goals),'contract':{'docx':True}}}}


def checked_table(*names):
 result=deepcopy(TABLE)
 result['locations']=[{'file':name,'sheet':'登记','row':i+2} for i,name in enumerate(names)]
 return result

class FactWritingTests(unittest.TestCase):
 def test_fact_blocks_keep_money_units_and_actual_row_order(self):
  facts=fact_catalog(TABLE,5)
  self.assertIn('350元',facts['S1_1']);self.assertIn('I02',facts['R1']);self.assertIn('300元',facts['R1'])
 def test_invalid_editor_values_cannot_rewrite_amounts(self):
  class Model:
   def generate(self,*args,**kw):return json.dumps({'title':'总计150元','facts':['invented:150']}),{}
  with tempfile.TemporaryDirectory() as temp:
   office=SimpleNamespace(agent=core.Agent(Model(),Path(temp)/'data'),core=core)
   context={'results':[('workbook',{'result_table':TABLE,'workbook_check':{'source_rows':5}})],'docs':[]}
   result=write_from_results(office,context,{'prompt':'写简短说明','workbook':{'program':{'write':'写简短说明'}}},'fact-brief')
   self.assertTrue(result['checked_fact_rendering']);self.assertIn('350元',result['text']);self.assertNotIn('150',result['text'])
   document=Document(next(a['path'] for a in result['artifacts'] if a['type']=='docx'))
   self.assertEqual([r.cells[0].text for r in document.tables[0].rows[1:]],['I02','I04','I01'])


class WritingTitleTests(unittest.TestCase):
 def render(self,plan,table,model):
  with tempfile.TemporaryDirectory() as temp:
   office=SimpleNamespace(agent=core.Agent(model,Path(temp)/'data'),core=core)
   context={'results':[('workbook',{'result_table':table,'workbook_check':{'source_rows':5}})],'docs':[]}
   result=write_from_results(office,context,plan,'brief')
   document=Document(next(a['path'] for a in result['artifacts'] if a['type']=='docx'))
   result['word_heading']=document.paragraphs[0].text
   result['word_paragraphs']=[p.text for p in document.paragraphs]
   return result

 def test_explicit_titles_keep_user_numbers_and_override_model_and_source(self):
  requests=[
   ('请写说明，标题为“2026年第四季度费用核对说明”。','2026年第四季度费用核对说明'),
   ('以《金额不少于2500元的登记》为标题，导出Word。','金额不少于2500元的登记'),
   ('不要修改正文，标题改为：阶段核对结果。','阶段核对结果'),
   ('不要修改数据且标题改为“费用核对”。','费用核对'),
   ('标题就叫设备登记说明并导出Word。','设备登记说明'),
   ('邮件主题：本月待核对事项。','本月待核对事项'),
  ]
  for prompt,expected in requests:
   with self.subTest(prompt=prompt):
    editor=Editor({'title':'无关补货标题','facts':['COUNT','S1_1']})
    result=self.render(writing_plan(prompt),checked_table('设备巡检.xlsx'),editor)
    self.assertEqual(result['word_heading'],expected);self.assertEqual(len(editor.calls),1)
    self.assertEqual(result['writing_check']['title_check']['source'],'explicit_request')
    self.assertIn('350元',result['text'])

 def test_followup_inherits_explicit_title_and_provides_full_attached_goal_context(self):
  original='在“会务领用.xlsx”核对剩余额度，写一段说明，标题为“会务领用情况”。'
  current='门槛改成不少于1800元，其他要求不变。'
  plan=writing_plan(current,goals=[original,'保持输出格式不变。',current])
  before=deepcopy(plan);editor=Editor({'title':'补货门槛调整说明','facts':['R3','R1']})
  result=self.render(plan,checked_table('会务领用.xlsx'),editor)
  self.assertEqual(result['word_heading'],'会务领用情况')
  self.assertEqual(result['writing_check']['title_check']['source'],'retained_explicit_request')
  self.assertEqual(len(editor.calls),1);self.assertEqual(plan,before)
  self.assertIn(original,editor.calls[0][1]['用户完整目标']);self.assertIn(current,editor.calls[0][1]['用户完整目标'])
  self.assertNotIn('补货',editor.calls[0][0]);self.assertNotIn('"title"',editor.calls[0][0])
  self.assertEqual(result['writing_check']['selected_facts'],['COUNT','S1_1','R1','R3'])

 def test_followup_uses_verified_source_topic_and_ignores_polluted_model_title(self):
  original='在“维修结算.csv”中核对剩余费用并写说明。'
  current='门槛改成不少于120元，其他要求不变。'
  plan=writing_plan(current,goals=[original,current],source_names=['无关备货.xlsx','维修结算.csv'])
  editor=Editor({'title':'补货额度说明','facts':['COUNT']})
  result=self.render(plan,checked_table('维修结算.csv'),editor)
  self.assertEqual(result['word_heading'],'维修结算情况说明')
  self.assertEqual(result['writing_check']['title_check'],{'source':'verified_source','basis':'维修结算.csv'})
  self.assertEqual(len(editor.calls),1);self.assertNotIn('补货额度说明',result['text'])

 def test_new_task_and_source_switch_do_not_inherit_old_explicit_title(self):
  old='请写说明，标题为“会务领用情况”。'
  for current in ('核对设备登记并写说明。','换成另一份工作簿，其他要求不变。','改用“设备登记.xlsx”，其他要求不变。','换“设备登记.csv”，其他要求不变。','切换到“设备登记.xlsx”，其他要求不变。'):
   with self.subTest(current=current):
    title,check=writing_title(writing_plan(current,goals=[old,current]),checked_table('设备登记.xlsx'))
    self.assertEqual(title,'设备登记情况说明');self.assertEqual(check['source'],'verified_source')

 def test_current_explicit_title_overrides_inherited_title(self):
  old='标题为“原有情况说明”。'
  current='其他要求不变，标题改为“核对邮件”。'
  title,check=writing_title(writing_plan(current,goals=[old,current]),checked_table('会务领用.xlsx'))
  self.assertEqual(title,'核对邮件');self.assertEqual(check['source'],'explicit_request')

 def test_verified_revision_and_keep_conditions_preserve_explicit_title(self):
  old='写说明，标题为“会务领用情况”。'
  for current,revision in [('把门槛改为500元，其他条件、排序和输出字段不变。',False),('把门槛改为500元。',True)]:
   with self.subTest(current=current):
    plan=writing_plan(current,goals=[old,current])
    if revision:plan['workbook']['flow']['contract']['revision']={'proof':'verified boundary revision'}
    title,check=writing_title(plan,checked_table('会务领用.xlsx'))
    self.assertEqual(title,'会务领用情况');self.assertEqual(check['source'],'retained_explicit_request')

 def test_quoted_source_negative_and_example_titles_are_not_explicit_requests(self):
  for prompt in ('处理“会务领用.xlsx”，写说明。','处理“标题为采购已完成.xlsx”，写说明。','不要用标题“采购已完成”，写简短说明。','例如标题为“采购说明”；本次请按真实资料写说明。','标题是根据真实资料自动生成，写说明。'):
   with self.subTest(prompt=prompt):
    title,check=writing_title(writing_plan(prompt),checked_table('维修结算.csv'))
    self.assertEqual(title,'维修结算情况说明');self.assertEqual(check['source'],'verified_source')

 def test_multiple_sources_use_neutral_title_without_concatenating_names(self):
  plan=writing_plan('合并明细并写说明。')
  title,check=writing_title(plan,checked_table('维修结算.xlsx','会务领用.xlsx'))
  self.assertEqual(title,'工作簿处理说明');self.assertEqual(check['basis'],'multiple_sources')
  plan['workbook']['program']['write']='写一份通知并导出Word。'
  self.assertEqual(writing_title(plan,checked_table('维修结算.xlsx','会务领用.xlsx'))[0],'工作簿通知')

 def test_generic_or_unsafe_names_stay_neutral_and_paths_are_never_headings(self):
  for name in ('Book1.xlsx','工作簿2.xlsx','设备\n登记.xlsx','设备#登记.xlsx','a'*50+'.xlsx','维修登记.xlsx.exe'):
   with self.subTest(name=name):
    self.assertEqual(writing_title(writing_plan('写说明。'),checked_table(name))[0],'工作簿处理说明')
  self.assertEqual(writing_title(writing_plan('写说明。'),checked_table('/本地目录/维修结算.xlsx'))[0],'维修结算情况说明')
  self.assertEqual(writing_title(writing_plan('写说明。'),checked_table(r'C:\资料\维修结算.csv'))[0],'维修结算情况说明')

 def test_zero_matches_keep_selected_source_and_no_unrelated_source_fallback(self):
  table=checked_table('会务领用.xlsx');table['rows']=[]
  result=self.render(writing_plan('改门槛，其他要求不变。'),table,Editor({'facts':['COUNT']}))
  self.assertEqual(result['word_heading'],'会务领用情况说明');self.assertIn('没有符合条件',result['text'])
  table=deepcopy(TABLE);table['inputs']=['会务领用.xlsx / 一月 · 表头1行','会务领用.xlsx / 二月 · 表头1行']
  self.assertEqual(writing_title(writing_plan('写说明。',source_names=['无关.xlsx']),table)[0],'会务领用情况说明')

 def test_email_and_notice_style_keep_source_topic_in_exported_word(self):
  for write,title,email in [('给财务写一封邮件说明核对结果。','维修结算情况说明',True),('请写一份通知并导出Word。','维修结算通知',False)]:
   with self.subTest(write=write):
    editor=Editor({'facts':['COUNT']})
    result=self.render(writing_plan(write,write),checked_table('维修结算.csv'),editor)
    self.assertEqual(result['word_heading'],title);self.assertEqual('您好：' in result['word_paragraphs'],email)
    self.assertEqual(len(editor.calls),1)

 def test_invalid_fact_selection_fallback_keeps_grounded_title_and_existing_retry_budget(self):
  editor=Editor({'title':'无关标题','facts':['invented']})
  result=self.render(writing_plan('写说明。'),checked_table('会务领用.xlsx'),editor)
  self.assertEqual(result['word_heading'],'会务领用情况说明');self.assertEqual(len(editor.calls),2)
  self.assertEqual(result['writing_check']['editor'],'safe_default');self.assertIn('350元',result['text'])

if __name__=='__main__':unittest.main()
