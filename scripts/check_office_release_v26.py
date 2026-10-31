"""Clean archive extraction, tests, build and privacy boundaries without user data."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile
import check_model_demo_v24 as check

ROOT=Path(__file__).resolve().parents[1]
check.ROOT=ROOT


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
        base=folder/'Guiyu-0.26.0'
        for line in (base/'SHA256SUMS').read_text().splitlines():
            h,name=line.split('  ',1);assert check.sha(folder/name)==h
    return base


def main():
    # Reuse the command logger, with a new versioned destination. No old
    # reports, builds or model-search freezes are overwritten.
    import subprocess
    def run(command,cwd,label,env=None):
        r=subprocess.run(command,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (ROOT/'qa/private/v0.26'/('extracted-'+label+'.log')).write_text(r.stdout)
        assert r.returncode==0,label+': '+r.stdout[-1200:]
        return r.stdout
    def probe(app,cwd,label):
        import plistlib
        run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],cwd,label+'-signature')
        info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
        assert info['CFBundleShortVersionString']=='0.26.0' and info['CFBundleVersion']=='26'
        text=run([str(app/'Contents/MacOS/Guiyu'),'--privacy-probe'],cwd,label+'-network')
        result=json.loads(text.strip().splitlines()[-1]);assert result['sandbox'] and all(p['denied'] for p in result['probes'])
        helper=app/'Contents/Helpers/GuiyuModelDownloader.app/Contents/MacOS/GuiyuModelDownloader'
        text=run([str(helper),'--boundary-probe'],cwd,label+'-helper')
        result=json.loads(text.strip().splitlines()[-1]);assert result['sandbox'] and all(p['denied'] for p in result['private_reads'])
        return {'signature_verified':True,'network_denied':True,'helper_private_reads_denied':True}
    packages=json.loads((ROOT/'qa/v0.26-package.json').read_text())
    for item in packages['archives'].values():assert check.sha(ROOT/item['path'])==item['sha256']
    with tempfile.TemporaryDirectory(prefix='guiyu-v26-source-check-') as temporary:
        folder=Path(temporary)
        source=extract(ROOT/packages['archives']['source']['path'],folder/'source')
        demo=extract(ROOT/packages['archives']['demo']['path'],folder/'demo')
        protocol=json.loads((source/'qa/v0.26/final-protocol.json').read_text())
        assert protocol['backend_hashes']=={p.name:check.sha(p) for p in (source/'backend').glob('*.py')}
        for name,label in [('initial-protocol.json','baseline-before-v0.26'),('adapted-protocol.json','baseline-v0.26-first-adaptation'),('recovery-protocol.json','baseline-v0.26-recovery'),('dependency-protocol.json','baseline-v0.26-dependency'),('focused-protocol.json','baseline-v0.26-focused'),('confirmation-first-protocol.json','baseline-v0.26-first-confirmation'),('boundary-protocol.json','baseline-v0.26-output-boundary'),('pre-condition-proof-protocol.json','baseline-v0.26-pre-condition-proof')]:
            old=json.loads((source/'qa/v0.26'/name).read_text())
            assert old['backend_hashes']=={p.name:check.sha(p) for p in (source/label/'backend').glob('*.py')}
        assert not (source/'fixtures/office_novel_v26/workspace/公开项目需求.docx').exists()
        env=dict(os.environ);env.pop('PYTHONPATH',None);env['GUIYU_DATA_DIR']=str(folder/'isolated-data')
        unit_output=run([os.sys.executable,'-m','unittest','discover','-s','tests','-q'],source,'unit',env)
        unit_count=int(re.search(r'Ran (\d+) tests',unit_output)[1])
        run(['/bin/zsh','scripts/check_native.sh'],source,'native',env)
        shipped=demo/'dist/Guiyu-0.26.0.app';shipped_checks=probe(shipped,demo,'shipped')
        run(['/bin/zsh','scripts/build_model_demo_v26.sh'],source,'build',env)
        rebuilt=source/'dist/Guiyu-0.26.0.app';rebuilt_checks=probe(rebuilt,source,'rebuilt')
        for app in (shipped,rebuilt):
            assert protocol['backend_hashes']=={p.name:check.sha(p) for p in (app/'Contents/Resources').glob('*.py')}
            assert check.sha(app/'Contents/Resources/model-catalog.json')==check.sha(source/'packaging/model-catalog.json')
        models=json.loads((source/'packaging/model-catalog.json').read_text())
        assert [m['id'] for m in models if m.get('purpose')=='chat']==['qwen3.6-35b-a3b']
    result={'status':'PASS_EXTRACTED_SOURCE_TESTS_NATIVE_REBUILD_SIGNATURES_AND_PRIVACY_BOUNDARIES','unit_tests':unit_count,
            'shipped_app':shipped_checks,'independently_rebuilt_app':rebuilt_checks,'original_and_intermediate_backend_freezes_preserved':True,
            'archive_hashes_verified':True,'normal_app_or_history_not_opened':True,'scope':'Command-line/native code validation and clean rebuild; GUI evidence is separate.'}
    (ROOT/'qa/v0.26-delivery-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
