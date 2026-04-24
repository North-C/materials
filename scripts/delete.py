# Copyright (c) 2024 Tencent Inc.
# SPDX-License-Identifier: Apache-2.0

import os

from e2b.api.client.api.sandboxes import delete_sandboxes_sandbox_id
from e2b.api.client.client import AuthenticatedClient
from e2b_code_interpreter import Sandbox
from env_utils import load_local_dotenv

load_local_dotenv()

template_id = os.environ["CUBE_TEMPLATE_ID"]
base_url = os.environ["E2B_API_URL"]
api_key = os.environ["E2B_API_KEY"]

paginator = Sandbox.list()
items = paginator.next_items()

matched = [s for s in items if s.template_id == template_id]

if not matched:
    print("no sandboxes found for template %s" % template_id)
else:
    client = AuthenticatedClient(base_url=base_url, token=api_key)
    for info in matched:
        resp = delete_sandboxes_sandbox_id.sync_detailed(info.sandbox_id, client=client)
        status = "ok" if resp.status_code == 204 else "fail(%d)" % resp.status_code
        print("sandbox %s %s" % (info.sandbox_id, status))
    print("%d sandbox(es) deleted" % len(matched))
