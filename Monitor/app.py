#!/usr/bin/env python3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import aws_cdk as cdk
from ops_loop_stack import SysSecOpsOpsLoopStack

app = cdk.App()
SysSecOpsOpsLoopStack(
    app,
    "SysSecOpsOpsLoopStack",
    description="SysSecOps Phase 4 ops-loop: drift detection, rollback notifications, CloudWatch alarms and dashboard",
)
app.synth()