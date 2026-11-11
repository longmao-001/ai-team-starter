# 变更记录

格式：`## [版本] - YYYY-MM-DD`，逐条写"改了什么 + 为什么"。只增不改，已发布版本的内容不回头修。

## [0.1.0] - 2026-11-11

首版骨架。

- 新增三类角色模板目录（功能 agent / 专家 bot / 管理 bot），占位符体例统一为 `{{UPPER_CASE}}`
- 新增 `00-quickstart`、`04-from-zero` 的 Day1 / Week1 检查表
- 新增 `90-tooling/sanitize_scan.py`：两层脱敏扫描（结构规则 + 本地实体名单），命中原文打码
- 新增 `90-tooling/scaffold.py`：按 `team.config.json` 渲染出团队目录
- 新增 `90-tooling/release.md`：先私有后公开的发布四步与打 tag 纪律
- 已知未完成：`01-role-templates/manager-bot/`、`02-knowledge-stack/`、`03-team-operations/` 仅有章节占位，正文待填
