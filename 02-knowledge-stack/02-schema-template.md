# 02 · Schema 模板：什么该成为实体，什么不该

Schema 是这张图的法律。它写坏了，后面所有查询都在替它擦屁股。这一页只讲判据和反例。

---

## 一、一个东西该不该成为实体：三问

对每个候选名词问三句：

1. **它需要被单独查吗？**（"2019 年出版的书有哪些"——年份需要独立成实体吗？不用，它是 `Book.year`）
2. **它有自己的出处吗？**（"作者"有；"作者的生卒年"没有，它是作者身上的属性）
3. **别的实体会引用它吗？**（"主题"会被很多书引用；"某本书的一句话简介"不会）

**三问占一条**才值得成为实体。占零条 = 它是属性。

| 名词 | 结论 | 理由 |
|---|---|---|
| 书 / 作者 / 主题 / 体裁 | 实体 | 都需被单独查，且互相引用 |
| 出版年份 | 属性 `Book.year` | 不需要单独查，没有独立出处 |
| 出版社 | 实体（若你要按社聚合）/ 属性（若只是标注） | 取决于你有没有"按社查"这类问题 |
| "本书简介" | 属性 | 只属于一本书 |
| 某化合物的 InChIKey | 属性 + 外部引用 | 是身份的一部分，不是独立知识 |

**反例（真实见过）**：把"年份"做成实体，于是每年一个节点，所有书都连到 `Year:2019`；查"2019 年的书"变成两跳，查"跨年份趋势"变成图遍历。属性就该待在属性层。

---

## 二、命名规则（五条，照做就不会乱）

| 对象 | 规则 | 好 | 坏 |
|---|---|---|---|
| 实体类型 | 单数、PascalCase | `Book`、`Enzyme` | `books`、`BOOK_TABLE` |
| 实体 id | `Type:slug`，slug 只用小写字母/数字/连字符 | `Book:b-01`、`Gene:dxs` | `Book:山谷与齿轮`（改名就断链） |
| 关系 | `UPPER_SNAKE`，动词，**单向** | `WRITTEN_BY`、`ABOUT` | `author`、`IS_AUTHOR_OF_AND_WRITTEN_BY` |
| 别名 | 真同义词用 `\|` 分隔 | `AI\|人工智能` | `一本讲 AI 与伦理的小说`（这是描述） |
| 字段名 | snake_case，`from`/`target` 不用 `source` 表两端 | `evidence_source` | `source` 同时指起点和出处（坑 7） |

**只存单向**：`Book -> Author` 一条够了，`Author -> Book` 由反向索引提供。两条都存，改一处漏一处，计数立刻翻倍且自相矛盾（坑 10）。

**不要造反义关系对**：有了 `NARROWER_THAN` 就不要再造 `BROADER_THAN`。查询层 `--neighbors` 本来就能反查。每多一条反向关系，就多一个"两边不一致"的机会。

---

## 三、主键策略：三类场景

| 场景 | 策略 | 例 |
|---|---|---|
| 全局唯一（书、化合物、专利） | 短 slug 或外部稳定 id | `Compound:CHEBI:15361` |
| 同名跨对象（基因、物种内基因） | **复合主键**：`基因名[物种]` | `Gene:TPS1[Arabidopsis-thaliana]` |
| 一个东西有多个外部 id | 主 id 用内部稳定 id，外部 id 做成**引用边** | `Enzyme:e-01` → `HAS_REF` → `UniProt:P12345` |

**铁律：主 id 一旦发布，永不复用、永不改语义。** 改名就断链，断链就丢历史。要改语义就新建类型（`EnzymeV2:`），旧类型标 `deprecated_in`。

---

## 四、置信度：三档，别混用

| 值 | 含义 | 允许的下游用途 |
|---|---|---|
| `SEED` | 人在原始表里逐行填的 | 可直接当事实引用 |
| `DB_REFERENCE` | 从公开库/接口抓的，带库内 ID | 可引用，但须注明"库 X、抓取时间" |
| `LLM_INFERRED` | 模型从文本里抽的，未经人核 | **只能当线索**，不能当结论；报告里必须标注来源为"模型推断" |

查询结果必须能把 `confidence` 带出来（模板里已在 `edges` 表保留）。下游要能说"我只用 SEED + DB_REFERENCE"，这句话必须是一条 `WHERE` 条件，而不是一句口头承诺。

---

## 五、填空表（把你的领域填进去）

```
图名：{{GRAPH_NAME}}
一句话领域：{{DOMAIN_ONE_LINER}}

实体类型（每个填一行）：
| 类型 | 为什么必须独立存在（三问之几） | 主 id 格式 | 专有属性 |
|------|------------------------------|-----------|---------|
| {{TYPE_1}} | {{REASON}} | {{Type:slug}} | {{ATTRS}} |
| {{TYPE_2}} | {{REASON}} | {{...}} | {{...}} |

关系类型（每个填一行）：
| 关系 | from | to | 语义（一句话） | 是否单向存储 |
|------|------|----|--------------|------------|
| {{REL_1}} | {{TYPE_A}} | {{TYPE_B}} | {{MEANING}} | 是 |

id_pattern：^{{TYPE_1}}|{{TYPE_2}}):[a-z0-9-]+$
置信度取值：SEED / DB_REFERENCE / LLM_INFERRED
日期未知占位：unknown
```

填完自查三题：
1. 有没有哪两个类型其实永远一起出现、从没被单独查过？→ 合并。
2. 有没有哪个"关系"其实是属性（一条边只可能有一个值）？→ 降级成字段。
3. 有没有哪个 id 里带了会变的信息（年份、版本、人名）？→ 换成稳定 slug。

---

## 六、版本演进

- `schema_version` 必填，写进 `kg.json`。
- **加字段/加类型** = 小版本（1.0 → 1.1）：老数据不用动，缺字段查询时按空处理。
- **删字段/改语义** = 大版本（1.x → 2.0）：必须先写迁移脚本 + 旧图快照 + 回滚点，按 `03-publish-discipline.md` 走发布流程。
- 删字段不要物理删：标 `deprecated` 并保留一个版本周期。图里删掉的数据，下游没人能复原。

---

## 七、一个最小可用的完整 Schema

```json
{
  "schema_version": "1.0",
  "graph": "{{GRAPH_NAME}}",
  "id_pattern": "^(Book|Author|Genre|Topic):[a-z0-9-]+$",
  "entity_types": {
    "Book":   {"required": ["id","type","name","source","source_date"], "optional": ["year","aliases"]},
    "Author": {"required": ["id","type","name","source","source_date"], "optional": ["aliases"]},
    "Genre":  {"required": ["id","type","name","source","source_date"], "optional": ["aliases"]},
    "Topic":  {"required": ["id","type","name","source","source_date"], "optional": ["aliases"]}
  },
  "relation_types": {
    "WRITTEN_BY":    {"from": ["Book"], "to": ["Author"]},
    "GENRE_OF":      {"from": ["Book"], "to": ["Genre"]},
    "ABOUT":         {"from": ["Book"], "to": ["Topic"]},
    "NARROWER_THAN": {"from": ["Topic"], "to": ["Topic"]}
  },
  "confidence": ["SEED","DB_REFERENCE","LLM_INFERRED"],
  "date_format": "YYYY-MM-DD",
  "date_unknown_placeholder": "unknown"
}
```

`required` 里必须有 `source` 和 `source_date`。这是本章唯一不允许通融的两列——它们决定三个月后还有没有人敢用这张图。
