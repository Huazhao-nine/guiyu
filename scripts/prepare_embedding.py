"""Task-free development preparation. The app uses the same pinned catalog in its downloader."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.request
root=Path(__file__).resolve().parents[1]
model=next(m for m in json.loads((root/'packaging/model-catalog.json').read_text()) if m['id']=='bge-small-zh-v1.5')
base=Path.home()/'Library/Application Support/GuiyuModels'
target=base/'Installed'/model['id']
if target.exists():print('EMBEDDING_ALREADY_INSTALLED');raise SystemExit(0)
stage=base/'DeveloperPreparation'/model['id'];stage.mkdir(parents=True,exist_ok=True,mode=0o700)
for file in model['files']:
 path=stage/file['name']
 if path.is_symlink():raise RuntimeError('Unexpected symlink')
 if path.exists() and path.stat().st_size==file['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==file['sha256']:continue
 count=path.stat().st_size if path.exists() else 0
 if count>file['bytes']:path.unlink();count=0
 for attempt in range(5):
  if count==file['bytes']:break
  headers={'User-Agent':'Guiyu-Embedding-Preparation/0.5','Accept-Encoding':'identity'}
  if count:headers['Range']=f'bytes={count}-'
  request=urllib.request.Request(f"https://huggingface.co/{model['repository']}/resolve/{model['revision']}/{file['name']}?download=true",headers=headers)
  try:
   with urllib.request.urlopen(request,timeout=45) as response:
    if response.status==200:count=0
    elif response.status==206:
     assert response.headers.get('Content-Range','').startswith(f'bytes {count}-')
    else:raise RuntimeError('Unexpected download response')
    fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW|(os.O_TRUNC if count==0 else os.O_APPEND),0o600)
    with os.fdopen(fd,'wb') as out:
     while chunk:=response.read(1024*1024):
      count+=len(chunk)
      if count>file['bytes']:raise RuntimeError('Unexpected file length')
      out.write(chunk)
  except (OSError,TimeoutError) as error:print('RESUMABLE_CONNECTION_INTERRUPTED',type(error).__name__,flush=True)
  print('PREPARATION_PROGRESS',count,file['bytes'],flush=True)
 if count!=file['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=file['sha256']:raise RuntimeError('Model checksum mismatch')
 print(file['name'],count,flush=True)
(stage/'guiyu-install.json').write_text(json.dumps({'repository':model['repository'],'revision':model['revision']}))
target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
shutil.move(stage,target)
print('BGE_MODEL_PREPARED',sum(f['bytes'] for f in model['files']),flush=True)
