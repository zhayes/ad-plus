---
name: viral-recreate-analyst
description: 拆解参考爆款视频，产出 skeleton.json 与 gag_spec.json（笑点机制、必须保留项、落点时间）。当用户给一条参考视频说“照着这个做”“复制爆款”“同款不同商品”时使用；只做拆解与判断，不生成画面。
---

# 爆款拆解分析（Analyst）

你的唯一产出是两份文件：`skeleton.json`（结构事实）和 `gag_spec.json`（笑点机制）。
不要在这一步生成脚本、画面或商品图。

## 何时用

- 用户给视频文件/链接，说“照着这个做一条”“复制这个爆款”“换个商品”。
- 用户已经在用「复制爆款」模块，需要确认“这条片子能不能复制”。

不要用于：只想剪辑原片、只想转录、只想换衣服（那是 restyle）。

## 第一步：跑解析器，不要手拆

```bash
python -m adplus.recreate.cli <video> --out <dir> --max-frames 8
```

读取 `<dir>/skeleton.json`。**先相信数字，再看画面**：切点、beat、语速、运动量都在里面。

## 第二步：判断能不能复制（先劝退，再开工）

按顺序检查，任一不满足就明确告诉用户“这条不建议复制”，并说明原因：

| 检查 | 门槛 | 不满足时 |
|---|---|---|
| 时长 | ≤ 20s（30s 以上要拆段） | 建议截取其中一段 |
| 切点 | ≤ 4 | 建议只取一个场景 |
| 商品可见 | ≥ 60% 的 beat | 商品槽不成立，换片 |
| 人声质量 | `speech.quality.status == "ok"` | 纯音乐片走“无对白模板”，不要编台词 |

`skeleton.json` 里 `speech.quality.status == "low"` 表示转写可能是音乐/音效误识别。
这种情况下**不要**引用台词做判断，只能基于画面与节奏。

## 第三步：写 gag_spec

笑点必须落到“机制”，不是“剧情简介”。先在下面选一个机制，不要自创：

| mechanism | 中文 | 典型结构 |
|---|---|---|
| `price_compare_punchline` | 比价 + 贬损 + 动作兑现 | 报价 → 被吐槽 → 有活动 → 去抢 |
| `status_contrast` | 身份反差 | 正经人做不正经的事 |
| `misunderstanding` | 误会 | A 以为 → B 揭穿 |
| `exaggeration` | 夸张 | 小事放大到荒诞 |
| `repetition` | 重复/复读 | 同一句反复，最后一次变味 |
| `snatch` | 抢夺/动作梗 | 语言说“抢”，身体真的抢 |
| `callout` | 打脸/反转 | 立 flag → 立刻打脸 |
| `testimonial` | 测评口播 | 痛点 → 演示 → 结论 |
| `unboxing` | 开箱 | 拆 → 看 → 用 |
| `none` | 无梗 | 纯展示片，如实写 none |

`gag_spec.json` 字段：

```json
{
  "mechanism": "price_compare_punchline",
  "mechanism_label": "攀比价格 → 贬损 → 促销反转 → 抢的双关兑现成动作",
  "comedy_structure": {"setup": "...", "escalation": "...", "twist": "...", "payoff": "..."},
  "why_it_is_funny": ["反差", "具体数字", "贬损", "语言兑现动作"],
  "must_keep": [
    {"id": "m1", "text": "四人正经群像", "beat": "b0", "confidence": 0.8}
  ],
  "may_change": ["商品", "价格", "人物", "场景", "措辞"],
  "timing": {"punchline_beat": "b5", "punchline_at_s": 9.0},
  "performance": {"style": "一本正经", "faces": "克制微笑"},
  "transferable": true,
  "risks": ["贬损台词可能被判不当表述", "价格需真实可举证"],
  "confidence": 0.8
}
```

### must_keep 的写法（最容易写坏）

1. **4–7 条，每条必须可检查**。写“要有趣”是废话；写“最后 2 秒有人跑出画”可检查。
2. **每条挂到一个 beat**，写不出 beat 的就不是结构，是感想。
3. **优先保留：机制、顺序、落点时间、动作**；其次才是服装、场景、道具。
4. 不要保留：具体台词措辞、品牌名、演员长相。

### 落点判断

- 笑点通常在全片最后 15–25%。用 `timing.punchline_at_s` 标出**动作发生**的时刻，不是台词开始。
- 如果最后一段语速明显变快、或运动量从 slow 跳到 fast，落点大概率在那里。
- 找不到落点就写 `"punchline_beat": null` 并把 `confidence` 压到 0.4 以下，明确告诉用户“这条片没看出梗”。

## 第四步：交付前自检

- [ ] mechanism 在词表里，不是自造词
- [ ] must_keep 每条都有 beat 且可被第三个人检查
- [ ] punchline 时间与 skeleton 的 beat 对得上（±0.3s）
- [ ] 没有任何“剧情简介式”的描述（“讲述了一个……的故事”）
- [ ] 商品槽、时长、切点已按门槛判断过

## 常见错误

| 错误 | 后果 |
|---|---|
| 把“剧情梗概”当 gag_spec | 后面改写出来没有笑点，只剩结构 |
| must_keep 写抽象要求 | 无法验收，等于没写 |
| 无对白片硬编台词 | 生成阶段会造出不存在的信息 |
| 忽略 `speech.quality` | 把音乐误识别当台词，整条跑偏 |
| 只保留画面、不保留落点时间 | 剪辑节奏散掉，笑点不响 |
