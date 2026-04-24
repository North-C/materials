# Copyright (c) 2024 Tencent Inc.
# SPDX-License-Identifier: Apache-2.0

import os
from e2b_code_interpreter import Sandbox
from env_utils import load_local_dotenv

load_local_dotenv()

template_id = os.environ["CUBE_TEMPLATE_ID"]

sandbox = Sandbox.create(template=template_id)
info = sandbox.get_info()
print("sandbox info %s" % info)

sandbox.kill()
print("sandbox %s killed" % sandbox.sandbox_id)
