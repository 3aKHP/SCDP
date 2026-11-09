"""Official inventory observations and resumable all-text selection."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json

from .core import canonical, now, safe_path, sha, write_json
from .official import ASSETS_URL, asset_url, manifest_url, classify, parse_json, selected, validate_story


def validate_manifest(data):
    value = parse_json(data)
    if not isinstance(value, dict) or type(value.get("version")) is not int or not isinstance(value.get("chunks"), list) or not value["chunks"]:
        raise ValueError("invalid_manifest")
    names = set()
    for group in value["chunks"]:
        if not isinstance(group, dict) or not group:
            raise ValueError("invalid_shard_group")
        for name, version in group.items():
            safe_path(name)
            if name in names or type(version) is not int or version < 0:
                raise ValueError("invalid_shard_identity")
            names.add(name)
    return value


def validate_shard(data):
    value = parse_json(data)
    if not isinstance(value, dict) or not value:
        raise ValueError("invalid_shard")
    for path, version in value.items():
        safe_path(path)
        if type(version) is not int or version < 0:
            raise ValueError("invalid_asset_version")
    return value


def discover(downloader, base=ASSETS_URL, *, audit=False):
    started = now()
    main = downloader.fetch("asset-map.json", manifest_url(base), validate_manifest, revalidate=True)
    manifest = validate_manifest(downloader.objects.get(main["decodedSha256"]))
    resources, shards = {}, []
    for group in manifest["chunks"]:
        for name, version in group.items():
            record = downloader.fetch(name, asset_url(name, base)+f"?v={version}", validate_shard, revalidate=audit)
            shard = validate_shard(downloader.objects.get(record["decodedSha256"]))
            for path, counter in shard.items():
                if path in resources:
                    raise ValueError("duplicate_inventory_path")
                resources[path] = counter
            shards.append({"logicalPath": name, "sourceVersion": version,
                           "rawSha256": record["rawSha256"], "decodedSha256": record["decodedSha256"]})
    after = downloader.fetch("asset-map.json", manifest_url(base), validate_manifest, revalidate=True)
    if after["decodedSha256"] != main["decodedSha256"]:
        raise ValueError("inventory_changed_during_discovery")
    identity = {"manifestSha256": main["decodedSha256"], "shards": shards, "inventorySha256": sha(canonical(resources))}
    result = {"observationId": sha(canonical(identity)), "startedAt": started, "endedAt": now(),
              "sourceVersion": manifest["version"], "sourceBase": base, "manifest": main, **identity,
              "resources": resources, "counts": dict(Counter(classify(p) for p in resources)),
              "selected": sum(selected(p) for p in resources), "consistency": "observation-window"}
    target = downloader.root / "observations" / (result["observationId"] + ".json")
    if not target.exists():
        write_json(target, result)
    write_json(downloader.root / "current.json", {"observationId": result["observationId"]})
    return result


def load_observation(root):
    root = Path(root)
    current = json.loads((root / "current.json").read_bytes())
    obs = json.loads((root / "observations" / (current["observationId"]+".json")).read_bytes())
    identity = {key: obs[key] for key in ("manifestSha256", "shards", "inventorySha256")}
    if sha(canonical(obs["resources"])) != obs["inventorySha256"] or sha(canonical(identity)) != current["observationId"]:
        raise ValueError("observation_digest_mismatch")
    return obs


def fetch_stories(downloader, observation, *, workers=2, limit=None, sample=False):
    if workers < 1 or workers > 8:
        raise ValueError("invalid_concurrency")
    choices = sorted(path for path in observation["resources"] if selected(path))
    total_selected = len(choices)
    if sample:
        groups = {}
        for path in choices:
            groups.setdefault(path.split("/")[1], path)
        representatives = ["json/produce_events/201502201.json", "json/produce_events/100100308.json", "json/produce_events/180300102.json", "json/produce_events/109900601.json", "json/game_event_communications/400109901.json"]
        choices = sorted(set(groups.values()) | {p for p in representatives if p in choices})
    if limit is not None:
        if limit < 1:
            raise ValueError("invalid_limit")
        choices = choices[:limit]
    results = []
    output = downloader.root / "fetch" / observation["observationId"]
    output.mkdir(parents=True, exist_ok=True)

    def one(path):
        version = observation["resources"][path]
        try:
            result = downloader.fetch(path, asset_url(path, observation["sourceBase"])+f"?v={version}", validate_story)
            result = {**result, "sourceVersion": version, "observationId": observation["observationId"]}
        except Exception as exc:
            result = {"logicalPath": path, "state": "failed", "error": type(exc).__name__, "sourceVersion": version}
        write_json(output / (sha(path.encode())+".json"), result)
        return result

    # Bounded queue avoids scheduling thousands of operations after a budget failure.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(choices), workers):
            batch = list(pool.map(one, choices[start:start+workers]))
            results.extend(batch)
            if any(r.get("error") == "BudgetExceeded" for r in batch):
                break
            if len(results) % 100 == 0:
                print(json.dumps({"processed": len(results), "selected": len(choices), **downloader.status()}), flush=True)
    report = {"observationId": observation["observationId"], "selected": len(choices), "totalSelected": total_selected, "scope": "full" if len(choices)==total_selected else "sample", "processed": len(results),
              "available": sum(r["state"] == "available" for r in results), "ledger": downloader.status(), "endedAt": now()}
    report["complete"] = report["selected"] == report["available"]
    write_json(downloader.root / "fetch-report.json", report)
    return report
