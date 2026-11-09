"""Lossless occurrences, explicit control edges and conservative unknown-field evidence."""
from collections import deque
from .core import sha

READABLE = {"text", "select", "title", "caption", "message"}
CONTROL = {"select", "label", "nextLabel"}
MEDIA = {"voice", "bg", "fg", "middleFg", "bgm", "se", "charId", "charCategory", "charType", "movie", "still", "stillId", "stillType"}
# Presentation-only fields observed in the client scenario command handler. Every
# unrecognized field remains visible evidence and is never silently dropped.
PRESENTATION = {
    "id", "speaker", "textFrame", "logTextFrame", "textCtrl", "textWait", "waitType", "waitTime", "autoWaitTime",
    "bgEffect", "bgEffectTime", "fgEffect", "fgEffectTime", "middleFgEffect", "middleFgEffectTime",
    "bgmFadeTime", "voiceKeep", "lip", "lipAnimDuration", "charLabel", "charPosition", "charScale", "charEffect",
    "charLipAnim", "charStill", "charSpine", "stillCtrl", "effectLabel", "effectTarget", "effectValue", "speakerIcon",
    "gameEventCommunicationMovie", "gameEventCommunicationSe",
    *{f"charAnim{i}{suffix}" for i in range(1, 6) for suffix in ("", "Loop")},
}


def walk(value, pointer=""):
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from walk(child, pointer+"/"+escaped)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, pointer+"/"+str(index))
    else:
        yield pointer, value


def control_graph(frames, labels, unknown_by_frame):
    """Graph of explicit labels and choices; unknown commands yield unresolved edges."""
    edges = []
    entries = [0] if frames else []
    for index, frame in enumerate(frames):
        if "nextLabel" in frame:
            value = frame["nextLabel"]
            targets = labels.get(value, []) if isinstance(value, str) else []
            edges.append({"from": index, "targets": targets, "kind": "choice" if "select" in frame else "jump",
                          "status": "resolved" if len(targets) == 1 and not unknown_by_frame.get(index) else "unresolved", "raw": value})
        elif "select" in frame:
            edges.append({"from": index, "targets": [], "kind": "choice", "status": "unresolved", "raw": None})
        elif index+1 < len(frames):
            end = index+1
            if "select" in frames[end]:
                while end+1 < len(frames) and "select" in frames[end+1]:
                    end += 1
                targets = list(range(index+1, end+1))
                kind = "choice_group"
            else:
                targets, kind = [index+1], "fallthrough"
            edges.append({"from": index, "targets": targets, "kind": kind,
                          "status": "unresolved" if unknown_by_frame.get(index) else "resolved"})
    if frames and "select" in frames[0]:
        end = 0
        while end+1 < len(frames) and "select" in frames[end+1]:
            end += 1
        entries = list(range(end+1))
    adjacency = {i: set() for i in range(len(frames))}
    for edge in edges:
        if edge["status"] == "resolved":
            adjacency[edge["from"]].update(edge["targets"])
    seen, pending = set(), list(entries)
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(adjacency[node]-seen)
    indegree = {i: 0 for i in adjacency}
    for targets in adjacency.values():
        for target in targets:
            indegree[target] += 1
    queue = deque(i for i, degree in indegree.items() if not degree)
    removed = 0
    while queue:
        node = queue.popleft()
        removed += 1
        for target in adjacency[node]:
            indegree[target] -= 1
            if not indegree[target]:
                queue.append(target)
    return {"nodes": list(range(len(frames))), "entries": entries, "edges": edges,
            "hasResolvedCycle": removed < len(frames), "notProvenReachable": sorted(set(adjacency)-seen),
            "semantics": "explicit labels, contiguous choices and potential order; unknown commands are unresolved"}


def project(script_id, frames, raw_sha, decoded_sha):
    occurrences, controls, media = [], [], []
    labels, unknown_by_frame = {}, {}
    known = READABLE | CONTROL | MEDIA | PRESENTATION
    for index, frame in enumerate(frames):
        if isinstance(frame.get("label"), str):
            labels.setdefault(frame["label"], []).append(index)
        unknown_by_frame[index] = sorted(set(frame)-known)
    for pointer, value in walk(frames):
        parts = pointer.split("/")
        field = parts[-1].replace("~1", "/").replace("~0", "~")
        top_field = parts[2].replace("~1", "/").replace("~0", "~")
        if isinstance(value, str) and (field in READABLE or top_field in unknown_by_frame[int(parts[1])]):
            occurrences.append({"pointer": pointer, "field": field, "text": value, "sha256": sha(value.encode())})
    for index, frame in enumerate(frames):
        for key, value in frame.items():
            pointer = f"/{index}/"+key.replace("~", "~0").replace("/", "~1")
            if key in CONTROL or key in unknown_by_frame[index] or (key in READABLE and not isinstance(value, str)):
                record = {"pointer": pointer, "field": key, "raw": value, "status": "unresolved"}
                if key == "nextLabel" and isinstance(value, str):
                    targets = labels.get(value, [])
                    record.update(targets=targets, status="resolved" if len(targets) == 1 else "unresolved")
                elif key in ("select", "label") and isinstance(value, str):
                    record["status"] = "preserved"
                controls.append(record)
            if key in MEDIA:
                media.append({"pointer": pointer, "field": key, "raw": value, "assetId": None, "status": "unresolved"})
    return {"scriptId": script_id, "assetId": "enza:json/"+script_id+".json", "rawSha256": raw_sha,
            "decodedSha256": decoded_sha, "category": script_id.split("/")[0], "title": script_id,
            "sourceLanguage": "ja", "frames": frames, "occurrences": occurrences, "controls": controls,
            "graph": control_graph(frames, labels, unknown_by_frame),
            "unknownFrameFields": sorted({key for keys in unknown_by_frame.values() for key in keys}),
            "mediaReferences": media, "unresolvedFields": ["officialTitle", "characters", "card", "event", "unlockCondition"],
            "metadataProvenance": []}


def verify_occurrences(story):
    expected = project(story["scriptId"], story["frames"], story["rawSha256"], story["decodedSha256"])["occurrences"]
    if expected != story["occurrences"]:
        raise ValueError("occurrence_coverage_mismatch")
    return len(expected)
