"""Offline text decoding and complete bilingual collection generation."""
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from . import __version__
from .core import Objects, atomic_write, canonical, now, safe_path, sha, write_json
from .official import classify, selected, validate_story, decode as official_decode
from .pipeline import load_observation
from .story import READABLE, project, verify_occurrences
from .translation import align, read_archive, read_fallbacks
from .catalog import Catalog
from .history import inventory_history, story_records, content_fingerprint
from .package import validate_tree

COLLECTION="games/shinycolors/story-bilingual"


def decoded_stories(root, observation, chosen=None):
    objects=Objects(Path(root)/"objects")
    chosen=story_records(root,observation) if chosen is None else chosen
    for path,record in sorted(chosen.items()):
        raw=objects.get(record["rawSha256"])
        data=objects.get(record["decodedSha256"])
        if official_decode(path,raw)!=data:
            raise ValueError("raw_decoded_mismatch")
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
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    longest=max((len(m.group()) for m in re.finditer(r"`+",text)),default=0)
    delimiter="`"*max(3,longest+1)
    return delimiter+"text\n"+text+"\n"+delimiter


def render(story, translations):
    lines=["# "+story["scriptId"],"", "标题与归属的来源候选见标准记录；官方完整目录及解锁条件未完成验证。", "",
           "本篇保留全部分支；帧顺序表示原件位置，选项与跳转决定路径。", "",
           "展示标题（来源候选见标准记录）：", fence(story["title"]), "",
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
                lines.extend(["中文（"+("通用词条回退" if translation["kind"]=="fallback" else "人工来源")+"）：", "", fence(translation["text"]), ""])
            else:
                lines.extend(["译文状态："+(translation["status"] if translation else "missing"), ""])
        for control in controls:
            lines.extend(["控制证据："+canonical(control).decode(), ""])
    return "\n".join(lines)+"\n"


def input_identity(observation, history, chosen, catalog, translations=None, translation_identity="absent"):
    translation_sha=sha(Path(translations).read_bytes()) if translations else None
    code_sha=sha(canonical({p.name:sha(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))}))
    inputs={"observationId":observation["observationId"],"translationIdentity":translation_identity,
            "translationArchiveSha256":translation_sha,"metadataInputs":catalog.inputs,"storyContentFingerprint":content_fingerprint(chosen),"inventoryHistoryFingerprint":sha(canonical(history)),"codeSha256":code_sha,"schemaSha256":sha((Path(__file__).parent/"contract.schema.json").read_bytes()),"toolVersion":__version__,
            }
    return inputs


def build(root, output, *, translations=None, translation_identity="absent", metadata=None, sequence=1, revision=0):
    root,output=Path(root),Path(output)
    observation=load_observation(root)
    translation_sha=sha(Path(translations).read_bytes()) if translations else None
    history=inventory_history(root,observation)
    chosen=story_records(root,observation,history)
    all_resources={path:state["sourceVersion"] for path,state in history.items()}
    catalog=Catalog(all_resources)
    catalog.load(metadata)
    fallbacks=read_fallbacks(translations,translation_identity) if translations else {}
    source_records,orphans=read_archive(translations,translation_identity) if translations else ({},[])
    inputs=input_identity(observation,history,chosen,catalog,translations,translation_identity)
    inputs.update(releaseSequence=sequence,publicationRevision=revision)
    snapshot_id=sha(canonical(inputs))
    identity_path=root/"build-identities"/(snapshot_id+".json")
    if identity_path.exists():
        identity=json.loads(identity_path.read_bytes())
        if identity["inputs"]!=inputs:
            raise ValueError("build_identity_conflict")
    else:
        identity={"inputs":inputs,"builtAt":now()}
        write_json(identity_path,identity)
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
        atomic_write(stage/"schema.json",(Path(__file__).parent/"contract.schema.json").read_bytes())
        atomic_write(collection/"collection.yaml",(f"id: {COLLECTION}\ntitle: 闪耀色彩剧情（日中）\nlanguage: ja\nvisibility: private\nstatus: active\ndefault_tags: [shinycolors, story, bilingual]\nsource:\n  kind: scdp\n  snapshot: {snapshot_id}\nindex:\n  include:\n    - docs/**/*.md\n    - references/**/*.md\n  exclude:\n    - attachments/**\n").encode())
        coverage=[];translated=Counter();control_keys=Counter();frame_keys=Counter(); fetched={}
        metadata_coverage=Counter();media_coverage=Counter();body_occurrences=readable_stories=unknown_strings=0
        with (stage/"stories.jsonl").open("wb") as story_out,(stage/"translations.jsonl").open("wb") as translation_out, (stage/"relations.jsonl").open("wb") as relation_out:
            for record,story,decoded in decoded_stories(root,observation,chosen):
                body_occurrences+=sum(o["field"] in READABLE for o in story["occurrences"])
                unknown_strings+=sum(o["field"] not in READABLE for o in story["occurrences"])
                readable_stories+=any(o["field"] in READABLE and o["text"].strip() for o in story["occurrences"])
                sources=source_records.get(story["scriptId"],[])
                catalog.enrich(story,sources)
                metadata_coverage.update([story["metadata"]["titleStatus"]])
                media_coverage.update(ref["status"] for ref in story["mediaReferences"])
                rows=align(story,sources,fallbacks)
                for ref in story["mediaReferences"]:
                    if ref["assetId"]:
                        relation_out.write(canonical({"from":story["assetId"]+"#"+ref["pointer"],"to":ref["assetId"],
                            "type":"frame_uses_"+ref["field"],"confidence":"explicit",
                            "provenance":{"source":"official","identity":story["decodedSha256"],"evidence":[ref["pointer"],ref["rule"]]}})+b"\n")
                translated.update(r["status"] for r in rows)
                story_out.write(canonical(story)+b"\n")
                for row in rows: translation_out.write(canonical(row)+b"\n")
                for frame in story["frames"]: frame_keys.update(frame.keys())
                control_keys.update(c["field"] for c in story["controls"])
                document="docs/"+safe_path(story["scriptId"])+".md"
                reference_name=sha(story["scriptId"].encode())+".json"
                write_json(collection/"references/assets"/reference_name,{"scriptId":story["scriptId"],"media":story["mediaReferences"]})
                import posixpath
                reference_link=posixpath.relpath("references/assets/"+reference_name,posixpath.dirname(document))
                text=(render(story,rows)+"\n[本篇媒体目录引用]("+reference_link+")\n").encode()
                atomic_write(collection/document,text)
                atomic_write(stage/"originals"/(story["scriptId"]+".json"),decoded)
                coverage.append({"scriptId":story["scriptId"],"path":document,"sha256":sha(text),"size":len(text),
                                 "occurrences":len(story["occurrences"]),"frames":len(story["frames"]),
                                 "rawSha256":record["rawSha256"],"decodedSha256":record["decodedSha256"]})
                fetched[record["logicalPath"]]=record
            for relation in catalog.relations:
                relation_out.write(canonical(relation)+b"\n")
        with (stage/"entities.jsonl").open("wb") as entity_out:
            for entity_id in sorted(catalog.entities):
                entity_out.write(canonical(catalog.entities[entity_id])+b"\n")
        write_json(stage/"history-audit.json",{"translationSeedScripts":len(source_records),
            "translationSeedsOutsideCurrentSelection":sorted(set(source_records)-{r["scriptId"] for r in coverage}),
            "semanticSeedScriptsMapped":len(catalog.story_metadata),
            "semanticSeedsUnresolved":[r for r in catalog.unresolved if r["kind"]=="script_lookup"],
            "orphanTranslationFiles":[r["path"] for r in orphans],
            "claim":"current inventory coverage; unresolved semantic IDs are not asserted to be missing scripts; complete game history unproven"})
        write_json(stage/"metadata-report.json",{"inputs":catalog.inputs,"titleCoverage":dict(metadata_coverage),
            "mediaReferenceCoverage":dict(media_coverage),"unresolved":catalog.unresolved,
            "sourceStatus":"third-party snapshots; official title and unlock completeness unproven"})
        write_json(stage/"sources.json",{"official":{"observationId":observation["observationId"],"manifestSha256":observation["manifestSha256"],
            "inventorySha256":observation["inventorySha256"],"shards":observation["shards"]},
            "historicalObservationIds":sorted({record["observationId"] for record in chosen.values()}-{observation["observationId"]}),
            "translation":{"identity":translation_identity,"archiveSha256":translation_sha,"license":"no license file in pinned source; private distribution"},
            "metadata":catalog.inputs})
        write_json(collection/"import-manifest.json",{"snapshotId":snapshot_id,"documents":coverage})
        index="# 剧情目录\n\n"+"\n".join(f"- [{r['scriptId']}]({r['path']})" for r in coverage)+"\n"
        atomic_write(collection/"README.md",index.encode())
        write_json(stage/"coverage.json",{"stories":len(coverage),"occurrences":sum(r["occurrences"] for r in coverage),"bodyOccurrences":body_occurrences,"readableStories":readable_stories,"emptyStories":len(coverage)-readable_stories,"unknownStringOccurrences":unknown_strings,
                    "translations":dict(translated),"frameKeys":dict(frame_keys),"controlKeys":dict(control_keys),
                    "historicalSeedsAbsent":sorted(set(source_records)-{r["scriptId"] for r in coverage}),
                    "translationOrphanFiles":[r["path"] for r in orphans],
                    "duplicateTranslationIds":{k:len(v) for k,v in source_records.items() if len(v)>1}})
        with (stage/"assets.jsonl").open("wb") as assets,(stage/"versions.jsonl").open("wb") as versions:
            for path,state in sorted(history.items()):
                counter=state["sourceVersion"]
                aid="enza:"+path
                assets.write(canonical({"assetId":aid,"logicalPath":path,"kind":classify(path),"dependencies":[],"extensions":{}})+b"\n")
                record=fetched.get(path)
                reps=[]
                if record:
                    reps=[{"representationId":"sha256:"+record["decodedSha256"],"role":"decoded","sha256":record["decodedSha256"],
                           "size":record["decodedBytes"],"mediaType":"application/json","locator":"originals/"+path.removeprefix("json/"),
                           "inputs":[record["rawSha256"]],"tool":"official-v1"}]
                versions.write(canonical({"assetId":aid,"observationId":record["observationId"] if record else state["observationId"],"sourceVersion":record["sourceVersion"] if record else counter,
                    "firstSeen":state["firstSeen"],"lastSeen":state["lastSeen"],"presence":state["presence"],
                    "availability":"available" if record else "inventoried","representations":reps,
                    "provenance":{"source":"official","identity":record["observationId"] if record else state["observationId"],"evidence":["inventory-observation:"+state["observationId"]]}})+b"\n")
        entries=[]
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                data=path.read_bytes()
                entries.append({"path":path.relative_to(stage).as_posix(),"size":len(data),"sha256":sha(data)})
        manifest={"schemaVersion":"1.0.0","snapshotId":snapshot_id,"releaseSequence":sequence,"publicationRevision":revision,
                  "observedAt":observation["endedAt"],"builtAt":identity["builtAt"],"source":{"observationId":observation["observationId"],"version":observation["sourceVersion"],"inventorySha256":observation["inventorySha256"],"inventoryCount":len(observation["resources"]),"consistency":"observation-window"},
                  "inputs":inputs,"capabilities":["story.original-json","story.occurrences","story.translation","catalog.partial","asset.inventory"],
                  "scope":{"selector":"json/**/*.json except json/support_skills/**","selected":observation["selected"],"stories":len(coverage),"historicalStories":len(chosen)-observation["selected"],"historicalCatalogOnly":[p for p in history if selected(p) and p not in chosen],"archiveInventoryCount":len(history),"media":"inventory-only","visibility":"private","historicalCompleteness":"unproven"},
                  "baseline":None,"predecessor":None,"validation":{"unresolvedMetadata":True,"unknownControl":"preserved"},"files":entries}
        if len(coverage)!=len(chosen): raise ValueError("build_scope_mismatch")
        write_json(stage/"snapshot.json",manifest)
        result=validate_tree(stage)
        os.replace(stage,output)
    return result
