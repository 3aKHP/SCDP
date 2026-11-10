"""Install root-owned with a fixed, root-owned consumer config; allow this argv only."""
import json
from pathlib import Path

from scdp.core import file_lock, job_lock
from scdp.storage import collect_candidates

config = json.loads(Path("/etc/scdp/consumer.json").read_bytes())
with job_lock(config["recovery"]), file_lock(config["deploymentLock"]):
    print(json.dumps(collect_candidates(config), sort_keys=True))
