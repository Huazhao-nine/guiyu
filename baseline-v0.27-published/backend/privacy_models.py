"""Pinned, on-demand CPU privacy components. No network client or remote code.

OpenAI BIOES constraints follow openai/privacy-filter opf/_core/decoding.py
(Apache-2.0), default calibration. NumPy implementation; overlapping windows
are a Guiyu memory bound, not the upstream full-context runtime.
AstrLink uses offset-consistent BIO with min span score .8 and local URL/IP
boundary normalization. This adapter does not claim vendor decoder parity.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile

IDS={'astrlink-guard','openai-privacy-filter'}
KINDS={'private_person':'person','private_address':'address','private_email':'email','email':'email',
       'private_phone':'phone','phone':'phone','private_date':'date','account_number':'account',
       'account':'account','payment_card':'bank','private_url':'url','url':'url',
       'ip_address':'ip','common_secret':'secret','secret':'secret'}


def catalog():
    here=Path(__file__).resolve().parent
    path=here/'model-catalog.json'
    if not path.is_file():path=here.parent/'packaging/model-catalog.json'
    return {m['id']:m for m in json.loads(path.read_text()) if m.get('purpose')=='privacy'}


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()


def verify_component(model_id,root=None):
    if model_id not in IDS:raise ValueError('未知隐私组件。')
    item=catalog()[model_id]
    root=Path(root) if root is not None else Path.home()/'Library/Application Support/GuiyuModels'
    folder=root/'Installed'/model_id
    if any(p.is_symlink() for p in [folder,*folder.parents]):raise ValueError('组件目录包含链接。')
    marker=json.loads((folder/'guiyu-install.json').read_text())
    if marker.get('revision')!=item['revision']:raise ValueError('组件版本不匹配。')
    for f in item['files']:
        path=folder/f['name']
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=f['bytes'] or digest(path)!=f['sha256']:
            raise ValueError('组件文件校验失败，请重新下载。')
    return item,folder


@contextmanager
def runtime(folder,item):
    # Extract only verified bundled runtime wheel; no pip, subprocess or installers.
    wheel=next(f for f in item['files'] if f['name'].startswith('onnxruntime-') and f['name'].endswith('.whl'))
    if sys.version_info[:2]!=(3,13):raise ValueError('请使用归屿自带的 Python 3.13 运行环境。')
    with tempfile.TemporaryDirectory(prefix='guiyu-privacy-runtime-') as tmp:
        with zipfile.ZipFile(folder/wheel['name']) as archive:
            total=0
            for f in archive.infolist():
                parts=Path(f.filename).parts;total+=f.file_size
                if not parts or '..' in parts or Path(f.filename).is_absolute() or (f.external_attr>>16)&0o170000==0o120000 or total>180_000_000:
                    raise ValueError('运行组件结构无效。')
                if parts[0]=='onnxruntime':archive.extract(f,tmp)
        sys.path.insert(0,tmp)
        try:
            import onnxruntime as ort
            yield ort
        finally:sys.path.remove(tmp)


def viterbi(logits,labels,biases):
    import numpy as np
    tags=[('O','O') if labels[str(i)]=='O' else tuple(labels[str(i)].split('-',1)) for i in range(len(labels))]
    n=len(tags);transition=np.full((n,n),-1e9,dtype=np.float32)
    for i,(a,kind) in enumerate(tags):
        for j,(b,nextkind) in enumerate(tags):
            if a in ('O','E','S') and b in ('O','B','S'):
                key=('background_stay' if b=='O' else 'background_to_start') if a=='O' else ('end_to_background' if b=='O' else 'end_to_start')
            elif a in ('B','I') and kind==nextkind and b in ('I','E'):key='inside_to_continue' if b=='I' else 'inside_to_end'
            else:continue
            transition[i,j]=biases['transition_bias_'+key]
    start=np.array([0 if a in ('O','B','S') else -1e9 for a,_ in tags],dtype=np.float32)
    end=np.array([0 if a in ('O','E','S') else -1e9 for a,_ in tags],dtype=np.float32)
    if len(logits)==0:return []
    scores=logits[0]+start;back=[]
    for row in logits[1:]:
        matrix=scores[:,None]+transition;paths=matrix.argmax(axis=0);back.append(paths);scores=matrix[paths,np.arange(n)]+row
    last=int((scores+end).argmax());path=[last]
    for row in reversed(back):last=int(row[last]);path.append(last)
    return list(reversed(path))


def token_spans(text,offsets,tag_ids,scores,labels,*,bioes=False):
    spans=[];current=None
    for (start,end),index,score in zip(offsets,tag_ids,scores):
        if start==end:continue
        tag=labels[str(int(index))];boundary,_,kind=tag.partition('-')
        if tag=='O':current=None;continue
        if not (0<=start<end<=len(text)):raise ValueError('识别位置无效。')
        # Only join continuous character coverage (whitespace gaps are permitted).
        adjacent=current is not None and start<=current[1] or current is not None and text[current[1]:start].isspace()
        if boundary in ('B','S') or current is None or current[2]!=kind or not adjacent:
            current=[start,end,kind,float(score)];spans.append(current)
        else:current[1]=max(current[1],end);current[3]=min(current[3],float(score))
        if bioes and boundary in ('S','E'):current=None
    return [s for s in spans if bioes or s[3]>=.8]


def normalize_span(text,start,end,kind):
    while start<end and text[start].isspace():start+=1
    while end>start and text[end-1].isspace():end-=1
    if kind in ('ip','url'):
        pattern=r'(?:[0-9]{1,3}\.){3}[0-9]{1,3}' if kind=='ip' else r'(?:https?://|www\.)[^\s<>"\x27，。；！？]+'
        for m in re.finditer(pattern,text):
            if m.start()<end and m.end()>start:start,end=m.span();break
    return start,end,kind


def detect(text,model_id,*,root=None):
    item,folder=verify_component(model_id,root)
    # One CPU detector across all windows/processes; lock stores no sensitive data.
    lock_path=folder.parent.parent/'privacy-detection.lock'
    with os.fdopen(os.open(lock_path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with runtime(folder,item) as ort:
            import numpy as np
            from tokenizers import Tokenizer
            tok=Tokenizer.from_file(str(folder/'tokenizer.json'));tok.no_padding();tok.no_truncation()
            cfg=json.loads((folder/'config.json').read_text());labels=cfg['id2label'];enc=tok.encode(text,add_special_tokens=False)
            options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1;options.enable_mem_pattern=False
            options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            openai=model_id=='openai-privacy-filter'
            name='model_quantized.onnx' if openai else 'model_int8.onnx'
            sess=ort.InferenceSession(str(folder/name),sess_options=options,providers=['CPUExecutionProvider'])
            width,overlap=(1024,256) if openai else (510,128)
            if len(enc.ids)>64000:raise ValueError('分词数量过多，请分段检查。')
            biases=json.loads((folder/'viterbi_calibration.json').read_text())['operating_points']['default']['biases'] if openai else None
            spans=[];windows=0
            for begin in range(0,len(enc.ids),width-overlap):
                ids=enc.ids[begin:begin+width];offsets=enc.offsets[begin:begin+width]
                if not openai:ids=[0]+ids+[2];offsets=[(0,0)]+offsets+[(0,0)]
                array=np.array([ids],dtype=np.int64)
                feeds={'input_ids':array,'attention_mask':np.ones_like(array),'token_type_ids':np.zeros_like(array),'position_ids':np.arange(len(ids),dtype=np.int64)[None,:]}
                logits=sess.run(None,{f.name:feeds[f.name] for f in sess.get_inputs()})[0][0]
                if not np.isfinite(logits).all():raise ValueError('模型返回无效结果。')
                exp=np.exp(logits-logits.max(-1,keepdims=True));probs=exp/exp.sum(-1,keepdims=True)
                path=viterbi(logits,labels,biases) if openai else probs.argmax(-1)
                scores=[probs[i,t] for i,t in enumerate(path)]
                for s,e,kind,score in token_spans(text,offsets,path,scores,labels,bioes=openai):
                    mapped=KINDS.get(kind)
                    if mapped:spans.append(normalize_span(text,s,e,mapped))
                windows+=1
                if begin+width>=len(enc.ids):break
            return spans,{'id':model_id,'name':item['name'],'revision':item['revision'],'provider':'CPUExecutionProvider','windows':windows,'window_tokens':width,'overlap_tokens':overlap,'decoder':'BIOES Viterbi default' if openai else 'Guiyu offset-consistent BIO .8'}
