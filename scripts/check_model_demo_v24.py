"""Independently extract, rebuild and inspect the preview without opening user data."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(path,folder):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for item in z.infolist():
            p=Path(item.filename)
            assert not p.is_absolute() and '..' not in p.parts
            assert ((item.external_attr>>16)&0o170000)!=0o120000
        z.extractall(folder)
        for item in z.infolist():
            p=folder/item.filename
            if p.is_file():p.chmod((item.external_attr>>16)&0o777 or 0o644)
        base=folder/'Guiyu-0.24.0'
        for line in (base/'SHA256SUMS').read_text().splitlines():
            h,name=line.split('  ',1);assert sha(folder/name)==h
    return base


def run(command,cwd,label,env=None):
    result=subprocess.run(command,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    log=ROOT/'qa/private/v0.24'/('extracted-'+label+'.log');log.write_text(result.stdout)
    assert result.returncode==0,label+': '+result.stdout[-1200:]
    return result.stdout


def probe(app,cwd,label):
    run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],cwd,label+'-signature')
    with (app/'Contents/Info.plist').open('rb') as stream:info=plistlib.load(stream)
    assert info['CFBundleShortVersionString']=='0.24.0' and info['CFBundleVersion']=='24'
    text=run([str(app/'Contents/MacOS/Guiyu'),'--privacy-probe'],cwd,label+'-network')
    result=json.loads(text.strip().splitlines()[-1]);assert result['sandbox'] and all(p['denied'] for p in result['probes'])
    helper=app/'Contents/Helpers/GuiyuModelDownloader.app/Contents/MacOS/GuiyuModelDownloader'
    text=run([str(helper),'--boundary-probe'],cwd,label+'-helper')
    boundary=json.loads(text.strip().splitlines()[-1]);assert boundary['sandbox'] and all(p['denied'] for p in boundary['private_reads'])
    return {'version':'0.24.0','signature_verified':True,'network_denied':True,'helper_private_reads_denied':True}


def main():
    packages=json.loads((ROOT/'qa/v0.24-package.json').read_text())
    for item in packages['archives'].values():assert sha(ROOT/item['path'])==item['sha256']
    with tempfile.TemporaryDirectory(prefix='guiyu-v24-source-check-') as temporary:
        folder=Path(temporary)
        source=extract(ROOT/packages['archives']['source']['path'],folder/'source')
        demo=extract(ROOT/packages['archives']['demo']['path'],folder/'demo')
        protocol=json.loads((source/'qa/v0.24/release/protocol.json').read_text())
        boundary=json.loads((source/'qa/v0.24/final/protocol.json').read_text())
        adapted=json.loads((source/'qa/v0.24/adaptation/protocol.json').read_text())
        old=json.loads((source/'qa/v0.24/search-protocol.json').read_text())
        assert protocol['backend_hashes']=={p.name:sha(p) for p in (source/'backend').glob('*.py')}
        assert old['backend_hashes']=={p.name:sha(p) for p in (source/'baseline-v0.22/backend').glob('*.py')}
        assert adapted['backend_hashes']=={p.name:sha(p) for p in (source/'baseline-v0.24-adapted/backend').glob('*.py')}
        assert boundary['backend_hashes']=={p.name:sha(p) for p in (source/'baseline-v0.24-before-month-scope/backend').glob('*.py')}
        env=dict(os.environ);env.pop('PYTHONPATH',None);env['GUIYU_DATA_DIR']=str(folder/'isolated-unit-data')
        unit_output=run([sys.executable,'-m','unittest','discover','-s','tests','-q'],source,'unit-tests',env)
        unit_count=int(re.search(r'Ran (\d+) tests',unit_output)[1])
        shipped=demo/'dist/Guiyu-0.24.0.app'
        shipped_checks=probe(shipped,demo,'shipped')
        run(['/bin/zsh','scripts/build_model_demo_v24.sh'],source,'build')
        rebuilt=source/'dist/Guiyu-0.24.0.app'
        rebuilt_checks=probe(rebuilt,source,'rebuilt')
        for app in [shipped,rebuilt]:
            assert protocol['backend_hashes']=={p.name:sha(p) for p in (app/'Contents/Resources').glob('*.py')}
            assert sha(app/'Contents/Resources/model-catalog.json')==sha(source/'packaging/model-catalog.json')
    result={'status':'PASS_EXTRACTED_SOURCES_UNIT_TESTS_REBUILD_SIGNATURES_AND_BOUNDARIES','unit_tests':unit_count,
            'shipped_app':shipped_checks,'independently_rebuilt_app':rebuilt_checks,
            'all_four_backend_freezes_preserved':True,'archive_hashes_verified':True,
            'normal_application_or_history_not_opened':True,'scope':'Command-line probes and clean rebuild, not actual GUI task execution; helper probes attempt private paths only inside an already-installed deny-read sandbox.'}
    (ROOT/'qa/v0.24-delivery-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
