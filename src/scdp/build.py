"""Offline text decoding and complete bilingual collection generation."""
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from . import __version__
from .core import Objects, atomic_write, canonical, now, safe_path, sha, write_json
from .official import classify, selected, validate_story
from .pipeline import load_observation
from .story import project, verify_occurrences
from .translation import align, read_archive
from .package import validate_tree

COLLECTION="games/shinycolors/story-bilingual"


def decoded_stories(root, observation):
    objects=Objects(Path(root)/"objects")
    for path in sorted(observation["resources"]):
        if not selected(path):
            continue
        checkpoint=Path(root)/"fetch"/observation["observationId"]/(sha(path.encode())+".json")
        if not checkpoint.exists():
            raise ValueError("missing_fetch_result")
        record=json.loads(checkpoint.read_bytes())
        if record.get("state")!="available" or record.get("logicalPath")!=path or record.get("sourceVersion")!=observation["resources"][path] or record.get("observationId")!=observation["observationId"]:
            raise ValueError("unavailable_story")
        objects.get(record["rawSha256"])
        data=objects.get(record["decodedSha256"])
        frames=validate_story(data)
        story=project(path.removeprefix("json/").removesuffix(".json"),frames,record["rawSha256"],record["decodedSha256"])
        verify_occurrences(story)
        yield record,story,data


def decode_all(root):
    observation=load_observation(root)
    count=occurrences=0
    target=Path(root)/"decoded.jsonl"
    fd,temp=tempfile.mkstemp(dir=Path(root),prefix=".decode-")
    try:
        with os.fdopen(fd,"wb") as out:
            for _,story,_ in decoded_stories(root,observation):
                out.write(canonical(story)+b"\n")
                count+=1
                occurrences+=len(story["occurrences"])
        os.replace(temp,target)
    finally:
        if Path(temp).exists(): Path(temp).unlink()
    return {"stories":count,"occurrences":occurrences,"sha256":sha(target.read_bytes())}


def fence(text):
    import re
    longest=max((len(m.group()) for m in re.finditer(r"`+",text)),default=0)
    delimiter="`"*max(3,longest+1)
    return delimiter+"text\n"+text+"\n"+delimiter


def render(story, translations):
    lines=["# "+story["scriptId"],"", "标题来源：稳定剧本编号。官方归属及解锁条件未解析。", "",
           "本篇保留全部分支；帧顺序表示原件位置，选项与跳转决定路径。", "",
           "原件 SHA-256："+story["rawSha256"], "解码 SHA-256："+story["decodedSha256"], ""]
    lookup={r["pointer"]:r for r in translations}
    by_frame={}
    for occurrence in story["occurrences"]:
        index=int(occurrence["pointer"].split("/")[1])
        by_frame.setdefault(index,[]).append(occurrence)
    for i,frame in enumerate(story["frames"]):
        controls=[c for c in story["controls"] if c["pointer"].startswith(f"/{i}/")]
        if not by_frame.get(i) and not controls:
            continue
        lines.extend([f"## 帧 {i}", ""])
        if frame.get("speaker"):
            lines.extend(["说话人："+str(frame["speaker"]),""])
        for occurrence in by_frame.get(i,[]):
            lines.extend(["位置：`"+occurrence["pointer"]+"`（"+occurrence["field"]+"）", "", fence(occurrence["text"]), ""])
            translation=lookup.get(occurrence["pointer"])
            if translation and translation["status"]=="aligned":
                lines.extend(["中文（人工来源）：", "", fence(translation["text"]), ""])
            else:
                lines.extend(["译文状态："+(translation["status"] if translation else "missing"), ""])
        for control in controls:
            lines.extend(["控制证据："+canonical(control).decode(), ""])
    return "\n".join(lines)+"\n"


def build(root, output, *, translations=None, translation_identity="absent", sequence=1, revision=0):
    root,output=Path(root),Path(output)
    observation=load_observation(root)
    translation_sha=sha(Path(translations).read_bytes()) if translations else None
    source_records,orphans=read_archive(translations,translation_identity) if translations else ({},[])
    code_sha=sha(canonical({p.name:sha(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))}))
    inputs={"observationId":observation["observationId"],"translationIdentity":translation_identity,
            "translationArchiveSha256":translation_sha,"codeSha256":code_sha,"toolVersion":__version__,
            "releaseSequence":sequence,"publicationRevision":revision}
    snapshot_id=sha(canonical(inputs))
    if output.exists():
        existing=json.loads((output/"snapshot.json").read_bytes())
        if existing["snapshotId"]!=snapshot_id: raise ValueError("build_target_exists")
        return validate_tree(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix=".build-") as temporary:
        stage=Path(temporary)
        collection=stage/"collection"
        (collection/"docs").mkdir(parents=True)
        (collection/"references").mkdir()
        write_json(stage/"inputs.json",inputs)
        atomic_write(collection/"collection.yaml",(f"id: {COLLECTION}\ntitle: 闪耀色彩剧情（日中）\nlanguage: ja\nvisibility: private\nstatus: active\ndefault_tags: [shinycolors, story, bilingual]\nsource:\n  kind: scdp\n  snapshot: {snapshot_id}\nindex:\n  include:\n    - docs/**/*.md\n    - references/**/*.md\n  exclude:\n    - attachments/**\n").encode())
        coverage=[];translated=Counter();control_keys=Counter();frame_keys=Counter(); fetched={}
        with (stage/"stories.jsonl").open("wb") as story_out,(stage/"translations.jsonl").open("wb") as translation_out:
            for record,story,decoded in decoded_stories(root,observation):
                rows=align(story,source_records.get(story["scriptId"],[]))
                translated.update(r["status"] for r in rows)
                story_out.write(canonical(story)+b"\n")
                for row in rows: translation_out.write(canonical(row)+b"\n")
                for frame in story["frames"]: frame_keys.update(frame.keys())
                control_keys.update(c["field"] for c in story["controls"])
                document="docs/"+safe_path(story["scriptId"])+".md"
                text=render(story,rows).encode()
                atomic_write(collection/document,text)
                atomic_write(stage/"originals"/(story["scriptId"]+".json"),decoded)
                coverage.append({"scriptId":story["scriptId"],"path":document,"sha256":sha(text),"size":len(text),
                                 "occurrences":len(story["occurrences"]),"frames":len(story["frames"]),
                                 "rawSha256":record["rawSha256"],"decodedSha256":record["decodedSha256"]})
                fetched[record["logicalPath"]]=record
        write_json(collection/"import-manifest.json",{"snapshotId":snapshot_id,"documents":coverage})
        index="# 剧情目录\n\n"+"\n".join(f"- [{r['scriptId']}]({r['path']})" for r in coverage)+"\n"
        atomic_write(collection/"README.md",index.encode())
        write_json(stage/"coverage.json",{"stories":len(coverage),"occurrences":sum(r["occurrences"] for r in coverage),
                    "translations":dict(translated),"frameKeys":dict(frame_keys),"controlKeys":dict(control_keys),
                    "historicalSeedsAbsent":sorted(set(source_records)-{r["scriptId"] for r in coverage}),
                    "translationOrphanFiles":[r["path"] for r in orphans],
                    "duplicateTranslationIds":{k:len(v) for k,v in source_records.items() if len(v)>1}})
        with (stage/"assets.jsonl").open("wb") as assets,(stage/"versions.jsonl").open("wb") as versions:
            for path,counter in sorted(observation["resources"].items()):
                aid="enza:"+path
                assets.write(canonical({"assetId":aid,"logicalPath":path,"kind":classify(path),"dependencies":[],"extensions":{}})+b"\n")
                record=fetched.get(path)
                reps=[]
                if record:
                    reps=[{"representationId":"sha256:"+record["decodedSha256"],"role":"decoded","sha256":record["decodedSha256"],
                           "size":record["decodedBytes"],"mediaType":"application/json","locator":"originals/"+path.removeprefix("json/"),
                           "inputs":[record["rawSha256"]],"tool":"official-v1"}]
                versions.write(canonical({"assetId":aid,"observationId":observation["observationId"],"sourceVersion":counter,
                    "firstSeen":observation["startedAt"],"lastSeen":observation["endedAt"],"presence":"current",
                    "availability":"available" if record else "inventoried","representations":reps,
                    "provenance":{"source":"official","identity":observation["observationId"],"evidence":[observation["inventorySha256"]]}})+b"\n")
        entries=[]
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                data=path.read_bytes()
                entries.append({"path":path.relative_to(stage).as_posix(),"size":len(data),"sha256":sha(data)})
        manifest={"schemaVersion":"1.0.0","snapshotId":snapshot_id,"releaseSequence":sequence,"publicationRevision":revision,
                  "observedAt":observation["endedAt"],"builtAt":now(),"source":{"observationId":observation["observationId"],"version":observation["sourceVersion"],"consistency":"observation-window"},
                  "inputs":inputs,"capabilities":["story.raw","story.occurrences","story.translation","asset.inventory"],
                  "scope":{"selector":"json/**/*.json except json/support_skills/**","selected":observation["selected"],"stories":len(coverage),"media":"inventory-only","visibility":"private","historicalCompleteness":"unproven"},
                  "baseline":None,"predecessor":None,"validation":{"unresolvedMetadata":True,"unknownControl":"preserved"},"files":entries}
        if len(coverage)!=observation["selected"]: raise ValueError("build_scope_mismatch")
        write_json(stage/"snapshot.json",manifest)
        result=validate_tree(stage)
        os.replace(stage,output)
    return result
