# sample：17 个实体的最小知识栈（可运行）

标准库实现，**零第三方依赖**。用虚构的书目数据，因为没有事实性风险，又足够演示多跳。

## 一条命令验证全部

```bash
python -X utf8 run_demo.py
```

不加 `-X utf8` 也能跑：脚本已把自身输出固定为 UTF-8（控制台是 cp936 时不再崩在编码上）。
若显示乱码，先 `chcp 65001`。

期望 13 项全 PASS、`VERDICT PASS 13/13`，证据写进 `output/demo_evidence.log`。

## 你要改什么

| 要改 | 怎么改 |
|---|---|
| 领域 | 换 `seed/*.csv` 和 `schema.json` 里的类型名；脚本一行不用动 |
| 实体 | 往 `seed/nodes.csv` 加行（`Type:slug` 格式） |
| 关系 | 往 `seed/edges.csv` 加行（单向，带出处） |
| 想不出 Schema | 先照抄示例的四个类型，跑通再加 |

**不用改**：`tools/*.py`。除了"加新的校验规则"，生成器不该为个案让步——它一让步，所有人对 sha 的信任就没了。

## 文件

| 文件 | 作用 |
|---|---|
| `schema.json` | 实体/关系声明、id 格式门、置信度取值 |
| `seed/nodes.csv` | 实体表（7 列，含出处与日期） |
| `seed/edges.csv` | 关系表（6 列，单向） |
| `tools/kb_build.py` | SEED → `kg.json` + `.sha256`（确定性、原子写、全量校验） |
| `tools/kb_load.py` | `kg.json` → `kb.sqlite`（先核 sidecar，再建索引） |
| `tools/kbq.py` | 查询：名/别名/ID/多跳；每次写 `query_log.jsonl` |
| `tools/rag_context.py` | 邻域 → prompt 上下文（每条事实带出处日期） |
| `tools/kb_audit.py` | 发布前体检：五项计数 + sha + 孤立/悬空 + 出处完整性 |
| `run_demo.py` | 端到端 13 项自检 |

## 产物（`output/`，不进版本库）

```
output/kg.json              知识图快照（纯内容，无时间戳）
output/kg.json.sha256       sidecar，格式同 sha256sum
output/build_report.json    构建时间、字节数、告警（不参与 sha）
output/kb.sqlite            索引 + 全文（只读查询）
output/audit.json           体检证据：路径 + sha + 计数 + verdict
output/demo_evidence.log    13 项自检的逐行结果
```

## 示例数据规模

4 本书 / 3 位作者 / 3 个体裁 / 7 个主题 = **17 节点、17 条边**。
边：`ABOUT` 7、`WRITTEN_BY` 4、`GENRE_OF` 4、`NARROWER_THAN` 2。

> 数字很小是故意的：先证明能查准，再谈规模。17 条查不准，17 万条只会更不准。
