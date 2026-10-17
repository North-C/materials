#!/usr/bin/env python3
import hashlib,json,os,shutil,subprocess,sys,tarfile
from pathlib import Path
root=Path(__file__).resolve().parent
os.umask(0o077)
(root/'tool').mkdir(); (root/'bin').mkdir(); (root/'evidence').mkdir(exist_ok=True)
with tarfile.open(root/'tool.tar') as t:t.extractall(root/'tool')
shutil.copy2(root/'scripts/capture_w3.py',root/'tool/capture_w3.py')
source=Path('/data/cubelet/c100n100-perf-tuning-90/20261016T104049Z')
c=json.loads((source/'capture100.agentwarn.json').read_text())
assert c['template_id']=='tpl-381852bfe518c30bb815e163' and c['warmup']==0 and c['cubemastercli']['exclusive_template']
shutil.copy2(c['benchmark_binary'],root/'bin/cube-bench')
assert hashlib.sha256((root/'bin/cube-bench').read_bytes()).hexdigest()=='ae2f32cc4ca0e542543ce0200d26521416ca6a23c3377c63cd7ea5e9fbbfb511'
c['benchmark_binary']=str(root/'bin/cube-bench')
(root/'capture100.agentwarn.json').write_text(json.dumps(c,indent=2))
env=dict(os.environ,CAPTURE_CONFIG=str(root/'capture100.agentwarn.json'))
subprocess.run(['python3',str(root/'scripts/state_snapshot.py'),str(root/'evidence/state-before.json')],check=True)
(root/'evidence/kernel.txt').write_text(subprocess.check_output(['uname','-a'],text=True))
try:
 for state,rounds in [('pilot',1),('formal',5)]:
  subprocess.run(['python3',str(root/'scripts/run_series.py'),str(root),state,str(rounds)],env=env,check=True)
finally:
 subprocess.run(['python3',str(root/'scripts/state_snapshot.py'),str(root/'evidence/state-after.json')],check=True)
