#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查询器：按名/别名/ID 检索 + 多跳邻居，并把每一次查询写进 query_log.jsonl。

记账四字段（IT 硬规第 3 条）：query / graph / snapshot_sha / hits，外加 ts。
零命中也要写：0 命中 = 策展缺口，不是"没查过"。

用法:
  python -X utf8 tools/kbq.py --root . --q 山谷
  python -X utf8 tools/kbq.py --root . --q 技术伦理 --engine fts
  python -X utf8 tools/kbq.py --root . --id Book:b-01 --neighbors 1
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

RANK = {"name_exact": 100, "alias_exact": 90, "name_prefix": 80, "alias_prefix": 70, "name_sub": 50, "alias_sub": 40}


def read_meta(con):
    return dict(con.execute("SELECT k, v FROM meta").fetchall())


def log_row(path: Path, record: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    # ensure_ascii=False：中文检索式必须原样落盘，否则 grep 不到（见 05-pitfalls.md 第 5 条）
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def search_like(con, q):
    rows = con.execute(
        "SELECT id,type,name,aliases,year,source_date FROM entities "
        "WHERE id = ? OR name LIKE ? OR aliases LIKE ?",
        (q, f"%{q}%", f"%{q}%"),
    ).fetchall()
    out = []
    for ent_id, ent_type, name, aliases, year, sdate in rows:
        alias_list = aliases.split(" ") if aliases else []
        if q == name:
            matched, score = "name_exact", RANK["name_exact"]
        elif q in alias_list:
            matched, score = "alias_exact", RANK["alias_exact"]
        elif name.startswith(q):
            matched, score = "name_prefix", RANK["name_prefix"]
        elif any(a.startswith(q) for a in alias_list):
            matched, score = "alias_prefix", RANK["alias_prefix"]
        elif q in name:
            matched, score = "name_sub", RANK["name_sub"]
        else:
            matched, score = "alias_sub", RANK["alias_sub"]
        out.append({"id": ent_id, "type": ent_type, "name": name, "year": year,
                    "source_date": sdate, "matched_on": matched, "score": score})
    return out


def search_fts(con, q):
    # trigram 分词器只能匹配 >=3 字符的检索词；2 字中文会命中 0（真实坑，见 05-pitfalls.md 第 8 条）
    try:
        rows = con.execute(
            "SELECT e.id,e.type,e.name,e.year,e.source_date FROM entity_fts f "
            "JOIN entities e ON e.id = f.entity_id WHERE entity_fts MATCH ?",
            (f'"{q}"',),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"id": r[0], "type": r[1], "name": r[2], "year": r[3], "source_date": r[4],
             "matched_on": "fts", "score": RANK["name_exact"]} for r in rows]


def neighbors(con, ent_id, depth):
    seen = {ent_id}
    frontier = {ent_id}
    hops = []
    for d in range(1, depth + 1):
        nxt = set()
        for e in frontier:
            for src, rel, dst in con.execute(
                "SELECT src,rel,dst FROM edges WHERE src = ? OR dst = ?", (e, e)
            ).fetchall():
                other = dst if src == e else src
                direction = "out" if src == e else "in"
                hops.append({"depth": d, "from": e, "relation": rel, "to": other, "direction": direction})
                if other not in seen:
                    nxt.add(other)
        seen |= nxt
        frontier = nxt
        if not frontier:
            break
    names = {r[0]: r[1] for r in con.execute(
        f"SELECT id,name FROM entities WHERE id IN ({','.join('?' * len(seen))})", tuple(seen)
    ).fetchall()}
    for h in hops:
        h["to_name"] = names.get(h["to"], h["to"])
    return hops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--q", default=None)
    ap.add_argument("--id", default=None)
    ap.add_argument("--neighbors", type=int, default=0)
    ap.add_argument("--engine", choices=["like", "fts"], default="like")
    ap.add_argument("--log", default="query_log.jsonl")
    ap.add_argument("--allow-stale", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    db_path = root / "output" / "kb.sqlite"
    side_path = root / "output" / "kg.json.sha256"
    if not db_path.exists():
        print("FAIL  kb.sqlite 不存在：先跑 kb_build.py 再跑 kb_load.py")
        return 2

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    meta = read_meta(con)
    live_sha = meta.get("kg_sha256", "")

    # 查询前守门：索引里的 sha 必须等于当前快照 sha，否则拒绝查询（STALE_INDEX）
    if side_path.exists():
        side_sha = side_path.read_text(encoding="utf-8").split()[0]
        if side_sha != live_sha and not args.allow_stale:
            print(f"STALE_INDEX  kb.sqlite 建于 {live_sha[:16]}…，当前快照是 {side_sha[:16]}…")
            print("             索引过期，拒绝查询。重跑 kb_load.py。")
            return 3

    if args.id:
        mode, query_text = "id", args.id
        rows = con.execute(
            "SELECT id,type,name,year,source_date FROM entities WHERE id = ?", (args.id,)
        ).fetchall()
        results = [{"id": r[0], "type": r[1], "name": r[2], "year": r[3],
                    "source_date": r[4], "matched_on": "id", "score": 100} for r in rows]
    elif args.q:
        mode, query_text = "text", args.q
        results = search_fts(con, args.q) if args.engine == "fts" else search_like(con, args.q)
    else:
        print("FAIL  需要 --q 或 --id")
        return 2

    results.sort(key=lambda r: (-r["score"], r["id"]))
    payload = {
        "query": query_text,
        "mode": mode,
        "engine": args.engine,
        "graph": meta.get("graph"),
        "snapshot_sha": live_sha,
        "fts_mode": meta.get("fts_mode"),
        "hits": len(results),
        "results": results,
    }
    if args.neighbors and results:
        payload["neighbors"] = neighbors(con, results[0]["id"], args.neighbors)
    con.close()

    log_row(root / args.log, {
        "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "query": query_text,
        "mode": mode,
        "engine": args.engine,
        "graph": meta.get("graph"),
        "snapshot_sha": live_sha,
        "hits": len(results),
    })
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
