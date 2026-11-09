"""Lossless occurrence projection. Graph evidence never replaces original frames."""
from .core import canonical, sha

READABLE = {"text", "select", "title", "caption", "message"}
CONTROL = {"select", "label", "nextLabel"}
MEDIA = {"voice", "bg", "fg", "bgm", "se", "charId", "charCategory", "charType", "movie"}


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


def project(script_id, frames, raw_sha, decoded_sha):
    occurrences, controls, media = [], [], []
    labels = {}
    for index, frame in enumerate(frames):
        if "label" in frame:
            labels.setdefault(str(frame["label"]), []).append(index)
    for pointer, value in walk(frames):
        field = pointer.rsplit("/",1)[-1]
        if field in READABLE and isinstance(value, str):
            occurrences.append({"pointer":pointer,"field":field,"text":value,"sha256":sha(value.encode())})
    for index, frame in enumerate(frames):
        for key, value in frame.items():
            if key in CONTROL or any(token in key.lower() for token in ("jump","branch","condition","flag","label","select")):
                record = {"pointer":f"/{index}/{key}", "field":key,"raw":value,"status":"unresolved"}
                if key == "nextLabel" and isinstance(value, str):
                    targets = labels.get(value, [])
                    record.update(targets=targets, status="resolved" if len(targets)==1 else "unresolved")
                elif key in ("select", "label") and isinstance(value, str):
                    record["status"] = "preserved"
                controls.append(record)
            if key in MEDIA:
                media.append({"pointer":f"/{index}/{key}","field":key,"raw":value,"assetId":None,"status":"unresolved"})
    return {"scriptId":script_id,"assetId":"enza:json/"+script_id+".json", "rawSha256":raw_sha,
            "decodedSha256":decoded_sha,"category":script_id.split("/")[0],"title":script_id,
            "sourceLanguage":"ja","frames":frames,"occurrences":occurrences,"controls":controls,
            "mediaReferences":media,"unresolvedFields":["officialTitle","characters","card","event","unlockCondition"],
            "metadataProvenance":[]}


def verify_occurrences(story):
    expected = project(story["scriptId"],story["frames"],story["rawSha256"],story["decodedSha256"])["occurrences"]
    if expected != story["occurrences"]:
        raise ValueError("occurrence_coverage_mismatch")
    return len(expected)
