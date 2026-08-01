"""One-off helper: drop rows for named scenarios from a campaign's runs.jsonl.

Used when a scenario has to be re-run after a fixture defect is corrected.  The
original file is kept alongside with a ``.bak`` suffix so the discarded rows
remain auditable.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    campaign_id, scenarios = argv[1], set(argv[2:])
    path = Path("logs/experiments") / campaign_id / "runs.jsonl"
    shutil.copy(path, path.with_suffix(".jsonl.bak"))

    kept, dropped = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if json.loads(line).get("scenario") in scenarios:
            dropped += 1
            continue
        kept.append(line)

    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"dropped {dropped} rows, kept {len(kept)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
