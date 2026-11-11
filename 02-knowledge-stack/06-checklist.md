# 06 · 检查表

四个门，每个门都是"能勾选的事实"，不是"感觉差不多了"。

---

## 门 A：建库门（从零到能查）

- [ ] Python ≥3.10，命令带 `-X utf8`
- [ ] `seed/nodes.csv` 每行都有 `source` 和 `source_date`
- [ ] `seed/edges.csv` 列名是 `from / relation / target / evidence_source / source_date / confidence`（没有重名列）
- [ ] `schema.json` 有 `id_pattern`，且所有 id 都符合
- [ ] `relation_types` 每个关系都写了 `from` / `to` 类型约束
- [ ] 关系只存单向（没有 `A->B` 又存 `B->A`）
- [ ] `python tools/kb_build.py --root .` 退出码 0
- [ ] `python tools/kb_build.py --root . --dry` 第二次跑：`字节相同=True`
- [ ] `output/kg.json.sha256` 与 `certutil`/`sha256sum` 独立计算结果一致
- [ ] `python tools/kb_load.py --root .` 后 `entities`/`edges` 与 KG 完全相等
- [ ] `python tools/kbq.py --root . --q {{一个你确定存在的词}}` 命中且带 `source_date`
- [ ] `python tools/kbq.py --root . --q {{一个确定不存在的词}}` 返回 `hits:0`，且日志多了一行
- [ ] `python -X utf8 run_demo.py` → `VERDICT PASS 13/13`
- [ ] **干净目录复验**：把目录复制到新建的空目录，默认控制台、README 里的原样命令再跑一遍 → exit 0（坑 15）

> 最后一项是最省事的整体自检：它跑的就是上面这些，外加 RAG 装配。

---

## 门 B：发布门（缺一件不发）

- [ ] 预注册已写：`round_id` / `prev_snapshot(sha)` / `out_dir` / 五项预期数字 / 口径 / 白名单
- [ ] 上一版快照已复制到 `output/snapshots/<round_id>/`，sha 已核
- [ ] 干跑已跑：`--dry` 输出已记录，`字节相同` 与预期一致
- [ ] 抽样已做：跨类型各 1 个节点在位
- [ ] 双向检索回归：被删名字搜不到 + 旧 id 仍命中
- [ ] `kb_audit.py --expect-nodes N --expect-edges M` → `verdict=PASS`，`output/audit.json` 已落盘
- [ ] 回滚方案 ≤3 步，且**第 3 步包含重建索引**（只回滚图不重建索引 = 没回滚）
- [ ] 发布记录已写：prev sha / new sha / 五项差 / 白名单外变更 / 回滚路径
- [ ] 失败产物（如有）已留档，未删除
- [ ] **独立脱敏扫描**（不认自扫）→ BLOCK 0；自扫只算预检。注意同一路径在 JSON 里转义成 `\\`、在正文里是 `\`，只搜一种形态会漏（本包踩过一次：讲"绝对路径"那条坑，正文里自己写了绝对路径）
- [ ] 门回执带覆盖数：实际扫了多少文件、多少字节；**扫到 0 个文件一律判 FAIL，不许报 PASS**（对空目录报"0 命中通过"是假门，扫 0 文件却 PASS 的门等于没装）

---

## 门 C：查询门（每次回答前）

- [ ] 结果里带 `snapshot_sha`
- [ ] 结果里带 `hits`
- [ ] 引用的事实带 `source_date`
- [ ] 多图并存时，结论里写清是哪张图；**不同图的指标不混算**
- [ ] 任何覆盖率/命中率数字都写了"图名 + sha + 分子分母口径"
- [ ] 零命中已记账，且写清"还试过哪些检索路径"

---

## 门 D：周检（10 分钟，每周一次）

- [ ] `kb_audit.py` 复跑，`verdict` 仍为 PASS，记录当前 sha
- [ ] 零命中 top10 导出，分类：该补 / 改别名 / 范围外
- [ ] 新增实体是否都有出处（抽查 5 条）
- [ ] `query_log.jsonl` 行数增长正常（突然不涨 = 查询器坏了或没人用了）
- [ ] 索引 sha 与快照 sha 仍相等（防"有人改了图没重建索引"）
- [ ] 上一周的补录清单，完成了几条（不完成就说明排期没进计划）

---

## 一页速记

```
建库：SEED 有出处 → Schema 有格式门 → 构建 sha 稳定 → 索引数相等 → 能查能反查
发布：预注册 → 干跑比字节 → 抽样/双向回归 → 体检 PASS → 回滚 ≤3 步 → 写记录
查询：带 sha、带 hits、带日期；零命中要记账；多图不混算
周检：audit 复跑 + 零命中 top10 + 出处抽查 + sha 仍相等
```
