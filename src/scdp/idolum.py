"""Compatibility preview for idolum's current Line/Episode boundary.

The full graph is a separate sidecar. This preview does not import production data
or assert that mutually exclusive lines are one character's experienced history.
"""
import ast
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


def preview(story, translations, character_map=None):
    character_map = character_map or {}
    translated = {r["pointer"]: r for r in translations if r["status"] == "aligned"}
    lines = []
    for occurrence in story["occurrences"]:
        if occurrence["field"] != "text":
            continue
        index = int(occurrence["pointer"].split("/")[1])
        frame = story["frames"][index]
        row = translated.get(occurrence["pointer"])
        lines.append({"speaker": frame.get("speaker") or None, "ja": occurrence["text"], "zh": row["text"] if row else None})
    characters = {entity for speaker in story.get("metadata",{}).get("speakers",[]) for entity in speaker["entityIds"]}
    return {"episode": {"id":story["scriptId"],"category":story["category"],"source":story["scriptId"],"title":story["title"],
                        "cast":sorted({character_map[c] for c in characters if c in character_map}),"lines":lines,
                        "imported_from":"csv" if any(line["zh"] for line in lines) else "json"},
            "branchContext": {"frames":story["frames"],"graph":story.get("graph"),"controls":story["controls"]},
            "policy":"preview-preserve-all; production experience filtering requires a dedicated consumer policy",
            "unmappedCharacters":sorted(characters-set(character_map)),"sourceAssetId":story["assetId"]}


def verify_current_dataclasses(corpus_source, projection):
    # Compile only the trusted repository's two data classes, avoiding application
    # startup, production databases, credentials and model-service dependencies.
    source = ast.parse(Path(corpus_source).read_text())
    classes = [node for node in source.body if isinstance(node,ast.ClassDef) and node.name in ("Line","Episode")]
    if {node.name for node in classes} != {"Line","Episode"}:
        raise ValueError("idolum_dataclass_boundary_missing")
    namespace = {"dataclass":dataclass,"ImportFormat":Literal["csv","json"]}
    exec(compile(ast.Module(body=classes,type_ignores=[]),"<idolum-contract>","exec"),namespace)
    data = dict(projection["episode"])
    data["lines"] = tuple(namespace["Line"](**line) for line in data["lines"])
    data["cast"] = frozenset(data["cast"])
    episode = namespace["Episode"](**data)
    if asdict(episode)["id"] != projection["episode"]["id"] or len(episode.lines) != len(data["lines"]):
        raise ValueError("idolum_contract_mismatch")
    return {"episodeId":episode.id,"lines":len(episode.lines),"translated":episode.translated,"cast":len(episode.cast),
            "branchesPreservedInSidecar":True,"productionActivated":False}
