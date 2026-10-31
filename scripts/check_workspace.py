"""Actual BGE + actual Qwen workspace workflow. Fictional fixtures only; denied network."""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout
import io
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path.home()/'Library/Application Support/GuiyuRuntime'
if '--isolated' not in sys.argv:
 result=subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',str(RUNTIME/'python/bin/python'),str(Path(__file__).resolve()),'--isolated'])
 raise SystemExit(result.returncode)
sys.path.insert(0,str(ROOT/'backend'))
import worker as core
from office_agent import OfficeAgent
from workspace_index import WorkspaceIndex
from bge_embedding import LocalEmbedder
started=time.perf_counter();checks={};report={'version':'0.9.0','date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'hardware':'Apple M5 32 GB','checks':checks,'fixture':'fictional workspace of 48 documents plus 46-document ledger workspace'}
def check(name,condition):
 checks[name]=bool(condition)
 if not condition:raise AssertionError(name)
check('index_and_inference_network_denied',core.network_probe()['blocked'])
encoder=LocalEmbedder(Path.home()/'Library/Application Support/GuiyuModels/Installed/bge-small-zh-v1.5',ROOT/'packaging/model-catalog.json')
check('pinned_bge_model_available',encoder.available)
report['embedding_key']=encoder.key
with tempfile.TemporaryDirectory(prefix='guiyu-semantic-') as temporary:
 base=Path(temporary).resolve();docs=base/'library';docs.mkdir()
 (docs/'交通凭证.txt').write_text('【虚构资料】\n为参加上海的项目会议，林晓购买往返高铁车票，票价合计128.50元。类别为交通，状态为已垫付待报销，日期2026-10-20。')
 (docs/'助教招募.txt').write_text('【虚构资料】\n课程团队拟招募两位助教，面试安排在周六上午九点，地点为教学楼三层。联系人陈老师。')
 topics=['天文观测：记录木星卫星位置和月面环形山。','番茄栽培：保持土壤湿润并修剪侧枝。','跑步训练：轻松跑结束后进行肌肉拉伸。','古诗阅读：唐诗中的秋日意象与用词变化。','陶艺笔记：控制转盘速度和泥土含水量。','烘焙配方：面粉牛奶混合后静置发酵。']
 for i in range(46):(docs/f'笔记{i}.txt').write_text(topics[i%len(topics)])
 index=WorkspaceIndex(docs,base/'index',encoder)
 first=index.retrieve({'query':'差旅支出'})
 check('workspace_exceeds_old_40_document_limit',first['indexed_documents']==48)
 check('semantic_synonym_retrieves_ticket',len(first['paths'])==1 and Path(first['paths'][0]).name=='交通凭证.txt')
 check('semantic_hit_without_literal_query_overlap',all(t not in first['hits'][0]['snippet'] for t in ['差旅','旅支','支出']))
 check('semantic_evidence_has_current_hash_and_line',first['hits'][0]['sha256']==core.digest(Path(first['paths'][0])) and first['hits'][0]['line']>=1)
 check('separate_semantic_topic_retrieves_recruitment',Path(index.retrieve({'query':'招聘安排'})['paths'][0]).name=='助教招募.txt')
 check('unrelated_query_has_no_fallback',index.retrieve({'query':'合同解除条款'})['paths']==[])
 ids=index.db.execute('SELECT id FROM chunks ORDER BY id').fetchall();unchanged=index.sync()
 check('unchanged_sync_does_not_rebuild_chunks',unchanged['changed']==0 and ids==index.db.execute('SELECT id FROM chunks ORDER BY id').fetchall())
 original=index.retrieve({'query':'出行开支'})
 old=docs/'交通凭证.txt';new=docs/'交通凭证更新.txt';old.rename(new)
 renamed=index.retrieve({'query':'出行开支'})
 check('rename_removes_old_path_and_retrieves_new',str(old) not in renamed['paths'] and str(new) in renamed['paths'])
 new.unlink();check('delete_prunes_semantic_content',index.retrieve({'query':'出行开支'})['paths']==[])
 index.close()
 ledger_dir=base/'ledger';ledger_dir.mkdir();ledger=ledger_dir/'社区费用台账.csv';shutil.copy2(ROOT/'fixtures/query/社区费用台账.csv',ledger)
 for i in range(45):(ledger_dir/f'阅读笔记{i}.txt').write_text(topics[i%len(topics)])
 idx=WorkspaceIndex(ledger_dir,base/'ledger-index',encoder)
 prompt='只统计状态包含待报销且金额大于100元，按经办人分组统计，再写一份简短费用说明。'
 found=idx.retrieve({'query':prompt,'kind':'workflow'})
 check('automatic_statistics_selects_ledger_from_46_files',found['paths']==[str(ledger)])
 model=core.LocalModel(RUNTIME/'model');agent=core.Agent(model,base/'tasks');office=OfficeAgent(agent,core)
 def run(prompt,retrieval,parent=None,history=None):
  request={'prompt':prompt,'paths':retrieval['paths'],'retrieval':retrieval,'kind':'auto','history':history or []}
  if parent:request['parent_id']=parent['id']
  if retrieval.get('refreshed'):request['refresh_sources']=True
  with redirect_stdout(io.StringIO()):
   plan=office.draft(request);result=office.execute({'plan_id':plan['id'],'paths':plan['paths']})
  return result
 result=run(prompt,found)
 check('automatic_grouped_totals_are_correct',sorted(r[3] for r in result['rows'])==['128.5','180'])
 check('real_local_model_writes_from_retrieved_rows','林晓' in result['text'] and '陈雨' in result['text'] and '128.5' in result['text'] and '180' in result['text'])
 check('statistics_and_draft_artifacts_exist',len(result['artifacts'])>=3 and all(Path(a['path']).is_file() for a in result['artifacts']))
 previous={'snapshots':result['plan']['snapshot'],'retrieval':result['plan']['retrieval']}
 same=idx.retrieve({'query':'那陈雨呢？','previous':previous})
 check('unchanged_followup_reuses_scope',same['reuse'])
 next_result=run('那陈雨呢？',same,result)
 check('followup_preserves_filters_and_returns_180',len(next_result['plan']['query']['filters'])==3 and next_result['rows'][0][3]=='180')
 ledger.write_text(ledger.read_text().replace('180.00','280.00'))
 fresh=idx.retrieve({'query':'那陈雨呢？','previous':{'snapshots':next_result['plan']['snapshot'],'retrieval':next_result['plan']['retrieval']}})
 check('modified_source_triggers_fresh_retrieval',fresh['refreshed'])
 updated=run('那陈雨呢？',fresh,next_result,history=[{'role':'assistant','text':'旧统计为陈雨180元，总计709元。'}])
 check('changed_file_recomputed_as_280',updated['rows'][0][3]=='280' and '180' not in updated['text'])
 check('changed_file_keeps_three_conditions',len(updated['plan']['query']['filters'])==3)
 write=idx.retrieve({'query':'把本轮结果写成一段简短说明。','previous':{'snapshots':updated['plan']['snapshot'],'retrieval':updated['plan']['retrieval']}})
 written=run('把本轮结果写成一段简短说明。',write,updated)
 check('fresh_draft_excludes_old_amounts','280' in written['text'] and '180' not in written['text'] and '709' not in written['text'])
 check('retrieval_evidence_persisted_with_task',written['plan']['retrieval']['embedding_key']==encoder.key and written['plan']['retrieval']['hits'])
 idx.close()
 samples=['出行开支','高铁往返车票金额128.50元。','招聘安排：周六面试。']
 batch=encoder.encode(samples);single=encoder.encode([samples[0]])[0]
 report['embedding_padding_check']={'maximum_component_delta':float(np.max(np.abs(single-batch[0]))),'cosine_agreement':float(np.dot(single,batch[0]))}
 check('encoder_normalized_and_padding_consistent',all(abs(float(np.linalg.norm(v))-1)<1e-5 for v in batch) and float(np.dot(single,batch[0]))>.99999)
report['all_checks_passed']=all(checks.values());report['wall_seconds']=round(time.perf_counter()-started,2)
(ROOT/'qa/v0.9-workspace-integration-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
