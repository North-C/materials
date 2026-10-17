#!/usr/bin/env python3
"""Derive an `agent.log=<level>` template create request from an existing READY template.

usage: make_template_request.py SRC_TEMPLATE_ID OUT.json [--log-level warn] [--cubemastercli PATH]
Reads `cubemastercli tpl info SRC --include-request --json` on this host (read-only) and
writes a request for `cubemastercli tpl create -f OUT.json --node <node-ip>`:
  * keeps the stored createRequest unchanged (rootfs artifact, resources, probe, volumes);
  * drops requestID;
  * sets an explicit new template id, working around the v0.7.1 CubeMaster bug where a
    request without one gets two different generated IDs (stored request vs snapshot);
  * adds the container annotation io.cubesandbox.vm.kernel.cmdline.append, which only a
    shim carrying patch A (A-cmdline-alias.patch) honours.
OUT.json contains the rootfs artifact download token; it is written with mode 0600.
"""
import argparse
import json
import os
import secrets
import subprocess

ANNO = 'io.cubesandbox.vm.kernel.cmdline.append'
TEMPLATE_ID_KEY = 'cube.master.appsnapshot.template.id'

ap = argparse.ArgumentParser()
ap.add_argument('src')
ap.add_argument('out')
ap.add_argument('--log-level', default='warn')
ap.add_argument('--cubemastercli', default='/usr/local/bin/cubemastercli')
a = ap.parse_args()

info = json.loads(subprocess.run([a.cubemastercli, 'tpl', 'info', a.src, '--include-request', '--json'],
                                 check=True, capture_output=True, text=True).stdout)
if info.get('status') != 'READY':
    raise SystemExit(f'source template {a.src} is {info.get("status")}, expected READY')
req = info['create_request']
req.pop('requestID', None)
if len(req.get('containers', [])) != 1:
    raise SystemExit('expected exactly one container in the stored create request')
new_id = 'tpl-' + secrets.token_hex(12)
req['annotations'][TEMPLATE_ID_KEY] = new_id
container = req['containers'][0]
container.setdefault('annotations', {})[ANNO] = json.dumps([f'agent.log={a.log_level}'])

fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    json.dump(req, f, indent=1)
print(json.dumps({'new_template_id': new_id, 'source': a.src, 'resources': container.get('resources'),
                  'writable_layer_size': container.get('image', {}).get('writable_layer_size'),
                  'rootfs': container.get('image', {}).get('image'), 'annotation': container['annotations'][ANNO]}))
