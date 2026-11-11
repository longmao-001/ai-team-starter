# 03 · 发布纪律：预注册 / 干跑 / 回滚

> 一条规矩：**能被回滚的变更才叫发布，其他都叫事故。**
> 本章把这条规矩落成三件可勾选的动作，缺一件不发。

---

## 0. 发布前先钉死三样东西（不允许写"默认"）

| 项 | 写什么 | 为什么不能省 |
|---|---|---|
| `prev_snapshot` | 上一版 `kg.json` 的**完整 sha256** + 文件路径 | "默认上一版"会让本轮产物 vs 上轮产物互相污染 |
| `out_dir` | 本轮产物目录（例 `output/2026-11-11-r3/`） | 覆盖写 = 上一版消失 = 无法回滚 |
| `round_id` | 本轮唯一名（例 `r3-add-5-books`） | 日志、发布记录、回滚记录靠它对齐 |

```bash
mkdir -p output/snapshots/2026-11-11-r3
cp output/kg.json output/snapshots/2026-11-11-r3/kg.json.prev
cp output/kg.json.sha256 output/snapshots/2026-11-11-r3/kg.json.prev.sha256
```

---

## 1. 预注册：先写"预期是多少"，再跑

预注册的作用不是流程感，是**让"结果不符合预期"这件事在跑之前就可判定**。

### 模板（`templates/prereg.md.template`）

```
round_id: {{ROUND_ID}}
时间: {{YYYY-MM-DD HH:MM}}
输入: seed/nodes.csv + seed/edges.csv（sha256: {{SEED_SHA}}）
prev_snapshot: {{PREV_SHA}}
out_dir: {{OUT_DIR}}

预期五项计数（写具体数字，不写"大概"）：
  nodes:      {{N}}      # 上一版 {{N_PREV}} + 新增 {{ADD}} - 删除 {{REM}}
  edges:      {{M}}      # 同上
  by_type:    {{TYPE:count,...}}
  orphans:    {{ORPHANS}}   # 预期 <= 上一版，且新增实体不得成为孤立
  dangling:   0            # 无条件为 0，非 0 即中止

允许改动：{{WHITELIST}}
  # 例：只允许新增节点/边；已有节点的 name、source_date 不得变
禁止改动：{{FORBIDDEN}}
  # 例：已发布实体的 id；已有边的 relation

确定性：同一输入重跑 {{K}} 次，sha 必须全等
口径：{{METRIC_DEF}}
  # 例："节点数=图内 entities 总数，不含 xref 节点"
```

**"口径"这一行经常被跳过，然后吵架。** 例如"覆盖率 62%"：分子是所有实体还是只算有出处的？分母是全部还是可查的？写清楚，否则两个人都没错、但数字对不上。

### 预注册的两个反模式

- **先跑再补**：跑完发现是 18 个节点，回填"预期 18"。这等于没有预注册——下次异常你还是看不出来。
- **预期写成区间**："17–20 个节点"。区间宽到能装下任何结果，就失去了判定力。要留余量就写"17，若多 1 个必须解释为什么"。

---

## 2. 干跑：比对必须到字节，不能只比计数

```bash
python -X utf8 tools/kb_build.py --root . --dry
```

```
DRY  previous sha=050d0a72d851e4ba…  new sha=050d0a72d851e4ba…  字节相同=True
DRY  would write 7398 bytes  nodes=17 edges=17
```

**判定**：
- `字节相同=False` 但你预期"这次不改内容" → 停手，查为什么（时间戳进了快照？排序不稳定？换行变了？）
- `字节相同=True` 但你说的变更没发生 → 同样停手（很可能改错了文件）

### 干跑的三项抽样（计数对了也可能内容换了）

1. **跨类型各抽一个节点**：确认上批的成果还在（防止"重建时把某个类型漏掉"）。
2. **双向检索回归**：
   - 被删/被隔离的名字 → **必须搜不到**
   - 仍然有效的旧 id → **必须还能命中**
3. **差集清单**：新增/删除各列前 10 条，人工扫一眼有没有明显不该出现的东西（占位文本、测试数据、"待补充"）。

### 发布前体检（机器门）

```bash
python -X utf8 tools/kb_audit.py --root . --expect-nodes 17 --expect-edges 17
```

输出 `output/audit.json`，包含 `kg_path` / `kg_sha256` / `counts` / `orphans` / `dangling` / `verdict`。**这份 JSON 就是"PASS"的证据**；没有它，任何人说 PASS 都只算口头。

---

## 3. 回滚方案：三步以内，而且现在就写下命令

回滚不是"有备份就行"，是**三分钟内能执行完的三条命令**。写不出三条，说明你的发布方式太复杂了。

```
回滚（≤3 步）：
1. cp output/snapshots/{{ROUND_ID}}/kg.json.prev  output/kg.json
   cp output/snapshots/{{ROUND_ID}}/kg.json.prev.sha256  output/kg.json.sha256
2. 核对 sha：sha256sum output/kg.json 必须 == {{PREV_SHA}}
3. python -X utf8 tools/kb_load.py --root .   # 重建索引，否则索引仍指向坏图
   然后复测 3 条已知查询（例：山谷 / Book:b-01 / 量子引力）
```

常见失败：**只回滚了 kg.json，没重建索引**。查询器会继续读新库，或者直接报 `STALE_INDEX`——两种都算没回滚干净。

---

## 4. 发布记录（发完立刻写，不要事后回忆）

```
round_id: {{ROUND_ID}}
prev_snapshot: {{PREV_SHA}}
new_snapshot:  {{NEW_SHA}}
out_dir: {{OUT_DIR}}
五项计数（预期 -> 实际 -> 差）:
  nodes  {{N_EXP}} -> {{N_ACT}} -> {{D_N}}
  edges  {{M_EXP}} -> {{M_ACT}} -> {{D_M}}
  by_type ...
  orphans ...
  dangling ...
规范化 sha 相等: {{YES/NO}}   （节点、边分开比）
白名单外变更: {{NONE / 清单}}
抽样节点（跨类型）: {{ID1, ID2, ID3}}
双向检索回归: {{被隔离名字搜不到 / 旧 id 仍命中}}
回滚路径: {{SNAPSHOT_DIR}}   （已验证可执行 / 未验证）
失败段: {{NONE / 失败产物路径 + 输入指纹 + 差值}}
```

**失败产物不删。** 删掉失败现场，下次会踩同一个坑，而且没人知道踩过。

---

## 5. 发布后 30 分钟：看账

```bash
python -X utf8 -c "
import json,collections
rows=[json.loads(l) for l in open('query_log.jsonl',encoding='utf-8')]
zero=[r for r in rows if r['hits']==0]
print('总查询',len(rows),'零命中',len(zero))
for q,c in collections.Counter(r['query'] for r in zero).most_common(10): print(' 缺口',q,c)
"
```

零命中突然变多，通常意味着：本次发布删掉了某些实体，或者别名没迁过来。**这种问题在发布当天发现只要 5 分钟，一周后要一天。**

---

## 6. 一张表总结三门

| 门 | 动作 | 不过怎么办 |
|---|---|---|
| 预注册门 | 预期数字 + 口径 + 白名单写到纸上 | 不跑。先写清楚预期 |
| 干跑门 | 字节比对 + 抽样 + 双向回归 | 停手排查，不"先发布再看看" |
| 回滚门 | ≤3 步命令 + 备份 sha 已核 | 不发布。回滚不了就不许发 |
