# A+B 落地：架构与 UI 交互调整方案

> 前置：[kickart-alignment-feasibility.md](kickart-alignment-feasibility.md)（路线 A：快速成片；路线 B：爆款裂变）
> 日期：2026-11-09
> 结论先说：A 和 B 不是两个功能，是**同一个缺失的原语**——批次（batch）里跑 N 个变体（variant）。补上它，A 和 B 只是两个入口、两套模板。

---

## 0. 现在卡在哪

当前是「**一个项目 = 一个当前版本 = 七道闸门**」：

- `project.current_version_id` 只指向一个版本（`adplus/project_store.py`）；
- `production_payload()` 只读当前版本，阶段状态由它派生（`adplus/production.py`）；
- `approvals.json` 是 `{stage: {...}}` 的扁平结构，没有版本维度；
- 前端 `StageRail` 把七个阶段摊开，`Studio` 一次只编辑一个版本；
- 批量生成、变体对比、采用哪条，都没有承载对象。

A 要的是「一个输入 → 3–6 条不同 hook 的片子」，B 要的是「一个源片 → 6–12 条同结构变体」。两者都是「一对多」，而现在数据模型是「一对一」。

---

## 1. 目标形态：三屏

```
① 输入屏 /create            ② 批次屏 /batch/:id           ③ 精修屏 /studio/:id/:stage
   图片/链接 + 3 个问题    →    6 个变体卡片、进度、成本   →    现有七阶段（不改内核）
   一次确认                  →    对比 / 采用 / 补齐失败     →    从某个变体进入，改完回批次
```

默认路径只有 ①→②。③ 是「精修」，不是必经之路。

---

## 2. 架构调整

### 2.1 领域模型：批量与变体

新增 `batches/<batch_id>.json`：

```json
{
  "id": "b1",
  "project_id": "p-xxx",
  "kind": "quick | fission",
  "source": {"type": "upload | url | project", "ref": "..."},
  "brief": {"product": "...", "audience": "...", "platform": "douyin", "duration_s": 15},
  "axes": [
    {"key": "hook", "values": ["痛点", "对比", "价格"]},
    {"key": "cover", "values": ["人物", "产品特写"]}
  ],
  "variants": [
    {"id": "b1v1", "version_id": "v2", "key": "hook=痛点|cover=人物", "status": "queued"},
    {"id": "b1v2", "version_id": "v3", "key": "hook=对比|cover=人物", "status": "failed", "error": "..."}
  ],
  "policy": {
    "auto_stages": ["brief", "proposal", "script", "scene", "assets", "compose"],
    "confirm_stages": ["review"],
    "max_cost_usd": 6.0,
    "concurrency": 2,
    "max_variants": 12
  },
  "adopted_variant": null,
  "created_at": "..."
}
```

`versions/<id>.json` **只做加法**：`batch_id`、`variant_key`、`template_id`、`parent_version_id`。`normalise` 里给默认值，老版本不受影响。

`project.json` 增加 `current_batch_id`；`current_version_id` 继续表示「被采用的那条」，语义不变。

**兼容策略**：老项目在读的时候生成一个虚拟批次 `b-legacy`（单变体），不跑迁移脚本。列表页看不出区别。

### 2.2 阶段派生改成「版本级 + 批次聚合」

三处具体改动：

| 现在 | 改成 |
|---|---|
| `production._version(project_id)` | `_version(project_id, version_id=None)`，不传才回落到 current |
| `production_payload(project_id)` | 增加 `version_id` 参数，返回该变体的七阶段 |
| `load_approvals(project_id)` → `{stage: {...}}` | `{version_id: {stage: {...}}}`，读到旧扁平结构时当作 `current_version_id` 的审批 |

新增 `batch_payload(batch_id)`：只聚合，不存状态。

```python
# 派生，不落盘
status = "complete" if all(v.ready or v.adopted) else
         "partial"  if any(v.ready) and any(v.failed) else
         "running"  if any(v.running) else "planned"
```

**不要**把批次状态写进 `project.json` 当真源——这是现在 `production.py` 已经踩过的坑（阶段状态必须可派生）。

### 2.3 Autopilot 策略层（新增 `adplus/autopilot.py`）

A 的核心不是「少点几下」，是**把七道确认变成一次确认 + 三类例外**：

```python
def decide(batch, stage, ctx) -> Literal["auto", "confirm", "blocked"]:
    # 预算：estimate > max_cost_usd      -> confirm（花钱前停一次）
    # 能力：provider blocked / 缺 key    -> blocked（提前停，不烧钱）
    # 质量：final_review fail / 标签失败 -> 不变 confirm，变体标记 failed
    # 其余：stage in policy.auto_stages  -> auto
```

自动审批仍写审批记录（`by: "autopilot"`、`policy`、`quote_id`），审计链不断。`review` 默认永远人工——这是 Ad+ 和 Kickart 的差异点，不要自动掉。

### 2.4 批次执行器（新增 `adplus/batch.py`）

只做调度，不做执行：

```
plan(batch)  →  build_batch_quote()  →  run(batch)
run:  按 concurrency 取 variant
      每个 variant：ensure_version → 依次跑 auto 阶段 → 停在 confirm 阶段
      成功 → ready；异常 → failed(error)，继续下一个
```

复用 `pipeline_runner` 与 `local_motion` 的 `start/build`，**不新造第二个 orchestrator**（`docs/architecture-reset.md` 的边界）。

三个必须有的细节：

- **幂等**：`variant_key` 哈希做去重，重跑只补 `failed`/`queued`；
- **失败隔离**：单条失败不 fail 整批，批次进 `partial`；
- **取消**：`batch.cancel_requested` 只停「还没开始的」，在跑的走现有 job 取消。

### 2.5 报价：从「一条」到「N 条」

`quote.build_quote()` 已有工具级估算（`adplus/quote.py`），加一层：

```python
build_batch_quote(brief, variants) -> {
  "unit_usd": 0.31, "count": 6, "subtotal_usd": 1.86,
  "retry_reserve_usd": 0.28, "total_usd": 2.14, "over_budget": false
}
```

- 预算守卫放在**启动前**和**每次 provider 调用前**（后者复用 `capabilities.preflight`）；
- 前端展示「单条 / 总价 / 上限」，超预算二次确认；
- 报价按变体拆行，不再是渲染级一口价（顺手修掉 `refactor-v5-status.md` 里的待办 5）。

### 2.6 模板：让 A 的供给成立

新增 `templates/<id>/manifest.json` + `scene.tsx`：

```json
{
  "id": "product-pop",
  "label": "产品快闪",
  "aspects": ["9:16", "1:1"],
  "durations": [6, 15, 30],
  "slots": ["hook", "product", "proof", "cta"],
  "params": {"palette": "brand", "caption": "bold-bottom"},
  "preview": "cover.jpg"
}
```

`local_motion.build(project_id, template_id, params)` 按 manifest 填槽，不再从分镜硬编码版式。**模板 = 版式 + 动效 + 字幕规则**，不是新 pipeline，也不碰 `vendor/openmontage`。

首批 8 套：从现有 `styles/` 和 `local_motion` 的占位版式里提炼，先覆盖「产品卖点 / 价格 / 对比 / 口播」四类。

### 2.7 B：改写（restyle）变体化

`plan.json` 现在是一份「基础造型」，加一个只读叠加层：

```json
"variants": [
  {"id": "r1", "label": "深色外套 + 黄字", "patch": {"cast": {"outfit_targets": {...}}, "captions": {...}}},
  {"id": "r2", "label": "浅色外套 + 白字", "patch": {...}}
]
```

派生用现成的 `plans.apply_patch()`，每个 patch 作用在 `copy.deepcopy(plan)` 上；渲染仍走 restyle 现有链路，失败回退原镜头。

**v1 边界要写死**（`docs/restyle-pipeline-plan.md` 已判定 MiniMax 生成主链路 No-Go）：

- 只做 L1 本地换色/换材质 + 字幕/BGM/旁白；
- 不承诺换版型、换品类、换脸；
- 质量门沿用 `safe / review / keep`。

好处是单位成本极低（本地换色近乎 0，TTS 几分钱），6–12 条变体的经济模型成立。

### 2.8 入口 intake（新增 `adplus/intake.py`）

- v1：上传图片/视频 + 产品名 + 卖点 + 平台/时长 → 生成 brief 草稿（用户可改，不自动花钱）；
- URL：只存引用 + 抓 OG 标题/主图；**不做抖音商品解析**（风控、合规、接口稳定性都不在可控范围），P2 再议；
- 输出结构直接喂 `project_store.create_project(brief=...)`。

### 2.9 API diff

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/batches` | `{kind, source, brief, axes, n, policy}` → batch |
| GET | `/api/batches/{id}` | 批次 + 变体 + 报价 + 进度 |
| POST | `/api/batches/{id}/plan` | 生成批量报价，不执行 |
| POST | `/api/batches/{id}/run` | 启动；返回 job/batch |
| POST | `/api/batches/{id}/cancel` | 停未开始的 |
| POST | `/api/batches/{id}/variants/{vid}/retry` | 只补失败 |
| POST | `/api/batches/{id}/variants/{vid}/adopt` | 设为 current_version |
| GET | `/api/projects/{id}/production?version_id=` | 变体级阶段视图 |
| GET | `/api/templates` | 模板列表 + 封面 |
| POST | `/api/intake/resolve` | 图片/URL → brief 草稿 |
| POST | `/api/restyle/{id}/variants` | 写入变体轴，派生 plan 副本 |
| POST | `/api/restyle/{id}/render` | 批量渲染（带变体 id 列表） |

### 2.10 存储布局

```
projects/<id>/
  project.json                 # + current_batch_id
  batches/b1.json
  versions/v2.json             # + batch_id / variant_key / template_id
  approvals.json               # 改成 {version_id: {stage: ...}}
  renders/<version_id>/...
  batch/b1/sheet.jpg           # 对比图
```

---

## 3. UI 交互调整

### 3.1 路由

| 现在 | 改成 |
|---|---|
| `/` `/projects` | 保留 |
| `/studio/:id/:tab?` | 保留，加 `?variant=`；语义变「精修」 |
| `/chat/:sessionId?` | **删除入口**，合并进 `/create` |
| — | **新增** `/create` |
| — | **新增** `/batch/:batchId` |
| `/restyle` `/restyle/:id` | 保留，工作台加变体矩阵 |
| `/assets` `/tasks` `/settings` | 保留，任务页按批次聚合 |

`/chat` 只留兼容跳转，不再出现在 Dock——现在「沙盒 vs 主流程」两个入口本身就是上一轮没收敛干净的地方（`docs/refactor-v5-status.md`）。

### 3.2 Dock

```
项目   快速成片   改写   资产   任务                设置
```

- 「制作」并入「项目 / 批次」：点项目直接进最近的批次，不再单独占一个入口；
- 「自由创作」改名「快速成片」，指向 `/create`；
- 「改写」保留，作为 B 的独立入口（它有自己的源片和权利确认流程）。

### 3.3 输入屏 `/create`

```
┌ 快速成片 ─────────────────────────────────────────────┐
│                                                        │
│   ┌──────────────┐   产品名  [炭火现烤红薯________]     │
│   │  拖入主图/视频 │   卖给谁  [下班想吃点热的年轻人__]   │
│   │  或粘贴链接    │   平台    [抖音] [小红书] [视频号]   │
│   └──────────────┘   时长    [6s] [15s] [30s]          │
│                      想突出  [现烤、流蜜、9.9________]  │
│                                                        │
│  变体  [3] [6] [12]      预计 6 条 · 约 $1.86 · 8 分钟  │
│                                      [ 生成 6 条 → ]   │
└────────────────────────────────────────────────────────┘
```

规则：

- 只问 4 件事，其余走默认值；
- 变体数直接关联报价，改数字实时改价；
- 没有「下一步」，点生成即开跑；
- 图片/链接二选一，链接解析失败时退化成「手动填」。

### 3.4 批次屏 `/batch/:id`

```
┌ 炭火红薯 · 6 变体 ─────────────────────────────────────┐
│ 4/6 完成   $1.24 / $6.00   [暂停] [全部导出]            │
│                                                        │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐                    │
│ │  v1 ▶   │ │  v2 ▶   │ │  v3 ⟳   │                    │
│ │ 痛点/人物│ │ 对比/特写│ │ 价格/人物│                    │
│ │ 15.0s   │ │ 14.8s   │ │ 生成中… │                    │
│ │ $0.31   │ │ $0.29   │ │ $0.31   │                    │
│ │[采用][精修]│ │[采用][精修]│ │[取消]   │                    │
│ └─────────┘ └─────────┘ └─────────┘                    │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐                    │
│ │  v4 ✕   │ │  v5 ▶   │ │  v6 ▶   │                    │
│ │ 生成失败 │ │ ...     │ │ ...     │                    │
│ │[重试]    │ │         │ │         │                    │
│ └─────────┘ └─────────┘ └─────────┘                    │
│                                                        │
│ 勾选 2–4 条 → [并排对比]   键盘 1–4 切换，空格播放       │
└────────────────────────────────────────────────────────┘
```

规则：

- 卡片只给「采用 / 精修 / 重试」三个动作，不做阶段轨道；
- 对比是独立模式，勾选后并排同步播放；
- 采用即 `current_version`，其余变体标 `archived`（不删，可回看）；
- 失败卡片显示可读原因（provider 拒绝 / 预算不足 / 质量门），不是堆栈。

### 3.5 精修屏 `/studio/:id/:stage?variant=v3`

- 顶部加面包屑：`← 6 变体 / v3 精修`；
- StageRail 保留，但只在这里出现；
- 审批写 `approvals[v3][stage]`，不污染别的变体；
- 改完回批次，卡片状态刷新为 `ready`。

### 3.6 改写工作台 `/restyle/:id`

现有三段（源片 / 基础 plan / 预览）不动，右侧加一列「变体矩阵」：

```
变体轴
  服装  [深色] [浅色] [条纹]
  字幕  [黄底黑字] [白字描边]
  旁白  [原声] [女声 A] [男声 B]
  封面  [人物] [产品]
  → 3 × 2 = 6 条            预计 $0.12 · 本地渲染
                            [ 生成 6 条 ]
```

底部变体条与批次屏复用同一个 `VariantGrid` 组件。

### 3.7 任务页 / 项目列表

- 任务页：按批次分组（`b1 · 4/6`），展开看单个 job；不再平铺所有 job；
- 项目卡：`6 变体 · 已采用 1` 替代阶段 badge；
- 项目详情：默认展示批次，精修历史折叠。

---

## 4. 交互规则（8 条，写进代码注释和验收）

1. **花钱前只确认一次**：N、单价、总价、ETA；之后只在预算/能力/质量三类事件打断。
2. **失败隔离**：变体失败不拖垮批次；「补齐」只跑 failed/queued。
3. **采用即锁定**：`current_version` + `batch.adopted_variant`；落选归档不删。
4. **精修不复制**：在变体上继续改，版本 lineage 保留，不新建项目。
5. **默认无阶段轨道**：轨道只在精修出现，避免把专业流程当默认。
6. **所有批量操作先出价**：无报价不允许点「开始」。
7. **同批次复用身份与商品锁**：只变 hook/文案/服装/BGM/封面，防身份漂移和标签漂移。
8. **任务按批次聚合**：用户理解的是「6 条片子」，不是 37 个 job。

---

## 5. 实施顺序

| 阶段 | 周期 | 交付 | 主要文件 | 验收 |
|---|---|---|---|---|
| **P0** | W1–2 | 批次模型 + autopilot + 批次执行器 + `/create` + `/batch`（仅 local_motion） | 新增 `adplus/batches.py`、`autopilot.py`、`batch.py`；改 `production.py`、`project_store.py`、`settings_server.py`；新增 `routes/Create.tsx`、`routes/Batch.tsx`、`components/batch/*` | 一个输入 → 3 条 → 一次确认 → 采用 1 条 |
| **P1** | W3–4 | restyle 变体轴 + 6–12 条 + 对比 + 失败补齐 | `adplus/restyle/plans.py`、`store.py`、`routes/RestyleWorkbench.tsx` | 6 条同结构变体，单条失败可补 |
| **P2** | W5–6 | 8 套模板 + 项目/任务聚合 + 批量导出 + AIGC 标识 | 新增 `templates/*`、`adplus/templates.py`；改 `local_motion.py`、`Tasks.tsx`、`Projects.tsx`、`ExportDialog.tsx` | 模板可换参；导出 zip + 标识 |

**P0 的隐藏工作量**：`approvals.json` 的版本维度迁移，和 `production_payload` 的变体参数。这两处不做，P1 会返工。

---

## 6. 明确不改的东西

- 七阶段本身、审批语义、`canonical_artifact`、OpenMontage 边界（`docs/architecture-reset.md`）；
- 商品锁定与标签保真、persona 授权、报价审计；
- `vendor/openmontage` 子模块，不加 `restyle.yaml`；
- 单条精修的完整能力——它是 Ad+ 的差异点，不能被「一键」吃掉。

**不要**新增第二个 orchestrator，也不要把批次状态存成第二份真源。

---

## 7. 风险与对策

| 风险 | 表现 | 对策 |
|---|---|---|
| 成本放大 | 12 条 × provider 调用，单次失控 | 默认 6、硬上限 12、预算守卫、按变体出价 |
| 限流/超时 | 并发打爆 provider | 并发 2 + 退避 + 失败隔离 |
| 身份漂移 | 6 条里人脸/商品不一致 | 同 persona/product lock，只变 hook/服装/BGM，固定种子 |
| 磁盘膨胀 | 6 份 1080p 渲染 | 变体 720p 落盘、采用后清理落选中间帧 |
| 改写质量 | 用户期待「换整件衣服」 | v1 只承诺换色/材质，UI 写明边界 |
| 链接解析 | 平台反爬/合规 | 只做引用 + OG，不承诺商品解析 |
| 入口再分叉 | `/chat` 与 `/create` 并存 | P0 就删 `/chat` 入口 |

---

## 8. 需要拍板的三件事

1. **默认变体数**：3（快、便宜）还是 6（更像 Kickart）？建议 6，上限 12。
2. **review 是否永远人工**：建议是——这是 Ad+ 唯一不能被自动化吃掉的价值。
3. **落选变体保留多久**：建议 30 天或「采用后保留 7 天」，避免磁盘和认知负担。

---

## 9. 可行性与质量上限（补）

### 9.1 两个分数要分开

| 维度 | 判断 | 说明 |
|---|---|---|
| **工程可行性** | **高** | A 基本是加法（批次/变体/入口），复用现有 production/local_motion；6 周 P0+P1 可信 |
| **质量对齐** | **中等偏低** | 同模型下「单镜头」能接近，「成片观感」不能自动接近；差距在模型之外 |

B 的工程可行性低于 A（约 5/10）：`adplus/restyle` 目前只有分析、blueprint、plan 和单帧换色，**没有视频渲染器**；`video_compose` / `video_stitch` 在能力审计里是缺口。B 要出 6 条片子，先得把合成链路补齐。

### 9.2 现状证据（决定质量上限的不是模型）

- `adplus/local_motion.py` 生成的 Remotion 场景只有**文字卡**：编号、标题、渐变背景、品牌水印；不引用商品图，也不引用任何实拍/生成画面。
- `music_library/` 为空；`final_review` 里 `music_present: False`。成片没有 BGM。
- `restyle` 的 L1 是 LAB 换色（`outfit.py`），单帧预览；没有逐帧合成与编码。
- `avatar_spokesperson` 目前 `available: False`；`hybrid` 依赖 key，默认不可用。
- 数字人冒烟是 Wav2Lip 480×720，文档自己写着「需要更好的口型/身份」。

**结论：现在 A 的默认成片不是「模型生成的广告」，是「带渐变背景的字幕卡」。** 在这条路径上，换任何模型都不会变好——因为它根本没用视频模型。

### 9.3 成片质量的构成

按短视频广告的经验拆：

```
成片观感 ≈ 模型生成 30% + 素材/模板 35% + 剪辑/音乐/字幕 25% + 文案 10%
```

Ad+ 今天：模型有（但走的是中档配置）、素材/模板弱、剪辑/音乐缺、文案中等。

Kickart 的「对应质量」里，很大一块是模板、音乐、节奏、字幕堆出来的，不是模型独家。**所以同模型下，Ad+ 的单镜头可以接近，成片不会自动接近。**

### 9.4 逐路线判断

| 路线 | 现在 | 精简 + 6 周 | 12 周上限 | 真正瓶颈 | 单条成本 |
|---|---|---|---|---|---|
| A · local_motion | 2/5（文字卡） | 3–3.5/5 | 4/5 | 模板设计 + 素材预处理 | ≈0 |
| A · hybrid（Seedance） | 2.5/5（路线默认不可用） | 3.5–4/5 | 4–4.5/5 | 剪辑/音乐/一致性 | $0.2–1 |
| B · restyle 裂变 | 1/5（无渲染器） | 3.5–4/5 | 4.5/5 | 可换维度太少（只有颜色/材质） | ≈0（TTS 几分钱） |
| 自由创作 | 不可评 | 不可评 | — | 沙盒，不该承诺质量 | 按调用 |
| 商品库/标签保真 | 4/5 | 4.5/5 | 4.5/5 | 与模型无关，是控制层 | 0 |

### 9.5 关键结论：A 难在质量，B 质量是继承来的

- **A 是从零生成**，要同时解决画面、版式、音乐、节奏，四条都得建；6 周只能做到「能看」，做不到「像 Kickart 的模板片」。
- **B 的质量继承自源片**：源片本身就是验证过的爆款，换色/换字幕/换旁白不会破坏它的镜头和节奏。所以 B 更快接近「敢投」，成本几乎为零。
- **B 的代价不是质量，是同质化和平台判定**：6 条变体长得像同一条片子，且涉及原创/搬运边界，需要权利确认和差异化门槛。
- 这也解释了为什么建议「A 做入口、B 做切口」：**A 负责让人愿意试，B 负责让人愿意付。**

「同样的模型」这个前提只对视频模型成立；Kickart 的规划模型、模板库、音乐库、投放数据都不在同一个起跑线上。字节自家还能更早拿到新 checkpoint，公开 API 通常滞后——这是结构性差距，工程补不了。

### 9.6 精简建议

**砍掉（不是隐藏）**：

- `/chat` 独立入口 → 并入 `/create`；
- 旧 `Workspace` 路由；
- 默认路径里的手动分镜编辑（保留在精修）；
- `avatar_spokesperson` 从路线选择里移除，只在「实验」里按 key 出现；
- `hybrid` 不作为默认路线，只在精修里选。

**保留（这些是质量资产）**：

- 商品库 + 标签/SKU 锁定 + 标签 QA；
- persona 授权与身份一致性；
- 报价 / 审批 / 审片；
- `local_motion` 与 `restyle`；
- 导出与交付包。

**缓做**：云编辑器、多人协作、模板市场、投放 API。

**精简为什么能提升质量**：现在的问题不是功能少，是**每条路都半成品**（hybrid 不可用、avatar 不可用、local_motion 是占位版式、restyle 没有渲染器）。砍到两条能跑通的路，默认路径的唯一性会让用户预期稳定，也让测试和调优有焦点。

### 9.7 质量提升的 ROI 排序（先做前四个）

1. **素材预处理**：商品抠图、白底/场景合成、首帧选择——便宜，观感提升最大。
2. **8–16 套真模板**：不是渐变卡，是有版式、有层级、有品牌位的东西——A 的生死线。
3. **BGM/音效库 + 节拍对齐**：现在是静音片，补上等于换了一个产品。
4. **字幕排版**：关键词强调、安全区、字重层级——便宜且立刻「像广告」。
5. **剪辑节奏**：hook 前 1.5s、0.8–1.2s 切、结尾 CTA 停留——算法可做。
6. **封面/首帧 A/B**：影响点击，不影响完播。
7. **生成式换装**：贵、慢、一致性风险高，最后做。

### 9.8 两周盲评实验（别用观点代替数据）

- 10 条真实 brief，3 组：A 默认、A + 模板/音乐、B（拿一条对标片裂变）。
- 5 位目标用户盲看，只问三题：像不像广告、想不想看完、敢不敢投。
- 同时记录：单条成本、出片时间、失败率。
- 决策规则：若 B 的「敢投」≥ A+0.5 且成本 < A 的 1/5，B 作为主切口；否则 A 做入口、B 做补充。

---

## 10. 一句话

**工程上做得到，质量上要分路线看：A 六周能做到「能看」，做不到「像 Kickart」；B 因为质量继承自源片，反而更快接近「敢投」。**
真正决定成败的不是模型，是模板、素材预处理、音乐和节奏这四件「不性感」的事。
