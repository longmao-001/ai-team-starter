#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""团队脚手架：按 team.config.json 渲染出一套可用的团队目录。

它做四件事，不做第五件：

1. 建目录（roles / ops / kb / runs）
2. 按角色类型渲染对应模板（功能 agent / 专家 bot / 管理 bot）
3. 生成 TEAM.md 索引（谁负责什么、谁验收）
4. 报告还有哪些 `{{占位符}}` 没填——**没填的地方就是你的下一步**

不做的：不替你写内容、不装依赖、不推送仓库。

用法
----
    cp 90-tooling/examples/team.config.example.json team.config.json
    # 改 team.config.json
    python 90-tooling/scaffold.py --config team.config.json --out ../my-team
    python 90-tooling/scaffold.py --config team.config.json --out ../my-team --force

配置里每个角色用同一套字段；模板里 `{{XXX}}` 与配置键一一对应（大写化）。
字段没给就留空，脚本会把空占位符列出来，不会静默填一个假值。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 类型 → (模板相对路径, 输出文件名)
TEMPLATES = {
    "functional": ("01-role-templates/functional-agent/ROLE_CARD.template.md", "role-card.md"),
    "expert": ("01-role-templates/expert-bot/PERSONA-TEMPLATE.md", "persona.md"),
    "manager": ("01-role-templates/manager-bot/ROLE_CARD.template.md", "role-card.md"),
}

PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def render(template: str, values: dict[str, str]) -> tuple[str, list[str]]:
    missing: list[str] = []

    def sub(m: re.Match) -> str:
        key = m.group(1)
        val = values.get(key, "")
        if not str(val).strip():
            if key not in missing:
                missing.append(key)
            return f"{{{{{key}}}}}"
        return str(val)

    return PLACEHOLDER.sub(sub, template), missing


def main() -> int:
    ap = argparse.ArgumentParser(description="按配置渲染团队目录")
    ap.add_argument("--config", required=True, help="team.config.json 路径")
    ap.add_argument("--out", required=True, help="输出目录（不存在则创建）")
    ap.add_argument("--force", action="store_true", help="输出目录非空时仍继续（会覆盖同名文件）")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"[ERR] 配置不存在：{cfg_path}", file=sys.stderr)
        return 2
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))

    out = Path(args.out)
    if out.exists() and any(out.iterdir()) and not args.force:
        print(f"[ERR] 输出目录非空：{out}（确认要覆盖请加 --force）", file=sys.stderr)
        return 2

    globals_ = {k.upper(): v for k, v in cfg.items() if k != "roles" and isinstance(v, (str, int, float))}
    roles = cfg.get("roles") or []
    if not roles:
        print("[ERR] 配置里没有 roles", file=sys.stderr)
        return 2

    for sub_dir in ("roles", "ops", "kb", "runs"):
        (out / sub_dir).mkdir(parents=True, exist_ok=True)

    index_rows: list[str] = []
    all_missing: dict[str, list[str]] = {}

    for i, role in enumerate(roles, start=1):
        rtype = (role.get("type") or "functional").strip().lower()
        name = (role.get("name") or f"role-{i}").strip()
        slug = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", name).strip("-").lower() or f"role-{i}"

        if rtype not in TEMPLATES:
            print(f"[WARN] 未知类型 {rtype}（{name}），按 functional 处理")
            rtype = "functional"
        tpl_rel, tpl_name = TEMPLATES[rtype]
        tpl_path = REPO / tpl_rel
        if not tpl_path.exists():
            print(f"[WARN] 模板不存在，跳过：{tpl_rel}（该类型模板尚未写好）")
            index_rows.append(f"| {i:02d} | {name} | {rtype} | 模板缺失，待补 | — |")
            continue

        values = {**globals_, "ROLE_NAME": name, "EXPERT_NAME": name}
        values.update({k.upper(): v for k, v in role.items() if k not in ("roles",)})
        text, missing = render(tpl_path.read_text(encoding="utf-8-sig"), values)

        target = out / "roles" / f"{i:02d}-{rtype}-{slug}.md"
        header = (f"<!-- 由 scaffold.py 从 {tpl_rel} 生成；占位符未填处保留原样，"
                  f"清单见文件末尾「待填清单」 -->\n\n")
        footer = ""
        if missing:
            footer = ("\n\n---\n\n## 待填清单（scaffold 生成，填完请删掉本节）\n\n"
                      + "\n".join(f"- `{{{{{k}}}}}`" for k in missing) + "\n")
            all_missing[str(target.relative_to(out))] = missing
        target.write_text(header + text + footer, encoding="utf-8", newline="\n")

        owner = role.get("owner") or "—"
        index_rows.append(f"| {i:02d} | [{name}](roles/{target.name}) | {rtype} | {owner} | {len(missing)} |")
        print(f"[OK] {target}  （未填占位符 {len(missing)} 个）")

    team_md = [
        f"# {cfg.get('team_name', '我的团队')}",
        "",
        f"负责人：{cfg.get('owner', '{{OWNER}}')}",
        "",
        "## 角色表",
        "",
        "| # | 角色 | 类型 | 验收人 | 未填占位符 |",
        "|---|---|---|---|---|",
        *index_rows,
        "",
        "## 目录",
        "",
        "- `roles/` — 角色卡，一个角色一份",
        "- `ops/` — 派工单、验收串、台账",
        "- `kb/` — 知识库（schema、构建脚本、快照）",
        "- `runs/` — 运行产物（**不入库**）",
        "",
        "## 下一步（按顺序，别跳）",
        "",
        "1. 把 `roles/` 里每一份的「待填清单」填完，填完删掉本节",
        "2. 跑一次真实任务，按 `04-from-zero/DAY1.md` 的第 3 步",
        "3. 把跑崩的点回写成角色卡的边界条款",
        "",
    ]
    (out / "TEAM.md").write_text("\n".join(team_md), encoding="utf-8", newline="\n")

    for name, body in (
        ("ops/派工单.template.md",
         "# 派工单 · {{TASK_ID}}\n\n| 项 | 内容 |\n|---|---|\n"
         "| 任务 ID | {{TASK_ID}} |\n| 输入 | {{INPUT}} |\n| 输出形态 | {{OUTPUT}} |\n"
         "| 验收串 | {{ACCEPTANCE}} |\n| 截止 | {{DUE}} |\n| 派给 | {{ASSIGNEE}} |\n"
         "| 升级路径 | 卡住时找 {{ESCALATE}} |\n\n"
         "> 没有任务 ID 的派工不算派工；收口时在**同一处**回复。\n"),
        ("kb/README.md",
         "# 知识库\n\n最小可用路径见仓库 `02-knowledge-stack/README.md`。\n\n"
         "先跑通**一个真实问题**：10–30 份资料 → 5 个实体类型 → 问 → 命中 → 带来源回答。\n"),
        ("runs/.gitkeep", ""),
        (".gitignore", "runs/\n*.log\n*.bak\ntmp/\n"),
    ):
        p = out / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8", newline="\n")

    print(f"\n[OK] 团队目录：{out}")
    if all_missing:
        total = sum(len(v) for v in all_missing.values())
        print(f"[TODO] 还有 {total} 个占位符未填，分布：")
        for f, keys in all_missing.items():
            print(f"  {f}: {', '.join(keys[:8])}{'…' if len(keys) > 8 else ''}")
    else:
        print("[OK] 没有未填占位符")
    return 0


if __name__ == "__main__":
    sys.exit(main())
