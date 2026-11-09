"""Semantic full-scope checks independent of byte-manifest verification."""
import json
from collections import Counter
from pathlib import Path
import jsonschema
from .contracts import schema
from .core import canonical, safe_path, sha
from .official import parse_json, selected
from .story import READABLE, CONTROL, MEDIA, PRESENTATION


def records(path, kind):
    contract = schema()
    validator = jsonschema.Draft202012Validator({"$schema": contract["$schema"], "$defs": contract["$defs"], "$ref": "#/$defs/"+kind})
    with Path(path).open("rb") as stream:
        for line in stream:
            if not line.endswith(b"\n"):
                raise ValueError("jsonl_unterminated_record")
            value = parse_json(line)
            validator.validate(value)
            yield value


def pointer_value(value, pointer):
    for part in pointer.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def check_occurrences(story, document):
    # Enumerate leaf positions directly from retained original frames, using the
    # format's field registry. This does not invoke the story projection or renderer.
    expected = {}
    known = READABLE | CONTROL | MEDIA | PRESENTATION
    for index, frame in enumerate(story["frames"]):
        pending = [(f"/{index}/"+key.replace("~", "~0").replace("/", "~1"), value, key not in known or (key=="command" and value!="conditional_jump"), key)
                   for key, value in frame.items()]
        while pending:
            pointer, value, unknown, field = pending.pop()
            if isinstance(value, dict):
                pending.extend((pointer+"/"+k.replace("~", "~0").replace("/", "~1"), v, unknown, k) for k, v in value.items())
            elif isinstance(value, list):
                pending.extend((pointer+"/"+str(i), v, unknown, str(i)) for i, v in enumerate(value))
            elif isinstance(value, str) and (unknown or field in READABLE):
                expected[pointer] = value
    actual = {o["pointer"]: o["text"] for o in story["occurrences"]}
    if len(actual) != len(story["occurrences"]) or actual != expected:
        raise ValueError("body_occurrence_set_mismatch")
    cursor = 0
    positions = []
    for occurrence in story["occurrences"]:
        if occurrence["sha256"] != sha(occurrence["text"].encode()):
            raise ValueError("body_occurrence_digest_mismatch")
        marker = "位置：`"+occurrence["pointer"]+"`（"+occurrence["field"]+"）\n\n"
        position = document.find(marker, cursor)
        if position < 0:
            raise ValueError("document_occurrence_missing")
        start = position+len(marker)
        line_end = document.find("\n", start)
        opening = document[start:line_end]
        delimiter = opening.removesuffix("text")
        if not opening.endswith("text") or len(delimiter) < 3 or set(delimiter) != {"`"}:
            raise ValueError("document_occurrence_fence")
        end = document.find("\n"+delimiter+"\n", line_end+1)
        if end < 0 or document[line_end+1:end] != occurrence["text"].replace("\r\n", "\n").replace("\r", "\n"):
            raise ValueError("document_occurrence_changed")
        cursor = end+len(delimiter)+2
        positions.append((occurrence["pointer"], position, cursor))
    spans = {pointer: (body_end, positions[i+1][1] if i+1 < len(positions) else len(document))
             for i, (pointer, _, body_end) in enumerate(positions)}
    return len(expected), spans


def validate_semantics(root, manifest):
    root = Path(root)
    required = ["assets.jsonl", "versions.jsonl", "stories.jsonl", "translations.jsonl", "entities.jsonl", "relations.jsonl", "coverage.json", "sources.json", "schema.json"]
    if any(not (root/name).is_file() for name in required):
        raise ValueError("missing_standard_record_file")
    if sha((root/"schema.json").read_bytes()) != manifest["inputs"]["schemaSha256"]:
        raise ValueError("package_schema_digest_mismatch")
    assets = {}
    for asset in records(root/"assets.jsonl", "Asset"):
        path = safe_path(asset["logicalPath"])
        if asset["assetId"] != "enza:"+path or asset["assetId"] in assets:
            raise ValueError("asset_identity_mismatch")
        assets[asset["assetId"]] = asset
    inventory, versions, historical_available = {}, {}, set()
    for version in records(root/"versions.jsonl", "AssetVersion"):
        aid = version["assetId"]
        if aid not in assets or aid in versions:
            raise ValueError("asset_version_set_mismatch")
        if version["presence"] == "current":
            inventory[assets[aid]["logicalPath"]] = version["sourceVersion"]
        elif version["presence"] == "historical" and version["availability"] == "available" and selected(assets[aid]["logicalPath"]):
            historical_available.add(assets[aid]["logicalPath"].removeprefix("json/").removesuffix(".json"))
        versions[aid] = version["availability"]
        if version["availability"] == "available" and not version["representations"]:
            raise ValueError("available_without_representation")
        for rep in version["representations"]:
            path = root/safe_path(rep["locator"])
            if not path.is_file() or path.stat().st_size != rep["size"] or sha(path.read_bytes()) != rep["sha256"]:
                raise ValueError("representation_integrity_mismatch")
    if set(versions) != set(assets):
        raise ValueError("asset_version_set_mismatch")
    if sha(canonical(inventory)) != manifest["source"]["inventorySha256"] or len(inventory) != manifest["source"]["inventoryCount"]:
        raise ValueError("inventory_fingerprint_mismatch")
    for asset in assets.values():
        for dependency in asset["dependencies"]:
            if dependency["assetId"] not in assets:
                raise ValueError("dependency_missing")
            if dependency["required"] and versions[asset["assetId"]] == "available" and versions[dependency["assetId"]] != "available":
                raise ValueError("required_dependency_unavailable")
    current_chosen = {p.removeprefix("json/").removesuffix(".json") for p in inventory if selected(p)}
    chosen = current_chosen | historical_available
    if manifest["scope"].get("historicalStories", 0) != len(historical_available):
        raise ValueError("historical_story_count_mismatch")
    collection_manifest = parse_json((root/"collection/import-manifest.json").read_bytes())
    docs = {d["scriptId"]: d for d in collection_manifest["documents"]}
    actual_docs = {p.relative_to(root/"collection").as_posix() for p in (root/"collection/docs").rglob("*.md")}
    if actual_docs != {d["path"] for d in docs.values()}:
        raise ValueError("document_file_set_mismatch")
    if len(docs) != len(collection_manifest["documents"]) or set(docs) != chosen:
        raise ValueError("document_selection_mismatch")
    seen = set()
    occurrence_count = empty_stories = 0
    translation_sources = {}
    translation_spans = {}
    control_counts = Counter()
    for story in records(root/"stories.jsonl", "Story"):
        sid = story["scriptId"]
        if sid in seen or sid not in chosen or story["assetId"] != "enza:json/"+sid+".json":
            raise ValueError("story_selection_mismatch")
        seen.add(sid)
        raw = (root/"originals"/(safe_path(sid)+".json")).read_bytes()
        if sha(raw) != story["decodedSha256"] or parse_json(raw) != story["frames"]:
            raise ValueError("story_original_mismatch")
        document = (root/"collection"/safe_path(docs[sid]["path"])).read_bytes()
        if sha(document) != docs[sid]["sha256"] or len(document) != docs[sid]["size"]:
            raise ValueError("document_manifest_mismatch")
        if b"\r" in document:
            raise ValueError("document_non_lf_line_endings")
        count, spans = check_occurrences(story, document.decode("utf-8"))
        if versions[story["assetId"]] != "available":
            raise ValueError("story_availability_mismatch")
        if story["rawSha256"] != docs[sid]["rawSha256"] or story["decodedSha256"] != docs[sid]["decodedSha256"]:
            raise ValueError("story_provenance_mismatch")
        required_controls = {}
        known = READABLE | CONTROL | MEDIA | PRESENTATION
        labels = {}
        for i, frame in enumerate(story["frames"]):
            if isinstance(frame.get("label"), str):
                labels.setdefault(frame["label"], []).append(i)
            for key, value in frame.items():
                if key in CONTROL or key not in known or (key in READABLE and not isinstance(value, str)):
                    pointer = f"/{i}/"+key.replace("~", "~0").replace("/", "~1")
                    required_controls[pointer] = value
        if {c["pointer"]: c["raw"] for c in story["controls"]} != required_controls or len(story["controls"]) != len(required_controls):
            raise ValueError("control_evidence_set_mismatch")
        graph = story.get("graph", {})
        if graph.get("nodes") != list(range(len(story["frames"]))):
            raise ValueError("graph_node_set_mismatch")
        jumps = {edge["from"]: edge for edge in graph.get("edges", []) if edge["kind"] in ("jump", "choice", "conditional_jump")}
        for i, frame in enumerate(story["frames"]):
            if "nextLabel" in frame or (isinstance(frame.get("select"),str) and frame["select"]):
                if i not in jumps or jumps[i]["raw"] != frame.get("nextLabel"):
                    raise ValueError("graph_control_edge_missing")
                value = frame.get("nextLabel")
                if jumps[i]["targets"] != (labels.get(value, [])[:1] if isinstance(value, str) else []):
                    raise ValueError("graph_control_target_mismatch")
        for i, frame in enumerate(story["frames"]):
            if frame.get("command") == "conditional_jump" and "nextLabel" in frame:
                outcomes = [e for e in graph.get("edges",[]) if e["from"]==i and e["kind"].startswith("conditional_")]
                expected = {True,False} if i+1 < len(story["frames"]) else {True}
                if {e.get("predicate",{}).get("equals") for e in outcomes} != expected:
                    raise ValueError("conditional_outcome_missing")
                if any(e["predicate"]["commandKey"] != frame.get("commandKey") for e in outcomes):
                    raise ValueError("conditional_source_key_changed")
                if i+1 < len(story["frames"]) and not any(e["kind"]=="conditional_fallthrough" and e["targets"]==[i+1] for e in outcomes):
                    raise ValueError("conditional_fallthrough_missing")
        for edge in graph.get("edges", []):
            if edge["from"] not in graph["nodes"] or any(t not in graph["nodes"] for t in edge["targets"]):
                raise ValueError("graph_dangling_edge")
        if count != docs[sid]["occurrences"] or len(story["frames"]) != docs[sid]["frames"]:
            raise ValueError("document_coverage_count_mismatch")
        occurrence_count += count
        empty_stories += not any(o["field"] in READABLE and o["text"].strip() for o in story["occurrences"])
        for control in story["controls"]:
            if pointer_value(story["frames"], control["pointer"]) != control["raw"]:
                raise ValueError("control_evidence_changed")
            control_counts[control["status"]] += 1
        for reference in story["mediaReferences"]:
            if reference.get("assetId") and reference["assetId"] not in assets:
                raise ValueError("media_reference_missing")
        for occurrence in story["occurrences"]:
            if occurrence["field"] in ("text", "select"):
                index = int(occurrence["pointer"].split("/")[1])
                context = sha(canonical(story["frames"][max(0, index-1):index+2]))
                translation_sources[(sid, occurrence["pointer"])] = (occurrence["sha256"], context)
                translation_spans[(sid, occurrence["pointer"])] = spans[occurrence["pointer"]]
    if seen != chosen or len(current_chosen) != manifest["scope"]["selected"] or manifest["scope"]["stories"] != len(chosen):
        raise ValueError("story_selection_mismatch")
    translation_seen, translation_counts = set(), Counter()
    current_document_id, current_document = None, ""
    for row in records(root/"translations.jsonl", "Translation"):
        key = row["scriptId"], row["pointer"]
        if key in translation_seen or translation_sources.get(key) != (row["sourceSha256"], row["contextSha256"]):
            raise ValueError("translation_occurrence_mismatch")
        translation_seen.add(key)
        translation_counts[row["status"]] += 1
        if row["status"] == "aligned" and (not row["text"] or any(not c.get("accepted") or c["text"] != row["text"] for c in row["candidates"]) or not row["candidates"]):
            raise ValueError("translation_alignment_claim_invalid")
        if row["status"] == "aligned":
            if current_document_id != row["scriptId"]:
                current_document_id = row["scriptId"]
                current_document = (root/"collection"/docs[current_document_id]["path"]).read_bytes().decode("utf-8")
            start, end = translation_spans[key]
            if "\n"+row["text"].replace("\r\n", "\n").replace("\r", "\n")+"\n" not in current_document[start:end]:
                raise ValueError("document_translation_missing")
        if row["status"] != "aligned" and row["text"] is not None:
            raise ValueError("unresolved_translation_claim_invalid")
    if translation_seen != set(translation_sources):
        raise ValueError("translation_occurrence_set_mismatch")
    entities = set()
    for entity in records(root/"entities.jsonl", "Entity"):
        if entity["entityId"] in entities:
            raise ValueError("entity_identity_duplicate")
        entities.add(entity["entityId"])
    for relation in records(root/"relations.jsonl", "Relation"):
        for endpoint in (relation["from"], relation["to"]):
            if endpoint.split("#", 1)[0] not in assets and endpoint not in entities:
                raise ValueError("relation_endpoint_missing")
    report = {"assets": len(assets), "stories": len(seen), "occurrences": occurrence_count,
              "emptyStories": empty_stories, "translations": dict(translation_counts), "controls": dict(control_counts), "entities": len(entities)}
    coverage = parse_json((root/"coverage.json").read_bytes())
    if coverage["stories"] != len(seen) or coverage["occurrences"] != occurrence_count or coverage["translations"] != dict(translation_counts) or coverage["emptyStories"] != empty_stories:
        raise ValueError("coverage_report_mismatch")
    return report
