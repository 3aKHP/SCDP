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


def align(story, sources):
    originals = [o for o in story["occurrences"] if o["field"] in ("text","select")]
    def original_key(o):
        frame=story["frames"][int(o["pointer"].split("/")[1])]
        return o["field"],normalized(o["text"]),normalized(str(frame.get("speaker", ""))) if o["field"]=="text" else ""
    keys=[original_key(o) for o in originals]
    counts=Counter(keys)
    by_occurrence=defaultdict(list)
    for source in sources:
        rows=source["rows"]
        translated_keys=[(r["field"],r["text"],r["speaker"] if r["field"]=="text" else "") for r in rows]
        row_counts=Counter(translated_keys)
        positions=defaultdict(list)
        for j,key in enumerate(translated_keys):
            positions[key].append(j)
        for i,key in enumerate(keys):
            matches=[]
            if keys==translated_keys:
                matches=[i]  # The entire ordered source stream agrees, including repeated occurrences.
            elif counts[key]==1 and row_counts[key]==1:
                matches=positions[key]
            elif key in positions:
                context=keys[max(0,i-1):i+2]
                matches=[j for j in positions[key] if translated_keys[max(0,j-1):j+2]==context]
                if len(matches)!=1 or sum(keys[max(0,k-1):k+2]==context for k in range(len(keys)))!=1:
                    matches=[]
            for j in matches:
                row=rows[j]
                if row["translation"]:
                    by_occurrence[i].append({"text":row["translation"],"file":source["path"],"line":row["line"],
                                             "identity":source["identity"],"sha256":source["sha256"],"rule":"ordered-context-v1"})
    result=[]
    for i,o in enumerate(originals):
        candidates=by_occurrence[i]
        values={c["text"] for c in candidates}
        status="aligned" if len(values)==1 else "ambiguous" if values else "missing"
        index=int(o["pointer"].split("/")[1])
        result.append({"scriptId":story["scriptId"],"pointer":o["pointer"],"sourceSha256":o["sha256"],
                       "contextSha256":sha(canonical(story["frames"][max(0,index-1):index+2])),"language":"zh-Hans",
                       "text":next(iter(values)) if len(values)==1 else None,"kind":"human" if candidates else "missing",
                       "status":status,"candidates":candidates,
                       "provenance":{"source":"SCTranslationData","identity":sources[0]["identity"] if sources else "absent",
                                     "evidence":sorted({c["file"]+":"+str(c["line"]) for c in candidates})}})
    return result
