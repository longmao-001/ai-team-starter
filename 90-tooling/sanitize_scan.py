#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脱敏扫描器（两层规则）。

为什么有两层
------------
公开仓库的脱敏有两类东西要查，性质完全不同：

1. **结构类**（路径、IP、邮箱、密钥、证件号）——规则可以公开，靠正则就能查。
   规则文件本身要进仓库，所以规则文档里出现的示例写法一律带 `sanitize:allow` 标记。
2. **实体类**（真实人名、机构名、项目代号）——**规则本身就是敏感信息**：
   把真名写进仓库的 denylist，等于换个地方泄露。

所以第二层是**本地名单** `90-tooling/rules/denylist.local.txt`，已被 .gitignore 排除。
CI 只能跑第一层；发布门要求本地跑第二层，并把**汇总结果**（命中数，不含原文）贴进回执。

用法
----
    python 90-tooling/sanitize_scan.py --root .
    python 90-tooling/sanitize_scan.py --root . --require-denylist --report scan-report.md
    python 90-tooling/sanitize_scan.py --root . --list-rules

退出码：0 = 无 BLOCK；1 = 有 BLOCK（不许发布）；2 = 配置错误（名单缺失等）。

输出里命中的原文一律打码（只留前 3 字符），所以报告本身可以公开贴。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------- 规则表

# (id, 级别, 正则, 说明)
# 级别：BLOCK = 命中即不许发布；WARN = 出版前逐条看，允许但要有理由。
STRUCTURAL_RULES = [
    # 负向前视/后顾两处都不能省：
    #  - 后顾 (?<![\w.\-]) 排除 URL：scheme 后面那串斜杠不算盘符分隔；
    #  - 前瞻 (?![\\/]) 排除双分隔写法。
    # 连这条注释本身也不能写出真实形态——写了就会被自己扫到（已实际发生 1 次）。
    ("win_abs_path", "BLOCK", r"(?<![\w.\-])[A-Za-z]:[\\/](?![\\/])",
     "盘符绝对路径（家目录 / 内网 / 项目目录）"),
    ("unc_path", "BLOCK", r"\\\\[A-Za-z0-9_.\-]+\\",
     "UNC 网络路径"),
    ("posix_home", "BLOCK", r"(?<![\w.])/(?:home|Users)/[A-Za-z0-9_.\-]+",
     "用户家目录绝对路径"),
    ("private_ip", "BLOCK", r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
     "内网 IP"),
    # 注意结尾的 (?![\w.])：否则 `denylist.local.txt` 这种普通文件名会被误判成内网主机
    ("internal_host", "BLOCK", r"\b[a-z0-9][a-z0-9\-]*\.(?:local|lan|internal|corp|intra)(?![\w.])",
     "内网主机名"),
    ("email", "BLOCK", r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+",
     "邮箱地址"),
    ("secret_github", "BLOCK", r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
     "GitHub token"),
    ("secret_openai", "BLOCK", r"\bsk-[A-Za-z0-9]{16,}\b",
     "API key（sk- 前缀）"),
    ("secret_aws", "BLOCK", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
     "AWS access key"),
    ("private_key", "BLOCK", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
     "私钥块"),
    ("jwt", "BLOCK", r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.",
     "JWT"),
    ("cn_id", "BLOCK", r"(?<!\d)\d{17}[\dXx](?!\d)",
     "身份证号"),
    ("cn_phone", "BLOCK", r"(?<!\d)1[3-9]\d{9}(?!\d)",
     "手机号"),
    ("credential_assign", "WARN",
     r"(?i)\b(?:password|passwd|pwd|secret|token|api[_\-]?key|access[_\-]?key)\s*[=:]\s*[\"']?[^\s\"']{6,}",
     "疑似凭据赋值"),
    ("unfilled_placeholder", "WARN", r"\{\{[A-Z0-9_]+\}\}",
     "未填占位符（模板中正常，成品中出现=漏填）"),
]

TEXT_SUFFIXES = {
    ".md", ".txt", ".json", ".jsonl", ".yml", ".yaml", ".py", ".ps1", ".sh", ".bat",
    ".csv", ".html", ".css", ".js", ".ts", ".toml", ".ini", ".cfg", ".env", ".template",
}
TEXT_NAMES = {"LICENSE", "LICENSE-DOCS", "VERSION", ".gitignore", ".gitattributes", "Makefile"}
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".mypy_cache"}

ALLOW_TOKEN = "sanitize:allow"          # 行尾标记：本行已知示例，跳过 BLOCK
DEFAULT_DENYLIST = Path("90-tooling/rules/denylist.local.txt")

# 已知无害的邮箱域名（示例用）
BENIGN_DOMAINS = ("example.com", "example.org", "example.net", "localhost")


def is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES


def mask(text: str, keep: int = 3) -> str:
    """打码：只留前 keep 个字符，长度信息保留 1 位（避免泄露原长）。"""
    text = text.strip()
    if len(text) <= keep:
        return "*" * len(text)
    return text[:keep] + "*" * min(len(text) - keep, 8)


def load_denylist(path: Path) -> list[tuple[str, str]]:
    """本地实体名单。每行 `类别:词条`，# 开头为注释。类别可自定义。"""
    if not path.exists():
        return []
    terms: list[tuple[str, str]] = []
    short: list[str] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                cat, term = line.split(":", 1)
                terms.append((cat.strip(), term.strip()))
            else:
                terms.append(("entity", line))
    # 单字词条不可用：中文单字会命中大量普通词（折/衡/利…），误报会淹没真命中。
    kept: list[tuple[str, str]] = []
    for cat, term in terms:
        if not term:
            continue
        if len(term) < 2:
            short.append(term)
            continue
        kept.append((cat, term))
    if short:
        print(f"[WARN] 名单中有 {len(short)} 条 <2 字词条已忽略（单字误报不可用）：{', '.join(short)}",
              file=sys.stderr)
    return kept


def git_tracked(root: Path) -> list[str] | None:
    """git ls-files 列出的文件（相对 root）。不是 git 仓库返回 None。

    为什么要有这个：工作区里躺着只该留在本地的敏感文件（本地名单、运行产物、
    扫描报告），它们被 .gitignore 排除、永不公开；扫工作区会把它们误报成"泄露"，
    而误报多了，真命中就会被忽略。默认只扫会被提交的东西。
    """
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True)
    except FileNotFoundError:
        return None
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]


def iter_files(root: Path, tracked: list[str] | None = None):
    if tracked is not None:
        for rel in tracked:
            path = root / rel
            if not path.is_file():
                continue
            if any(part in EXCLUDE_DIRS for part in path.parts):
                continue
            yield path
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        yield path


def scan(args) -> int:
    root: Path = Path(args.root).resolve()
    if not root.is_dir():
        print(f"[ERR] root 不是目录: {root}", file=sys.stderr)
        return 2

    denylist_path = Path(args.denylist) if args.denylist else (root / DEFAULT_DENYLIST)
    terms = load_denylist(denylist_path)
    if not terms and args.require_denylist:
        print(f"[ERR] 实体名单缺失：{denylist_path}（--require-denylist 要求必须有）", file=sys.stderr)
        return 2

    compiled = [(rid, sev, re.compile(rx), note) for rid, sev, rx, note in STRUCTURAL_RULES]
    tracked = None if args.all_files else git_tracked(root)
    if tracked is None and args.tracked_only:
        print(f"[ERR] --tracked-only 要求 --root 是 git 仓库：{root}", file=sys.stderr)
        return 2
    mode = (f"tracked-only（git ls-files {len(tracked)} 条，只扫会被提交的文件）"
            if tracked is not None else "目录全量（非 git 目录，或显式 --all-files）")
    hits: list[dict] = []          # 所有命中
    allowed: list[dict] = []       # 被 sanitize:allow 放行的命中（仍计数，供审计）
    files_scanned = 0
    files_skipped = 0
    text_bytes = 0
    crlf_files: list[str] = []
    bom_files: list[str] = []
    large: list[tuple[str, int]] = []

    for path in iter_files(root, tracked):
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        if size > args.block_mb * 1024 * 1024:
            large.append((rel, size))
            hits.append({"rule": "large_file", "sev": "BLOCK", "file": rel, "line": 0,
                         "match": f"{size/1024/1024:.1f} MB 超过 {args.block_mb} MB 上限"})
            continue
        if not is_text(path):
            files_skipped += 1
            continue
        try:
            raw = path.read_bytes()
        except OSError as exc:
            print(f"[WARN] 读不了 {rel}: {exc}", file=sys.stderr)
            continue

        if raw.startswith(b"\xef\xbb\xbf"):
            bom_files.append(rel)
        if b"\r\n" in raw:
            crlf_files.append(rel)

        text = raw.decode("utf-8-sig", errors="replace")
        files_scanned += 1
        text_bytes += len(raw)
        for lineno, line in enumerate(text.split("\n"), start=1):
            line_allowed = ALLOW_TOKEN in line
            for rid, sev, rx, note in compiled:
                for m in rx.finditer(line):
                    hit = {"rule": rid, "sev": sev, "file": rel, "line": lineno,
                           "match": m.group(0), "note": note}
                    if rid == "email" and any(d in m.group(0).lower() for d in BENIGN_DOMAINS):
                        continue
                    if line_allowed and sev == "BLOCK":
                        allowed.append(hit)
                    else:
                        hits.append(hit)
            for cat, term in terms:
                if term and term.lower() in line.lower():
                    hit = {"rule": f"denylist_{cat}", "sev": "BLOCK", "file": rel,
                           "line": lineno, "match": term,
                           "note": f"实体名单命中（类别 {cat}）"}
                    if line_allowed:
                        allowed.append(hit)
                    else:
                        hits.append(hit)

    # ------------------------------------------------------------ 假门拦截
    # 扫到 0 个文件却报 PASS，是"假门"：导出失败、路径写错、权限没读到，
    # 都会表现为"0 命中"。所以覆盖为 0 一律判 FAIL，不许静默通过。
    if files_scanned == 0:
        print("脱敏扫描报告（sanitize_scan.py）")
        print(f"root            : {root}")
        print(f"扫描对象         : {mode}")
        print(f"扫描覆盖         : 0 个文件 / 0 字节")
        print(f"非文本跳过       : {files_skipped} 个")
        print()
        print("[FAIL] 扫描覆盖为 0：一个文本文件都没扫到。")
        print("       空目录不是通过，是假门——先确认导出/路径/权限是否正确。")
        return 1

    # ------------------------------------------------------------ 汇总
    blocks = [h for h in hits if h["sev"] == "BLOCK"]
    warns = [h for h in hits if h["sev"] == "WARN"]

    print("脱敏扫描报告（sanitize_scan.py）")
    print(f"root            : {root}")
    print(f"扫描对象         : {mode}")
    print(f"扫描覆盖         : {files_scanned} 个文本文件 / {text_bytes:,} 字节")
    print(f"非文本跳过       : {files_skipped} 个")
    print(f"结构规则         : {len(STRUCTURAL_RULES)} 条")
    print(f"实体名单         : {len(terms)} 条来自 {denylist_path.name}"
          + ("" if terms else "  ← 未加载（本机没有名单，只跑了结构层）"))
    print(f"allow 放行       : {len(allowed)} 处（{ALLOW_TOKEN} 标记）")
    print()

    def dump(title: str, items: list[dict]):
        if not items:
            return
        print(title)
        by_rule: dict[str, list[dict]] = {}
        for h in items:
            by_rule.setdefault(h["rule"], []).append(h)
        for rid in sorted(by_rule, key=lambda r: -len(by_rule[r])):
            group = by_rule[rid]
            note = group[0].get("note", "")
            files = len({h["file"] for h in group})
            print(f"  {rid:22s} ×{len(group):<4d} 涉及 {files} 文件   {note}")
            for h in group[: args.samples]:
                loc = f"{h['file']}:{h['line']}" if h["line"] else h["file"]
                print(f"    {loc}  <<{mask(h['match'])}>>")
            if len(group) > args.samples:
                print(f"    … 另 {len(group) - args.samples} 处同类（报告里只列前 {args.samples} 处）")
        print()

    dump(f"[BLOCK] {len(blocks)} 处", blocks)
    dump(f"[WARN] {len(warns)} 处", warns)

    if crlf_files:
        print(f"[WARN] 含 CRLF 的文件 {len(crlf_files)} 个（应统一 LF）：{', '.join(crlf_files[:5])}"
              + ("…" if len(crlf_files) > 5 else ""))
    if bom_files:
        print(f"[WARN] 含 BOM 的文件 {len(bom_files)} 个（应 UTF-8 无 BOM）：{', '.join(bom_files[:5])}"
              + ("…" if len(bom_files) > 5 else ""))
    if large:
        print(f"[BLOCK] 超大文件 {len(large)} 个：{', '.join(f'{n}({b/1024/1024:.1f}MB)' for n, b in large)}")
    print()

    ok = not blocks
    print(f"结论：BLOCK {len(blocks)} / WARN {len(warns)} → "
          + ("PASS，可以发布" if ok else "FAIL，不许发布（先清 BLOCK，WARN 逐条给理由）"))

    if args.report:
        report = render_report(root, files_scanned, text_bytes, terms, allowed, blocks, warns, crlf_files, bom_files, ok)
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"报告已写入：{args.report}")

    if args.json:
        payload = {"root": str(root), "pass": ok,
                   "blocks": len(blocks), "warns": len(warns),
                   "allowed": len(allowed), "files": files_scanned,
                   "bytes": text_bytes,
                   "hits": [{**h, "match": mask(h["match"])} for h in hits]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0 if ok else 1


def render_report(root, files, text_bytes, terms, allowed, blocks, warns, crlf, bom, ok) -> str:
    lines = ["# 脱敏扫描报告", "",
             f"- 根目录：`{root}`",
             f"- 扫描覆盖：{files} 个文本文件 / {text_bytes:,} 字节（覆盖为 0 一律判 FAIL）",
             f"- 实体名单：{len(terms)} 条" + ("" if terms else "（未加载，仅结构层）"),
             f"- allow 放行：{len(allowed)} 处",
             f"- 结论：**{'PASS' if ok else 'FAIL'}**（BLOCK {len(blocks)} / WARN {len(warns)}）",
             "", "> 命中原文已打码，本报告可直接公开。", ""]
    for title, items in (("BLOCK", blocks), ("WARN", warns)):
        if not items:
            continue
        lines += [f"## {title}", "", "| 规则 | 位置 | 命中（打码） |", "|---|---|---|"]
        for h in items:
            loc = f"`{h['file']}:{h['line']}`" if h["line"] else f"`{h['file']}`"
            lines.append(f"| {h['rule']} | {loc} | `{mask(h['match'])}` |")
        lines.append("")
    if crlf or bom:
        lines += ["## 编码", "",
                  f"- CRLF 文件：{len(crlf)} 个",
                  f"- BOM 文件：{len(bom)} 个", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="公开仓库脱敏扫描（结构层 + 本地实体名单层）")
    ap.add_argument("--root", default=".", help="扫描根目录，默认当前目录")
    ap.add_argument("--tracked-only", action="store_true",
                    help="只扫 git ls-files 列出的文件（在 git 仓库里这是默认行为）")
    ap.add_argument("--all-files", action="store_true",
                    help="无视 .gitignore，扫目录下全部文件（只用于排查误报）")
    ap.add_argument("--report", help="把汇总写成 Markdown（不含原文，可公开）")
    ap.add_argument("--denylist", help=f"本地实体名单路径，默认 <root>/{DEFAULT_DENYLIST.as_posix()}")
    ap.add_argument("--require-denylist", action="store_true", help="名单缺失即报错（发布门用）")
    ap.add_argument("--block-mb", type=float, default=5.0, help="单文件体积上限，默认 5 MB")
    ap.add_argument("--samples", type=int, default=5, help="每类规则最多列几条示例，默认 5")
    ap.add_argument("--json", action="store_true", help="额外输出 JSON 摘要")
    ap.add_argument("--list-rules", action="store_true", help="只打印规则表")
    args = ap.parse_args()

    if args.list_rules:
        print(f"{'ID':24s} {'级别':6s} 说明")
        for rid, sev, _rx, note in STRUCTURAL_RULES:
            print(f"{rid:24s} {sev:6s} {note}")
        print("\n实体名单：<root>/90-tooling/rules/denylist.local.txt（不进仓库）")
        return 0
    return scan(args)


if __name__ == "__main__":
    sys.exit(main())
