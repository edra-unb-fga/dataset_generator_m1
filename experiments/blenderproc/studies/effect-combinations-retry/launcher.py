import json, os, subprocess
from pathlib import Path
log=open('/content/retry-worker.log','ab',buffering=0)
process=subprocess.Popen(['python3','/content/retry-worker.py'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
Path('/content/retry-worker.json').write_text(json.dumps({'pid':process.pid}))
print('Background worker started; pid',process.pid,flush=True)
