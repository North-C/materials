#!/usr/bin/python3
"""Fixed-mapping post-start enforcement; never creates or pulls a container."""
import subprocess,json,sys,time
from pathlib import Path
names={'cube-egress','cube-proxy','cube-lifecycle-manager','cube-webui','cube-sandbox-redis','cube-sandbox-mysql','cube-sandbox-minio','cube-proxy-coredns'}
name=sys.argv[1];assert name in names
end=time.monotonic()+60
while time.monotonic()<end:
 try:
  d=json.loads(subprocess.check_output(['docker','inspect',name],timeout=5,stderr=subprocess.DEVNULL))[0]
  if d['State']['Running']:
   ident=d['Id'];subprocess.run(['docker','update','--cpuset-cpus','96-191','--cpuset-mems','1',ident],check=True,timeout=10,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   after=json.loads(subprocess.check_output(['docker','inspect',name],timeout=5))[0]
   if after['Id']==ident and after['State']['Running'] and after['HostConfig']['CpusetCpus']=='96-191' and after['HostConfig']['CpusetMems']=='1':
    cg=next(x.split(':',2)[2] for x in (Path('/proc')/str(after['State']['Pid'])/'cgroup').read_text().splitlines() if x.split(':')[1]=='cpuset')
    p=Path('/sys/fs/cgroup/cpuset')/cg.lstrip('/')
    if (p/'cpuset.cpus').read_text().strip()=='96-191' and (p/'cpuset.mems').read_text().strip()=='1':sys.exit(0)
 except (subprocess.SubprocessError,OSError,ValueError,KeyError,StopIteration):pass
 time.sleep(1)
raise SystemExit('container cpuset enforcement timed out: '+name)
