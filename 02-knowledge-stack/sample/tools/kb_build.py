#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEED -> kg.json (+ .sha256 sidecar).

确定性构建：同一份 seed 字节 -> 同一份 kg.json 字节 -> 同一个 sha256。
产物内部不放时间戳（时间写 build_report.json，不进快照），否则每次重跑 sha 都变。
只用标准库，无第三方依赖。

用法:
  python -X utf8 tools/kb_build.py --root .
  python -X utf8 tools/kb_build.py --root . --dry        # 只校验 + 比对，不写盘
  python -X utf8 tools/kb_build.py --root . --out out2   # 输出到别处（干跑用）
"""
import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

# 控制台可能是 cp936（中文 Windows 默认），中文/特殊符号会直接抛 UnicodeEncodeError。
# 输出固定 UTF-8 并允许替换：判据不变，但别人照 README 跑不会崩在编码上。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REQUIRED_EDGE = ["from", "relation", "target", "evidence_source", "source_date", "confidence"]


def read_csv(path: Path):
    # utf-8-sig: 吃掉 Excel 另存 CSV 时塞进去的 BOM，否则第一列表头会变成 '\ufeffentity_id'
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]
        return [r for r in rows if any(r.values())]


def load_schema(root: Path):
    with open(root / "schema.json", "r", encoding="utf-8") as f:
        return json.load(f)


def split_aliases(raw: str):
    return [x.strip() for x in (raw or "").split("|") if x.strip()]


def build(root: Path):
    schema = load_schema(root)
    id_re = re.compile(schema["id_pattern"])
    errors, warnings = [], []

    # ---------- 节点 ----------
    nodes = []
    seen_ids = set()
    for i, row in enumerate(read_csv(root / "seed" / "nodes.csv"), start=2):
        ent_id, ent_type = row.get("entity_id", ""), row.get("type", "")
        where = f"nodes.csv:{i} ({ent_id or '?'})"
        if not id_re.match(ent_id):
            errors.append(f"{where} id 不符合 id_pattern")
        if ent_id in seen_ids:
            errors.append(f"{where} 重复 id")
        seen_ids.add(ent_id)
        if ent_type not in schema["entity_types"]:
            errors.append(f"{where} 未声明的实体类型 {ent_type!r}")
            continue
        for field in schema["entity_types"][ent_type]["required"]:
            csv_col = "entity_id" if field == "id" else field   # schema 用 id，CSV 列名是 entity_id
            if not row.get(csv_col):
                errors.append(f"{where} 必填字段缺失: {field}")
        if row.get("source_date"):
            if row["source_date"] != schema["date_unknown_placeholder"] and not DATE_RE.match(row["source_date"]):
                errors.append(f"{where} source_date 格式须为 YYYY-MM-DD: {row['source_date']!r}")
        node = {
            "id": ent_id,
            "type": ent_type,
            "name": row.get("name", ""),
            "aliases": split_aliases(row.get("aliases", "")),
            "source": row.get("source", ""),
            "source_date": row.get("source_date", ""),
        }
        if row.get("year"):
            node["year"] = row["year"]
        nodes.append(node)

    # ---------- 边 ----------
    edges = []
    seen_edges = set()
    known = {n["id"]: n["type"] for n in nodes}
    for i, row in enumerate(read_csv(root / "seed" / "edges.csv"), start=2):
        src, rel, dst = row.get("from", ""), row.get("relation", ""), row.get("target", "")
        where = f"edges.csv:{i} ({src} -{rel}-> {dst})"
        for field in REQUIRED_EDGE:
            if not row.get(field):
                errors.append(f"{where} 必填字段缺失: {field}")
        if rel not in schema["relation_types"]:
            errors.append(f"{where} 未声明的关系类型 {rel!r}")
            continue
        if src not in known or dst not in known:
            errors.append(f"{where} 悬空引用（引用了不存在的实体）")
            continue
        spec = schema["relation_types"][rel]
        if known[src] not in spec["from"] or known[dst] not in spec["to"]:
            errors.append(f"{where} 端点类型不合规: {known[src]} -{rel}-> {known[dst]}")
        key = (src, rel, dst)
        if key in seen_edges:
            errors.append(f"{where} 重复边")
        seen_edges.add(key)
        if src == dst:
            warnings.append(f"{where} 自环边")
        if row.get("confidence") not in schema["confidence"]:
            errors.append(f"{where} confidence 不在允许集合: {row.get('confidence')!r}")
        if row.get("source_date") == schema["date_unknown_placeholder"]:
            warnings.append(f"{where} 来源日期未知，按 unknown 记")
        # 起点用 from、出处用 evidence_source：不要都叫 source，否则一个键两种含义
        edges.append({
            "id": f"e:{src}|{rel}|{dst}",
            "from": src,
            "relation": rel,
            "target": dst,
            "evidence_source": row.get("evidence_source", ""),
            "source_date": row.get("source_date", ""),
            "confidence": row.get("confidence", ""),
        })

    kg = {
        "schema_version": schema["schema_version"],
        "graph": schema["graph"],
        "nodes": sorted(nodes, key=lambda n: n["id"]),
        "edges": sorted(edges, key=lambda e: (e["from"], e["relation"], e["target"])),
    }
    return kg, errors, warnings


def canonical_bytes(kg) -> bytes:
    # 确定性三件套：sort_keys + 固定缩进 + LF 结尾 + UTF-8 无 BOM
    return (json.dumps(kg, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sidecar_text(digest: str, filename: str) -> str:
    # 与 sha256sum 的输出格式一致：'<hex>  <filename>\n'
    return f"{digest}  {filename}\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="output")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--allow-warn", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out

    kg, errors, warnings = build(root)
    for w in warnings:
        print(f"WARN  {w}")
    if errors:
        for e in errors:
            print(f"FAIL  {e}")
        print(f"\n构建中止：{len(errors)} 个错误。修 seed 或 schema，不要改生成器绕过。")
        return 2
    if warnings and not args.allow_warn:
        print(f"\n构建中止：{len(warnings)} 个告警。确认后用 --allow-warn 放行。")
        return 2

    data = canonical_bytes(kg)
    digest = sha256_hex(data)
    kg_path = out / "kg.json"
    side_path = out / "kg.json.sha256"

    counts = {
        "nodes": len(kg["nodes"]),
        "edges": len(kg["edges"]),
        "by_type": {t: sum(1 for n in kg["nodes"] if n["type"] == t) for t in sorted({n["type"] for n in kg["nodes"]})},
    }

    if args.dry:
        prev = None
        if kg_path.exists():
            prev = kg_path.read_bytes()
            same = prev == data
            print(f"DRY  previous sha={sha256_hex(prev)[:16]}…  new sha={digest[:16]}…  字节相同={same}")
        else:
            print("DRY  目标不存在（首次构建按新增处理）")
        print(f"DRY  would write {len(data)} bytes  nodes={counts['nodes']} edges={counts['edges']}")
        return 0

    out.mkdir(parents=True, exist_ok=True)
    # 二进制写：避免 Windows 文本模式把 \n 翻成 \r\n 导致 sha 对不上
    # 原子替换：先写 .tmp 再 os.replace，避免中途崩溃留下截断的 kg.json
    import os
    tmp = kg_path.with_name("kg.json.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, kg_path)
    side_tmp = side_path.with_name("kg.json.sha256.tmp")
    side_tmp.write_bytes(sidecar_text(digest, "kg.json").encode("utf-8"))
    os.replace(side_tmp, side_path)

    report = {
        "graph": kg["graph"],
        "schema_version": kg["schema_version"],
        "counts": counts,
        "sha256": digest,
        "bytes": len(data),
        "warnings": warnings,
    }
    (out / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"OK    {kg_path}")
    print(f"      sha256 {digest}")
    print(f"      nodes={counts['nodes']} edges={counts['edges']} {counts['by_type']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
