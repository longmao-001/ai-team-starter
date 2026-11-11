# 90 工具与发布

| 文件 | 作用 | 用法 |
|---|---|---|
| [`sanitize_scan.py`](sanitize_scan.py) | 脱敏扫描（结构层 + 本地实体名单层） | `python 90-tooling/sanitize_scan.py --root .` |
| [`scaffold.py`](scaffold.py) | 按配置渲染团队目录 | `python 90-tooling/scaffold.py --config team.config.json --out ../my-team` |
| [`release.md`](release.md) | 发布流程与打 tag 纪律 | 发布前逐条走 |
| [`rules/denylist.example.txt`](rules/denylist.example.txt) | 本地实体名单的**格式示例** | 复制成 `rules/denylist.local.txt`（不入库） |
| [`examples/team.config.example.json`](examples/team.config.example.json) | 脚手架配置示例 | 复制成 `team.config.json` 改 |

## 核文件不要用 `Get-Content`（Windows PowerShell 5.1）

这个坑两条都要记，都是实测：

| 动作 | 用 `Get-Content` 会怎样 | 改用什么 |
|---|---|---|
| 读 UTF-8 无 BOM 的中文文件 | 默认按 ANSI 解码 → 满屏乱码，看着像文件坏了 | `Get-Content -Encoding utf8`，或直接用编辑器的 read |
| 数行数 | 对某些 UTF-8 文件会数错（实测 37 vs 实际 97，同一文件） | `[IO.File]::ReadAllLines($p).Count` |

报行数、报字节、报哈希，都要说清口径：**什么工具、什么编码、算不算末尾空行**。不然两份"都对"的数字会打起来。

## 为什么扫描器分两层

公开仓库要防两类东西，性质不同：

1. **结构类**（路径、IP、邮箱、密钥、证件号）→ 规则可以公开，正则就能查，规则文件随仓库走；
2. **实体类**（真实人名、机构名、项目代号）→ **名单本身就是敏感信息**。把真名写进仓库的 denylist，等于换个地方泄露。

所以第二层是**本地名单** `90-tooling/rules/denylist.local.txt`，`.gitignore` 已排除。

代价要说清：**CI 只能跑第一层**。实体类只能靠发布人在本地跑，并把**汇总结果**（命中条数，不含原文）贴在回执里。这是刻意取舍，不是遗漏。

**名单词条至少 2 个字。** 单字词条（折 / 衡 / 利…）会命中大量普通词——实测中文单字名单在 50 个文件里立刻报出 2 处误报（"打折"里的"折"），真命中会被淹没。扫描器遇到 <2 字词条会忽略并警告，别指望它替你记住这条。

## 一行标记：`sanitize:allow`

规则文档里必然出现"坏例子"，例如路径长什么样。这类行尾加：

```markdown
例：`\\host\share` 属于内网路径 <!-- sanitize:allow -->
```

被放行的命中仍会计数并显示在 "allow 放行" 一行——**放行不是隐身**，审计时能看见放行了多少处。

## 扫描结果怎么读

- **BLOCK**：命中即不许发布，没有例外（要走例外就改规则文件并写明理由，改规则本身要留痕）。
- **WARN**：允许存在，但每条要有理由。占位符 `{{X}}` 在模板里是正常的，在成品里就是漏填。
- 报告里命中的原文**一律打码**（只留前 3 字符），所以报告本身可以贴进 PR 或回执。
