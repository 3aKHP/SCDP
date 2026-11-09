"""Independent translation snapshot and conservative occurrence-aware alignment."""
import csv
import io
import tarfile
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from .core import canonical, safe_path, sha


def normalized(text):
    return text.replace("\\n", "\n").replace("\r\n", "\n").strip()


def read_archive(path, identity):
    records = defaultdict(list)
    orphaned = []
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            if not member.isfile() or not member.name.endswith(".csv") or "/data/story/" not in member.name:
                continue
            safe_path(member.name)
            if member.size > 16*1024**2:
                raise ValueError("translation_file_limit")
            data = archive.extractfile(member).read()
            source_path = "data/story/"+member.name.split("/data/story/",1)[1]
            source_ids, rows = [], []
            for number, row in enumerate(csv.reader(io.StringIO(data.decode("utf-8-sig"))),1):
                row = row+[""]*max(0,4-len(row))
                frame_id, speaker, text, translated = row[:4]
                if frame_id == "info":
                    candidate = speaker.strip().removesuffix(".json").removeprefix("json/")
                    if candidate:
                        safe_path(candidate)
                        source_ids.append(candidate)
                elif frame_id not in ("id", "译者") and (text or frame_id == "select"):
                    rows.append({"id":frame_id,"speaker":normalized(speaker),"text":normalized(text),
                                 "translation":normalized(translated),"field":"select" if frame_id=="select" else "text", "line":number})
            record = {"path":source_path,"sha256":sha(data),"identity":identity,"rows":rows,
                      "title":PurePosixPath(source_path).stem,"sourceIds":sorted(set(source_ids))}
            if len(set(source_ids)) == 1:
                records[source_ids[0]].append(record)
            else:
                orphaned.append(record)
    return dict(records), orphaned


def read_fallbacks(path, identity):
    """Global story phrases only; UI/common dictionaries are outside story scope."""
    result = defaultdict(list)
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            if not member.isfile() or not member.name.endswith("/data/comm-story.csv"):
                continue
            safe_path(member.name)
            if member.size > 16*1024**2:
                raise ValueError("translation_file_limit")
            raw = archive.extractfile(member).read()
            for line, row in enumerate(csv.reader(io.StringIO(raw.decode("utf-8-sig"))), 1):
                if line == 1 or len(row) < 2 or not row[1].strip() or row[0].startswith("#"):
                    continue
                result[normalized(row[0])].append({"text": normalized(row[1]), "file": "data/comm-story.csv", "line": line,
                    "identity": identity, "sha256": sha(raw), "rule": "exact-global-story-phrase-v1", "accepted": True})
    return dict(result)


def align(story, sources, fallbacks=None):
    originals = [o for o in story["occurrences"] if o["field"] in ("text", "select")]
    def original_key(o):
        frame = story["frames"][int(o["pointer"].split("/")[1])]
        return o["field"], normalized(o["text"]), normalized(str(frame.get("speaker", ""))) if o["field"] == "text" else ""
    keys = [original_key(o) for o in originals]
    counts = Counter(keys)
    contexts = [tuple(keys[max(0, i-1):i+2]) for i in range(len(keys))]
    context_counts = Counter(contexts)
    by_occurrence = defaultdict(list)
    for source in sources:
        rows = source["rows"]
        translated_keys = [(r["field"], r["text"], r["speaker"] if r["field"] == "text" else "") for r in rows]
        row_counts = Counter(translated_keys)
        positions = defaultdict(list)
        for j, key in enumerate(translated_keys):
            positions[key].append(j)
        identical_stream = keys == translated_keys
        for i, key in enumerate(keys):
            matches = []
            if identical_stream:
                matches = [i]
            elif counts[key] == 1 and row_counts[key] == 1:
                matches = positions[key]
            elif key in positions:
                matches = [j for j in positions[key] if tuple(translated_keys[max(0, j-1):j+2]) == contexts[i]]
                if len(matches) != 1 or context_counts[contexts[i]] != 1:
                    matches = []
            for j in matches or positions[key]:
                row = rows[j]
                if row["translation"]:
                    by_occurrence[i].append({"text": row["translation"], "file": source["path"], "line": row["line"],
                        "identity": source["identity"], "sha256": source["sha256"], "rule": "ordered-context-v1",
                        "accepted": j in matches})
    result = []
    for i, occurrence in enumerate(originals):
        candidates = by_occurrence[i]
        kind = "human"
        # Ambiguous script-specific evidence is retained for review, not overridden by fallback.
        if not candidates and fallbacks:
            candidates = fallbacks.get(normalized(occurrence["text"]), [])
            kind = "fallback"
        accepted = [c for c in candidates if c["accepted"]]
        values = {c["text"] for c in accepted}
        status = "aligned" if len(values) == 1 and len(accepted) == len(candidates) else "ambiguous" if candidates else "missing"
        index = int(occurrence["pointer"].split("/")[1])
        result.append({"scriptId": story["scriptId"], "pointer": occurrence["pointer"], "sourceSha256": occurrence["sha256"],
            "contextSha256": sha(canonical(story["frames"][max(0, index-1):index+2])), "language": "zh-Hans",
            "text": next(iter(values)) if status == "aligned" else None, "kind": kind if candidates else "missing",
            "status": status, "candidates": candidates,
            "provenance": {"source": "SCTranslationData", "identity": candidates[0]["identity"] if candidates else sources[0]["identity"] if sources else "absent",
                "evidence": sorted({c["file"]+":"+str(c["line"]) for c in candidates})}})
    return result
