"""One bounded update cycle; scheduling is supplied by a systemd timer."""
import json
import subprocess
import uuid
from pathlib import Path
from .build import build, input_identity
from .catalog import Catalog
from .core import canonical, job_lock, now, sha, write_json
from .fetch import Downloader
from .history import inventory_history, story_records, save_fetch_record
from .official import ASSETS_URL, asset_url, selected, validate_story
from .package import pack, publish
from .pipeline import discover, fetch_stories, load_observation
from .sources import translation_source


def baseline_state(config, root):
    path = root/"cycle-state.json"
    if path.exists():
        return json.loads(path.read_bytes())
    if config.get("seedManifest"):
        manifest = json.loads(Path(config["seedManifest"]).read_bytes())
        inputs = dict(manifest["inputs"])
        inputs.pop("releaseSequence", None)
        inputs.pop("publicationRevision", None)
        return {"inputs": inputs, "snapshotId": manifest["snapshotId"], "releaseSequence": manifest["releaseSequence"],
                "publicationRevision": manifest["publicationRevision"], "rollingCursor": 0}
    return {"rollingCursor": 0}


def cycle(config, *, transport=None):
    root = Path(config["work"])
    report = {"runId": uuid.uuid4().hex, "startedAt": now(), "command": "cycle",
              "configurationSha256": sha(canonical(config)), "scope": "official-current-plus-archived-history",
              "state": "running", "errors": [], "codeCommit": config.get("codeCommit"), "workspaceDiffSha256": config.get("workspaceDiffSha256"), "recovery": "."}
    downloader = None
    try:
        with job_lock(root):
            state = baseline_state(config, root)
            downloader = Downloader(root, budget=config.get("budgetBytes",1024**3), rate=config.get("rate",1), transport=transport)
            previous = load_observation(root) if (root/"current.json").exists() else None
            shard_cursor = state.get("shardCursor",0)
            shard_names = [s["logicalPath"] for s in previous["shards"]] if previous else []
            shard_count = min(config.get("shardChecks",1),len(shard_names))
            audit_shards = [shard_names[(shard_cursor+i)%len(shard_names)] for i in range(shard_count)]
            observation = discover(downloader, config.get("sourceBase",ASSETS_URL),audit_shards=audit_shards)
            state["shardCursor"] = (shard_cursor+shard_count)%max(1,len(shard_names))
            source_changed = previous is None or previous["observationId"] != observation["observationId"]
            if source_changed:
                acquired = fetch_stories(downloader,observation,workers=config.get("workers",2))
                if not acquired["complete"]:
                    raise ValueError("cycle_incomplete_fetch")
            history = inventory_history(root,observation)
            try:
                chosen = story_records(root,observation,history)
            except (ValueError, OSError):
                acquired = fetch_stories(downloader,observation,workers=config.get("workers",2))
                if not acquired["complete"]:
                    raise ValueError("cycle_incomplete_fetch")
                chosen = story_records(root,observation,history)
            current_paths = sorted(path for path in observation["resources"] if selected(path))
            cursor = state.get("rollingCursor",0)
            drift = []
            for offset in range(min(config.get("rollingChecks",1),len(current_paths))):
                path = current_paths[(cursor+offset)%len(current_paths)]
                old = chosen[path]
                version = observation["resources"][path]
                record = downloader.fetch(path,asset_url(path,observation["sourceBase"])+f"?v={version}",validate_story,revalidate=True)
                record.update(sourceVersion=version,observationId=observation["observationId"])
                save_fetch_record(root,observation["observationId"],record)
                if record["rawSha256"] != old["rawSha256"]:
                    drift.append({"path":path,"old":old["rawSha256"],"new":record["rawSha256"]})
                chosen[path] = record
            state["rollingCursor"] = (cursor+min(config.get("rollingChecks",1),len(current_paths)))%max(1,len(current_paths))
            translation, translation_id, translation_receipt = translation_source(config.get("translation"),root/"translation-cache")
            catalog = Catalog({p:s["sourceVersion"] for p,s in history.items()})
            catalog.load(config.get("metadata"))
            inputs = input_identity(observation,history,chosen,catalog,translation,translation_id)
            report.update(observationId=observation["observationId"], inputsSha256=sha(canonical(inputs)),
                          drift=drift, translation=translation_receipt, codeSha256=inputs["codeSha256"])
            if inputs == state.get("inputs"):
                report.update(state="unchanged", snapshotId=state["snapshotId"])
                write_json(root/"cycle-state.json",state)
                return report
            # Before any new publication, independently revalidate every shard.
            after = discover(downloader,config.get("sourceBase",ASSETS_URL),audit=True)
            if after["observationId"] != observation["observationId"]:
                raise ValueError("cycle_source_changed_during_build_window")
            old_inputs = state.get("inputs",{})
            upstream_keys = ("observationId","translationIdentity","translationArchiveSha256","metadataInputs")
            same_upstream = old_inputs and all(old_inputs.get(k)==inputs.get(k) for k in upstream_keys)
            sequence = state.get("releaseSequence",0)+(0 if same_upstream else 1)
            revision = state.get("publicationRevision",0)+1 if same_upstream else 0
            snapshot_id = sha(canonical({**inputs,"releaseSequence":sequence,"publicationRevision":revision}))
            output = root/"builds"/snapshot_id
            result = build(root,output,translations=translation,translation_identity=translation_id,metadata=config.get("metadata"),sequence=sequence,revision=revision)
            if result["snapshotId"] != snapshot_id:
                raise ValueError("cycle_build_inputs_changed")
            archive = root/"packages"/(snapshot_id+".tar.gz")
            packed = pack(output,archive)
            publication = publish(archive,config["destination"])
            report.update(snapshotId=snapshot_id,publication=publication,packageBytes=packed["compressedBytes"],state="published")
            # The command is an operator-configured argv, never shell-interpolated.
            # It stages, audits and activates a consumer; failures retain the prior active pair.
            if config.get("consumerCommand"):
                args = [part.replace("{bundle}",str(output)).replace("{archive}",str(archive)).replace("{snapshotId}",snapshot_id)
                        for part in config["consumerCommand"]]
                completed = subprocess.run(args,capture_output=True,timeout=config.get("consumerTimeout",3600))
                write_json(root/"consumer-receipts"/(report["runId"]+".json"),
                           {"exitCode":completed.returncode,"stdout":completed.stdout.decode(errors="replace"),"stderr":completed.stderr.decode(errors="replace")})
                if completed.returncode:
                    raise ValueError("consumer_activation_failed")
                report["state"] = "activated"
            state.update(inputs=inputs,snapshotId=snapshot_id,releaseSequence=sequence,publicationRevision=revision)
            write_json(root/"cycle-state.json",state)
            return report
    except BaseException as exc:
        report.update(state="failed",errors=[type(exc).__name__+":"+str(exc) if isinstance(exc,ValueError) else type(exc).__name__])
        raise
    finally:
        report["endedAt"] = now()
        if downloader:
            report["ledger"] = downloader.status()
            downloader.close()
        write_json(root/"runs"/(report["runId"]+".json"),report)
