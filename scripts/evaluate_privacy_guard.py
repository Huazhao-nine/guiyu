"""Opt-in pinned AstrLink Guard evaluation; fictional text only, CPU, offline inference.

--download fetches fixed public model files into qa/private, never user content.
The ordinary invocation enters a deny-network sandbox before loading ONNX.
This research adapter is not a production detector or a chat-model replacement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'qa/private/v0.13/privacy-guard'
REPO='QuantumNous/astrlink-guard'
REVISION='v0.1.3'
PINNED={'model_int8.onnx':'0a070d3113615e33ba3b84d6bd486f663a377c04c4b056e7381732179f51832a',
        'model_int8.onnx_data':'0ba34216ceead01e0ae2dfd8e46d52b67e7aee80b04f722d9b758613a91c0067',
        'tokenizer.json':'0cf3b235ef125658015a6c8026a5fe6f28088bf825101a990ec18a10200feef4',
        'config.json':'2c20003590d642e273c03c4c7c82d9849fa75f64bf29a71ec0a0c9a20ba4a150'}
CASES=[
 {'id':'zh_contact','text':'请联系张伟，电话13812345678，邮箱zhangwei@example.com。收货地址北京市海淀区中关村大街27号。','sensitive':['张伟','13812345678','zhangwei@example.com','北京市海淀区中关村大街27号']},
 {'id':'en_secret','text':'Contact Jane Doe at jane.doe@example.org. Server 10.0.3.17, api_key = "q7Vt2LmX9pRk4sWz8bNc3yHd6fJg1aE5"','sensitive':['Jane Doe','jane.doe@example.org','10.0.3.17','q7Vt2LmX9pRk4sWz8bNc3yHd6fJg1aE5']},
 {'id':'office_numbers','text':'订单号202409301234567890，预算3600元，场地1200元，物料35元买24份，交通480元。活动日期2026-11-06，提前7天确认。','sensitive':[]},
 {'id':'benign_code','text':'version = "0.13.0"\ntimeout = 120\nrequest_id = "c34dbe91-2345-45ef-9000-fb98219b0312"\namount = 1280.50','sensitive':[]},
 {'id':'personal_dates','text':'王芳的生日是1992年7月8日，护照有效期至2031-05-01。','sensitive':['王芳','1992年7月8日','2031-05-01']},
 {'id':'long_boundary','text':'工作记录，不含个人信息。'*180+'联系人张伟，邮箱zhangwei@example.com。'+'普通工作记录。'*100,'sensitive':['张伟','zhangwei@example.com']},
]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--download',action='store_true');p.add_argument('--isolated',action='store_true');a=p.parse_args()
    if a.download:
        PRIVATE.mkdir(parents=True,exist_ok=True)
        with urllib.request.urlopen(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}',timeout=30) as r:commit=json.load(r)['sha']
        if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit):raise ValueError('Invalid revision')
        for name,expected in PINNED.items():
            path=PRIVATE/name
            if path.is_file() and digest(path)==expected:continue
            with urllib.request.urlopen(f'https://huggingface.co/{REPO}/resolve/{commit}/int8/{name}',timeout=60) as r:data=r.read(50_000_001)
            if len(data)>50_000_000 or hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Pinned model hash mismatch: '+name)
            path.write_bytes(data)
        (PRIVATE/'download.json').write_text(json.dumps({'repository':REPO,'revision':REVISION,'commit':commit,'files':PINNED},indent=2)+'\n')
        print('Downloaded verified public INT8 model files; no text was sent.');return
    if not a.isolated:
        raise SystemExit(subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',sys.executable,str(Path(__file__).resolve()),'--isolated']).returncode)
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer
    sys.path.insert(0,str(ROOT/'backend'));import worker as core
    assert core.network_probe()['blocked']
    assert all((PRIVATE/n).is_file() and digest(PRIVATE/n)==h for n,h in PINNED.items())
    config=json.loads((PRIVATE/'config.json').read_text());labels=config['id2label']
    tokenizer=Tokenizer.from_file(str(PRIVATE/'tokenizer.json'));tokenizer.no_truncation();tokenizer.no_padding()
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    started=time.perf_counter();sess=ort.InferenceSession(str(PRIVATE/'model_int8.onnx'),sess_options=options,providers=['CPUExecutionProvider']);load=time.perf_counter()-started
    rows=[]
    for case in CASES:
        enc=tokenizer.encode(case['text'],add_special_tokens=False);spans=[];started=time.perf_counter();windows=0
        for begin in range(0,len(enc.ids),382):
            ids=[0]+enc.ids[begin:begin+510]+[2];offsets=[(0,0)]+enc.offsets[begin:begin+510]+[(0,0)]
            array=np.array([ids],dtype=np.int64);feed={'input_ids':array,'attention_mask':np.ones_like(array),'token_type_ids':np.zeros_like(array)}
            logits=sess.run(['logits'],feed)[0][0];probs=np.exp(logits-logits.max(-1,keepdims=True));probs/=probs.sum(-1,keepdims=True);current=None
            for tag_id,score,(start,end) in zip(probs.argmax(-1),probs.max(-1),offsets):
                tag,_,kind=labels[str(int(tag_id))].partition('-')
                if start==end or tag=='O' or float(score)<.8:current=None;continue
                if tag=='B' or current is None or current['kind']!=kind or start>current['end']+1:
                    current={'kind':kind,'start':start,'end':end};spans.append(current)
                else:current['end']=end
            windows+=1
            if begin+510>=len(enc.ids):break
        spans=[dict(s,text=case['text'][s['start']:s['end']]) for s in spans]
        covered={i for s in spans for i in range(s['start'],s['end'])}
        hits={value:all(i in covered for i in range(case['text'].index(value),case['text'].index(value)+len(value))) for value in case['sensitive']}
        rows.append({'id':case['id'],'windows':windows,'characters':len(case['text']),'seconds':round(time.perf_counter()-started,4),'expected_span_coverage':hits,'unexpected_detection_on_empty_case':bool(spans) if not case['sensitive'] else None,'detections':spans})
    r={'date':'2026-10-28','repository':REPO,'revision':REVISION,'pinned_files':PINNED,'network_denied':True,'provider':'CPUExecutionProvider','onnxruntime':ort.__version__,'load_seconds':round(load,4),'process_peak_rss_gb':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,3),'cases':rows,'limitations':['Six fictional developer cases; not a held-out benchmark or privacy guarantee.','Adapter uses documented approximate argmax BIO decoding, not vendor exact cleanup/decoding.','Threshold0.8; overlapping510-token windows with128-token overlap.','Research adapter only; model not installed in normal app, not a UI download or production integration.']}
    (ROOT/'qa/v0.13-privacy-guard-evaluation.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(r,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
