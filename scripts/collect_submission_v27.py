"""Copy only fictional submission task artifacts into an inspectable public gallery."""
import hashlib,html,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    run=ROOT/'qa/private/v0.27/20261031T104000-eec503';report=json.loads((ROOT/'qa/v0.27/reports/delivery-final-20261031T104000-eec503.json').read_text());suite=json.loads((ROOT/'fixtures/submission_v27/tasks.json').read_text());out=ROOT/'qa/v0.27/examples';out.mkdir(exist_ok=True)
    assert report['passed']==report['total']==5 and report['backend_unchanged']
    title={'transfer_support':'工作簿汇总与Word','transfer_top_followup':'简短追问只保留第一名','transfer_office_notice':'最新通知费用与日期','fresh_training_notice':'新培训资料的迁移验证','local_share_copy':'本地脱敏分享副本'}
    items=[]
    for row in report['cases']:
        result=json.loads((run/(row['id']+'-result.json')).read_text());dest=out/row['id'];dest.mkdir(exist_ok=True);artifacts=[]
        for a in result.get('artifacts',[]):
            p=Path(a['path']);assert p.is_file() and not p.is_symlink() and p.resolve().is_relative_to((run/'data/Outputs').resolve())
            assert a['type'] in ('xlsx','csv','docx','md','txt');target=dest/p.name
            if target.exists():assert sha(target)==sha(p),'Preserve recorded outputs.'
            else:shutil.copy2(p,target)
            artifacts.append({'name':target.name,'type':a['type'],'path':str(target.relative_to(ROOT)),'sha256':sha(target)})
        (dest/'预览.txt').write_text(result['text'])
        items.append({'id':row['id'],'title':title[row['id']],'prompt':row['prompt'],'seconds':row['seconds'],'checks':row['checks'],'artifacts':artifacts,'previews':[{'name':q.name,'type':'pdf','path':str(q.relative_to(ROOT)),'sha256':sha(q)} for q in dest.glob('*.pdf')],'source_names':row.get('source_names',[])})
    (out/'manifest.json').write_text(json.dumps({'version':'0.27.0','origin':'Actual local model outputs on fictional frozen inputs, preserved without regeneration. Not live GUI execution.','items':items},ensure_ascii=False,indent=2)+'\n')
    lines=['# 归屿0.27实际成果','\n以下文件来自真实本地35B模型和工具执行，使用虚构资料。它们是已生成成果，不是实时GUI演示，也不是手工填写的预期答案。模型任务禁网，原始资料哈希未变。首次3/5和复测日期评分纠正见上级证据索引。\n']
    cards=[]
    for c in items:
        lines+=['## '+c['title'],'\n'+c['prompt'],f"\n任务耗时 {c['seconds']} 秒。\n"]
        links=[]
        for a in c['artifacts']+c['previews']:
            path=Path(a['path']).relative_to(out.relative_to(ROOT)).as_posix();lines.append(f"- [{a['name']}]({path})");links.append(f'<a href="{html.escape(path,quote=True)}">{html.escape(a["name"])}</a>')
        cards.append(f'<article><span class="eyebrow">已通过交付检查 · {c["seconds"]} 秒</span><h2>{html.escape(c["title"])}</h2><p>{html.escape(c["prompt"])}</p><nav>{"".join(links)}</nav></article>')
    (out/'README.md').write_text('\n\n'.join(lines)+'\n')
    css='''body{margin:0;background:#f6f4ec;color:#163b37;font:16px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1000px;margin:64px auto;padding:0 30px}header{padding-bottom:35px;border-bottom:1px solid #cbd4c9}h1{font-size:46px;margin:10px 0}h2{font-size:25px;margin:8px 0}p{color:#4b625b;max-width:850px}article{padding:32px 0;border-bottom:1px solid #cbd4c9}.eyebrow{font-size:13px;color:#637f72}nav{display:flex;flex-wrap:wrap;gap:10px}a{color:#23675b;padding:7px 14px;background:#e2eade;border-radius:7px;text-decoration:none}a:hover{background:#d5e2d2}footer{font-size:13px;color:#697b74;margin-top:40px}'''
    (out/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>归屿 0.27 实际成果</title><style>'+css+'</style><main><header><span class="eyebrow">归屿 Guiyu · 32GB 本地版 · 0.27</span><h1>一份目标，一份可检查的成果。</h1><p>以下为本机真实生成的成果，使用虚构资料。点击文件即可查看表格、文稿和脱敏副本。此页是结果目录，不是原生应用截图或实时执行。原始输入与检查报告随源码包提供。</p></header>'+''.join(cards)+'<footer>本地处理，无云端回退。修改原文件需预览及独立确认。有限开发验证不能代表任意新资料成功率。</footer></main></html>')
    print(len(items),'goals',sum(len(x['artifacts']) for x in items),'artifacts')
if __name__=='__main__':main()
