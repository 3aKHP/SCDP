"""Pull verified public releases, activate through an operator adapter, bound disk use."""
import argparse
import json
import os
import subprocess
from pathlib import Path

from .core import file_lock, job_lock, now, write_json
from .github_release import GitHub, newest_data, read_descriptor
from .package import unpack, publish
from .storage import GiB, capacity_plan, collect_candidates, collect_distribution, require_space


def collect(config):
    if config.get("retentionCommand"):
        completed = subprocess.run(config["retentionCommand"], capture_output=True, check=True, timeout=300)
        return json.loads(completed.stdout)
    with file_lock(config["deploymentLock"]):
        return collect_candidates(config)


def pull(config, api):
    root = Path(config["work"])
    with job_lock(root):
        state_path = root/"active-release.json"
        if not state_path.exists():
            raise ValueError("consumer_seed_required")
        current = json.loads(state_path.read_bytes())
        collection = collect(config)
        latest = newest_data(api)
        if latest is None:
            return {"state": "no-data-release", "reclaimedBytes": collection["reclaimBytes"]}
        descriptor, asset = read_descriptor(api, latest)
        old = current["releaseSequence"], current["publicationRevision"]
        new = descriptor["releaseSequence"], descriptor["publicationRevision"]
        if new < old or (new == old and descriptor["snapshotId"] != current["snapshotId"]):
            raise ValueError("consumer_release_order_conflict")
        if new == old:
            registry = json.loads((Path(config["recovery"])/"active.json").read_bytes())
            if registry["snapshotId"] != descriptor["snapshotId"]:
                raise ValueError("consumer_active_snapshot_changed")
            return {"state": "unchanged", "snapshotId": descriptor["snapshotId"], "reclaimedBytes": collection["reclaimBytes"]}
        limit = config.get("maxArchiveBytes", 512*1024**2)
        if descriptor["bytes"] > limit:
            raise ValueError("consumer_archive_size_limit")
        require_space(root, descriptor["bytes"]+config.get("reserveBytes", 4*GiB))
        # Fixed work name lets the next run reclaim an interrupted download or
        # extraction. This directory never contains active sources or an index.
        incoming = root/"incoming"
        if incoming.exists():
            import shutil
            if incoming.is_symlink():
                raise ValueError("consumer_incoming_symlink")
            shutil.rmtree(incoming)
        incoming.mkdir()
        try:
            archive = incoming/"package.tar.gz"
            api.download(asset, archive, expected_sha=descriptor["sha256"], max_bytes=limit)
            plan = capacity_plan(config, archive)
            write_json(root/"capacity.json", {**plan, "observedAt": now()})
            bundle = incoming/"bundle"
            verified = unpack(archive, bundle, max_bytes=config.get("maxUnpackedBytes", 3*GiB))
            manifest = json.loads((bundle/"snapshot.json").read_bytes())
            if verified["snapshotId"] != descriptor["snapshotId"] or any(manifest[key] != descriptor[key] for key in ("releaseSequence", "publicationRevision")):
                raise ValueError("consumer_package_identity_mismatch")
            args = [part.replace("{bundle}", str(bundle)).replace("{archive}", str(archive)).replace("{snapshotId}", descriptor["snapshotId"])
                    for part in config["consumerCommand"]]
            with (root/"last-adapter.log").open("wb") as log:
                completed = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT,
                                           timeout=config.get("consumerTimeout", 7200))
            if completed.returncode:
                raise ValueError("consumer_activation_failed")
            registry = json.loads((Path(config["recovery"])/"active.json").read_bytes())
            if registry["state"] != "active" or registry["snapshotId"] != descriptor["snapshotId"]:
                raise ValueError("consumer_activation_not_confirmed")
            if config.get("distribution"):
                publish(archive, config["distribution"])
                with job_lock(config["distribution"]):
                    collect_distribution(config["distribution"])
            write_json(root/"previous-release.json", current)
            write_json(state_path, descriptor)
            collected = collect(config)
            return {"state": "activated", "snapshotId": descriptor["snapshotId"], "capacity": plan,
                    "reclaimedBytes": collection["reclaimBytes"]+collected["reclaimBytes"]}
        finally:
            import shutil
            shutil.rmtree(incoming)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_bytes())
    api = GitHub(config["repository"], os.environ.get("GH_TOKEN"))
    try:
        result = pull(config, api)
        write_json(Path(config["work"])/"last-run.json", {**result, "endedAt": now()})
        print(json.dumps(result))
    finally:
        api.close()


if __name__ == "__main__":
    main()
