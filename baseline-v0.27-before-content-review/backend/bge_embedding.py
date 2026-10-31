"""Fixed BGE-small Chinese encoder in MLX; no hub client or repository code execution.

BERT post-normalization, CLS pooling and L2 normalization follow the model card.
Weights retain BAAI's MIT license. All inference is under the index worker's deny-network policy.
"""
import hashlib
import json
from pathlib import Path
import numpy as np

class LocalEmbedder:
    def __init__(self,model_path,catalog_path):
        self.root=Path(model_path);self.available=False;self.key='bge-small-zh-v1.5-missing';self.dimension=512
        if not self.root.exists():return
        catalog=json.loads(Path(catalog_path).read_text())
        manifest=next(m for m in catalog if m['id']=='bge-small-zh-v1.5' and m.get('purpose')=='embedding')
        for file in manifest['files']:
            p=self.root/file['name']
            if p.is_symlink() or p.stat().st_size!=file['bytes']:raise ValueError('中文语义模型不完整，请从模型库重新准备。')
            h=hashlib.sha256()
            with p.open('rb') as f:
                for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
            if h.hexdigest()!=file['sha256']:raise ValueError('中文语义模型校验失败，未读取工作区。')
        import mlx.core as mx
        import mlx.nn as nn
        from tokenizers import Tokenizer
        self.mx=mx;self.nn=nn
        self.config=json.loads((self.root/'config.json').read_text())
        c=self.config
        if c.get('model_type')!='bert' or c.get('hidden_act')!='gelu' or c.get('auto_map') or c.get('hidden_size')!=512:raise ValueError('不支持这个语义模型配置。')
        self.weights=mx.load(str(self.root/'model.safetensors'))
        # Only tensor data is read; no Python files or custom tokenizer code are imported.
        if 'bert.embeddings.word_embeddings.weight' in self.weights:self.weights={k.removeprefix('bert.'):v for k,v in self.weights.items()}
        self.tokenizer=Tokenizer.from_file(str(self.root/'tokenizer.json'))
        self.tokenizer.enable_padding(pad_id=c.get('pad_token_id',0),pad_token='[PAD]')
        self.tokenizer.enable_truncation(max_length=512)
        self.dimension=c['hidden_size'];self.key='BAAI/bge-small-zh-v1.5@'+manifest['revision']+'|mlx-cls-v2';self.available=True
    def linear(self,x,key):return x@self.weights[key+'.weight'].T+self.weights[key+'.bias']
    def norm(self,x,key):return self.mx.fast.layer_norm(x,self.weights[key+'.weight'],self.weights[key+'.bias'],self.config.get('layer_norm_eps',1e-12))
    def forward(self,ids,mask):
        mx=self.mx;c=self.config;w=self.weights;batch,length=ids.shape
        x=w['embeddings.word_embeddings.weight'][ids]+w['embeddings.position_embeddings.weight'][mx.arange(length)][None,:,:]+w['embeddings.token_type_embeddings.weight'][0]
        x=self.norm(x,'embeddings.LayerNorm')
        heads=c['num_attention_heads'];dim=c['hidden_size']//heads
        attention_mask=mx.where(mask[:,None,None,:]>0,0.,-1e9)
        for layer in range(c['num_hidden_layers']):
            prefix=f'encoder.layer.{layer}'
            q,k,v=[self.linear(x,prefix+'.attention.self.'+name).reshape(batch,length,heads,dim).transpose(0,2,1,3) for name in ['query','key','value']]
            attended=mx.fast.scaled_dot_product_attention(q,k,v,scale=dim**-.5,mask=attention_mask).transpose(0,2,1,3).reshape(batch,length,c['hidden_size'])
            x=self.norm(x+self.linear(attended,prefix+'.attention.output.dense'),prefix+'.attention.output.LayerNorm')
            hidden=self.nn.gelu(self.linear(x,prefix+'.intermediate.dense'))
            x=self.norm(x+self.linear(hidden,prefix+'.output.dense'),prefix+'.output.LayerNorm')
        vectors=x[:,0,:]
        vectors=vectors/mx.maximum(mx.linalg.norm(vectors,axis=-1,keepdims=True),1e-12)
        mx.eval(vectors)
        return np.array(vectors,dtype=np.float32)
    def encode(self,texts,query=False):
        if not self.available:return [None]*len(texts)
        values=[]
        for start in range(0,len(texts),16):
            batch=texts[start:start+16]
            # BGE v1.5 supports instruction-free queries; keep short Chinese task phrases intact.
            encodings=self.tokenizer.encode_batch(batch)
            ids=self.mx.array([e.ids for e in encodings]);mask=self.mx.array([e.attention_mask for e in encodings])
            vectors=self.forward(ids,mask)
            if vectors.shape!=(len(batch),self.dimension) or not np.isfinite(vectors).all():raise ValueError('语义向量异常。')
            values.extend(vectors)
        return values
    def close(self):pass
