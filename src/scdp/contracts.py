"""Public contract validation plus dependencies and occurrence identity checks."""
import json
from importlib.resources import files
import jsonschema
from .core import canonical, safe_path, sha


def schema():
    return json.loads(files("scdp").joinpath("contract.schema.json").read_bytes())


def validate(bundle):
    jsonschema.Draft202012Validator(schema()).validate(bundle)
    ids = set()
    for asset in bundle["assets"]:
        safe_path(asset["logicalPath"])
        if asset["assetId"] in ids:
            raise ValueError("duplicate_asset")
        ids.add(asset["assetId"])
    versions = {}
    for version in bundle["versions"]:
        if version["assetId"] not in ids or version["assetId"] in versions:
            raise ValueError("invalid_asset_version_reference")
        versions[version["assetId"]] = version
        if version["availability"] == "available" and not version["representations"]:
            raise ValueError("available_without_representation")
        for rep in version["representations"]:
            safe_path(rep["locator"])
    if set(versions) != ids:
        raise ValueError("missing_asset_version")
    for asset in bundle["assets"]:
        for dep in asset["dependencies"]:
            if dep["assetId"] not in ids:
                raise ValueError("missing_dependency")
            if dep["required"] and versions[asset["assetId"]]["availability"] == "available" and versions[dep["assetId"]]["availability"] != "available":
                raise ValueError("required_dependency_unavailable")
    story_ids = set()
    for story in bundle["stories"]:
        if story["scriptId"] in story_ids or story["assetId"] not in ids:
            raise ValueError("invalid_story_identity")
        story_ids.add(story["scriptId"])
        pointers = set()
        for occurrence in story["occurrences"]:
            if occurrence["pointer"] in pointers or sha(occurrence["text"].encode()) != occurrence["sha256"]:
                raise ValueError("invalid_occurrence")
            pointers.add(occurrence["pointer"])
    paths = set()
    for entry in bundle["snapshot"]["files"]:
        safe_path(entry["path"])
        if entry["path"] in paths:
            raise ValueError("duplicate_package_path")
        paths.add(entry["path"])
    return summary(bundle)


def summary(bundle):
    return {"snapshotId":bundle["snapshot"]["snapshotId"],
            "assets":sorted(a["assetId"] for a in bundle["assets"]),
            "stories":sorted(s["scriptId"] for s in bundle["stories"]),
            "representations":sorted(r["sha256"] for v in bundle["versions"] for r in v["representations"]),
            "dependencies":sorted(a["assetId"]+"|"+d["assetId"]+"|"+str(d["required"]).lower() for a in bundle["assets"] for d in a["dependencies"])}
