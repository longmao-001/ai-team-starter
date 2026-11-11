# 05 · 坑注册表：15 条真实故障

> 收录标准：**现象能看见、原因说得清、改法能照做、最好能复现**。
> 写"要注意编码问题"没有用；写"PowerShell 控制台按 GBK 解码 UTF-8，你会看到 `灞辫胺`，但文件是好的"才让人少踩一次。

编号在全文被引用（代码注释、检查表），不要改号。

---

## 坑 1 `STALE_INDEX`：图重建了，索引还是旧的

**现象**：新加的实体搜不到；改过的属性查出来还是旧值；查询器直接报 `STALE_INDEX` 并拒绝查询。

**原因**：`kg.json` 重建了，`kb.sqlite` 没重建，或者重建到一半失败被忽略。查询器读到的是上一版的索引，但对外报的是当前图的名字——**看起来没坏，其实答的是旧世界**。

**改法**（三层，缺一层都可能复发）：
1. 索引里存 `meta.kg_sha256`，查询前与 sidecar 比对，不一致就拒查（本模板已实现，退出码 3）。
2. 建库成功后立刻复算一次实体数/边数，必须与 KG 相等。
3. 把"重建图 + 重建索引"绑成同一个命令/同一个脚本，不给人漏做一步的机会。

**复现**：改一行 seed → 只跑 `kb_build.py` → 再查询：

```
STALE_INDEX  kb.sqlite 建于 050d0a72d851e4ba…，当前快照是 09bfcd126e2e9187…
             索引过期，拒绝查询。重跑 kb_load.py。
```

---

## 坑 2 只比计数，不看字节

**现象**：发布记录写"nodes 17→17，edges 17→17，无变化"，但抽样节点发现某个实体的 `source_date` 被改了。计数一样，内容换了。

**原因**：比较的是 `COUNT(*)`，不是内容。计数是最弱的相等性。

**改法**：比规范化后的 sha256（`sort_keys` + 固定缩进 + LF），节点和边**分开算**。本模板的 `--dry` 直接打 `字节相同=True/False`：

```
DRY  previous sha=050d0a72d851e4ba…  new sha=050d0a72d851e4ba…  字节相同=True
```

再补一层抽样：跨类型各取一个节点，人工确认上批成果还在。

---

## 坑 3 Windows 文本模式换行，把 sha 弄坏

**现象**：同一份内容，两次构建 sha 不同；或者 sidecar 里的 hash 与 `certutil` / `sha256sum` 算出来的不一致。

**原因**：`open(path, "w")` 在 Windows 上把 `\n` 翻成 `\r\n`。内容看起来一样，字节多了 17 个 `\r`。

**改法**：产物一律二进制写。

```python
kg_path.write_bytes(data)          # 而不是 open(..., "w").write(text)
```

所有文本文件统一 LF；CI 上比对前先确认工作区没有 `core.autocrlf` 在暗中转换。

**验证**：`certutil -hashfile output/kg.json SHA256` 与 sidecar 逐位相同。

---

## 坑 4 控制台乱码：文件是好的，显示是坏的

**现象**：`Get-Content query_log.jsonl` 看到 `"query": "灞辫胺"`，以为日志写坏了；用 Python 读出来却是 `山谷`。

**原因**：文件是 UTF-8，控制台按本地代码页（GBK）解码。字节没变，只是"翻译"错了。

**改法**：
- 跑 Python 一律加 `-X utf8`；
- 看文件用 `Get-Content -Encoding utf8`；
- **判断真伪只用程序**：`json.loads` 逐行通过 = 文件是好的。

这一条最贵：它让人去修一个不存在的问题，顺便把好的日志重写成真坏的。

---

## 坑 5 `ensure_ascii=True`：中文全变 `\uXXXX`

**现象**：日志里搜不到中文检索式，`grep 山谷 query_log.jsonl` 返回空；打开文件看到满屏 `\u5c71\u8c37`。

**原因**：`json.dumps` 默认 `ensure_ascii=True`，非 ASCII 全部转义。文件合法，但人工不可读、`grep` 不可用。

**改法**：`json.dumps(obj, ensure_ascii=False)` + UTF-8 编码写盘。

---

## 坑 6 Excel 另存的 CSV 带 BOM

**现象**：构建报一屏 `必填字段缺失: id`，但打开 CSV 明明有 `entity_id` 列。

**原因**：Excel「CSV UTF-8」会在文件头塞 BOM，第一列列名变成 `\ufeffentity_id`，`DictReader` 的键对不上，于是每个字段都"缺失"。

**改法**：读到的一切 CSV 用 `encoding="utf-8-sig"`（会自动吃掉 BOM）。这是唯一一处"编码参数写死"的地方，值得写死。

**自查**：报错里出现"全部行都缺同一列"时，先怀疑 BOM，不要怀疑数据。

---

## 坑 7 同一列名两种含义（我在搭这套示例时真踩到）

**现象**：所有边都报"悬空引用"，一次 34 个错误，节点全部正常。

**原因**：`edges.csv` 表头写成 `source,relation,target,source,...`——第一个 `source` 是起点、最后一个 `source` 是出处。`DictReader` 遇到重名列只保留最后一个，于是"起点"读成了"出处字符串"（`DEMO_SEED`），当然找不到这个实体。

**改法**：列名分开——`from` / `target` / `evidence_source`。一个词只表达一个含义；图上两端叫 `from`/`to` 或 `from`/`target`，出处永远叫 `source` 类名字。

**教训**：报错数量突然等于"边数"时，先查表头，不要逐行查数据。

---

## 坑 8 FTS5 对中文按整串分词

**现象**：图里明明有「山谷与齿轮」，搜「山谷」命中 0；换成 `LIKE` 就命中 1。

**原因**：FTS5 默认 `unicode61` 分词器把连续的中文字符当成**一个 token**，「山谷与齿轮」是整体，子串「山谷」匹配不到。换 `tokenize='trigram'` 能解子串，但 **trigram 只匹配长度 ≥3 的词**，2 字中文还是 0。

**改法**（按查询长度分流）：
- 检索词 ≥3 字符 → 可走 `trigram` FTS；
- 检索词 1–2 字符 → 走 `LIKE '%词%'`；
- 数据量不大时干脆统一 `LIKE`，别为省几毫秒引入一个"时灵时不灵"的索引。

**复现**：

```bash
python -X utf8 tools/kbq.py --root . --q 山谷 --engine fts          # hits=0  ← 坑
python -X utf8 tools/kbq.py --root . --q 山谷与齿轮 --engine fts     # hits=1  ← ≥3 字才行
python -X utf8 tools/kbq.py --root . --q 山谷 --engine like         # hits=1  ← 正解
```

顺带一提：`hits:0` 的这一幕被写进了 `run_demo.py` 第 ⑩ 项，因为它太容易让人误判"知识库里没有"。

---

## 坑 9 没有出处、没有日期的知识入了图

**现象**：三个月后要引用一条事实，找不到它从哪来；报告里只能写"据相关资料"。

**原因**：`source` 允许为空，或者写了一个未来的日期、一个"待补"。

**改法**：
- `source` + `source_date` 设成 schema 必填；
- 日期格式用正则卡死 `YYYY-MM-DD`；
- 确实不知道就写 `unknown`，构建时**告警**而不是静默通过；
- 过期不删，标 `invalid_since`（见 `04-query-contract.md` 第六节）。

---

## 坑 10 双向冗余边：改一处漏一处

**现象**：节点数没变，边数突然翻倍；或者正反两条边属性不一致，查询结果时有时无。

**原因**：`Book->Author` 和 `Author->Book` 都存了一遍。修一条忘一条。

**改法**：**只存单向 + 反向索引**。`kb.sqlite` 里 `idx_edges_src` 和 `idx_edges_dst` 两个索引已经够反查，`--neighbors` 两个方向都走。冗余存储带来的"查询更快"远小于"不一致"的代价。

---

## 坑 11 零命中不记账

**现象**：有人问"这个知识库覆盖得怎么样"，只能靠感觉；同一个缺口被不同的人重复排查。

**原因**：日志只在 `hits>0` 时写。

**改法**：`hits=0` 照写（模板已强制，`run_demo.py` 第 ⑧ 项专门验这条）。周复盘按检索式聚合，top10 零命中就是补录排期表。

**一句话**："查了但没命中"和"没查"必须是两件事，否则审计线不成立。

---

## 坑 12 时间戳写进快照

**现象**：每次重跑 sha 都不一样，于是无法回答"这次到底改没改内容"；有人干脆不看 sha 了。

**原因**：`kg.json` 里有 `built_at` 之类的字段。

**改法**：时间只写 `build_report.json`（不参与 sha），快照本身保持纯内容。要追溯"什么时候构建的"，看报告，不看快照。

---

## 坑 13 绝对路径写进产物

**现象**：别人 clone 下来直接报"路径不存在"；报告里的证据路径在他机器上打不开。

**原因**：生成时把「用户家目录绝对路径」写进了 JSON 或文档——最常出现两类：Windows 的盘符开头、类 Unix 的 home 目录开头。

**改法**：产物里存相对路径；文档用 `{{KB_ROOT}}` 占位；只有"证据日志"允许写绝对路径（它本来就是给同机复核用的）。

---

## 坑 14 直接覆盖写，中途崩溃留下半个文件

**现象**：`kg.json` 解析失败（JSON 截断），或者 sidecar 是新 sha、内容是旧的。

**原因**：原地 `open(..., "w")` 边写边覆盖；进程在写到一半时被杀/断电；或者两个进程同时写。

**改法**：
1. **原子替换**：写 `kg.json.tmp` → `os.replace()` 覆盖。替换是原子的，读者要么看到旧版要么看到新版。
2. **单写者**：`kg.json` 只由 `kb_build.py` 写，其他脚本只读。
3. **保留上一版快照**：替换不等于删除历史，`output/snapshots/<round_id>/` 留一份。

---

## 坑 15 在作者的机器上跑通 ≠ 别人能跑通

**现象**：作者本机 `python run_demo.py` → `PASS 13/13`；别人在一台干净的 Windows 上原样照 README 跑 → **退出码 1**：

```
UnicodeEncodeError: 'gbk' codec can't encode character '\u246a' in position 6
```

**原因**：输出里用圈码 `①—⑬` 当步骤编号。`①—⑩` 在 GBK（cp936）里存在，`⑪` 起不在——控制台一编码就抛异常。加 `-X utf8` 或 `PYTHONIOENCODING=utf-8` 能绕过，但 README 没让你加，读者就不会加。

**改法**（三层，缺一层还会复发）：
1. 脚本开头把自身输出固定成 UTF-8，并允许替换字符（不因终端编码中断）：
   ```python
   for _stream in (sys.stdout, sys.stderr):
       try:
           _stream.reconfigure(encoding="utf-8", errors="replace")
       except (AttributeError, ValueError):
           pass
   ```
2. **机器可读的标签用 ASCII**：`[11]` 而不是 `⑪`。装饰性符号不要当编号——它只在作者的字体里稳定。
3. 发布前在**新建的空目录**里跑一遍，不在原目录跑。原目录可能已被环境"养好"（PYTHONIOENCODING、改过的 PATH、缓存产物），它证明不了别人能跑。

**判据**：新建空目录 + 默认控制台 + README 里的原样命令 → exit 0。这一条已写进检查表门 B，且 `run_demo.py` 的第 [02] 项本身就在用临时目录做确定性重跑——同一个思路，用到发布上。

> 讽刺之处：本坑注册表第 4、8 条讲的就是编码显示问题。知道这类问题不等于不会踩，**只有"干净目录重跑"这道门能拦住它**。

---

## 速查表

| # | 坑 | 一句话判据 |
|---|---|---|
| 1 | STALE_INDEX | 查询前核 `meta.kg_sha256` == sidecar |
| 2 | 只比计数 | `--dry` 必须打 `字节相同` |
| 3 | 换行 | 二进制写，LF，certutil 交叉验 |
| 4 | 控制台乱码 | `json.loads` 通过就是好的 |
| 5 | `\uXXXX` | `ensure_ascii=False` |
| 6 | CSV BOM | `encoding="utf-8-sig"` |
| 7 | 列名两义 | `from` / `evidence_source` |
| 8 | FTS 中文 | <3 字走 LIKE，别信 FTS |
| 9 | 无出处 | `source_date` 必填 + 正则 |
| 10 | 双向边 | 单向存，反向索引查 |
| 11 | 零命中不记 | `hits:0` 照写 |
| 12 | 时间戳进快照 | 时间只进 `build_report.json` |
| 13 | 绝对路径 | 产物用相对路径 |
| 14 | 覆盖写 | tmp + `os.replace` |
| 15 | 只有作者机器能跑 | 干净空目录 + 默认控制台 + 原样命令 → exit 0 |
