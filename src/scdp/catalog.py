"""Provenanced semantic metadata and inventory-only media references.

Path templates are facts observed in the public game's scenario assetFormat.
Only explicit game metadata fields are projected; application/user state is excluded.
"""
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse
from .core import canonical, safe_path, sha

MEDIA_TEMPLATES = {
    "voice": "sounds/voice/events/{id}.m4a",
    "bg": "images/event/bg/{id}.jpg", "fg": "images/event/fg/{id}.png",
    "middleFg": "images/event/fg/{id}.png", "bgm": "sounds/bgm/{id}.m4a",
    "se": "sounds/se/event/{id}.m4a", "movie": "movies/idols/card/{id}.mp4",
    "still": "images/event/still/{id}.jpg", "textFrame": "images/event/text_frame/{id}.png",
    "gameEventCommunicationMovie": "movies/game_event_communications/{id}.mp4",
    "gameEventCommunicationSe": "sounds/se/game_event_communications/{id}.m4a",
}
SENTINELS = {"", "off", "on", "none", "keep", "stop"}
SPINE_CATEGORY_ALIASES = {"stand_fix": "stand", "stand_flex": "stand", "stand_costume_fix": "stand_costume", "stand_costume_flex": "stand_costume"}


def media_references(frames, inventory):
    result = []
    for index, frame in enumerate(frames):
        values = []
        for key, template in MEDIA_TEMPLATES.items():
            if key in frame:
                value = frame[key]
                path = template.format(id=value) if isinstance(value, str) and value not in SENTINELS else None
                values.append((key, value, path))
        if "charId" in frame:
            value = frame["charId"]
            category = frame.get("charCategory", "stand")
            category = SPINE_CATEGORY_ALIASES.get(category, category)
            path = f"spine/{frame.get('charType', '')}/{category}/{value}/data.json" if frame.get("charType") else None
            values.append(("charId", value, path))
        if "stillId" in frame:
            value = frame["stillId"]
            kind = frame.get("stillType")
            if kind == "game_event_communications":
                values.extend(("stillId", value, template.format(id=value)) for template in
                              (MEDIA_TEMPLATES["gameEventCommunicationMovie"], MEDIA_TEMPLATES["gameEventCommunicationSe"]))
            else:
                path = f"images/content/{kind}/card/{value}.jpg" if kind else None
                values.append(("stillId", value, path))
        for key, value, path in values:
            if path:
                try:
                    safe_path(path)
                except ValueError:
                    path = None
            found = path in inventory if path else False
            result.append({"pointer": f"/{index}/{key}", "field": key, "raw": value,
                           "assetId": "enza:"+path if found else None,
                           "logicalPath": path, "status": "resolved" if found else "sentinel" if isinstance(value, str) and value in SENTINELS else "unresolved",
                           "rule": "client-scenario-asset-format-v1"})
    return result


class Catalog:
    def __init__(self, inventory):
        self.inventory = inventory
        self.entities = {}
        self.relations = []
        self.story_metadata = defaultdict(list)
        self.speaker_aliases = defaultdict(set)
        self.inputs = []
        self.unresolved = []
        self.script_ids = defaultdict(list)
        for path in inventory:
            if path.startswith("json/") and path.endswith(".json"):
                self.script_ids[Path(path).stem].append(path.removeprefix("json/").removesuffix(".json"))

    def entity(self, kind, game_id, name, provenance):
        entity_id = f"enza:{kind}:{game_id}"
        record = {"entityId": entity_id, "kind": kind, "gameId": str(game_id), "name": name or None, "provenance": provenance}
        previous = self.entities.get(entity_id)
        if previous and previous["name"] != record["name"]:
            self.unresolved.append({"kind": "entity_name_conflict", "entityId": entity_id, "candidates": [previous, record]})
        else:
            self.entities[entity_id] = record
        return entity_id

    def relation(self, source, target, kind, provenance, confidence="explicit"):
        self.relations.append({"from": source, "to": target, "type": kind, "confidence": confidence, "provenance": provenance})

    def communication(self, number, title, provenance, *, character=None, card=None, extra=None):
        if not str(number).isdigit():
            return
        matches = self.script_ids.get(str(number), [])
        if len(matches) != 1:
            self.unresolved.append({"kind": "script_lookup", "gameId": str(number), "candidates": matches, "provenance": provenance})
            return
        script_id = matches[0]
        # The metadata supplies the numeric ID; the namespace match is an inventory inference.
        record = {"title": title or None, "characterId": character, "cardId": card,
                  "confidence": "inferred", "provenance": provenance, **(extra or {})}
        self.story_metadata[script_id].append(record)
        story_id = "enza:json/"+script_id+".json"
        if character:
            self.relation(story_id, character, "character_appears_in_story", provenance, "inferred")
        if card:
            self.relation(card, story_id, "card_has_story", provenance, "inferred")

    def ingest(self, source_url, data, digest):
        host = urlparse(source_url).hostname
        if host not in {"api.shinycolors.moe", "cf-static.shinycolors.moe", "metadata.example.test"}:
            raise ValueError("unsupported_metadata_source")
        provenance = {"source": "ShinyColorsDB", "identity": digest, "evidence": [source_url]}
        self.inputs.append({"source": source_url, "sha256": digest})
        if "albumCommunicationTitles" in data:
            character = self.entity("character", data["id"], data.get("name"), provenance)
            for alias in (data.get("name"), data.get("firstName")):
                if alias:
                    self.speaker_aliases[alias.replace(" ", "").replace("　", "")].add(character)
            for group in ("produceIdols", "supportIdols"):
                for card in data.get(group, []):
                    card_id = self.entity("card", card["id"], card.get("name"), provenance)
                    self.relation(card_id, character, "card_belongs_to_character", provenance)
            for costume in data.get("idolCostumes", []):
                costume_id = self.entity("costume", costume["id"], costume.get("name"), provenance)
                self.relation(costume_id, character, "costume_belongs_to_character", provenance)
                if costume.get("idolId"):
                    card_id = self.entity("card", costume["idolId"], costume.get("name"), provenance)
                    self.relation(costume_id, card_id, "costume_belongs_to_card", provenance)
            for row in data.get("communications", []):
                extra = {key: row.get(key) for key in ("albumType", "communicationCategory", "releasedConditionComment", "questionComment")}
                for field in ("communicationId", "failureCommunicationId", "successCommunicationId"):
                    self.communication(row.get(field), row.get("title"), provenance, character=character,
                                       extra={**extra, "routeEvidence": field})
        elif "enzaId" in data and "cardName" in data:
            character = self.entity("character", data["idolId"], (data.get("idol") or {}).get("idolName"), provenance)
            card = self.entity("card", data["enzaId"], data.get("cardName"), provenance)
            self.relation(card, character, "card_belongs_to_character", provenance)
            for group in ("cardSupportEvents", "cardIdolEvents", "cardProduceEvents", "produceEvents"):
                for row in data.get(group, []):
                    self.communication(row.get("eventId"), row.get("eventName") or row.get("eventTitle"), provenance, character=character, card=card)
        else:
            self.unresolved.append({"kind": "unsupported_metadata_shape", "provenance": provenance})

    def load(self, directory):
        if directory is None:
            return
        root = Path(directory)
        candidates = sorted([*root.glob("album[0-9]*.json"), *root.glob("card-*.json")])
        for path in candidates:
            raw = path.read_bytes()
            wrapped = json.loads(raw)
            if not isinstance(wrapped, dict) or not isinstance(wrapped.get("data"), dict):
                raise ValueError("invalid_metadata_wrapper")
            self.ingest(wrapped["url"], wrapped["data"], sha(raw))

    def enrich(self, story, translation_sources=()):
        records = list(self.story_metadata.get(story["scriptId"], []))
        for source in translation_sources:
            records.append({"title": source["title"], "confidence": "explicit",
                            "provenance": {"source": "SCTranslationData", "identity": source["identity"], "evidence": [source["path"]]}})
        titles = sorted({r["title"] for r in records if r.get("title")})
        story["metadata"] = {"candidates": records, "titleCandidates": titles,
                             "titleStatus": "unique" if len(titles) == 1 else "conflict" if titles else "unresolved"}
        if len(titles) == 1:
            story["title"] = titles[0]
        speakers = []
        for raw in sorted({f["speaker"] for f in story["frames"] if isinstance(f.get("speaker"), str)}):
            parts = [p.replace(" ", "").replace("　", "") for p in re.split(r"[＆&、]", raw)]
            candidates = [self.speaker_aliases.get(part, set()) for part in parts]
            matches = sorted(set().union(*candidates)) if candidates else []
            status = "resolved" if candidates and all(len(c)==1 for c in candidates) else "ambiguous" if any(len(c)>1 for c in candidates) else "unresolved"
            speakers.append({"raw":raw,"entityIds":matches,"status":status})
            if status == "resolved":
                for entity_id in matches:
                    source = self.entities[entity_id]["provenance"]
                    provenance = {"source":"official+ShinyColorsDB","identity":sha(canonical([story["decodedSha256"],source["identity"]])),
                                  "evidence":["speaker-name-match",source["identity"],story["decodedSha256"]]}
                    self.relation(story["assetId"],entity_id,"character_speaks_in_story",provenance,"inferred")
        story["metadata"]["speakers"] = speakers
        story["metadataProvenance"] = [r["provenance"] for r in records]
        story["mediaReferences"] = media_references(story["frames"], self.inventory)
        return story
