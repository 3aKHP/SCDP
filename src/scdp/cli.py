import argparse
import json
from .core import job_lock
from .build import build, decode_all
from .package import pack, publish, publish_plan, validate_tree
from .fetch import Downloader
from .official import ASSETS_URL
from .pipeline import discover, fetch_stories, load_observation


def main():
    parser = argparse.ArgumentParser(description="SCDP text archive pipeline")
    parser.add_argument("--work", default="work/scdp")
    parser.add_argument("--budget", type=int, default=1024**3)
    parser.add_argument("--rate", type=float, default=1.0)
    sub = parser.add_subparsers(dest="command", required=True)
    discovery = sub.add_parser("discover", help="freeze official all-type inventory")
    discovery.add_argument("--base", default=ASSETS_URL)
    discovery.add_argument("--audit", action="store_true", help="revalidate every shard")
    for name in ("fetch", "resume"):
        p = sub.add_parser(name, help="acquire selected text using persistent checkpoints")
        p.add_argument("--workers", type=int, default=2)
        p.add_argument("--limit", type=int)
        p.add_argument("--sample", action="store_true", help="one sample per category plus branch/failure/new-card representatives")
    sub.add_parser("status", help="report the cumulative request ledger")
    sub.add_parser("decode", help="project all archived stories offline")
    builder = sub.add_parser("build", help="build the complete text collection offline")
    builder.add_argument("--output", required=True)
    builder.add_argument("--translations")
    builder.add_argument("--metadata", help="directory of pinned public metadata responses")
    builder.add_argument("--translation-identity", default="absent")
    builder.add_argument("--sequence", type=int, default=1)
    builder.add_argument("--revision", type=int, default=0)
    check = sub.add_parser("validate", help="verify package tree file set and digests")
    check.add_argument("directory")
    package = sub.add_parser("package", help="create an immutable text archive")
    package.add_argument("directory")
    package.add_argument("--output", required=True)
    for name in ("publish-plan", "publish"):
        p = sub.add_parser(name, help="plan or publish to a private filesystem target")
        p.add_argument("archive")
        p.add_argument("--destination", required=True)
    kb = sub.add_parser("kb-stage", help="validate and install through MCP-KB native CLI in isolation")
    kb.add_argument("bundle")
    kb.add_argument("--kb-root", required=True)
    kb.add_argument("--python", required=True)
    kb.add_argument("--output", required=True)
    kb.add_argument("--base-sources", help="clone and preserve an existing source tree")
    activate = sub.add_parser("kb-activate", help="switch verified sources and index during a service maintenance window")
    activate.add_argument("candidate")
    activate.add_argument("--sources", required=True)
    activate.add_argument("--index", required=True)
    activate.add_argument("--recovery", required=True)
    activate.add_argument("--service", required=True)
    activate.add_argument("--deployment-lock")
    rollback = sub.add_parser("kb-rollback", help="restore the previous complete source and index pair")
    rollback.add_argument("--recovery", required=True)
    rollback.add_argument("--service", required=True)
    rollback.add_argument("--deployment-lock")
    recover = sub.add_parser("kb-recover", help="recover an interrupted source/index switch from its journal")
    recover.add_argument("--recovery", required=True)
    recover.add_argument("--activation-id", required=True)
    recover.add_argument("--service", required=True)
    recover.add_argument("--deployment-lock")
    tick = sub.add_parser("cycle", help="run one locked, budgeted discovery/build/publication cycle")
    tick.add_argument("--config", required=True)
    args = parser.parse_args()
    if args.command == "cycle":
        from pathlib import Path
        from .cycle import cycle
        print(json.dumps(cycle(json.loads(Path(args.config).read_bytes())),ensure_ascii=False,sort_keys=True))
        return
    with job_lock(args.work):
        downloader = Downloader(args.work, budget=args.budget, rate=args.rate)
        try:
            if args.command == "discover":
                result = discover(downloader, args.base, audit=args.audit)
                result = {k: v for k, v in result.items() if k not in ("resources", "shards", "manifest")}
            elif args.command in ("fetch", "resume"):
                result = fetch_stories(downloader, load_observation(args.work), workers=args.workers, limit=args.limit, sample=args.sample)
            elif args.command == "kb-activate":
                from .activation import activate
                result = activate(args.candidate, args.sources, args.index, args.recovery, service=args.service, deployment_lock=args.deployment_lock)
            elif args.command == "kb-recover":
                from .activation import recover_switch
                result = recover_switch(args.recovery,args.activation_id,service=args.service,deployment_lock=args.deployment_lock)
            elif args.command == "kb-rollback":
                from .activation import rollback
                result = rollback(args.recovery, service=args.service, deployment_lock=args.deployment_lock)
            elif args.command == "kb-stage":
                from .kb import stage
                result = stage(args.bundle, args.kb_root, args.python, args.output, args.base_sources)
            elif args.command == "decode":
                result = decode_all(args.work)
            elif args.command == "build":
                result = build(args.work, args.output, translations=args.translations, translation_identity=args.translation_identity, metadata=args.metadata, sequence=args.sequence, revision=args.revision)
            elif args.command == "validate":
                result = validate_tree(args.directory)
            elif args.command == "package":
                result = pack(args.directory, args.output)
            elif args.command == "publish-plan":
                result = publish_plan(args.archive, args.destination)
            elif args.command == "publish":
                result = publish(args.archive, args.destination)
            else:
                result = downloader.status()
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            if result.get("complete") is False:
                raise SystemExit(2)
        finally:
            downloader.close()


if __name__ == "__main__":
    main()
