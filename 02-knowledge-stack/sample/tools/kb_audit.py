#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布前体检：五项计数 + sidecar 核对 + 悬空/重复/孤立 + 出处完整性。

输出 output/audit.json，有任何 FAIL 则退出码 1（CI / 发布门直接用它）。
"报 PASS 必有证据"：这份 JSON 就是证据，路径+sha+计数都在里面。

用法:
  python -X utf8 tools/kb_audit.py --root .
  python -X utf8 tools/kb_audit.py --root . --expect-nodes 17 --expect-edges 17
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--expect-nodes", type=int, default=None)
    ap.add_argument("--expect-edges", type=int, default=None)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    kg_path = root / "output" / "kg.json"
    side_path = root / "output" / "kg.json.sha256"
    checks = []

    def check(name, ok, detail):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
        return ok

    if not check("kg.json 存在", kg_path.exists(), str(kg_path)):
        print("\n".join(f"{c['status']}  {c['check']}: {c['detail']}" for c in checks))
        return 1

    data = kg_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()

    side_ok = side_path.exists()
    side_digest = ""
    if side_ok:
        parts = side_path.read_text(encoding="utf-8").split()
        side_digest = parts[0] if parts else ""
        check("sidecar 格式", len(parts) == 2 and parts[1] == "kg.json", str(parts))
    check("sidecar 存在", side_ok, "kg.json.sha256")
    check("sha256 逐字节一致", digest == side_digest, f"computed={digest} sidecar={side_digest}")

    kg = json.loads(data.decode("utf-8"))
    nodes, edges = kg["nodes"], kg["edges"]
    ids = [n["id"] for n in nodes]
    check("节点数", True, f"{len(nodes)}")
    check("边数", True, f"{len(edges)}")
    if args.expect_nodes is not None:
        check("节点数=预注册", len(nodes) == args.expect_nodes, f"actual={len(nodes)} expect={args.expect_nodes}")
    if args.expect_edges is not None:
        check("边数=预注册", len(edges) == args.expect_edges, f"actual={len(edges)} expect={args.expect_edges}")

    dup_ids = len(ids) - len(set(ids))
    check("无重复实体 id", dup_ids == 0, f"dups={dup_ids}")

    ekeys = [(e["from"], e["relation"], e["target"]) for e in edges]
    dup_edges = len(ekeys) - len(set(ekeys))
    check("无重复边", dup_edges == 0, f"dups={dup_edges}")

    known = set(ids)
    dangling = [e["id"] for e in edges if e["from"] not in known or e["target"] not in known]
    check("无悬空引用", not dangling, f"dangling={len(dangling)}")

    deg = {i: 0 for i in ids}
    for e in edges:
        if e["from"] in deg:
            deg[e["from"]] += 1
        if e["target"] in deg:
            deg[e["target"]] += 1
    orphans = [i for i, d in deg.items() if d == 0]
    check("无孤立节点", not orphans, f"orphans={orphans}")

    bad_src = [n["id"] for n in nodes if not n.get("source")]
    check("节点都带出处", not bad_src, f"missing={len(bad_src)}")
    bad_edge_src = [e["id"] for e in edges if not e.get("evidence_source")]
    check("边都带出处", not bad_edge_src, f"missing={len(bad_edge_src)}")
    bad_date = [n["id"] for n in nodes if not DATE_RE.match(n.get("source_date", ""))]
    bad_date += [e["id"] for e in edges if not DATE_RE.match(e.get("source_date", ""))]
    check("出处日期格式 YYYY-MM-DD", not bad_date, f"bad={len(bad_date)}")

    by_type = {}
    for n in nodes:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    by_rel = {}
    for e in edges:
        by_rel[e["relation"]] = by_rel.get(e["relation"], 0) + 1

    report = {
        "graph": kg["graph"],
        "schema_version": kg["schema_version"],
        "kg_path": str(kg_path),
        "kg_sha256": digest,
        "sidecar_path": str(side_path),
        "counts": {"nodes": len(nodes), "edges": len(edges), "by_type": by_type, "by_relation": by_rel},
        "orphans": orphans,
        "dangling": dangling,
        "verdict": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
        "checks": checks,
    }
    out = root / "output" / "audit.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    for c in checks:
        print(f"{c['status']:4}  {c['check']}: {c['detail']}")
    print(f"\n{report['verdict']}  {out}")
    print(f"sha256 {digest}  nodes={len(nodes)} edges={len(edges)}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
