#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg.json -> kb.sqlite（可查询的 KB 分片 + 中文友好的全文索引）。

KG 管"实体+关系"（导航、多跳）；KB 管"详情+检索"（属性、全文）。
查询前先比对 kg.json 与 sidecar：sha 不一致说明索引是旧的，直接拒查（见 05-pitfalls.md 第 1 条）。

用法:
  python -X utf8 tools/kb_load.py --root .
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DDL = """
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE entities (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL,
  aliases TEXT NOT NULL DEFAULT '', year TEXT,
  source TEXT NOT NULL, source_date TEXT NOT NULL
);
CREATE TABLE edges (
  id TEXT PRIMARY KEY, src TEXT NOT NULL, rel TEXT NOT NULL, dst TEXT NOT NULL,
  evidence_source TEXT NOT NULL, source_date TEXT NOT NULL, confidence TEXT NOT NULL
);
CREATE INDEX idx_edges_src ON edges(src);
CREATE INDEX idx_edges_dst ON edges(dst);
CREATE INDEX idx_entities_type ON entities(type);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    kg_path = root / "output" / "kg.json"
    side_path = root / "output" / "kg.json.sha256"
    db_path = root / "output" / "kb.sqlite"

    data = kg_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    side_digest = side_path.read_text(encoding="utf-8").split()[0]
    if digest != side_digest:
        print(f"FAIL  kg.json 与 sidecar 不一致：{digest[:16]}… vs {side_digest[:16]}…")
        print("      拒绝建库：先重跑 kb_build.py，再 load。")
        return 2

    kg = json.loads(data.decode("utf-8"))
    if db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(db_path)
    con.executescript(DDL)

    # 中文全文索引：默认 unicode61 分词器会把"山谷与齿轮"当整串一个 token，
    # 搜"山谷"命中 0；trigram 分词器支持子串匹配，中文可用。
    fts_mode = "like"
    try:
        con.execute("CREATE VIRTUAL TABLE entity_fts USING fts5(entity_id UNINDEXED, name, aliases, tokenize='trigram')")
        fts_mode = "fts5-trigram"
    except sqlite3.OperationalError:
        try:
            con.execute("CREATE VIRTUAL TABLE entity_fts USING fts5(entity_id UNINDEXED, name, aliases)")
            fts_mode = "fts5-default"
        except sqlite3.OperationalError:
            fts_mode = "like"

    for n in kg["nodes"]:
        aliases = " ".join(n.get("aliases", []))
        con.execute(
            "INSERT INTO entities(id,type,name,aliases,year,source,source_date) VALUES(?,?,?,?,?,?,?)",
            (n["id"], n["type"], n["name"], aliases, n.get("year"), n["source"], n["source_date"]),
        )
        if fts_mode.startswith("fts5"):
            con.execute("INSERT INTO entity_fts(entity_id,name,aliases) VALUES(?,?,?)", (n["id"], n["name"], aliases))

    for e in kg["edges"]:
        con.execute(
            "INSERT INTO edges(id,src,rel,dst,evidence_source,source_date,confidence) VALUES(?,?,?,?,?,?,?)",
            (e["id"], e["from"], e["relation"], e["target"], e["evidence_source"], e["source_date"], e["confidence"]),
        )

    meta = {
        "graph": kg["graph"],
        "schema_version": kg["schema_version"],
        "kg_sha256": digest,
        "fts_mode": fts_mode,
    }
    con.executemany("INSERT INTO meta(k,v) VALUES(?,?)", [(k, str(v)) for k, v in meta.items()])
    con.commit()

    n_ent = con.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    n_edge = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    con.close()

    if n_ent != len(kg["nodes"]) or n_edge != len(kg["edges"]):
        print(f"FAIL  入库数不符：entities {n_ent}/{len(kg['nodes'])}  edges {n_edge}/{len(kg['edges'])}")
        return 1
    print(f"OK    {db_path}")
    print(f"      entities={n_ent} edges={n_edge} fts={fts_mode} kg_sha={digest[:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
