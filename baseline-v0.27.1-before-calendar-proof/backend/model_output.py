"""Render final model content without exposing or parsing reasoning channels."""
import re


def visible_text(raw,architecture):
    text=raw.strip()
    if architecture=='gpt_oss':
        markers=('<|channel|>final<|message|>','final<|message|>')
        marker=next((m for m in markers if m in text),None)
        if not marker:raise ValueError('本地模型没有返回完整正文，请精简要求后重试。')
        text=text.rsplit(marker,1)[1]
        text=re.split(r'<\|return\|>|<\|end\|>|<\|start\|>',text)[0]
    if text.startswith('<think>'):
        if '</think>' not in text:raise ValueError('本地模型没有返回完整正文，请精简要求后重试。')
        text=text.split('</think>',1)[1]
    if text.lstrip().startswith('<|channel>thought'):
        if '<channel|>' not in text:raise ValueError('本地模型没有返回完整正文，请精简要求后重试。')
        text=text.split('<channel|>',1)[1]
    text=re.sub(r'^(?:<\|channel>final\s*|<\|message\|>)','',text.strip())
    text=re.sub(r'(?:<turn\|>|<\|im_end\|>|<\|endoftext\|>)\s*$','',text.strip())
    if not text.strip():raise ValueError('本地模型没有返回完整正文，请精简要求后重试。')
    return text.strip()
