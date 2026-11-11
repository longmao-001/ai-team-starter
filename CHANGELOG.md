# 变更记录

格式：`## [版本] - YYYY-MM-DD`，逐条写"改了什么 + 为什么"。只增不改，已发布版本的内容不回头修。

## [1.0.0] - 2026-11-11

首个对外版本。四块内容齐：三类角色模板（功能 agent / 专家 bot / 管理 bot）、知识库+图谱+RAG 最小可用路径、团队作业台（纪律/派工/门控/台账/备份）、从零搭队检查表；另含一篇行业实例与一套发布工具（脱敏扫描 / 历史扫描 / 脚手架）。

发布门（三层，扫的是发布树不是工作区）：
- 结构层 + 实体层：**覆盖 69 / 72 件**（`.template` ×2、`.jsonl` ×1 当时不在文本扩展名里，从未被扫过）/ 15 条实体词条 / **BLOCK 0 / WARN 167**
- 历史层：13 个提交 / 740 个 blob / **BLOCK 0**，OVERRIDE 4 项（2 行）
- 远端侧：`refs/tags/v1.0.0` 指向的 sha 与本地一致

> **这次 PASS 的覆盖范围要一起看**：69/72 的覆盖面，加上当时**没有「零对象判 FAIL」**这条判据——两个缺口叠加。回执里那句「70 个文件」把扫描器自己的输出文件也数了进去，是口径错误。v1.0.1 起改为 72/72 且覆盖为 0 即 FAIL。

## [1.0.1] - 2026-11-11

- 结构层：**覆盖 72 / 72 件**（补 `.template` / `.jsonl` 两类扩展名）、新增「扫描覆盖」一行、**覆盖为 0 一律 FAIL**
- 盘符正则加后顾断言：URL 里的 scheme 不再被误判成盘符（此前全仓 URL 会进 WARN）
- 内容侧补齐「零对象 = FAIL」：`03-gates.md`（门控必须打印对象数）、`07-pitfalls.md` 坑 17、`06-checklist.md`（发布门前置项）
- 解释规则的文字本身也受规则约束：改正则后 `release.md` 与 `sanitize_scan.py` 的注释写出形态，自身产生 2 处 BLOCK，已改为描述性写法
- 一次历史改写（force-push）：见 [`90-tooling/rules/history-rewrites.md`](90-tooling/rules/history-rewrites.md)

## [0.4.3] - 2026-11-11

- `history-waivers.txt` 改为只定位不复述（`提交:文件:行|规则|理由`）：复述一次就等于把不该出现的内容抄进库，已实际发生并被门拦下
- `scan_history.py`：短 sha 前缀匹配（手写 7 位 vs 扫出 8 位）；豁免理由参与聚合展示；输出改为 OVERRIDE
- `90-tooling/README.md` 新增：扫描对象必须是**发布树**（`git archive HEAD`）——扫工作区会把只该留本地的敏感文件误报成泄露，也会漏掉已删除但仍在历史里的内容

## [0.4.2] - 2026-11-11

- 修 `history-waivers.txt` 注释：第一版为说明"原文长什么样"把路径形态抄了一遍，导致该文件自身产生 2 处 BLOCK（全量门当场 FAIL）
- 历史定性补充：`e5a5a8c1` 那 2 处属省略号形态路径示例，无个人信息，登记豁免、不改写历史
- 教训入库：**记录教训的文件本身也会犯同一个错**，所以"豁免清单"也必须被扫

## [0.4.1] - 2026-11-11

- 新增 `90-tooling/scan_history.py`：逐提交扫历史，与工作区共用同一套规则表；支持 `sanitize:allow` 行标记
- 新增 `90-tooling/rules/history-waivers.txt`：已定性豁免登记（单独列出、不计入通过、可审计）
- `03-team-operations/01-discipline.md` 增第九条：件数/字节/行数/占位符次数/HEAD 一律现取现算，抄来的数不进发布门
- `03-team-operations/03-gates.md`：门回执必须报层次（几层、名单几条、WARN 是什么）
- 历史定性：`e3a00cb` 的 2 处为省略号形态路径示例，负责人裁定不构成泄密、不改写历史

## [0.4.0] - 2026-11-11

- 首篇行业实例入库：`05-examples/case-short-drama.md`（影视，占位符全文计数 2/2/3）
- `release.md`：新增「门 0 历史扫描」，并要求回执带现取 HEAD、数字一律脚本出

## [0.2.0] - 2026-11-11

并入知识栈一章（知识库 + 知识图谱 + RAG 的最小可用路径），21 件 95,788 B（git blob 口径，LF 归一）。

- `02-knowledge-stack/`：最小路径、schema 模板、发布纪律、查询契约、坑注册表（15 条）、检查表、索引
- `sample/`：可跑的七步示例（seed → schema → build → load → query → 记账 → RAG 装配）+ 5 个脚本 + 2 个 seed
- `templates/`：预注册、发布记录、查询记账三份填空模板
- `sample/output/` 与 `query_log.jsonl` 按 `sample/.gitignore` 排除，运行产物不入库
- 并入前独立验过：在干净目录、默认 cp936 控制台、不设任何编码变量下 `python run_demo.py` → exit 0，PASS 13/13

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
