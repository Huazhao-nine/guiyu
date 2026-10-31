"""Workspace-only incremental index. SQLite and sentence vectors never leave local pipes."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import numpy as np
from worker import SUPPORTED, MAX_FILE_BYTES, digest, emit, network_probe, read_document, secure_dir

MAX_DOCUMENTS=2000
MAX_NODES=20000
MAX_CHUNKS=50000
CHUNK_CHARS=320
OVERLAP=48
STOP={'帮我','请问','查找','找到','找一下','检索','搜索','工作区','文档','资料','相关','列出','出处','原文','统计','写成','起草','一份','一下','这些','根据','完成','总结','说明','全部','所有','整个'}

def query_text(text):
    quoted=re.findall(r'[“"「](.*?)[”"」]',text)
    if quoted:return ' '.join(quoted)[:500]
    for word in sorted(STOP,key=len,reverse=True):text=text.replace(word,' ')
    return re.sub(r'\s+',' ',text).strip()[:500] or '内容'

def terms(text):
    text=text.casefold()
    result=re.findall(r'[a-z0-9_]{2,}',text)
    for sequence in re.findall(r'[\u3400-\u9fff]+',text):
        result.extend(sequence[i:i+2] for i in range(len(sequence)-1) if sequence[i:i+2] not in STOP)
    return Counter(result)

def chunks(text):
    for start in range(0,len(text),CHUNK_CHARS-OVERLAP):
        body=text[start:start+CHUNK_CHARS]
        if body.strip():yield start,text.count('\n',0,start)+1,body
        if start+CHUNK_CHARS>=len(text):break

from bge_embedding import LocalEmbedder

class WorkspaceIndex:
    def __init__(self,root,data,embedder,notify=lambda *a,**k:None,exclusions=()):
        self.root=Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():raise ValueError('工作区文件夹无法读取。')
        self.data=secure_dir(data).resolve();self.embedder=embedder;self.notify=notify
        self.exclusions=[Path(p).resolve() for p in exclusions]+[self.data]
        path=self.data/'workspace-index.sqlite3'
        if path.is_symlink():raise ValueError('索引位置异常。')
        self.db=sqlite3.connect(path);path.chmod(0o600)
        self.db.execute('PRAGMA foreign_keys=ON');self.db.execute('PRAGMA journal_mode=DELETE');self.db.execute('PRAGMA secure_delete=ON')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS docs(path TEXT PRIMARY KEY,relative TEXT,size INTEGER,stamp TEXT,sha TEXT,status TEXT,error TEXT,chars INTEGER);
        CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY,path TEXT REFERENCES docs(path) ON DELETE CASCADE,start INTEGER,line INTEGER,text TEXT,vector BLOB,terms TEXT);''')
        identity=str(self.root)+'|'+self.embedder.key+'|v2'
        if self.meta('identity')!=identity:self.db.execute('DELETE FROM docs');self.put('identity',identity);self.db.commit()
        self.last_status={}
    def meta(self,key):
        row=self.db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone();return row[0] if row else None
    def put(self,key,value):self.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,str(value)))
    def permitted(self,path):
        path=Path(path)
        return not path.is_symlink() and path.resolve().is_relative_to(self.root) and not any(path.resolve().is_relative_to(p) for p in self.exclusions)
    def inventory(self):
        if not self.root.is_dir() or self.root.is_symlink():raise ValueError('工作区已移动或暂时无法读取。')
        files=[];nodes=0;limited=False;errors=[]
        def onerror(error):errors.append(str(error))
        for parent,dirs,names in os.walk(self.root,followlinks=False,onerror=onerror):
            dirs[:]=sorted(d for d in dirs if not d.startswith('.') and not d.endswith(('.app','.bundle','.photoslibrary')) and self.permitted(Path(parent)/d))
            for name in sorted(names):
                nodes+=1
                if nodes>MAX_NODES:limited=True;break
                path=Path(parent)/name
                if name.startswith('.') or path.suffix.lower() not in SUPPORTED or not self.permitted(path):continue
                if len(files)>=MAX_DOCUMENTS:limited=True;break
                try:
                    stat=path.stat();stamp=f'{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}'
                    files.append({'path':str(path),'relative':str(path.relative_to(self.root)),'bytes':stat.st_size,'stamp':stamp})
                except OSError as error:errors.append(str(error))
            if limited:break
        return files,limited,errors
    def status(self,phase='ready',**extra):
        counts=dict(self.db.execute('SELECT status,count(*) FROM docs GROUP BY status').fetchall())
        skipped=[{'name':r[0],'reason':r[1]} for r in self.db.execute("SELECT relative,error FROM docs WHERE status!='ready' ORDER BY relative LIMIT 20")]
        value={'phase':phase,'indexed':counts.get('ready',0),'total':sum(counts.values()),'chunks':self.db.execute('SELECT count(*) FROM chunks').fetchone()[0],
               'semantic':self.embedder.available,'embedding_key':self.embedder.key,'updated':float(self.meta('updated') or 0),'skipped_count':sum(v for k,v in counts.items() if k!='ready'),'skipped':skipped,
               'limited':self.meta('limited')=='1','coverage_note':'每份最多读取 60,000 字符；Excel 每表最多 1,000 行。','truncated_count':self.db.execute('SELECT count(*) FROM docs WHERE chars>=60000').fetchone()[0]}
        value.update(extra);self.last_status=value;self.notify('index_status',**value);return value
    def sync(self,rebuild=False):
        self.status('scanning')
        try:files,limited,errors=self.inventory()
        except Exception:
            self.db.execute('DELETE FROM docs');self.db.commit();self.put('updated',time.time());self.db.commit()
            self.status('unavailable',message='工作区无法读取，旧索引已停用。请检查文件夹位置或磁盘。');raise
        if rebuild:self.db.execute('DELETE FROM docs')
        known={r[0]:r[1] for r in self.db.execute('SELECT path,stamp FROM docs')}
        live={f['path'] for f in files};removed=len(set(known)-live)
        self.db.executemany('DELETE FROM docs WHERE path=?',[(p,) for p in set(known)-live]);self.db.commit()
        changed=0
        for item in files:
            if known.get(item['path'])==item['stamp']:continue
            changed+=1;path=Path(item['path']);relative=item['relative']
            self.db.execute('DELETE FROM docs WHERE path=?',(str(path),));self.db.commit()
            try:
                if item['bytes']>MAX_FILE_BYTES:raise ValueError('超过单文件 8 MiB 范围，未建立内容索引。')
                if not self.permitted(path):raise ValueError('文件已变为链接或不在工作区内。')
                before=digest(path);text=read_document(path);pieces=list(chunks(text))
                total=self.db.execute('SELECT count(*) FROM chunks').fetchone()[0]
                if total+len(pieces)>MAX_CHUNKS:raise ValueError('索引片段达到 50,000 上限，请使用更具体的工作区。')
                vectors=self.embedder.encode([relative[:100]+'\n'+p[2] for p in pieces])
                if digest(path)!=before or not self.permitted(path):raise ValueError('读取时文档发生变化，将在下一次更新重试。')
                self.db.execute('INSERT INTO docs VALUES(?,?,?,?,?,?,?,?)',(str(path),relative,item['bytes'],item['stamp'],before,'ready','',len(text)))
                for (offset,line,body),vector in zip(pieces,vectors):
                    self.db.execute('INSERT INTO chunks(path,start,line,text,vector,terms) VALUES(?,?,?,?,?,?)',(str(path),offset,line,body,None if vector is None else vector.tobytes(),json.dumps(terms(relative+' '+body),ensure_ascii=False)))
            except Exception as error:
                # A failed replacement must never leave the old searchable content behind.
                self.db.execute('DELETE FROM docs WHERE path=?',(str(path),))
                self.db.execute('INSERT INTO docs VALUES(?,?,?,?,?,?,?,?)',(str(path),relative,item['bytes'],'retry:'+item['stamp'],'','skipped',str(error)[:160],0))
            self.db.commit()
            self.status('indexing',processed=files.index(item)+1,discovered=len(files),message='正在更新 '+relative)
        self.put('updated',time.time());self.put('limited',int(limited or bool(errors)));self.db.commit()
        return self.status(changed=changed,removed=removed,inventory=[{k:v for k,v in f.items() if k!='stamp'} for f in files],message='资料已自动更新' if changed or removed else '工作区索引已就绪')
    def retrieve(self,request):
        status=self.sync()
        prompt=str(request.get('query','')).strip()[:4000]
        query=query_text(prompt)
        prior=request.get('previous') or {}
        snapshots=prior.get('snapshots') or {}
        generation=hashlib.sha256(json.dumps(self.db.execute('SELECT path,sha,status FROM docs ORDER BY path').fetchall(),ensure_ascii=False).encode()).hexdigest()
        followup=request.get('continue_previous') is True or bool(re.search(r'^(那|那么|这些|这份|这笔|其中|继续|再|把|按|只|清除|取消|改成|换成|写成|总结)|筛选|分组|本轮|上轮|上一轮|这轮|上次|刚才|金额多少',prompt))
        from local_query import named_paths, wants_query
        named_all=named_paths(prompt,[r[0] for r in self.db.execute('SELECT path FROM docs')])
        continue_thread=(not named_all or named_all==set(snapshots)) and bool(snapshots) and followup and not re.search(r'重新检索|重新查找|另找|换个主题|换一批|在整个工作区|在工作区.*查找',prompt)
        pinned=set(snapshots) if continue_thread and request.get('continue_previous') is True else set()
        if pinned:
            for path in pinned:
                row=self.db.execute('SELECT status,chars FROM docs WHERE path=?',(path,)).fetchone()
                if not row or row[0]!='ready' or row[1]>=60000:raise ValueError('上轮资料范围中有文件已移除或未完整读取，请确认资料后再继续。')
        if continue_thread:
            unchanged=all(self.db.execute("SELECT sha FROM docs WHERE path=? AND status='ready'",(p,)).fetchone()==(sha,) for p,sha in snapshots.items())
            unchanged=unchanged and (bool(pinned) or (prior.get('retrieval') or {}).get('index_generation')==generation)
            if unchanged:
                result=dict(prior.get('retrieval') or {});result.update(paths=list(snapshots),snapshots=snapshots,reuse=True,refreshed=False)
                if pinned:result.update(index_generation=generation,scope_note=f'沿用上轮已核对范围（{len(pinned)} 份资料）。')
                result['status']=status;result['indexed_documents']=status['indexed'];return result
            query=str((prior.get('retrieval') or {}).get('query') or query)[:500]
        is_statistics=request.get('kind') in ('statistics','workflow') or bool(re.search(r'统计|合计|平均|求和|金额|报销|那.+呢|筛选|分组|算一下|算一算|总额|总共',prompt))
        universal=bool(re.search(r'(全部|所有)(资料|文档|文件)|整个工作区|全工作区|工作区.*全部',prompt)) and not continue_thread
        rows=self.db.execute("SELECT c.path,c.start,c.line,c.text,c.vector,c.terms,d.relative,d.sha FROM chunks c JOIN docs d ON d.path=c.path WHERE d.status='ready'").fetchall()
        # A document title explicitly named by the user is a scope instruction.
        # Match only names from this already-authorized index, never new paths.
        from local_query import named_paths, wants_query
        named=pinned or (named_paths(prompt,[row[0] for row in {r[0]:r for r in rows}.values()]) if not universal else set())
        is_statistics=is_statistics or wants_query(prompt)
        if universal:named_all=set()
        for path,relative,state,chars in self.db.execute('SELECT path,relative,status,chars FROM docs'):
            if path in named_all and (state!='ready' or chars>=60000):
                raise ValueError('指定文档未完整读取，请检查“我的资料”中的读取状态或缩小资料后再试。')
        if named:rows=[row for row in rows if row[0] in named]
        query_vector=self.embedder.encode([query],query=True)[0] if self.embedder.available else None
        qterms=terms(query);df=Counter()
        for row in rows:df.update(json.loads(row[5]).keys())
        scored=[]
        for path,start,line,text,blob,raw_terms,relative,sha in rows:
            counts=json.loads(raw_terms);lexical=sum((1+math.log((len(rows)+1)/(df[t]+1)))*min(2,counts.get(t,0)) for t in qterms)
            semantic=float(np.dot(query_vector,np.frombuffer(blob,dtype=np.float32))) if query_vector is not None and blob else 0.
            exact=query.casefold() in (relative+' '+text).casefold()
            relevant=semantic>=.43 or lexical>=2.0 or exact
            if relevant or universal or path in named:
                score=.75*max(0,semantic)+.25*(1-math.exp(-lexical/5))+(0.15 if exact else 0)
                scored.append({'path':path,'name':Path(path).name,'relative':relative,'start':start,'line':line,'snippet':text,'sha256':sha,'score':round(score,4),'semantic_score':round(semantic,4),'reason':'指定文档' if path in named else '名称或原文匹配' if exact else '语义相近 + 关键词' if lexical>0 and semantic>=.43 else '语义相近' if semantic>=.43 else '关键词匹配'})
        if scored and not is_statistics and not universal:
            best=max(h['semantic_score'] for h in scored)
            scored=[h for h in scored if h['reason']!='语义相近' or h['semantic_score']>=max(.43,best-.16)]
        scored.sort(key=lambda x:(-x['score'],x['relative'],x['start']))
        by_path={}
        for hit in scored:by_path.setdefault(hit['path'],hit)
        candidates=list(by_path.values())
        if universal:
            all_docs=self.db.execute("SELECT path,relative,sha FROM docs WHERE status='ready' ORDER BY relative").fetchall()
            for path,relative,sha in all_docs:
                if path not in by_path:candidates.append({'path':path,'name':Path(path).name,'relative':relative,'sha256':sha,'score':0,'semantic_score':0,'start':0,'line':1,'snippet':'','reason':'按要求纳入全部可读取资料'})
        if is_statistics and not named and (status['limited'] or status['skipped_count'] or status['truncated_count']):raise ValueError('工作区有未完整读取的资料，无法给出全范围统计。请在“我的资料”查看原因，改为手动范围后统计。')
        if (is_statistics or universal or pinned) and len(candidates)>40:raise ValueError(f'匹配到 {len(candidates)} 份资料，超过单次 40 份范围。请限定主题、日期或子文件夹，避免遗漏后仍给出总计。')
        selected=candidates[:40 if is_statistics or universal or pinned else 8]
        selected_paths=[h['path'] for h in selected];snapshots={h['path']:h['sha256'] for h in selected}
        hits=[]
        for best in selected:
            # One citation card per file; extra chunks still enter the generation context.
            own=[h for h in scored if h['path']==best['path']][:3]
            hits.extend(own or [best])
        return {'query':query,'workspace_root':str(self.root),'paths':selected_paths,'snapshots':snapshots,'hits':hits,'matched_documents':len(candidates),'indexed_documents':status['indexed'],'selected_documents':len(selected),
                'semantic':self.embedder.available,'embedding_key':self.embedder.key,'index_generation':generation,'reuse':False,'refreshed':continue_thread,'status':status,
                'scope_note':(f'已纳入工作区全部可读取资料（{len(selected)} 份）。' if universal else f'从 {status["indexed"]} 份资料中找到 {len(candidates)} 份候选，本次使用 {len(selected)} 份。'+('统计只覆盖这些资料，可展开核对范围。' if is_statistics else ''))}
    def close(self):self.db.close()

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--data',type=Path,required=True);parser.add_argument('--embedding',type=Path,required=True);parser.add_argument('--catalog',type=Path,required=True);parser.add_argument('--exclude',type=Path,action='append',default=[])
    args=parser.parse_args();probe=network_probe();emit('index_privacy',**probe)
    if not probe['blocked']:emit('index_error',message='索引进程未隔离，未读取工作区。');return 2
    embedder=None;index=None
    try:
        embedder=LocalEmbedder(args.embedding,args.catalog);index=WorkspaceIndex(args.workspace,args.data,embedder,emit,args.exclude)
        emit('index_ready',semantic=embedder.available,embedding_key=embedder.key)
        for line in sys.stdin:
            request={}
            try:
                request=json.loads(line);command=request.get('command')
                if command=='shutdown':break
                if command=='clear':
                    index.db.execute('DELETE FROM docs');index.db.commit();index.db.execute('VACUUM');index.db.commit();index.status('paused',message='本地索引已清空并暂停')
                elif command=='sync':index.sync(request.get('rebuild',False))
                elif command=='retrieve':emit('retrieval',request_id=request.get('request_id'),result=index.retrieve(request))
            except Exception as error:emit('index_error',request_id=request.get('request_id'),message=str(error)[:320])
    except Exception as error:emit('index_error',message='本地索引暂时无法启动：'+str(error)[:200]);return 2
    finally:
        if index:index.close()
        if embedder:embedder.close()
    return 0
if __name__=='__main__':raise SystemExit(main())
