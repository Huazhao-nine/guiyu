"""Prepare a chosen pinned model separately from the offline document application."""
import argparse
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from model_info import describe_model

def main():
    parser=argparse.ArgumentParser(description='准备其他本地 MLX 模型，不读取归屿任务资料。')
    parser.add_argument('--repository',required=True,help='模型仓库 owner/name')
    parser.add_argument('--revision',required=True,help='固定的40位提交 SHA')
    parser.add_argument('--destination',type=Path,required=True,help='新的独立模型目录')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',args.repository) or not re.fullmatch(r'[0-9a-f]{40}',args.revision):parser.error('请提供模型仓库和固定的40位提交。')
    target=args.destination.expanduser().resolve()
    private=Path.home()/'Library/Application Support/Guiyu'
    if target==private or private in target.parents or target.exists():parser.error('请选择尚不存在的独立模型目录，不能使用归屿的记录目录。')
    from huggingface_hub import snapshot_download
    target.mkdir(parents=True,mode=0o700)
    print('只下载选定模型，不读取或上传任务资料。')
    snapshot_download(repo_id=args.repository,revision=args.revision,local_dir=target,token=False,allow_patterns=['*.safetensors','*.json','*.model','*.txt','*.tiktoken','*.jinja'])
    info=describe_model(target)
    print(f'已准备 {info["architecture"]} / {info["bytes"]:,} 字节。可在归屿的本地模型库添加此目录。')

if __name__=='__main__':main()
