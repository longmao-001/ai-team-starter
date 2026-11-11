#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史扫描：不只扫工作区，逐提交扫。

为什么必须有这个
----------------
工作区干净不等于仓库干净。一次"先 push、后扫出命中、再修工作区"，
修的是**最新那一版**；旧版本还躺在历史里，任何人 `git clone` 都能翻到。

本脚本对 `git rev-list --all` 的每个提交，读取它当时树里的全部文本 blob
逐行跑同一套规则（与 sanitize_scan.py 同一份规则表，不另抄一套）。

用法
----
    python 90-tooling/scan_history.py
    python 90-tooling/scan_history.py --denylist 90-tooling/rules/denylist.local.txt
    python 90-tooling/scan_history.py --max-commits 0        # 0 = 全部
    python 90-tooling/scan_history.py --json

判读纪律（重要）
----------------
历史命中**不等于**要改写历史。每条命中必须定性：

- **泄露**（真实人名 / 机构 / 可用路径 / 凭据）→ 立刻处理：改 private、清历史、再评估公开
- **无害形态**（示意用省略号、规则文档里的示例写法）→ 记录结论即可，不改写历史

定性结论要写进 CHANGELOG，不写就等于没人定过性。

退出码：0 = 历史无 BLOCK；1 = 有 BLOCK（须逐条定性）；2 = 不是 git 仓库。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# 与 sanitize_scan.py 共用规则表：同一条规则只存一处正文
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sanitize_scan import STRUCTURAL_RULES, BENIGN_DOMAINS, is_text, load_denylist, mask  # noqa: E402


def git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.decode("utf-8", "replace").strip())
    return out.stdout.decode("utf-8", "replace")


def commits(limit: int) -> list[tuple[str, str, str]]:
    """返回 [(sha, 短 sha, 提交标题)]，新→旧。"""
    raw = git("rev-list", "--all", f"--max-count={limit}" if limit else "--all")
    shas = [s for s in raw.split("\n") if s.strip()]
    out = []
    for sha in shas:
        try:
            subj = git("log", "-1", "--format=%s", sha).strip()
        except RuntimeError:
            subj = ""
        out.append((sha, sha[:8], subj))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="逐提交扫描历史（同一套规则）")
    ap.add_argument("--root", default=".", help="git 仓库路径，默认当前目录")
    ap.add_argument("--denylist", help="本地实体名单（默认 <root>/90-tooling/rules/denylist.local.txt）")
    ap.add_argument("--max-commits", type=int, default=0, help="只扫最近 N 个提交，0 = 全部")
    ap.add_argument("--samples", type=int, default=3, help="每类规则最多列几条")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        print(f"[ERR] 不是 git 仓库：{root}", file=sys.stderr)
        return 2

    denylist = Path(args.denylist) if args.denylist else (root / "90-tooling/rules/denylist.local.txt")
    terms = load_denylist(denylist)
    compiled = [(rid, sev, re.compile(rx), note) for rid, sev, rx, note in STRUCTURAL_RULES]

    revs = commits(args.max_commits)
    print("历史扫描（逐提交，与工作区扫描同一套规则）")
    print(f"仓库            : {root}")
    print(f"提交数          : {len(revs)}" + ("（全部）" if not args.max_commits else f"（最近 {args.max_commits}）"))
    print(f"实体名单        : {len(terms)} 条" + ("" if terms else "  ← 未加载，只跑了结构层"))
    print()

    hits: list[dict] = []
    blobs_scanned = 0
    for sha, short, subj in revs:
        try:
            tree = git("ls-tree", "-r", sha)
        except RuntimeError:
            continue
        for line in tree.split("\n"):
            parts = line.split("\t")
            if len(parts) != 2:
                continue
            meta, path = parts
            fields = meta.split()
            if len(fields) < 3 or fields[1] != "blob":
                continue
            if not is_text(Path(path)):
                continue
            blob = fields[2]
            try:
                raw = subprocess.run(["git", "cat-file", "-p", blob], capture_output=True).stdout
            except Exception:
                continue
            blobs_scanned += 1
            text = raw.decode("utf-8-sig", errors="replace")
            for lineno, content in enumerate(text.split("\n"), start=1):
                for rid, sev, rx, note in compiled:
                    for m in rx.finditer(content):
                        if rid == "email" and any(d in m.group(0).lower() for d in BENIGN_DOMAINS):
                            continue
                        hits.append({"commit": short, "subject": subj, "file": path,
                                     "line": lineno, "rule": rid, "sev": sev,
                                     "match": m.group(0), "note": note})
                for cat, term in terms:
                    if term and term.lower() in content.lower():
                        hits.append({"commit": short, "subject": subj, "file": path,
                                     "line": lineno, "rule": f"denylist_{cat}", "sev": "BLOCK",
                                     "match": term, "note": f"实体名单命中（类别 {cat}）"})

    blocks = [h for h in hits if h["sev"] == "BLOCK"]
    warns = [h for h in hits if h["sev"] == "WARN"]

    # 按 文件+规则 聚合：同一处在多个提交里重复出现只报一次，但带上提交数
    def group(items: list[dict]):
        agg: dict[tuple[str, str], dict] = {}
        for h in items:
            key = (h["file"], h["rule"])
            slot = agg.setdefault(key, {"file": h["file"], "rule": h["rule"], "note": h["note"],
                                        "commits": [], "line": h["line"], "match": h["match"]})
            if h["commit"] not in slot["commits"]:
                slot["commits"].append(h["commit"])
        return sorted(agg.values(), key=lambda s: (-len(s["commits"]), s["file"]))

    def dump(title: str, items: list[dict]):
        if not items:
            return
        print(title)
        for g in group(items)[: args.samples * 6]:
            print(f"  {g['rule']:22s} {g['file']}:{g['line']}  <<{mask(g['match'])}>>"
                  f"  出现在 {len(g['commits'])} 个提交：{', '.join(g['commits'][:4])}")
        print()

    print(f"扫描 blob 数     : {blobs_scanned}")
    dump(f"[BLOCK] {len(blocks)} 处（按文件+规则聚合）", blocks)
    dump(f"[WARN] {len(warns)} 处", warns)

    ok = not blocks
    print(f"结论：BLOCK {len(blocks)} / WARN {len(warns)} → "
          + ("历史干净" if ok else "历史有命中，须逐条定性：泄露（清历史）还是无害形态（记录结论）"))
    if not ok:
        print("判读纪律见本脚本头部注释；定性结论写进 CHANGELOG。")

    if args.json:
        print(json.dumps({"pass": ok, "blocks": len(blocks), "warns": len(warns),
                          "commits": len(revs), "blobs": blobs_scanned,
                          "hits": [{**h, "match": mask(h["match"])} for h in blocks[:50]]},
                         ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
