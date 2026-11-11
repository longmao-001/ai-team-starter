#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端自检：构建 -> 确定性重跑 -> 建库 -> 体检 -> 查询 -> 记账核对。

一次跑完，打印每步 PASS/FAIL 和证据路径。任何一步失败退出码 1。
这是"照做能不能成"的最小验证：别人 clone 后只需运行这一条。

用法:
  python run_demo.py            # 不需要 -X utf8，脚本自己锁 UTF-8 输出
  python -X utf8 run_demo.py    # 等价
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 控制台可能是 cp936（中文 Windows 默认），圈码/中文会直接抛 UnicodeEncodeError。
# 把自身输出固定成 UTF-8 并允许替换，判据不变，但不再因终端编码崩掉。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent
PY = [sys.executable, "-X", "utf8"]
results = []


def sh(args):
    p = subprocess.run(PY + args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def step(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))
    return ok


def main():
    shutil.rmtree(ROOT / "output", ignore_errors=True)
    shutil.rmtree(ROOT / "output2", ignore_errors=True)   # 旧版遗留的干跑目录
    if (ROOT / "query_log.jsonl").exists():
        (ROOT / "query_log.jsonl").unlink()

    code, out = sh(["tools/kb_build.py", "--root", "."])
    step("[01] 构建 kg.json", code == 0, out.strip().splitlines()[-1] if out.strip() else "")
    sha1 = (ROOT / "output" / "kg.json.sha256").read_text(encoding="utf-8").split()[0]

    # 确定性重跑写到系统临时目录，跑完清掉：不在成品树里留第二个 output
    det = Path(tempfile.mkdtemp(prefix="kb_detcheck_"))
    try:
        code, out = sh(["tools/kb_build.py", "--root", ".", "--out", str(det)])
        sha2 = (det / "kg.json.sha256").read_text(encoding="utf-8").split()[0]
        same_bytes = (ROOT / "output" / "kg.json").read_bytes() == (det / "kg.json").read_bytes()
        step("[02] 同一输入重跑 -> 字节与 sha 全等", code == 0 and same_bytes and sha1 == sha2,
             f"sha={sha1[:16]}…")
    finally:
        shutil.rmtree(det, ignore_errors=True)

    code, out = sh(["tools/kb_load.py", "--root", "."])
    step("[03] kg.json -> kb.sqlite", code == 0, out.strip().splitlines()[-1] if out.strip() else "")

    code, out = sh(["tools/kb_audit.py", "--root", ".", "--expect-nodes", "17", "--expect-edges", "17"])
    step("[04] 发布前体检（17/17 预注册）", code == 0, "verdict=PASS")
    audit = json.loads((ROOT / "output" / "audit.json").read_text(encoding="utf-8"))
    step("[05] 体检证据含路径与 sha", audit["kg_sha256"] == sha1 and audit["verdict"] == "PASS", audit["kg_path"])

    code, out = sh(["tools/kbq.py", "--root", ".", "--q", "山谷"])
    q1 = json.loads(out)
    step("[06] 按别名检索命中 1 条", code == 0 and q1["hits"] == 1 and q1["results"][0]["id"] == "Book:b-01",
         f"matched_on={q1['results'][0]['matched_on']}")

    code, out = sh(["tools/kbq.py", "--root", ".", "--q", "科技伦理"])
    q2 = json.loads(out)
    step("[07] 按名检索命中 1 条", code == 0 and q2["hits"] == 1 and q2["results"][0]["id"] == "Topic:t-07",
         f"snippet={q2['results'][0]['name']}")

    code, out = sh(["tools/kbq.py", "--root", ".", "--q", "量子引力"])
    q3 = json.loads(out)
    step("[08] 零命中也被记录（不是'没查过'）", code == 0 and q3["hits"] == 0, f"hits={q3['hits']}")

    code, out = sh(["tools/kbq.py", "--root", ".", "--q", "山谷与齿轮", "--neighbors", "1"])
    q4 = json.loads(out)
    step("[09] 多跳邻居（1 跳）", code == 0 and len(q4.get("neighbors", [])) == 4, f"neighbors={len(q4.get('neighbors', []))}")

    code, out = sh(["tools/kbq.py", "--root", ".", "--q", "山谷", "--engine", "fts"])
    q5 = json.loads(out)
    step("[10] 已知坑复现：trigram FTS 搜 2 字中文命中 0", code == 0 and q5["hits"] == 0, "见 05-pitfalls.md 第 8 条")

    code, out = sh(["tools/rag_context.py", "--root", ".", "--id", "Book:b-01", "--depth", "2"])
    facts = out.count("[d")
    step("[11] RAG 上下文装配（带出处日期）", code == 0 and facts >= 4 and "快照sha=" in out, f"facts={facts}")

    log_lines = [json.loads(x) for x in (ROOT / "query_log.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    required = {"query", "graph", "snapshot_sha", "hits", "ts"}
    schema_ok = all(required <= set(r) for r in log_lines)
    step("[12] 记账 6 行且四字段齐全", len(log_lines) == 6 and schema_ok,
         f"lines={len(log_lines)} keys={sorted(log_lines[0])}")
    step("[13] 记账里的快照 sha 就是快照文件的 sha", all(r["snapshot_sha"] == sha1 for r in log_lines), sha1[:16] + "…")

    ok = all(r[1] for r in results)
    lines = [f"{'PASS' if r[1] else 'FAIL'}  {r[0]}" + (f"  {r[2]}" if r[2] else "") for r in results]
    lines.append(f"\nVERDICT {'PASS' if ok else 'FAIL'}  {sum(1 for r in results if r[1])}/{len(results)}")
    lines.append(f"snapshot_sha {sha1}")
    (ROOT / "output" / "demo_evidence.log").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"\nVERDICT {'PASS' if ok else 'FAIL'}  {sum(1 for r in results if r[1])}/{len(results)}")
    print(f"evidence: {ROOT / 'output' / 'demo_evidence.log'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
