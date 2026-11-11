#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 KG 邻域 + KB 详情拼成一段可塞进模型 prompt 的上下文（最小 RAG）。

输出两段：
  1) 事实块：一行一条关系，带出处与日期（引用可直接核）
  2) 边界声明：告诉模型"块外的东西不要编"

用法:
  python -X utf8 tools/rag_context.py --root . --id Book:b-01 --depth 2
  python -X utf8 tools/rag_context.py --root . --id Book:b-01 --json
"""
import argparse
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--id", required=True)
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log", default="query_log.jsonl")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    db_path = root / "output" / "kb.sqlite"
    if not db_path.exists():
        print("FAIL  kb.sqlite 不存在")
        return 2

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    meta = dict(con.execute("SELECT k,v FROM meta").fetchall())
    row = con.execute("SELECT id,type,name,aliases,year,source,source_date FROM entities WHERE id=?", (args.id,)).fetchone()
    if not row:
        print(f"FAIL  没有这个实体: {args.id}")
        con.close()
        return 1
    ent = {"id": row[0], "type": row[1], "name": row[2], "aliases": row[3].split() if row[3] else [],
           "year": row[4], "source": row[5], "source_date": row[6]}

    facts, seen, frontier = [], {args.id}, {args.id}
    for d in range(1, args.depth + 1):
        nxt = set()
        for node in sorted(frontier):
            name = con.execute("SELECT name FROM entities WHERE id=?", (node,)).fetchone()[0]
            for src, rel, dst in con.execute(
                "SELECT src,rel,dst FROM edges WHERE src=? OR dst=? ORDER BY rel,src,dst", (node, node)
            ).fetchall():
                other = dst if src == node else src
                direction = "→" if src == node else "←"
                facts.append({
                    "depth": d, "subject": name, "direction": direction, "relation": rel,
                    "object": con.execute("SELECT name FROM entities WHERE id=?", (other,)).fetchone()[0],
                    "object_id": other, "source_date": con.execute(
                        "SELECT source_date FROM entities WHERE id=?", (other,)).fetchone()[0],
                })
                if other not in seen:
                    nxt.add(other)
        seen |= nxt
        frontier = nxt
        if not frontier:
            break
    con.close()

    if args.json:
        print(json.dumps({"entity": ent, "facts": facts, "graph": meta.get("graph"),
                          "snapshot_sha": meta.get("kg_sha256"), "depth": args.depth},
                         ensure_ascii=False, indent=2))
    else:
        print(f"[上下文] 图={meta.get('graph')} 快照sha={meta.get('kg_sha256')}")
        print(f"[实体] {ent['type']} {ent['name']} (id={ent['id']}, 出处={ent['source']} {ent['source_date']})")
        if ent["aliases"]:
            print(f"[别名] {' / '.join(ent['aliases'])}")
        for f in facts:
            print(f"  [d{f['depth']}] {f['subject']} {f['direction']} {f['relation']} {f['direction']} "
                  f"{f['object']}  (出处日期 {f['source_date']})")
        print("[边界] 以上是该实体的 1–N 跳邻域；块外未知即说未知，不要补全。")

    # 记账：RAG 装配也是一次查询
    with open(root / args.log, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({
            "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query": args.id, "mode": "rag", "engine": "graph",
            "graph": meta.get("graph"), "snapshot_sha": meta.get("kg_sha256"), "hits": len(facts) + 1,
        }, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
