"""Restore the hash-pinned public document used only in the v0.26 audit.

No app data, model, API, credentials or conversation is used. The original
public document is not redistributed in the source or demo archives.
"""
import argparse,hashlib
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
URL='https://www.naujsc.edu.cn/_upload/article/files/10/20/dc49255248658537182763235cde/c62be1a7-d4bb-4387-b2eb-09a6d00c0263.docx'
EXPECTED='073dd3f85158cfaee917ac369c2085f06d853e83af0dc1481f529c45cf1960ff'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore-public-document',action='store_true')
    args=parser.parse_args()
    target=ROOT/'fixtures/office_novel_v26/workspace/公开项目需求.docx'
    if target.exists():
        assert hashlib.sha256(target.read_bytes()).hexdigest()==EXPECTED,'Existing document differs; preserving it.'
        print('Public input already matches the frozen hash.');return
    if not args.restore_public_document:
        print('Optional reproduction input. Use --restore-public-document to fetch its fixed public URL.');return
    with urllib.request.urlopen(URL,timeout=60) as response:data=response.read(8*1024*1024+1)
    assert len(data)<=8*1024*1024 and hashlib.sha256(data).hexdigest()==EXPECTED,'Public source changed; refusing to replace the frozen input.'
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as handle:handle.write(data)
    print('Hash-pinned public input restored for local evaluation.')

if __name__=='__main__':main()
