"""Ephemeral local redaction preview. No files, network, history or restoration map."""
from collections import Counter
import json
import re
import secrets
import sys

LABELS={'secret':'密钥与密码','email':'邮箱','phone':'手机号','identity':'身份证号',
        'bank':'银行卡号','custom':'自定义词','person':'姓名','address':'地址',
        'date':'私人日期','account':'账号','ip':'IP地址','url':'网址'}
MAX_TEXT=24000


def _list(value,limit=80):
    if not isinstance(value,list) or len(value)>limit or any(not isinstance(v,str) or not 1<=len(v)<=120 for v in value):
        raise ValueError('自定义条目数量或长度超出范围。')
    return list(dict.fromkeys(value))


def _luhn(text):
    digits=[int(c) for c in text if c.isdigit()]
    if len(set(digits))<3:return False
    return sum((n if i%2==0 else (2*n-9 if n>=5 else 2*n)) for i,n in enumerate(reversed(digits)))%10==0


def _identity(text):
    weights=(7,9,10,5,8,4,2,1,6,3,7,9,10,5,8,4,2)
    return '10X98765432'[sum(int(c)*w for c,w in zip(text[:17],weights))%11]==text[-1].upper()


def preview(request, *, detector=None):
    text=request.get('text','')
    if not isinstance(text,str) or len(text)>MAX_TEXT:raise ValueError('一次最多检查24,000个字符，请分段处理。')
    policy=request.get('policy',{})
    if not isinstance(policy,dict):raise ValueError('检查设置无效。')
    words=_list(policy.get('words',[]));allow={v.casefold() for v in _list(policy.get('allow',[]))}
    prefixes=_list(policy.get('prefixes',[]),16)
    if any(not 2<=len(p)<=48 or re.search(r'\s',p) for p in prefixes):raise ValueError('密钥前缀应为2至48个非空白字符。')
    categories=policy.get('categories',{})
    if not isinstance(categories,dict) or any(k not in LABELS or type(v) is not bool for k,v in categories.items()):raise ValueError('分类设置无效。')
    def enabled(kind):
        base=policy.get('secrets',True) is True if kind=='secret' else policy.get('personal',True) is True
        return categories.get(kind,base if kind not in ('date','ip','url','custom') else kind=='custom')
    placeholders=[m.span() for m in re.finditer(r'⟪(?:'+ '|'.join(map(re.escape,LABELS.values())) +r')_[a-f0-9]{8}_[1-9][0-9]*⟫',text)]
    spans=[]
    def add(start,end,kind):
        if any(a<=start and end<=b for a,b in placeholders):return
        if enabled(kind) and start<end and text[start:end].casefold() not in allow:spans.append((start,end,kind))
    if policy.get('secrets',True) is True:
        for m in re.finditer(r'-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----[\s\S]*?-----END (?:[A-Z ]*PRIVATE KEY)-----',text):add(*m.span(),'secret')
        for m in re.finditer(r'(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret|密码|口令)\s*[=:：]\s*(?:"([^"\n]+)"|\x27([^\x27\n]+)\x27|([^\s,，;；。！？]+))',text):
            i=next(i for i in (1,2,3) if m.group(i) is not None);add(*m.span(i),'secret')
        for m in re.finditer(r'(?<![A-Za-z0-9])(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})(?![A-Za-z0-9_-])',text):add(*m.span(),'secret')
        for prefix in prefixes:
            for m in re.finditer(re.escape(prefix)+r'[^\s"\x27,，;；。！？<>]{1,256}',text):add(*m.span(),'secret')
    if any(enabled(k) for k in ('email','phone','identity','bank')):
        for m in re.finditer(r'(?<![A-Za-z0-9_.+-])[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+',text):add(*m.span(),'email')
        for m in re.finditer(r'(?<![0-9])(?:\+?86[ -]?)?1[3-9][0-9]{9}(?![0-9])',text):add(*m.span(),'phone')
        for m in re.finditer(r'(?<![0-9])[1-9][0-9]{16}[0-9Xx](?![0-9])',text):
            if _identity(m[0]):add(*m.span(),'identity')
        for m in re.finditer(r'(?<![0-9])[0-9]{16,19}(?![0-9])',text):
            context=re.split(r'[，,。;；\n]',text[max(0,m.start()-18):m.start()])[-1]
            if _luhn(m[0]) and re.search(r'银行卡|卡号|银行账号|信用卡',context):add(*m.span(),'bank')
    for word in words:
        for m in re.finditer(re.escape(word),text,re.I):add(*m.span(),'custom')
    model_id=request.get('detector','rules')
    info={'id':'rules','name':'本地规则'}
    if model_id!='rules':
        if model_id not in ('astrlink-guard','openai-privacy-filter'):raise ValueError('未知识别组件。')
        if detector is None:
            from pathlib import Path
            # -I intentionally removes script dir; add only this trusted bundle directory.
            sys.path.insert(0,str(Path(__file__).resolve().parent))
            from privacy_models import detect
            detector=detect
        found,info=detector(text,model_id)
        # Protect office currency amounts and dates from model false positives.
        # Explicit secret rules/custom words still take precedence.
        protected=[m.span() for m in re.finditer(r'(?:[¥￥$]\s*[0-9][0-9,]*(?:\.[0-9]+)?|[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:万元|元|美元|人民币))',text)]
        protected += [m.span() for m in re.finditer(r'(?i)(?:活动|项目|总|本次)?(?:金额|预算|合计|总计|余额|单价|实付|amount|price)\s*[=:：]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)',text)]
        if not enabled('date'):
            protected += [m.span() for m in re.finditer(r'(?:[12][0-9]{3}[-/.年][0-9]{1,2}[-/.月][0-9]{1,2}日?|[0-9]{1,2}月[0-9]{1,2}日)',text)]
        for start,end,kind in found:
            if kind not in LABELS or type(start) is not int or type(end) is not int or not 0<=start<end<=len(text):raise ValueError('模型识别位置无效。')
            # Allowlist compares whole model detection, never fragments after protection.
            if text[start:end].casefold() in allow:continue
            pieces=[(start,end)]
            for a,b in placeholders:
                pieces=[part for s,e in pieces for part in ([(s,min(a,e))] if s<a else [])+([(max(b,s),e)] if b<e else []) if part[0]<part[1]]
            if kind!='secret':
                for a,b in protected:
                    pieces=[part for s,e in pieces for part in ([(s,min(a,e))] if s<a else [])+([(max(b,s),e)] if b<e else []) if part[0]<part[1]]
            for s,e in pieces:add(s,e,kind)
    # Mask the union of overlapping hits; nested/partly overlapping secrets
    # cannot survive merely because another detector selected the short span.
    merged=[]
    for start,end,kind in sorted(spans,key=lambda s:(s[0],-s[1])):
        if merged and start<merged[-1][1]:
            a,b,k=merged[-1];merged[-1]=(a,max(b,end),'secret' if 'secret' in (k,kind) else k)
        elif not merged or (start,end)!=merged[-1][:2]:merged.append((start,end,kind))
    nonce=secrets.token_hex(4);tokens={};counts=Counter();pieces=[];cursor=0;findings=[]
    for start,end,kind in merged:
        key=(kind,text[start:end].casefold())
        if key not in tokens:tokens[key]=f'⟪{LABELS[kind]}_{nonce}_{len(tokens)+1}⟫'
        token=tokens[key];pieces.extend((text[cursor:start],token));cursor=end;counts[kind]+=1
        finding={'kind':kind,'label':LABELS[kind],'replacement':token,'characters':end-start}
        if request.get('include_positions') is True:finding.update(start=start,end=end)
        findings.append(finding)
    pieces.append(text[cursor:])
    return {'text':''.join(pieces),'count':len(merged),'counts':{LABELS[k]:v for k,v in counts.items()},
            'findings':findings,'detector':info['name'],'component':info,'local_only':True,'saved':False,
            'scope':'模型按分类识别，规则补充格式明确的敏感值。金额与普通日期默认保留；分享前请核对预览。'}


if __name__=='__main__':
    try:
        # Bound bytes before JSON decoding as well as Unicode characters.
        line=sys.stdin.buffer.readline(160001)
        if len(line)>160000:raise ValueError('输入过长，请分段处理。')
        print(json.dumps(preview(json.loads(line)),ensure_ascii=False))
    except Exception:
        print(json.dumps({'error':'本次检查未完成，请检查输入长度与设置后重试。'},ensure_ascii=False))
        raise SystemExit(1)
