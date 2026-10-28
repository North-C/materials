import datetime,hashlib,json,os,pathlib,subprocess,sys,urllib.request
base=pathlib.Path('/path/to/workdir')
def get(url):
 with urllib.request.urlopen(url,timeout=15) as r:return json.load(r)
api=get('http://127.0.0.1:3000/v2/sandboxes?limit=10000')
taps=get('http://127.0.0.1:9998/v1/network/taps')
procs=[];allowed=[]
ALLOW_PID=421105;ALLOW_GUEST='guest=foreign-vm'
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  comm=(p/'comm').read_text().strip();exe=str((p/'exe').resolve())
  if '/cube-shim/' in exe or comm in ['perf','qemu-kvm','ffmpeg','x265','rustc','cargo','cube-bench']:
   # 10-28: user accepted running alongside this one foreign libvirt VM; it is recorded, not treated as a conflict.
   if comm=='qemu-kvm' and int(p.name)==ALLOW_PID and ALLOW_GUEST in (p/'cmdline').read_bytes().decode(errors='replace'):
    allowed.append({'pid':int(p.name),'comm':comm,'guest':ALLOW_GUEST,'cpu_jiffies':sum(int(x) for x in (p/'stat').read_text().rsplit(')',1)[1].split()[11:13])})
    continue
   procs.append({'pid':int(p.name),'comm':comm,'exe':exe})
 except (OSError,RuntimeError):pass
files=['/usr/local/services/cubetoolbox/Cubelet/bin/cubelet','/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs','/usr/local/services/cubetoolbox/cube-shim/bin/cube-runtime','/data/cubelet/root/component_versions/cube-shim/v0.7.1/bin/containerd-shim-cube-rs','/data/cubelet/root/component_versions/cube-shim/v0.7.1/bin/cube-runtime','/usr/local/services/cubetoolbox/Cubelet/config/config.toml','/usr/local/services/cubetoolbox/Cubelet/dynamicconf/conf.yaml']
record={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inventory':api,'tap_counts':taps.get('stateCounts'),'tap_total':len(taps['taps']),'active_tap_owners':[x for x in taps['taps'] if x.get('sandboxID') or x.get('ownerSandboxID')],'conflicting_processes':procs,'allowed_foreign_processes':allowed,'hugepages_free':[l.split()[1] for l in open('/proc/meminfo') if l.startswith('HugePages_Free')][0],'loadavg':pathlib.Path('/proc/loadavg').read_text().strip(),'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'kernel':os.uname().release,'sha256':{f:hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest() for f in files}}
path=pathlib.Path(sys.argv[1]);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(record,indent=2)+'\n')
assert api==[], 'nonempty inventory'
assert len(taps["taps"])>=600 and all(x['state']=='Ready' and not x.get('sandboxID') and not x.get('ownerSandboxID') for x in taps['taps']), 'TAP pool not clean'
assert not procs, 'conflicting processes'
assert float(record['loadavg'].split()[0])<=4.0, 'load gate'
print('gate passed: empty inventory, 600 Ready/free TAPs, no VM/perf/build/benchmark processes except allowed foreign VM %s, load <=4'%[a['pid'] for a in allowed])
