#!/usr/bin/env bash
# Deliberately does nothing unless explicitly invoked with B or A2.
set -Eeuo pipefail
case "${1:-}" in B|A2) ;; *) echo "Usage: $0 B|A2 (changes installed components; no benchmarks)" >&2; exit 2;; esac
exec python3 - "$1" <<'PY'
import datetime,fcntl,hashlib,json,os,pathlib,re,shutil,signal,stat,subprocess,sys,time,urllib.request
BASE=pathlib.Path('/path/to/workdir')
T=pathlib.Path('/usr/local/services/cubetoolbox')
PIN=pathlib.Path('/data/cubelet/root/component_versions/cube-shim/v0.7.1/bin')
COMM=BASE/'backup/community-tested'
OPT=BASE/'boostkit-build/out'
PHASE=sys.argv[1]
BINARIES=[T/'Cubelet/bin/cubelet',T/'Cubelet/bin/cubecli',T/'cube-shim/bin/containerd-shim-cube-rs',T/'cube-shim/bin/cube-runtime',PIN/'containerd-shim-cube-rs',PIN/'cube-runtime']
STATIC=T/'Cubelet/config/config.toml'; DYNAMIC=T/'Cubelet/dynamicconf/conf.yaml'
FILES=BINARIES+[STATIC,DYNAMIC]
SERVICES=['cube-sandbox-cubelet.service','cube-sandbox-cube-egress-net.service','cube-sandbox-cube-egress.service']
SHA='2babb6f7405677c04b7fed1563c6a5d53a8e771b'
assert os.geteuid()==0,'must run as root'
os.umask(0o077)
lock=open(BASE/'tools/swap-components.lock','a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
RUN=BASE/'logs'/('swap-'+PHASE+'-'+stamp);RUN.mkdir()
log=open(RUN/'events.log','a',buffering=1)
def event(message):
    line=datetime.datetime.now(datetime.timezone.utc).isoformat()+' '+message
    print(line,flush=True);log.write(line+'\n')
def call(args,**kw):
    event('RUN '+' '.join(map(str,args)))
    return subprocess.run(list(map(str,args)),check=True,**kw)
def get(url):
    with urllib.request.urlopen(url,timeout=10) as response:return json.load(response)
def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def info(path):
    st=path.stat()
    assert path.is_file() and not path.is_symlink(),f'nonregular target {path}'
    return {'path':str(path),'sha256':digest(path),'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid,'size':st.st_size}
def conflicting():
    result=[]
    for p in pathlib.Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():continue
        try:
            comm=(p/'comm').read_text().strip();exe=str((p/'exe').resolve()); argv=(p/'cmdline').read_bytes().decode(errors='replace').split('\0')
            name=pathlib.Path(exe).name
            bad=('/cube-shim/' in exe or name in {'cube-runtime','containerd-shim-cube-rs','perf','qemu-kvm','qemu-system-x86_64','qemu-system-aarch64','ffmpeg','x265','rustc','cargo','cube-bench','cpb'} or (name in {'go','gcc','g++','cc','cc1','clang','ld','ld.lld'}))
            if name.startswith('python'):
                bad=bad or any(pathlib.Path(a).name.startswith(('bench_','benchmark_')) or ('cube-perf-bench' in a) or ('cube_perf_bench' in a) for a in argv[1:] if a and not a.startswith('-'))
            if bad:result.append({'pid':int(p.name),'comm':comm,'exe':exe,'argv':argv[:5]})
        except (OSError,RuntimeError):pass
    return result
def gate(name,taps=True):
    inventory=get('http://127.0.0.1:3000/v2/sandboxes?limit=10000')
    conflicts=conflicting()
    state={'inventory':inventory,'conflicting_processes':conflicts}
    assert inventory==[],f'nonempty inventory: {inventory}'
    assert not conflicts,f'conflicting processes: {conflicts}'
    if taps:
        pool=get('http://127.0.0.1:9998/v1/network/taps');state['taps']=pool
        assert len(pool["taps"])>=600 and all(t['state']=='Ready' and not t.get('sandboxID') and not t.get('ownerSandboxID') for t in pool['taps']),'TAP pool must be >=600 Ready/free'
    (RUN/(name+'.json')).write_text(json.dumps(state,indent=2)+'\n')
    event('PASS '+name)
def config_check():
    s=STATIC.read_text();d=DYNAMIC.read_text()
    for key,value in [('mcpu_limit','1200000'),('mem_limit','"1200Gi"'),('mvm_limit','600'),('creation_concurrent_num','100')]:
        assert re.search(r'^    '+key+r':\s*'+re.escape(value)+r'\s*$',d,re.M),f'unexpected tested quota: {key}'
    assert re.search(r'^\s*tap_init_num\s*=\s*600\s*$',s,re.M),'expected 600 configured TAPs'
    assert d.count('\nhost:\n')==1,'unexpected YAML host block'
def backup_into(where):
    where.mkdir(parents=True,exist_ok=False)
    records=[]
    for i,path in enumerate(FILES):
        rec=info(path);dest=where/f'{i:02d}-{path.name}'
        shutil.copy2(path,dest);os.chown(dest,rec['uid'],rec['gid'])
        assert digest(dest)==rec['sha256']
        rec['backup_file']=dest.name;records.append(rec)
    (where/'manifest.json').write_text(json.dumps({'files':records,'created_utc':stamp,'role':'community-tested' if where==COMM else 'transaction-entry'},indent=2)+'\n')
    return records
def load_backup(where):
    records=json.loads((where/'manifest.json').read_text())['files']
    assert [r['path'] for r in records]==list(map(str,FILES)),'backup target mismatch'
    for rec in records:assert digest(where/rec['backup_file'])==rec['sha256'],'backup checksum mismatch'
    return records
def atomic_copy(source,target,metadata):
    temp=target.parent/(target.name+'.user-swap-'+stamp)
    try:
        shutil.copyfile(source,temp);os.chmod(temp,metadata['mode']);os.chown(temp,metadata['uid'],metadata['gid'])
        assert digest(temp)==digest(source),'staged checksum mismatch'
        os.replace(temp,target)
        got=info(target)
        assert got['sha256']==digest(source) and all(got[k]==metadata[k] for k in ['mode','uid','gid']),'installed verification mismatch'
    finally:
        if temp.exists():temp.unlink()
def stop():
    call(['systemctl','stop',SERVICES[0]])
    assert subprocess.run(['systemctl','is-active','--quiet',SERVICES[0]]).returncode!=0,'Cubelet still active'
    for p in pathlib.Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if str((p/'exe').resolve()) in [str(BINARIES[0]),str(BINARIES[0])+' (deleted)']:raise AssertionError('cubelet process survived stop')
        except (OSError,RuntimeError):pass
    gate('after-stop',taps=False)
def ready():
    call(['systemctl','start',SERVICES[0]])
    # Requires/After causes stop propagation; reverse start is not automatic.
    call(['systemctl','start','--no-block',SERVICES[1],SERVICES[2]])
    deadline=time.monotonic()+300;last=''
    while time.monotonic()<deadline:
        try:
            pool=get('http://127.0.0.1:9998/v1/network/taps')
            assert len(pool["taps"])>=600 and all(t['state']=='Ready' and not t.get('sandboxID') and not t.get('ownerSandboxID') for t in pool['taps'])
            assert all(subprocess.run(['systemctl','is-active','--quiet',s]).returncode==0 for s in SERVICES)
            assert get('http://127.0.0.1:3000/health').get('status')=='ok'
            break
        except Exception as exc:last=repr(exc);time.sleep(2)
    else:raise RuntimeError('600 Ready/services/health deadline: '+last)
    with open(RUN/'quickcheck.log','ab') as output:
        env=os.environ.copy();env['CUBE_QUICKCHECK_READY_TIMEOUT']='120'
        # MinIO and Web UI were stopped by another stack restart at 17:02 and stayed down for the B run;
        # keep them down and skip only those two checks. The copy holds credentials: 0600, removed after.
        qenv=RUN/'quickcheck-env';text=(T/'.one-click.env').read_text()
        assert text.count('\nCUBE_SANDBOX_MINIO_ENABLED=1\n')==1,'unexpected MinIO setting'
        assert 'WEB_UI_ENABLE=' not in text,'unexpected Web UI setting'
        qenv.write_text(text.replace('\nCUBE_SANDBOX_MINIO_ENABLED=1\n','\nCUBE_SANDBOX_MINIO_ENABLED=0\n').rstrip('\n')+'\nWEB_UI_ENABLE=0\n');os.chmod(qenv,0o600)
        env['ONE_CLICK_RUNTIME_ENV_FILE']=str(qenv)
        try:call(['bash',T/'scripts/one-click/quickcheck.sh'],stdout=output,stderr=subprocess.STDOUT,env=env,timeout=150)
        finally:qenv.unlink()
    gate('after-start')
def check_identity(records):
    for rec in records:
        got=info(pathlib.Path(rec['path']))
        assert all(got[k]==rec[k] for k in ['sha256','mode','uid','gid']),f'unexpected deployed bytes/mode/owner {rec["path"]}'
    pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value',SERVICES[0]]))
    assert pid>0 and digest(f'/proc/{pid}/exe')==digest(BINARIES[0]),'running Cubelet does not match target'
    (RUN/'running-cubelet.json').write_text(json.dumps({'pid':pid,'exe':os.readlink(f'/proc/{pid}/exe'),'sha256':digest(f'/proc/{pid}/exe')},indent=2)+'\n')

def interrupted(signum,frame):raise RuntimeError('interrupted by signal '+str(signum))
signal.signal(signal.SIGTERM,interrupted)
event('BEGIN '+PHASE+'; no benchmark will be launched')
gate('before-backup');config_check()
opt_manifest=json.loads((OPT/'manifest.json').read_text());assert opt_manifest['commit']==SHA
opt_hash={x['name']:x['sha256'] for x in opt_manifest['binaries']}
for name,wanted in opt_hash.items():assert digest(OPT/'bin'/name)==wanted,'optimized checksum mismatch'
# Record and validate the CURRENT tested community state, never the install defaults.
if PHASE=='B':
    for path in BINARIES:
        version=subprocess.check_output([str(path),'--version'],text=True,stderr=subprocess.STDOUT)
        assert '31d911e' in version and 'boostkit' not in version,'B requires current community binaries'
    assert not re.search(r'^\s*dirty_log:\s*true\s*$',DYNAMIC.read_text(),re.M),'community configuration already opted into dirty logging'
    if COMM.exists():
        community=load_backup(COMM);check_identity(community)
    else:community=backup_into(COMM)
else:
    community=load_backup(COMM)
    for path in BINARIES:assert digest(path)==opt_hash[path.name],'A2 requires the expected optimized components'
    assert re.search(r'^    dirty_log:\s*true\s*$',DYNAMIC.read_text(),re.M),'A2 requires dirty_log true in B'
    assert digest(STATIC)==community[-2]['sha256'],'static test config drifted'
    expected=(COMM/community[-1]['backup_file']).read_text().replace('\nhost:\n','\nhost:\n  memory:\n    dirty_log: true\n')
    assert DYNAMIC.read_text()==expected,'B dynamic config drifted; no overwrite'
entry=backup_into(RUN/'rollback')
check_identity(entry)
gate('before-stop')
plan=[]
for i,target in enumerate(FILES):
    source=OPT/'bin'/target.name if PHASE=='B' and target in BINARIES else COMM/community[i]['backup_file']
    if PHASE=='B' and target==DYNAMIC:
        text=source.read_text();assert not re.search(r'^  memory:',text,re.M),'unexpected existing memory section'
        source=RUN/'dynamic-B.yaml';source.write_text(text.replace('\nhost:\n','\nhost:\n  memory:\n    dirty_log: true\n'))
    plan.append({'source':str(source),'target':str(target),'sha256':digest(source),'mode':community[i]['mode'],'uid':community[i]['uid'],'gid':community[i]['gid']})
(RUN/'replacement-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
stopped=False
try:
    stopped=True;stop()
    for item in plan:atomic_copy(pathlib.Path(item['source']),pathlib.Path(item['target']),item)
    ready()
    final=[info(path) for path in FILES]
    check_identity(final)
    for got,wanted in zip(final,plan):assert got['sha256']==wanted['sha256'],'post-start changed installed file'
    (RUN/'installed.json').write_text(json.dumps(final,indent=2)+'\n')
    (RUN/'SUCCESS').write_text(PHASE+'\n')
    event('SUCCESS '+PHASE+'; inventory empty, 600 Ready, egress active, quickcheck passed')
except BaseException as exc:
    event('FAILED '+repr(exc))
    if stopped:
        try:
            # Never kill an unexpected workload to perform rollback.
            gate('rollback-inventory',taps=False)
            stop()
            for rec in entry:atomic_copy(RUN/'rollback'/rec['backup_file'],pathlib.Path(rec['path']),rec)
            ready();check_identity(entry)
            (RUN/'ROLLED_BACK').write_text('restored exact entry bytes, modes, owners and config\n')
            event('ROLLBACK COMPLETE')
        except BaseException as rollback_exc:
            (RUN/'ROLLBACK_FAILED').write_text(repr(rollback_exc)+'\n')
            event('ROLLBACK FAILED; manual review required: '+repr(rollback_exc))
    raise
PY
