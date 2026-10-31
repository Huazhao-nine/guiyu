"""Verify the packaged submission sources by clean extraction, tests and rebuild."""
import hashlib,json,os,re,subprocess,tempfile,zipfile,plistlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def extract(p,d,prefix):
    with zipfile.ZipFile(p) as z:
        assert z.testzip() is None
        for i in z.infolist():
            n=Path(i.filename);assert not n.is_absolute() and '..' not in n.parts and ((i.external_attr>>16)&0o170000)!=0o120000
            assert n.suffix not in ('.safetensors','.onnx','.onnx_data','.whl','.jsonl') and n.name not in ('history.json','local-models.json','workspaces.json')
        z.extractall(d)
        for i in z.infolist():
            p=d/i.filename
            if p.is_file():p.chmod((i.external_attr>>16)&0o777 or 0o644)
        root=d/prefix
        for line in (root/'SHA256SUMS').read_text().splitlines():h,n=line.split('  ',1);assert sha(d/n)==h
    return root

def main():
    p=json.loads((ROOT/'qa/v0.27-package.json').read_text())
    for item in p['archives'].values():assert sha(ROOT/item['path'])==item['sha256']
    def run(command,cwd,label,env):
        result=subprocess.run(command,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (ROOT/'qa/private/v0.27'/('extracted-'+label+'.log')).write_text(result.stdout)
        assert result.returncode==0,label+': '+result.stdout[-1800:]
        return result.stdout
    def probe(app,cwd,label,env):
        run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],cwd,label+'-signature',env)
        info=plistlib.loads((app/'Contents/Info.plist').read_bytes());assert info['CFBundleShortVersionString']=='0.27.0' and info['CFBundleVersion']=='27'
        v=json.loads(run([str(app/'Contents/MacOS/Guiyu'),'--privacy-probe'],cwd,label+'-network',env).strip().splitlines()[-1]);assert v['sandbox'] and all(x['denied'] for x in v['probes'])
        h=app/'Contents/Helpers/GuiyuModelDownloader.app/Contents/MacOS/GuiyuModelDownloader'
        v=json.loads(run([str(h),'--boundary-probe'],cwd,label+'-helper',env).strip().splitlines()[-1]);assert v['sandbox'] and all(x['denied'] for x in v['private_reads'])
        return {'signature_verified':True,'network_denied':True,'helper_private_reads_denied':True}
    with tempfile.TemporaryDirectory(prefix='guiyu-v27-clean-check-') as temporary:
        d=Path(temporary);src=extract(ROOT/p['archives']['source']['path'],d/'source','Guiyu-0.27.0');demo=extract(ROOT/p['archives']['demo']['path'],d/'demo','Guiyu-0.27.0');application=extract(ROOT/p['archives']['application']['path'],d/'application','Guiyu-GCC-Cohort4-v0.27.0')
        protocol=json.loads((src/'qa/v0.27/final-protocol.json').read_text());assert protocol['backend_hashes']=={f.name:sha(f) for f in (src/'backend').glob('*.py')}
        for report,label in [('qa/v0.27/reports/first-20261031T101720-c6e32a.json','baseline-v0.27-first'),('qa/v0.27/reports/adapted-20261031T102446-2dcf4f.json','baseline-v0.27-before-content-review')]:
            r=json.loads((src/report).read_text());assert r['backend_hashes']=={f.name:sha(f) for f in (src/label/'backend').glob('*.py')}
        env=dict(os.environ);env.pop('PYTHONPATH',None);env['GUIYU_DATA_DIR']=str(d/'isolated-data')
        output=run([os.sys.executable,'-m','unittest','discover','-s','tests','-q'],src,'unit',env);count=int(re.search(r'Ran (\d+) tests',output)[1]);assert count==701
        run(['/bin/zsh','scripts/check_native.sh'],src,'native',env)
        shipped=demo/'dist/Guiyu-0.27.0.app';shipped_checks=probe(shipped,demo,'shipped',env)
        run(['/bin/zsh','scripts/build_model_demo_v27.sh'],src,'build',env);rebuilt=src/'dist/Guiyu-0.27.0.app';rebuilt_checks=probe(rebuilt,src,'rebuilt',env)
        for app in (shipped,rebuilt):
            assert protocol['backend_hashes']=={f.name:sha(f) for f in (app/'Contents/Resources').glob('*.py')}
            assert sha(app/'Contents/Resources/model-catalog.json')==sha(src/'packaging/model-catalog.json')
            showcase=app/'Contents/Resources/submission-showcase';assert len(list(showcase.iterdir()))==4
            assert all(sha(f)==sha(src/'fixtures/submission_v27/workspace'/f.name) for f in showcase.iterdir())
        assert json.loads((src/'qa/v0.27/word-validation.json').read_text())['passed']
    result={'version':'0.27.0','status':'PASS_EXTRACTED_SOURCE_TESTS_NATIVE_REBUILD_SIGNATURES_AND_PRIVACY_BOUNDARIES','unit_tests':count,'shipped_app':shipped_checks,'independently_rebuilt_app':rebuilt_checks,'all_archive_crcs_and_hashes_verified':True,'both_previous_v27_backend_snapshots_verified':True,'four_bundled_fictional_sources_match':True,'normal_app_history_and_workspaces_not_opened':True,'scope':'Packaged sources and native code/probes; GUI task execution remains separately reported.'}
    (ROOT/'qa/v0.27-delivery-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
