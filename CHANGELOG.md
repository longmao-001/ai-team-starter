# 变更记录

格式：`## [版本] - YYYY-MM-DD`，逐条写"改了什么 + 为什么"。只增不改，已发布版本的内容不回头修。

## [0.1.2] - 2026-11-11

- 修 `sanitize_scan.py`：实体名单 <2 字词条一律忽略并警告。实测单字词条（"折"）在 50 个文件里立刻产生 2 处误报，真命中会被淹没
- 发布门实跑记录：50 文件 / 15 条实体词条 / BLOCK 0 / WARN 116 → PASS

## [0.1.1] - 2026-11-11

并入两章正文（管理 bot + 团队作业台），共 14 个文件 55,109 B，逐件 sha256/md5 与交付方声明的表对上。

- 新增 `01-role-templates/manager-bot/`：角色卡、工作契约、技能绑定、填表示范、反例、索引（6 件）
- 新增 `03-team-operations/`：纪律、派工与验收、门控、台账、备份与回滚、节奏、坑注册表、索引（8 件）
- 两个目录的占位壳 README 被正文替换（旧壳已由交付方另存备份）
- 未收录：`WRITING_STYLE.md`（根目录《写作口径》），脱敏扫描有 3 处 BLOCK，修好后单独提交
- 已知待办：`CONTRIBUTING.md` 对《写作口径》的指路一行，与上述文件同批提交，避免出现死链

## [0.1.0] - 2026-11-11

首版骨架。

- 新增三类角色模板目录（功能 agent / 专家 bot / 管理 bot），占位符体例统一为 `{{UPPER_CASE}}`
- 新增 `00-quickstart`、`04-from-zero` 的 Day1 / Week1 检查表
- 新增 `90-tooling/sanitize_scan.py`：两层脱敏扫描（结构规则 + 本地实体名单），命中原文打码
- 新增 `90-tooling/scaffold.py`：按 `team.config.json` 渲染出团队目录
- 新增 `90-tooling/release.md`：先私有后公开的发布四步与打 tag 纪律
- 已知未完成：`01-role-templates/manager-bot/`、`02-knowledge-stack/`、`03-team-operations/` 仅有章节占位，正文待填
