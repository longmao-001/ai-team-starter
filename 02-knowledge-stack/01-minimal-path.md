# 01 · 最小可用路径：从零到第一条查询

> 目标：**30–60 分钟内**让一条知识能被查出来，并且查得清出处。
> 路径固定七步，每步都有"通过判据"。判据不满足就停在这一步，不要往下一步走——后面所有问题都会被前一层的脏数据放大。

---

## 第 0 步：准备环境（5 分钟）

要求只有一条：**Python 3.10 或更新**，不需要第三方包（不用 pip install）。

```bash
python -X utf8 --version
# Python 3.13.3   ← 版本号 ≥3.10 即可
```

`-X utf8` 不是可选项。Windows 默认用本地编码打开文件，中文实体名会在某些机器上变成乱码；加这个参数让 I/O 固定走 UTF-8。Linux/macOS 上加了也无害，建议全平台统一。

本包的 6 个脚本已经把**自身输出**固定成 UTF-8（`sys.stdout.reconfigure(...)`），所以 `python run_demo.py` 不加 `-X utf8` 也能跑；但读写数据文件时仍建议带 `-X utf8`。若控制台显示中文乱码，先 `chcp 65001` 再跑。

复制示例目录作为你的起点：

```bash
cp -r sample my-kb
cd my-kb
```

> **不要**直接在 `sample/` 上改。示例留着当"标准答案"，以后跑 `run_demo.py` 对照。

---

## 第 1 步：填 SEED（10–20 分钟，占全程 80% 的价值）

SEED 只有两张表。**一行 = 一个事实**。

### `seed/nodes.csv`（实体）

| 列 | 必填 | 说明 |
|---|---|---|
| `entity_id` | ✅ | 格式 `Type:slug`，例 `Book:b-01`。**建好就别改**，它是别的表引用你的唯一方式 |
| `type` | ✅ | 必须是 `schema.json` 里声明过的实体类型 |
| `name` | ✅ | 显示名，用你最常搜的那个写法 |
| `aliases` | ⬜ | 真同义词，`\|` 分隔（例 `AI\|人工智能`）。**不要**塞描述句 |
| `source` | ✅ | 出处，写"哪个库/哪份文件/哪一行"，例 `DEMO_SEED`、`NCBI:gene:1234` |
| `source_date` | ✅ | 出处日期 `YYYY-MM-DD`，确实不知道就写 `unknown`（构建时会告警） |
| `year` | ⬜ | 类型自己的属性。**属性放列里，不要做成实体** |

### `seed/edges.csv`（关系）

| 列 | 必填 | 说明 |
|---|---|---|
| `from` | ✅ | 起点实体 id |
| `relation` | ✅ | 关系名，`UPPER_SNAKE`，例 `WRITTEN_BY` |
| `target` | ✅ | 终点实体 id |
| `evidence_source` | ✅ | 这条关系从哪来（**列名不能叫 `source`**，见坑 7） |
| `source_date` | ✅ | 同上 |
| `confidence` | ✅ | `SEED` / `DB_REFERENCE` / `LLM_INFERRED` 三档 |

**三条填表规矩**
1. **只存单向**。存 `Book -> Author`，不要同时存 `Author -> Book`；反查由索引负责（坑 10）。
2. **一条边只写一个出处**。两个来源就写两行，别在单元格里塞分号。
3. **不确定就别写**。空着的边能补；写错的边会被下游当真。

**通过判据**：打开两张 CSV，随便抽 5 行问自己"这行的出处我去哪儿能核？"——5 行都答得出来才继续。

---

## 第 2 步：定 Schema（10 分钟）

`schema.json` 决定"什么能进图、什么进不来"。它同时是**格式门**和**文档**。

最小内容（照 `sample/schema.json` 改）：

```json
{
  "schema_version": "1.0",
  "graph": "{{YOUR_GRAPH_NAME}}",
  "id_pattern": "^(Book|Author|Genre|Topic):[a-z0-9-]+$",
  "entity_types": {
    "Book": {"required": ["id","type","name","source","source_date"], "optional": ["year","aliases"]}
  },
  "relation_types": {
    "WRITTEN_BY": {"from": ["Book"], "to": ["Author"]}
  },
  "confidence": ["SEED","DB_REFERENCE","LLM_INFERRED"],
  "date_format": "YYYY-MM-DD",
  "date_unknown_placeholder": "unknown"
}
```

`id_pattern` 是正则硬门：不符合的实体在**构建期直接报错**，不会悄悄进图。宁可今天报 34 个错，也别三个月后发现图里混着 `"待补充"` 这种 id。

设计取舍细节见 `02-schema-template.md`。

**通过判据**：你能对每个实体类型说出"它为什么必须单独成为一个实体"（而不是别人身上的一个属性）。

---

## 第 3 步：构建 KG（1 分钟）

```bash
python -X utf8 tools/kb_build.py --root .
```

期望输出：

```
OK    .../output/kg.json
      sha256 050d0a72d851e4ba6178ec53b823e96762fbd7ffeb812b472e7195af043ab2a9
      nodes=17 edges=17 {'Author': 3, 'Book': 4, 'Genre': 3, 'Topic': 7}
```

> 这个 sha 是**随包示例 SEED** 的。你换了自己的数据，sha 必然不同——不同才是对的。

同时生成 `output/kg.json.sha256`，内容形如 `<64位hex>  kg.json`，与 `sha256sum` 输出一致，可直接用系统工具复核：

```bash
certutil -hashfile output/kg.json SHA256     # Windows
sha256sum output/kg.json                     # Linux/macOS
```

**构建器做的五件事**（也是它拒绝写盘的五种情况）：
1. id 格式、类型、必填字段、日期格式
2. 边端点必须存在且类型匹配（`WRITTEN_BY` 的终点必须是 `Author`）
3. 重复实体、重复边
4. 悬空引用、自环（自环告警）
5. 出处为空

任何一条不过，**构建中止并列出全部错误**，不写盘。修 seed 或 schema，**不要改生成器绕过**——生成器一旦能通融，所有人的"sha 一致"都不再等于"内容一致"。

**确定性怎么保证**：`sort_keys` + 固定缩进 + LF 结尾 + UTF-8 无 BOM + 产物内**不放时间戳**。时间写进 `output/build_report.json`，不参与 sha。反过来验一次：

```bash
python -X utf8 tools/kb_build.py --root . --dry
# DRY  previous sha=050d0a72d851e4ba…  new sha=050d0a72d851e4ba…  字节相同=True
```

`字节相同=True` 才叫"重跑没变"。只比节点数会漏掉"数量一样、内容换了"（坑 2）。

---

## 第 4 步：建索引 KB（1 分钟）

```bash
python -X utf8 tools/kb_load.py --root .
```

期望：

```
OK    .../output/kb.sqlite
      entities=17 edges=17 fts=fts5-trigram kg_sha=050d0a72d851e4ba…
```

`kb_load.py` 先核 sidecar：`kg.json` 的 sha 与 `kg.json.sha256` 不一致就**拒绝建库**。这样"索引比图旧"在源头就被挡住。

**通过判据**：`entities` / `edges` 与第 3 步打印的 `nodes` / `edges` **逐数相等**。不等就是入库逻辑有 bug，别往下走。

---

## 第 5 步：查第一条（2 分钟）

```bash
python -X utf8 tools/kbq.py --root . --q 山谷
```

真实输出：

```json
{
  "query": "山谷",
  "mode": "text",
  "engine": "like",
  "graph": "demo-books",
  "snapshot_sha": "050d0a72d851e4ba6178ec53b823e96762fbd7ffeb812b472e7195af043ab2a9",
  "fts_mode": "fts5-trigram",
  "hits": 1,
  "results": [
    {
      "id": "Book:b-01",
      "type": "Book",
      "name": "山谷与齿轮",
      "year": "2019",
      "source_date": "2026-01-01",
      "matched_on": "alias_exact",
      "score": 90
    }
  ]
}
```

四种查法（覆盖日常 90% 需求）：

```bash
python -X utf8 tools/kbq.py --root . --q 山谷              # 按名/别名，子串命中
python -X utf8 tools/kbq.py --root . --id Book:b-01        # 按 id 精确取
python -X utf8 tools/kbq.py --root . --q 山谷与齿轮 --neighbors 1   # 带 1 跳邻居
python -X utf8 tools/kbq.py --root . --q 量子引力           # 零命中（hits=0）
```

**通过判据**：结果里有 `matched_on`（命中方式）和 `source_date`（出处日期）。这两个字段缺一个，说明你的查询层没把出处带上来，下游引用会变成"据说"。

**为什么快照 sha 要出现在查询结果里**：同一句话，在两张不同版本的图里可能是两个答案。没有 sha 的结论无法复核。任何覆盖率、命中数都必须带"哪张图 + 哪个 sha"。

---

## 第 6 步：记账（自动，但要看一眼）

`tools/kbq.py` 每次查询都会往 `query_log.jsonl` 追加一行：

```json
{"engine":"like","graph":"demo-books","hits":1,"mode":"text","query":"山谷","snapshot_sha":"050d…","ts":"2026-11-11T11:37:03Z"}
```

四字段 `query / graph / snapshot_sha / hits` + `ts`。**零命中同样写**（`hits:0`）。

**通过判据**：用 Python 逐行 `json.loads` 全部通过——不要用控制台肉眼看中文是否正常（坑 4）：

```bash
python -X utf8 -c "import json;[json.loads(l) for l in open('query_log.jsonl',encoding='utf-8')];print('OK')"
```

---

## 第 7 步：喂给模型（RAG 最小形态）

```bash
python -X utf8 tools/rag_context.py --root . --id Book:b-01 --depth 1
```

真实输出：

```
[上下文] 图=demo-books 快照sha=050d0a72d851e4ba…
[实体] Book 山谷与齿轮 (id=Book:b-01, 出处=DEMO_SEED 2026-01-01)
[别名] 山谷
  [d1] 山谷与齿轮 → ABOUT → 人工智能  (出处日期 2026-01-01)
  [d1] 山谷与齿轮 → ABOUT → 机器伦理  (出处日期 2026-01-01)
  [d1] 山谷与齿轮 → GENRE_OF → 科幻  (出处日期 2026-01-01)
  [d1] 山谷与齿轮 → WRITTEN_BY → 林砚  (出处日期 2026-01-01)
[边界] 以上是该实体的 1–N 跳邻域；块外未知即说未知，不要补全。
```

这段文本就是 prompt 的"资料区"：**每条事实带出处日期，末尾一句边界声明**。
边界声明不是客套——没有它，模型会用训练记忆填补块外的空白，而你不知道哪句是编的。

多跳查询会把 `depth=2` 的路径也拉进来；深度越深，噪声越多。经验值：**1–2 跳**，超过 2 跳改问一句更具体的话，比加深有用。

---

## 完成判据（全绿才算"能查了"）

```bash
python -X utf8 run_demo.py
```

```
VERDICT PASS  13/13
```

这 13 项就是本章的可验收定义：构建、确定性、建库、五项体检、别名命中、按名命中、零命中记账、多跳、已知坑复现、RAG 装配、记账完整性、sha 绑定。

---

## 扩增挂点：从 17 条到 1 万条

规模上来只有两件事会变，架构不变：

1. **SEED 来源**：从手写 CSV 变成"从 API/数据库导出 CSV"。导出脚本必须产出与手写**完全相同的列**——不要给富集批次开第二条写路径。
2. **分批与对账**：每批先 `--dry` 看差量（新增/变更/删除各多少），再落盘；每批单独记 `build_report.json`，出现异常能定位到"第几批"。
   一个批次应当只有一个自然的回滚点（上一批的 `kg.json` + sha）。

三条扩增纪律：
- **增量导入只加不删**：老实体改了出处，覆盖 `source` 字段，不要新建节点（否则同一实体两个 id，多跳立刻分叉）。
- **富集失败要进 gaps**：API 查不到就记"缺",不要留空字段假装查过。空字段和"查过但无"在审计时是两回事。
- **每批之后重跑 `kb_audit.py`**：孤立节点、悬空引用往往在扩增量达到几千条时才暴露。

---

## 失败处理速查

| 现象 | 去哪个文件 |
|---|---|
| 构建报一堆"必填字段缺失" | 坑 6（BOM）、坑 7（列名重名） |
| sha 与 sidecar 对不上 | 坑 3（换行）、坑 12（时间戳进快照） |
| 查询报 `STALE_INDEX` | 坑 1（索引比图旧） |
| 搜中文命中 0 | 坑 4（控制台编码）、坑 8（FTS 分词） |
| 记账里中文变 `\u5c71` | 坑 5（ensure_ascii） |

全部 14 条见 `05-pitfalls.md`，每条附复现命令。
