"""Run final local-model checks serially, keeping every stage's report."""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[1]

def main():
    jobs=[('transfer-first',['scripts/check_office_transfer_v26.py','--group','confirmation','--label','transfer-first']),
          ('confirmation-final',['scripts/check_office_novel_v26.py','--group','confirmation','--label','confirmation-final']),
          ('development-final',['scripts/check_office_novel_v26.py','--group','development','--label','development-final']),
          ('primary-regression',['scripts/check_primary_regression_v26.py','--suite','primary'])]
    codes=[]
    for label,args in jobs:
        log=ROOT/'qa/private/v0.26'/('final-'+label+'.log')
        print('START',label,flush=True)
        with log.open('x') as handle:result=subprocess.run([sys.executable,*args],cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT)
        codes.append(result.returncode);print('END',label,'exit',result.returncode,flush=True)
    raise SystemExit(0 if all(code==0 for code in codes) else 1)

if __name__=='__main__':main()
