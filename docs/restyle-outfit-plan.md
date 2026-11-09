# 换装（Outfit Restyle）调研与旧版计划

> **执行版已迁移到 [restyle-pipeline-plan.md](restyle-pipeline-plan.md)。** 本文件保留市场调研和早期推演，不再作为实施依据。

> 目标：同一条广告、同一个人、同一个商品、同一节奏；把衣服**真正换掉**，输出可播放视频。
> 范围：先做“保版型换装”，再评估“换版型/换品类”。

---

## 0. 整体思路

> **结构锁死，人物分层；能确定的用本地 CV，必须生成的只生成 mask 内的一小块，再合成回原帧。**

```text
广告结构层（锁死）：切点 / 时长 / 音频 / 商品 / 字幕位置
        ↓
人物层（可改）：人体解析 → 衣服 mask → 换色 / 换材质
        ↓
生成层（可选）：只对衣服 mask 做 inpaint / VTON，结果必须回贴
        ↓
合成层：原帧 + 新衣服 + 原商品 + 原背景
        ↓
编码层：原时间线 + 原音频
```

三条原则：

1. **商品像素不重建**：商品 mask 优先级最高；
2. **AI 只进 mask 里面**：整帧生成会改商品、改手、改背景；
3. **能局部重试**：一个镜头坏了只重渲染一个镜头，不整段重来。

## 0.1 先把“换装”拆成两级

| 级别 | 做什么 | 技术 | 风险 | 是否 v1 |
|---|---|---|---|---|
| **L1 保版型换装** | 同一件/同类版型，换颜色、材质、图案、明暗 | 人体解析 +  garment mask + LAB/纹理合成 | 低，商品可锁死 | ✅ 主验收 |
| **L2 换版型/换品类** | 短袖→长袖、浴袍→连衣裙、不同领口/廓形 | 生成式 inpainting / VTON，关键帧+传播 | 高，可能改手/商品/体型 | ⏳ 增强，单独验收 |

**建议（2026-11 修订）**：

- v1 的**控制面**仍然本地：拆镜、mask、商品锁、预览、QA、合成、回退；
- **生成引擎**由 M0 benchmark 决定：本地 L1（换色/材质）是默认与离线兜底；专用视频编辑 API（阿里云/腾讯云/Runway/Vidu/Seedance）作为 `review`/hero 镜头的候选；
- 如果“换装”必须包含 L2 换版型，不要把 L2 混进 L1 验收；单独 benchmark、单独排期。

---

## 0.2 质量优先原则（2026-11-09 修订）

既然目标是“更可控、能保证质量”，v1 采用**质量门控**，而不是追求 22 个镜头全换：

1. **v1 不做整段生成，也不做 L2 换版型**；只做本地 L1 换色/换材质。
2. 每个镜头先分类：
   - `safe`：解析置信度高、无商品/手遮挡、衣服面积足够 → 自动换；
   - `review`：边缘/遮挡/褶皱复杂 → 只出预览，用户确认后才换；
   - `keep`：商品特写、手部遮挡、解析失败 → 原样保留。
3. **默认只自动处理 `safe`**；`review` 必须人工点“通过”；`keep` 不允许偷偷改。
4. 渲染后自动 QA：商品 mask 像素、时序闪烁、边缘异常；不达标自动回退原镜头。
5. 接受覆盖率下降：参考片可能只有 **1/3–1/2 的镜头**真正换装；宁可少换，不换坏。

> 质量不是靠模型“每次都生成对”，而是靠**只改有把握的镜头 + 可预览 + 可回退**。

## 0.3 与当前项目架构对齐（必须先做）

前面两版计划有一个明显偏差：**我把 Restyle 当成一个独立 Python 管线在设计，但 OpenMontage 的整体架构是 instruction-driven：agent 读 pipeline manifest + stage skill，调用 BaseTool，checkpoint 审批；Python 只做 tools + persistence。**

如果不先对齐，会出现：

- `adplus/restyle` 变成第二个 orchestrator，和 `pipeline_runner` / `pipeline_defs` 打架；
- 自己写 scene detect / frame extract / compose / encode，重复 `scene_detect`、`video_analyzer`、`frame_sampler`、`video_stitch`、`video_compose`；
- 自己接阿里云/腾讯云 SDK，绕过 `video_selector`、secrets、`cost_tracker`、quote/approval；
- 渲染结果只写 `restyle/` sidecar，不进 canonical artifacts / version / `render_report`；
- Windows 包体再塞一套 ONNX/ffmpeg/tesseract，和现有 tools 的依赖重复。

### 正确的边界

| 层 | 归谁 | 做什么 |
|---|---|---|
| 产品状态 / UI / plan | `adplus/restyle` | 创建改写项目、镜头条、plan、预览入口；**不做渲染 orchestration** |
| 生产流程 | `pipeline_defs/restyle.yaml`（或 `hybrid` 的 restyle 模式） | stages、gates、review focus、cost |
| 能力 | `tools/` 下的 BaseTool | 分析、换装、合成、QA；selector + provider |
| 编排 | agent + stage skills | 选 provider、调工具、checkpoint、decision_log |
| 结果 | `asset_manifest` / `render_report` / version | 可审、可导出、可回溯 |

### 可复用的现有能力（先审计，不重复造）

- 分析：`scene_detect`、`video_analyzer`、`frame_sampler`、`video_understand`、`visual_qa`；
- 合成：`video_stitch`、`video_compose`、`video_trimmer`；
- 人像：`bg_remove`（rembg/U2Net，可作为粗分割基线）；
- 生成：`video_selector` + `runway_video` / `vidu_video` / `seedance_video` / `kling_video` / `minimax_video` / `hunyuan_video` 等；
- 成本：`cost_tracker`、Ad+ `quote` / approval；
- Windows：现有 tools 已有 ffmpeg 依赖说明，先统一路径，不另起一套。

### 修正后的实现形态

1. **先做 M-1：capability audit**
   - 跑 `tool_registry`，列出可用的 analysis/video/enhancement 工具；
   - 确认 `video_selector` 是否已有 Runway/Vidu/Seedance 编辑能力；
   - 确认 `video_compose` 能否直接吃“原视频 + 逐镜替换片段”；
   - 输出 gap list：缺哪个 tool，才写哪个 tool。
2. **Restyle 只保留产品层**
   - `adplus/restyle` 的 `analysis.py` 改为调用 `video_analyzer`/`scene_detect`，不自己写 ffmpeg 切镜；
   - `store.py` 只做项目/plan/sidecar；
   - 渲染/预览通过 pipeline job，不写自定义 render loop。
3. **新增能力按 ToolContract**
   - `outfit_edit_selector`（路由）
   - `outfit_edit_local`（SCHP + LAB）
   - `outfit_edit_aliyun` / `outfit_edit_tencent` / `outfit_edit_runway` / `outfit_edit_vidu`（按需）
   - 每个 provider 有 `input_schema`、cost、fallback、`agent_skills`；
   - 输出统一 `asset_manifest` 片段。
4. **pipeline manifest**
   - `pipeline_defs/restyle.yaml`：`reference → plan → outfit_edit → compose → review → export`；
   - 每 stage 有 skill、checkpoint、review focus；
   - paid 调用前 quote/approval。
5. **质量门**
   - `safe/review/keep` 由 agent + `visual_qa` 决定；
   - 商品 mask SSIM、时序、身份检查写进 `render_report`；
   - 不合格回退原镜头，不静默替换。

> 结论：**先对齐架构，再谈模型。** 否则 M0 做的 mask/API benchmark 可能直接落在错误的层里。

## 1. 为什么不用“整段视频重新生成”

P0 的直接生成 A/B 已经证明：

- Seedance 会把桶/手改掉；
- MiniMax 会改人物和商品，背景也没换对；
- 整段生成无法保证商品像素。

所以换装必须走**逐帧编辑 + 合成**：

```
原视频 → 逐帧解码 → 人体解析 → 衣服 mask → 保护商品/手/皮肤
      → 换色/换材质 → 合成 → 编码 + 原音频 → 输出
```

结构、切点、时长、音频、商品都不重新生成。

---

## 2. 当前基础

已有：

- `adplus/restyle/analysis.py`：探针、切镜、关键帧、OCR、场景/造型分组；
- `adplus/restyle/plans.py`：`cast.outfit_targets` 已有占位 `{mode:"hue", value:0}`；
- `/api/restyle` 创建/读片/plan；
- `/restyle` 工作台：镜头条、读片卡、场景组、造型组。

缺：

- 没有 garment mask；
- 没有逐帧合成；
- 没有 `/frame` 预览；
- 没有预演/导出；
- 造型组只有编号，没有缩略图和可操作控件。

---

## 3. 技术方案（L1）

### 3.1 人体解析

- 模型：**SCHP / CIHP 人体解析 ONNX**（20 类左右），输出 `upper-clothes`、`pants`、`skirt`、`dress`、`belt` 等；
- 运行时：`onnxruntime`（Windows CPU 基线，DirectML/CUDA 可选）；
- 输入：短边 256/320，按 shot 批量；
- 不引入 torch，不打 2GB 模型；模型 + 配置放 `resources/models/`；
- 许可：优先 MIT/Apache 模型；RVM 是 GPL-3.0，商业分发避开。

### 3.2 衣服 mask

```text
garment = union(parsing labels: upper-clothes, pants, skirt, dress, belt…)
mask = garment
     - product mask
     - hand / arm / face / hair mask
     - 低置信度区域
mask = guided_filter(frame, mask, radius=4)
mask = feather(mask, 3–5px)
```

- **禁止**对二值 mask 做 EMA 累积（P0 已踩过，会越盖越大）；
- 时序稳定用 3–5 帧中值 + 光流传播；
- 商品 mask 优先级最高，商品像素不参与换装；
- 手动画笔 mask 作为兜底（P1 可先只做自动，P2 加画笔）。

### 3.3 换色 / 换材质

**换色（保细节）**

1. 帧转 LAB；
2. 保留 L（褶皱、阴影、高光）；
3. 把 a/b 向目标色偏移；
4. 按软 mask 合成；
5. 用原帧做 guided filter，保住边缘。

**换材质/图案**

- 目标纹理图（针织/丝/棉/用户上传）；
- 按 mask 做纹理坐标映射 + 明暗乘法；
- `strength` 控制强度；
- `preserve_logo=true` 时保留原 logo/图案区域。

**为什么不用简单 HSV 全图换色**：会把皮肤、商品、背景一起改；必须逐像素 mask。

### 3.4 逐帧合成

```python
for frame in decode(shot):
    parse = session.run(rgb(frame))
    garment = labels_to_mask(parse)
    mask = refine(garment, product_mask, skin_mask)
    out = recolor_or_texture(frame, mask, target)
    out = composite(frame, out, mask)
    write(out)
```

- 输出分辨率跟源片；720p 默认，1080p 仅源片足够时；
- 编码 `libx264`，音频直接 copy；
- 帧率、时长、切点不变；
- 先按 shot 渲染，再 concat，避免整段重编码两次。

### 3.5 预览与渲染

- **静帧预览**：当前帧 + 当前 plan，200–400ms 出图；
- **单镜预演**：3s 低清（360/480p），看时序是否闪；
- **全片渲染**：720p，后台 job，逐镜进度；
- 所有结果带 `plan_revision`，plan 变了旧预览自动失效。

---

## 4. 数据模型

### 4.1 Blueprint 增加

```json
{
  "shots": [
    {
      "id": "s03",
      "garment": {
        "labels": ["upper-clothes", "pants"],
        "coverage": 0.31,
        "confidence": 0.92,
        "mask": "restyle/masks/s03/garment.png"
      },
      "person": {"bbox": [0.12, 0.08, 0.88, 0.98], "confidence": 0.96},
      "risk": {"level": "safe", "reasons": []}
    }
  ]
}
```

> 全序列 mask 不进 blueprint，放 `restyle/masks/<shot>/`，按源 hash + 模型版本缓存。

### 4.2 Plan 的 outfit target

```json
{
  "cast": {
    "outfit_targets": {
      "of01": {
        "mode": "recolor",
        "color": "#1F2937",
        "palette": ["#1F2937", "#E5E7EB", "#8B5CF6"],
        "texture": {"path": null, "scale": 1.0, "strength": 0.0},
        "preserve_logo": true,
        "strength": 0.85
      }
    }
  },
  "overrides": {
    "s03": {"outfit": {"mode": "keep"}}
  },
  "render": {"resolution": "720p", "fps": 30}
}
```

- `mode`: `keep` / `recolor` / `texture`；
- 场景组和造型组都可设置；
- `overrides[shot_id]` 单镜覆盖；
- 硬镜头默认 `keep`，不假装能改。

### 4.3 API

| Method | Path | 作用 |
|---|---|---|
| `GET` | `/api/restyle/{id}/frame/{shot_id}?t=&variant=outfit&rev=` | 静帧预览 JPEG |
| `POST` | `/api/restyle/{id}/preview` | 单镜/单帧预演 job |
| `POST` | `/api/restyle/{id}/render` | 全片渲染 job |
| `GET` | `/api/restyle/{id}/renders` | 渲染结果列表 |
| `POST` | `/api/restyle/{id}/mask/{shot_id}` | 手动画笔 mask（后续） |

Job 类型：

- `restyle_frame`
- `restyle_preview`
- `restyle_render`

进度：按 shot / frame 更新，支持 cancel。

---

## 5. UI（工作台）

### 5.1 造型组卡片

现在只有「造型 1 / 造型 2」。改成：

- 人物衣服缩略图（从 keyframe 裁 bbox）；
- 组名可编辑；
- 每个组一行：
  - `保留`
  - `换色` → 色板 + 自定义色
  - `换材质` → 棉/针织/丝/上传
  - `强度` 滑块
  - `保留 logo/图案` 开关
- 组内镜头数、风险标记。

### 5.2 单镜覆盖

- 选中镜头后，右侧显示「本镜造型」；
- 可覆盖组设置；
- 硬镜头默认 `keep`，显示原因。

### 5.3 预览

- 播放器下方加 **Before / After 滑块**；
- 「预览本帧」按钮；
- 「预演本镜 3s」按钮；
- 「生成全片」按钮；
- 渲染进度、取消、失败原因。

### 5.4 风险提示

- `safe`：直接可换；
- `review`：边缘/遮挡，建议先预览；
- `keep`：手/商品/接触家具，默认不改。

---

## 6. 分阶段实施

| 阶段 | 时间 | 交付 | 验收 |
|---|---|---|---|
| **M0a 本地 mask spike** | 1–2 天 | SCHP/CIHP ONNX 跑通 3 个镜头；测 CPU 耗时；确认许可 | s03/s18 能出 garment mask；单帧 <0.5s |
| **M0b 生成引擎 benchmark** | 2–3 天 | 3 个镜头 × 2–3 家（阿里云 / 腾讯云 / Runway 或 Vidu）；本地 L1 对照 | 商品 SSIM ≥0.99、身份/背景/时序可接受、成本/时延有数据 |
| **M1 mask 管线** | 2–3 天 | `outfit.py`：解析、mask 细化、商品/皮肤排除、缓存 | 合成前景/背景边界可接受；单测通过 |
| **M2 静帧换装** | 3–4 天 | 换色/材质合成；`GET /frame`；UI Before/After | 一条镜头肉眼可见换装；商品 ROI 不变 |
| **M3 单镜预演** | 3–4 天 | 3s 低清预演；时序中值/光流；per-shot override | 不闪、不跳；硬镜头 keep |
| **M4 全片渲染** | 3–4 天 | 全片 720p；原音频；渲染列表；QA | 时长/切点/音频不变；32s <5min CPU |
| **M5 Windows 打包** | 2–3 天 | 模型/ffmpeg 随包；sidecar；NSIS；CI | 干净 Windows 机器能预览/渲染 |
| **L2 生成式（可选）** | 5–8 天 | 关键帧 VTON/inpainting + 传播 | 只对 hero 镜头；人工审片 |

总计 v1（本地控制面 + M0 benchmark）约 **16–22 个工作日**；如果 benchmark 选中云引擎，集成另加 3–5 天。  
L2 不放进 v1 验收，避免范围膨胀。

---

## 7. 验收标准

### 7.1 画面

- 造型组覆盖的镜头中，**≥80% 有明显换装效果**；
- 商品 mask 内像素不变（SSIM ≥ 0.999，或 max diff < 1/255）；
- 背景、人物脸、体型、姿势不变；
- 硬镜头（手/商品/接触家具）默认 `keep`，不出现悬浮/补丁。

### 7.2 视频

- 时长、帧率、切点与源片一致；
- 音频原样 copy；
- 无丢帧、无音画不同步；
- 输出可播放 H.264/AAC MP4。

### 7.3 性能

- 静帧预览 p95 ≤ 2s（含解析）；
- 单镜 3s 360p 预演 ≤ 20s；
- 32s 720p 全片 ≤ 5min（Windows 中端 CPU）；
- 内存峰值 ≤ 2GB。

### 7.4 测试

- 合成视频：红衣服→蓝衣服，商品区域不变；
- 参考片 s03/s18 视觉对比；
- mask 边界、皮肤、手、商品遮挡的单测；
- Windows CI：synthetic smoke + 渲染一帧。

---

## 8. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 人体解析把浴袍/腿分错 | 高 | 置信度阈值；低置信度 keep；手动画笔兜底 |
| 商品/手遮挡衣服 | 高 | 商品 mask 优先级最高；手/皮肤从 garment 中扣除 |
| 换色发灰/发脏 | 中 | 保 L、LAB 偏移、纹理强度、预设色板 |
| 时序闪烁 | 高 | 3–5 帧中值 + 光流；逐帧解析；不做二值 EMA |
| 纹理/图案不跟随褶皱 | 中 | 用 L 调制；位移贴图；强度上限 |
| 用户期望“换一件不同款” | 高 | 明确 L1/L2；L2 单独排期 |
| 模型许可 | 高 | 先审 SCHP/CIHP；避开 GPL RVM |
| Windows ONNX 性能 | 中 | CPU 基线；DirectML 可选；缓存 mask |
| 22 镜渲染慢 | 中 | 逐镜缓存；只重渲染改动镜头；后台队列 |

---

## 9. 需要确认的决策

1. **v1 是否接受 L1（保版型换色/材质）作为“真正换装”？**  
   如果必须换版型/品类，L2 要进主排期，时间和风险都会增加。
2. 目标衣服来源：内置色板/材质，还是用户上传参考图？
3. 是否允许对 hard shot 手动画笔 mask？
4. 输出默认 720p 是否够？
5. 模型许可由谁确认（SCHP/CIHP）？

---

## 10. 立即执行（M0）

### M0a：本地 mask / L1 基线

1. 选 SCHP/CIHP ONNX，确认许可；
2. 在 s03 / s18 上跑 parsing，输出 garment mask；
3. 用一帧做 LAB 换色，肉眼检查边缘、手、商品；
4. 记录 CPU 单帧耗时和显存/内存；
5. 通过后进 M1，不通过则换模型或退到手动 mask。

### M0b：生成引擎 benchmark

同一组 3 个镜头：

- A：全身体、衣服清晰；
- B：腿部/脚部，衣服只占一部分；
- C：手持商品特写（应该 `keep`，用来测商品保护）。

分别跑：

1. 本地 L1；
2. 阿里云 `EcomVideoRecreation`（reference 模式）；
3. 腾讯云广告素材 / Runway Aleph 2 / Vidu S2-Editing（按可用性选 1–2 家）。

评分：

| 指标 | 目标 |
|---|---|
| 商品 mask SSIM | ≥0.99，或人工确认无变化 |
| 人物身份 / 脸 | 不变 |
| 背景 | 不变 |
| 切点/时长/音频 | 不变 |
| 时序闪烁 | 可接受 |
| 单镜成本 / 时延 | 记录，算一条 32s 广告的总价 |
| 内容审核 | 真实人物是否被拒 |

> 只有 M0a 的 mask 和 M0b 的引擎数据都过关，才决定主链路。
> 如果所有 API 都保不住商品，就回到“本地 L1 + 硬镜头 keep”，不要为了换装牺牲商品。
