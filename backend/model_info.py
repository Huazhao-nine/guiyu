"""Inspect a local MLX model without executing repository code or contacting a hub."""
import hashlib
import json
from pathlib import Path
import re

def describe_model(path):
    root=Path(path).expanduser().resolve(strict=True)
    if not root.is_dir():raise ValueError('请选择本地 MLX 模型文件夹。')
    def read(name):
        item=root/name
        if item.is_symlink() or item.stat().st_size>16*1024*1024:raise ValueError('模型配置异常。')
        return json.loads(item.read_text())
    config=read('config.json')
    kind=config.get('model_type','')
    if not re.fullmatch(r'[a-z0-9_]{1,60}',kind) or config.get('auto_map'):raise ValueError('当前只支持 MLX LM 内置架构，不运行模型目录中的自定义代码。')
    tokenizer=read('tokenizer_config.json')
    if tokenizer.get('auto_map'):raise ValueError('当前不支持自定义分词器代码。')
    weights=sorted(root.glob('*.safetensors'))
    if not weights:raise ValueError('没有找到 safetensors 权重；GGUF 需要其他运行后端。')
    if (root/'model.safetensors.index.json').exists():
        index=read('model.safetensors.index.json')
        for name in set(index.get('weight_map',{}).values()):
            if not isinstance(name,str) or Path(name).name!=name or not (root/name).is_file():raise ValueError('分片模型缺少权重文件。')
    fingerprint=hashlib.sha256()
    fingerprint.update(str(root).encode());fingerprint.update(json.dumps(config,sort_keys=True).encode())
    size=0
    for item in weights:
        if item.is_symlink() or not item.is_file():raise ValueError('请使用实际保存在模型目录中的权重文件。')
        info=item.stat();size+=info.st_size
        fingerprint.update(f'{item.name}:{info.st_size}:{info.st_mtime_ns}'.encode())
    bits=config.get('quantization',config.get('quantization_config',{})).get('bits')
    return {'key':fingerprint.hexdigest()[:24],'name':root.name,'architecture':kind,'bits':bits,'bytes':size,'path':str(root)}
