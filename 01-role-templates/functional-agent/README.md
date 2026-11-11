# 功能 agent（执行者）

## 它是谁

有**固定输入、固定输出、可验收**的执行者。你不需要它"有想法"，你需要它**每次都按同一个口径交同一个东西**。

## 目录

| 文件 | 用途 | 什么时候填 |
|---|---|---|
| [`ROLE_CARD.template.md`](ROLE_CARD.template.md) | 主角色卡（一页） | 建 bot 的第一步 |
| [`WORK_SCOPE.template.md`](WORK_SCOPE.template.md) | 工作内容与交付形态 | 角色卡填完后 |
| [`SKILLS.template.md`](SKILLS.template.md) | 技能挂载与调用条件 | 有可复用方法论时 |
| [`antipatterns.md`](antipatterns.md) | 写歪了长什么样 | 每稿都对照一遍 |

## 判断它该不该存在

连续问三个问题，都要能答"能"：

1. 这件事**每周都干**吗？（一次性的事，别建 bot）
2. 产出**能被别人一眼判对错**吗？（判不了，说明还没想清楚）
3. 输入**能从固定来源拿到**吗？（靠人临时凑，它必然漂移）

## 一个最小可用的样子

> `{{ROLE_NAME}}` 拿到 `{{INPUT_SOURCE}}`，按 `{{METHOD}}` 处理，产出 `{{OUTPUT_ARTIFACT}}`，交 `{{OWNER}}` 验收。输入不全就停下并列出缺哪几项，不许猜。

这句话里五个空都填实，功能 agent 就能跑了。
