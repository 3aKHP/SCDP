"""Actual MCP protocol audit, run in an environment with MCP-KB client dependencies.

Authentication is injected from a token file. Neither credentials nor content are
written to the report; original documents remain in the private package directory.
"""
import argparse
import asyncio
import json
import re
from pathlib import Path

from .build import COLLECTION
from .core import sha, write_json


def result_value(result):
    if result.isError:
        raise ValueError("kb_tool_error")
    value = result.structuredContent
    if value is None:
        parts = [part.text for part in result.content if getattr(part, "type", None) == "text"]
        text = "\n".join(parts)
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = text
    if isinstance(value, dict) and value.get("isError"):
        raise ValueError("kb_tool_result_error")
    return value


async def probe(url, token_file, bundle, report, *, page_lines=1000):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    import httpx
    bundle = Path(bundle)
    manifest = json.loads((bundle/"collection/import-manifest.json").read_bytes())
    # Operational credential use; keep it entirely outside logs and reports.
    token = next(line.strip().removeprefix("Bearer ") for line in Path(token_file).read_text().splitlines() if line.strip() and not line.lstrip().startswith("#"))
    calls = pages = lines_read = 0
    samples = {}
    stories = {}
    for line in (bundle/"stories.jsonl").open():
        story = json.loads(line)
        category = story["category"]
        if category not in samples:
            samples[category] = story["scriptId"]
        if any(key in story["scriptId"] for key in ("100100308", "201502201", "180300102", "109900601", "302402101")):
            samples[story["scriptId"]] = story["scriptId"]
        if story["scriptId"] in samples.values():
            stories[story["scriptId"]] = story
    chinese = {}
    for line in (bundle/"translations.jsonl").open():
        row = json.loads(line)
        category = row["scriptId"].split("/")[0]
        if row["status"] == "aligned" and row["text"] and category not in chinese:
            chinese[category] = (row["scriptId"], row["text"])
    report_path = Path(report)
    document_receipts = []
    async with httpx.AsyncClient(headers={"Authorization": "Bearer "+token}, timeout=60) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                async def call(name, args):
                    nonlocal calls
                    calls += 1
                    return result_value(await session.call_tool(name, args))

                listing = await call("kb_list_collections", {})
                if COLLECTION not in {c["id"] for c in listing["collections"]}:
                    raise ValueError("kb_collection_not_visible")
                tree = await call("kb_tree", {"path": "collections/"+COLLECTION, "depth": 2, "max_entries": 50})
                if "docs" not in str(tree):
                    raise ValueError("kb_tree_missing_docs")
                for doc in manifest["documents"]:
                    path = "collections/"+COLLECTION+"/"+doc["path"]
                    source = (bundle/"collection"/doc["path"]).read_bytes()
                    if sha(source) != doc["sha256"]:
                        raise ValueError("probe_input_digest_mismatch")
                    expected = source.decode("utf-8").splitlines()
                    start = 1
                    while start <= len(expected):
                        part = await call("kb_cat", {"path": path, "start_line": start, "max_lines": page_lines})
                        if part["path"] != path or part["start_line"] != start or part["end_line"] < start or part["total_lines"] != len(expected):
                            raise ValueError("kb_cat_range_mismatch")
                        end = part["end_line"]
                        if end > len(expected) or part["text"] != "\n".join(expected[start-1:end]):
                            raise ValueError("kb_cat_body_mismatch")
                        pages += 1
                        lines_read += end-start+1
                        start = end+1
                        if bool(part["truncated"]) != (start <= len(expected)):
                            raise ValueError("kb_cat_truncation_mismatch")
                    document_receipts.append({"scriptId": doc["scriptId"], "sha256": doc["sha256"], "lines": len(expected)})
                    if len(document_receipts) % 100 == 0:
                        write_json(report_path.with_suffix(".checkpoint.json"), {"snapshotId": manifest["snapshotId"], "documentsRead": len(document_receipts), "pages": pages, "complete": False})
                queries = []
                query_inputs = []
                for sid in sorted(set(samples.values())):
                    story = stories[sid]
                    texts = [o["text"] for o in story["occurrences"] if o["field"] in ("text", "select")]
                    query_inputs.append((sid, "ja", "\n".join(texts)))
                query_inputs.extend((sid, "zh-Hans", text) for sid, text in chinese.values())
                for sid, language, text in query_inputs:
                    candidates = re.findall(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u9fff]{3,}", text)
                    if not candidates:
                        continue
                    query = max(candidates, key=len)[:12]
                    result = await call("kb_search", {"query": query, "collection": COLLECTION, "limit": 5})
                    if not result["results"]:
                        raise ValueError("kb_search_no_sample_hit")
                    hit = result["results"][0]
                    if not hit["path"].startswith("collections/"+COLLECTION+"/"):
                        raise ValueError("kb_search_wrong_collection")
                    chunk = await call("kb_read_chunk", {"chunk_id": hit["chunk_id"]})
                    start, end = hit["line_range"]
                    excerpts = []
                    while start <= end:
                        excerpt = await call("kb_cat", {"path": hit["path"], "start_line": start, "max_lines": min(1000, end-start+1)})
                        if excerpt["end_line"] < start or excerpt["end_line"] > end:
                            raise ValueError("kb_chunk_range_mismatch")
                        excerpts.append(excerpt["text"])
                        start = excerpt["end_line"]+1
                    if chunk.get("text", "").strip() != "\n".join(excerpts).strip():
                        raise ValueError("kb_chunk_read_mismatch")
                    path = "collections/"+COLLECTION+"/docs/"+sid+".md"
                    await call("kb_outline", {"path": path, "max_items": 200})
                    lexical = await call("kb_grep", {"pattern": re.escape(query), "path_prefix": path, "limit": 5})
                    if not lexical.get("results"):
                        raise ValueError("kb_grep_no_sample_hit")
                    queries.append({"scriptId": sid, "language": language, "querySha256": sha(query.encode()), "search": True, "chunk": True, "grep": True})
    result = {"snapshotId": manifest["snapshotId"], "documentsRead": len(document_receipts), "pages": pages,
              "linesRead": lines_read, "calls": calls, "documents": document_receipts, "samples": queries,
              "transport": "MCP streamable HTTP", "complete": len(document_receipts) == len(manifest["documents"])}
    write_json(report_path, result)
    return {k: v for k, v in result.items() if k not in ("documents", "samples")}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True)
    p.add_argument("--token-file", required=True)
    p.add_argument("--bundle", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--page-lines", type=int, default=1000)
    args = p.parse_args()
    print(json.dumps(asyncio.run(probe(args.url, args.token_file, args.bundle, args.report, page_lines=args.page_lines))))


if __name__ == "__main__":
    main()
