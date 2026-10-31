"""Index consistency tests use a deterministic encoder; model quality is tested separately with real BGE."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from workspace_index import WorkspaceIndex
from test_office import FakeAgent
from office_agent import OfficeAgent
import worker as core

class TestEncoder:
 available=True;key='test-encoder-v1';dimension=3
 def __init__(self):self.calls=0;self.mutate=None
 def encode(self,texts,query=False):
  self.calls+=len(texts)
  if self.mutate:
   action,self.mutate=self.mutate,None;action()
  return [np.array([1.,0,0],dtype=np.float32) if any(t in s for t in ('差旅','车票','交通','报销','费用','金额')) else np.array([0,1.,0],dtype=np.float32) for s in texts]
 def close(self):pass

class IndexTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name).resolve()
  self.root=self.base/'workspace';self.root.mkdir();self.encoder=TestEncoder()
  self.index=WorkspaceIndex(self.root,self.base/'data',self.encoder)
 def tearDown(self):self.index.close();self.temp.cleanup()
 def write(self,name,text):
  path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);return path
 def find(self,query,previous=None):return self.index.retrieve({'query':query,'previous':previous or {}})
 def test_explicit_conversation_context_reuses_scope_without_retrieval_keywords(self):
  path=self.write('支出记录.txt','交通费用128.50元。');first=self.find('差旅')
  before=self.encoder.calls
  result=self.index.retrieve({'query':'门槛调到200，其余不变。','continue_previous':True,'previous':{'snapshots':first['snapshots'],'retrieval':first}})
  self.assertTrue(result['reuse']);self.assertEqual(result['paths'],[str(path)]);self.assertEqual(self.encoder.calls,before)
 def test_explicit_context_never_overrides_a_different_named_source(self):
  self.write('甲说明.txt','交通费用128.50元。');other=self.write('乙说明.txt','其他安排。');first=self.find('甲说明.txt')
  result=self.index.retrieve({'query':'改看乙说明.txt','continue_previous':True,'previous':{'snapshots':first['snapshots'],'retrieval':first}})
  self.assertFalse(result['reuse']);self.assertEqual(result['paths'],[str(other)])
 def test_explicit_context_still_refreshes_changed_source_snapshots(self):
  path=self.write('支出记录.txt','交通费用128.50元。');first=self.find('差旅');path.write_text('交通费用300元。')
  result=self.index.retrieve({'query':'门槛调到200，其余不变。','continue_previous':True,'previous':{'snapshots':first['snapshots'],'retrieval':first}})
  self.assertFalse(result['reuse']);self.assertTrue(result['refreshed']);self.assertEqual(result['paths'],[str(path)]);self.assertNotEqual(first['snapshots'],result['snapshots'])
 def test_explicit_context_does_not_include_new_related_documents(self):
  original=self.write('原登记.txt','交通费用128.50元。');first=self.find('差旅')
  self.write('新草稿.txt','交通费用900元。')
  result=self.index.retrieve({'query':'门槛调到200，其余不变。','continue_previous':True,'previous':{'snapshots':first['snapshots'],'retrieval':first}})
  self.assertTrue(result['reuse']);self.assertEqual(result['paths'],[str(original)])
 def test_explicit_context_refreshes_only_original_scope(self):
  original=self.write('原登记.txt','交通费用128.50元。');first=self.find('差旅')
  original.write_text('交通费用300元。');self.write('新草稿.txt','交通费用900元。')
  result=self.index.retrieve({'query':'门槛调到200，其余不变。','continue_previous':True,'previous':{'snapshots':first['snapshots'],'retrieval':first}})
  self.assertTrue(result['refreshed']);self.assertEqual(result['paths'],[str(original)])
 def test_explicit_context_reports_a_missing_source_instead_of_replacing_it(self):
  original=self.write('原登记.txt','交通费用128.50元。');first=self.find('差旅');original.unlink();self.write('新草稿.txt','交通费用900元。')
  with self.assertRaisesRegex(ValueError,'上轮资料范围'):
   self.index.retrieve({'query':'门槛调到200，其余不变。','continue_previous':True,'previous':{'snapshots':first['snapshots'],'retrieval':first}})
 def test_explicit_new_search_can_expand_a_previously_pinned_scope(self):
  original=self.write('原登记.txt','交通费用128.50元。');first=self.find('差旅');other=self.write('新草稿.txt','交通费用900元。')
  result=self.index.retrieve({'query':'重新检索差旅费用','kind':'workflow','continue_previous':True,'previous':{'snapshots':first['snapshots'],'retrieval':first}})
  self.assertFalse(result['reuse']);self.assertEqual(set(result['paths']),{str(original),str(other)})
 def test_pinned_refresh_preserves_more_than_eight_files_for_writing(self):
  paths=[self.write(f'车票{i}.txt','交通费用128.50元。') for i in range(9)]
  first=self.index.retrieve({'query':'统计差旅费用','kind':'workflow'});self.assertEqual(len(first['paths']),9)
  paths[0].write_text('交通费用300元。')
  result=self.index.retrieve({'query':'写成说明。','continue_previous':True,'previous':{'snapshots':first['snapshots'],'retrieval':first}})
  self.assertTrue(result['refreshed']);self.assertEqual(set(result['paths']),{str(p) for p in paths})
 def test_vector_retrieval_can_match_without_literal_overlap(self):
  path=self.write('票据.txt','车票128.50元。')
  result=self.find('差旅')
  self.assertEqual(result['paths'],[str(path)]);self.assertEqual(result['hits'][0]['reason'],'语义相近')
 def test_unchanged_documents_reuse_cached_vectors(self):
  self.write('车票.txt','交通费用128.50元。');self.index.sync();before=self.encoder.calls
  self.index.sync();self.assertEqual(self.encoder.calls,before)
 def test_modify_replaces_old_text_and_vectors(self):
  path=self.write('记录.txt','交通费用128.50元。');self.index.sync()
  path.write_text('招聘面试安排。');self.index.sync()
  stored=' '.join(r[0] for r in self.index.db.execute('SELECT text FROM chunks'))
  self.assertNotIn('128.50',stored);self.assertIn('招聘',stored)
  self.assertEqual(self.find('差旅')['paths'],[])
 def test_delete_removes_searchable_content(self):
  path=self.write('车票.txt','交通费用128.50元。');self.index.sync();path.unlink()
  self.assertEqual(self.find('差旅')['paths'],[])
  self.assertEqual(self.index.db.execute('SELECT count(*) FROM chunks').fetchone()[0],0)
 def test_rename_updates_path_and_prunes_old_reference(self):
  path=self.write('旧名.txt','交通费用128.50元。');self.index.sync();new=path.with_name('新名.txt');path.rename(new)
  self.assertEqual(self.find('差旅')['paths'],[str(new)])
 def test_links_hidden_files_and_own_storage_are_excluded(self):
  outside=self.base/'外部.txt';outside.write_text('交通费用')
  (self.root/'链接.txt').symlink_to(outside);(self.root/'链接目录').symlink_to(self.base,target_is_directory=True)
  self.write('.隐藏.txt','交通费用')
  self.index.close();inside=self.root/'internal';inside.mkdir();(inside/'缓存.txt').write_text('交通费用')
  self.index=WorkspaceIndex(self.root,inside,self.encoder)
  self.assertEqual(self.find('差旅')['paths'],[])
 def test_changed_while_reading_is_not_published(self):
  path=self.write('车票.txt','交通费用128.50元。');self.encoder.mutate=lambda:path.write_text('交通费用999元。')
  status=self.index.sync()
  self.assertEqual(status['skipped_count'],1);self.assertEqual(status['chunks'],0)
 def test_parse_failure_cannot_retain_old_document(self):
  path=self.write('车票.txt','交通费用128.50元。');self.index.sync();path.write_text('交通费用200元。')
  with patch('workspace_index.read_document',side_effect=ValueError('不能读取')):status=self.index.sync()
  self.assertEqual(status['chunks'],0);self.assertEqual(status['skipped_count'],1)
 def test_root_unavailable_disables_cached_index(self):
  self.write('车票.txt','交通费用128.50元。');self.index.sync();shutil.rmtree(self.root)
  with self.assertRaisesRegex(ValueError,'工作区'):self.find('差旅')
  self.assertEqual(self.index.db.execute('SELECT count(*) FROM chunks').fetchone()[0],0)
 def test_statistics_do_not_silently_truncate_41_matches(self):
  for i in range(41):self.write(f'车票{i}.txt','交通费用128.50元。')
  with self.assertRaisesRegex(ValueError,'41.*40'):self.find('统计差旅费用')
 def test_partial_document_blocks_automatic_workspace_total(self):
  self.write('长车票.txt','交通费用'+('文本'*31000))
  with self.assertRaisesRegex(ValueError,'未完整读取'):self.find('统计全部费用')
 def test_no_matching_query_has_no_fallback(self):
  self.write('招聘.txt','招聘面试安排')
  self.assertEqual(self.find('差旅')['paths'],[])
 def test_named_document_limits_related_workspace_candidates(self):
  target=self.write('费用台账.csv','项目,金额\n星桥,128.50')
  self.write('预算说明.txt','项目费用预算500元。')
  result=self.find('费用台账中统计项目金额。')
  self.assertEqual(result['paths'],[str(target)]);self.assertEqual(result['hits'][0]['reason'],'指定文档')
 def test_two_named_documents_stay_within_explicit_scope(self):
  a=self.write('青松设备方案.txt','设备报价2800元。');b=self.write('远山设备方案.txt','设备报价3200元。')
  self.write('其他设备方案.txt','设备报价3100元。')
  self.assertEqual(set(self.find('比较青松设备方案和远山设备方案。')['paths']),{str(a),str(b)})
 def test_named_truncated_document_cannot_bypass_read_completeness(self):
  self.write('费用台账说明.txt','费用'+('文字'*31000))
  with self.assertRaisesRegex(ValueError,'指定文档未完整'):self.find('统计费用台账说明的金额。')
 def test_new_document_refreshes_thread_instead_of_using_old_scope(self):
  self.write('车票.txt','交通费用128.50元。');first=self.find('差旅')
  self.write('新车票.txt','交通费用180元。')
  next_turn=self.find('那陈雨呢？',{'snapshots':first['snapshots'],'retrieval':first})
  self.assertTrue(next_turn['refreshed']);self.assertEqual(len(next_turn['paths']),2)
 def test_embedding_revision_change_rebuilds_vectors(self):
  self.write('车票.txt','交通费用128.50元。');self.index.sync();self.index.close()
  second=TestEncoder();second.key='test-encoder-v2';self.index=WorkspaceIndex(self.root,self.base/'data',second)
  self.assertEqual(self.index.db.execute('SELECT count(*) FROM chunks').fetchone()[0],0)
  self.index.sync();self.assertGreater(second.calls,0)
 def test_task_snapshot_rejects_mutation_after_retrieval(self):
  path=self.write('车票.txt','交通费用128.50元。');result=self.find('差旅');path.write_text('交通费用999元。')
  office=OfficeAgent(FakeAgent(self.base/'tasks'),core)
  with redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'检索后发生变化'):
   office.draft({'prompt':'统计费用','paths':result['paths'],'retrieval':result})
 def test_followup_after_update_recomputes_and_preserves_conditions(self):
  path=self.root/'台账.csv';shutil.copy2(ROOT/'fixtures/query/社区费用台账.csv',path)
  first=self.find('只统计状态包含待报销且金额大于100元，按经办人分组统计。')
  office=OfficeAgent(FakeAgent(self.base/'tasks'),core)
  with redirect_stdout(io.StringIO()):
   plan=office.draft({'prompt':'只统计状态包含待报销且金额大于100元，按经办人分组统计。','paths':first['paths'],'retrieval':first,'kind':'statistics'})
   office.execute({'plan_id':plan['id'],'paths':plan['paths']})
  path.write_text(path.read_text().replace('180.00','280.00'))
  fresh=self.find('那陈雨呢？',{'snapshots':first['snapshots'],'retrieval':first})
  with redirect_stdout(io.StringIO()):
   second=office.draft({'prompt':'那陈雨呢？','paths':fresh['paths'],'retrieval':fresh,'refresh_sources':True,'parent_id':plan['id'],'kind':'statistics'})
   result=office.execute({'plan_id':second['id'],'paths':second['paths']})
  self.assertTrue(second['sources_refreshed']);self.assertIn('280',result['text']);self.assertNotIn('128.5',result['text'])
  self.assertEqual(len(second['query']['filters']),3)

 def test_manual_workspace_scope_rejects_parent_link_swap(self):
  folder=self.root/'sub';folder.mkdir();file=folder/'inside.txt';file.write_text('原始内容')
  outside=self.base/'outside';outside.mkdir();(outside/'inside.txt').write_text('外部内容')
  file.unlink();folder.rmdir();folder.symlink_to(outside,target_is_directory=True)
  with self.assertRaisesRegex(ValueError,'当前工作区'):core.scope_from_request({'paths':[str(file)],'workspace_root':str(self.root)})
 def test_auto_multi_sheet_statistics_includes_all_compatible_sheets(self):
  from openpyxl import Workbook
  path=self.root/'费用.xlsx';book=Workbook();book.active.append(['金额']);book.active.append([100]);sheet=book.create_sheet('二月');sheet.append(['金额']);sheet.append([200]);book.save(path)
  retrieved=self.find('统计费用')
  office=OfficeAgent(FakeAgent(self.base/'tasks'),core)
  with redirect_stdout(io.StringIO()):
   plan=office.draft({'prompt':'统计费用','paths':retrieved['paths'],'retrieval':retrieved})
   result=office.execute({'plan_id':plan['id'],'paths':plan['paths']})
  self.assertIn('300',result['text']);self.assertIn('二月',result['text'])
