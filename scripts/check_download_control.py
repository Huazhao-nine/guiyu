"""Check a pause arriving before a transfer starts, without downloading any weights."""
import json
from pathlib import Path
import subprocess
import time
root=Path(__file__).resolve().parents[1]
store=Path.home()/'Library/Application Support/GuiyuModels'
command=store/'command.json'
status=store/'qwen3-8b.status.json'
assert not command.exists(),'A real download request is pending.'
for p in store.glob('*.status.json'):
 assert json.loads(p.read_text())['phase'] not in ('starting','downloading','verifying','pausing'),'A real download is active.'
assert not (store/'Partial/qwen3-8b').exists(),'Preserve an existing user download; skip this control test.'
prior=status.read_bytes() if status.exists() else None
helper=None
try:
 status.write_text(json.dumps({'modelID':'qwen3-8b','phase':'pausing','completed':0,'total':4623783401,'detail':'test','updated':time.time()}))
 command.write_text(json.dumps({'id':'control-check','action':'pause','modelID':'qwen3-8b'}))
 helper=subprocess.Popen([str(root/'dist/Guiyu.app/Contents/Helpers/GuiyuModelDownloader.app/Contents/MacOS/GuiyuModelDownloader'),'--serve'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 deadline=time.monotonic()+12
 while time.monotonic()<deadline:
  current=json.loads(status.read_text())
  if current['phase']=='paused':break
  time.sleep(.1)
 else:raise AssertionError('Idle pause was not acknowledged.')
 assert current['completed']==0 and not command.exists()
 assert not (store/'Partial/qwen3-8b').exists()
 report={'version':'0.4.0','checks':{'pause_before_start_is_acknowledged':True,'no_weight_files_downloaded':True,'zero_byte_progress_preserved':True},'all_checks_passed':True}
 (root/'qa/v0.4-download-control-report.json').write_text(json.dumps(report,indent=2)+'\n')
 print('DOWNLOAD_CONTROL_PASS')
finally:
 if helper and helper.poll() is None:
  helper.terminate();helper.wait(timeout=10)
 command.unlink(missing_ok=True)
 if prior is None:status.unlink(missing_ok=True)
 else:status.write_bytes(prior)
