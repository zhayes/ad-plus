# Restyle 换装实施计划 v2（架构对齐版）

> 2026-11-09 重新制定。上一版 [restyle-outfit-plan.md](restyle-outfit-plan.md) 保留为市场调研，本文件是执行版。
>
> 目标：在 Ad+ / OpenMontage 现有架构内，做出**可预览、可回退、商品像素不变**的换装；不新造第二个 orchestrator。

---

## 1. 范围

### v1 做什么

- 同一条广告、同一人、同商品、同切点/时长/音频；
- 只改衣服：颜色、材质、图案（保版型）；
- 支持 `safe / review / keep` 质量门；
- 静帧预览 → 单镜预演 → 全片渲染；
- 失败/低置信度回退原镜头。

### v1 不做什么

- 不换版型/品类（浴袍→连衣裙）；
- 不换脸/换身体/重演；
- 不整段重生成；
- 不保证 22/22 镜头都换。

---

## 2. M-1 审计结果（已完成）

跑 `python scripts/restyle_capability_audit.py`（2026-11-09，macOS）：

### 可直接复用

| 工具 | 状态 | 用途 |
|---|---|---|
| `scene_detect` | available | 切镜 |
| `video_analyzer` | available | 参考片结构/关键帧 |
| `frame_sampler` | available | 抽帧 |
| `visual_qa` | available | 审片/帧检查 |
| `video_stitch` | available | 多镜拼接 |
| `video_compose` | available | 合成/编码/字幕 |
| `video_trimmer` | available | 切/裁/变速 |
| `video_selector` | unavailable | 统一视频 provider 路由；当前无可用 key |
| `atlas_video` | unavailable | 已注册 `video_edit`；当前无 key |
| `bg_remove` | unavailable | rembg 未安装；只能做粗人像 mask |

### 关键发现

1. **现有 `video_edit` 能力已经存在**：`atlas_video` 支持 `google/gemini-omni-flash/video-edit`，720p，$0.14/s。缺的是 API key，不是代码。
2. **现有 pipeline 没有 `restyle`**；`hybrid` 可用（`idea → script → scene_plan → assets → edit → compose → publish`）。
3. **不要新增 `pipeline_defs/restyle.yaml` 到 vendor 子模块**；v1 先按 `hybrid` 走，等 upstream 支持自定义 defs 再加 manifest。
4. **`bg_remove` 不是衣服分割**；它是 U2Net 人像/显著物体，不能直接当 garment mask。
5. **当前 API key 为空**：`.env` 里 `RUNWAY_API_KEY` / `ATLASCLOUD_API_KEY` / `ARK_API_KEY` / `MINIMAX_API_KEY` 都是空字符串，视频 provider 全部不可用。

### 结论

- 本地控制面（拆镜、mask、商品锁、合成、QA）必须自研；
- 换装生成引擎优先试**已有 `atlas_video` video_edit**，不先接阿里云/腾讯云 SDK；
- 本地 L1 是离线兜底；
- 先补 key 做 M0b，不要先写大管线。

---

## 3. 架构边界

```text
Ad+ 产品层（adplus/restyle）
  项目 / 镜头条 / plan / 预览入口 / 质量门
        ↓  只传参数和状态，不跑渲染编排
OpenMontage pipeline（v1 复用 hybrid）
  idea → script → scene_plan → assets → edit → compose → publish
        ↓
BaseTool
  scene_detect / video_analyzer / frame_sampler
  outfit_edit_selector（新增）
    ├─ outfit_edit_local（本地 L1）
    └─ atlas_video video_edit（现有，M0b 先验）
  video_compose / video_stitch / visual_qa
        ↓
canonical artifacts
  asset_manifest / edit_decisions / render_report
```

### 产品层保留什么

- `projects/<id>/restyle/`：source、blueprint、plan、previews、renders；
- `/api/restyle`：创建/读片/plan/预览/渲染任务；
- `/restyle` 工作台；
- **不写** ffmpeg 切镜、不写 compose、不写 provider SDK。

### 生产层负责什么

- 选 provider；
- 调工具；
- 写 checkpoint / asset_manifest / render_report；
- quote / approval / cost；
- 质量门。

---

## 4. 工具设计

### 4.1 复用

- `scene_detect`：替代 `analysis.detect_cuts` 的长期方向；
- `video_analyzer`：参考片结构/关键帧；
- `frame_sampler`：按时间抽帧；
- `video_compose` / `video_stitch`：最终拼接/编码/音频；
- `visual_qa`：抽帧审片。

> P1 的 `analysis.py` 先保留，M1 再逐步改为调用这些工具；不要一次性重写。

### 4.2 新增 `outfit_edit_selector`

职责：按镜头风险、可用 provider、成本、质量选引擎。

输入：

```json
{
  "shot_id": "s03",
  "mode": "recolor|video_edit|keep",
  "garment_mask": "restyle/masks/s03/garment.png",
  "product_mask": "restyle/masks/s03/product.png",
  "outfit": {"color": "#1F2937", "texture": null, "strength": 0.85},
  "reference_image": "assets/outfit.png",
  "risk": "safe|review|keep"
}
```

输出：

```json
{
  "provider": "local|atlas",
  "output": "restyle/edits/s03.mp4",
  "product_ssim": 0.998,
  "status": "ok|review|failed"
}
```

### 4.3 `outfit_edit_local`（L1）

已开始实现 [outfit.py](../adplus/restyle/outfit.py)：

- LAB 保 L 换色；
- 商品/手/皮肤 mask 扣除；
- 软 mask + 羽化；
- 单测：换色只改 mask 内、商品 mask 不变、羽化边缘。

待补：

- `garment_mask` 来源（SCHP/CIHP ONNX 或 rembg 粗分割 + 颜色/区域细化）；
- 视频逐帧包装成 BaseTool；
- 时序中值/光流；
- 成本 0，离线。

### 4.4 生成引擎（M0b）

先用现有 `atlas_video`：

- model: `google/gemini-omni-flash/video-edit`
- 720p，$0.14/s
- 输入：`video_path` + `reference_images` + prompt
- 脚本：[restyle_edit_benchmark.py](../scripts/restyle_edit_benchmark.py)

如果 Atlas 不行，再评估阿里云/腾讯云/Runway/Vidu；**不先写 SDK**。

---

## 5. 数据与产物

### 5.1 产品 sidecar

```text
projects/<id>/restyle/
  source.json
  blueprint.json          # 镜头、分组、OCR、风险
  plan.json               # outfit targets / overrides
  masks/<shot>/garment.png
  masks/<shot>/product.png
  previews/<shot>.jpg
  edits/<shot>.mp4
  renders/<variant>.mp4
  edit_report.json        # provider、成本、QA
```

### 5.2 canonical artifacts

- `asset_manifest`：每镜 edit 输出；
- `edit_decisions`：选了哪个 provider、为什么；
- `render_report`：最终合成、时长、音频、QA；
- `decision_log`：provider/model 变更。

### 5.3 plan 字段

```json
{
  "cast": {
    "outfit_targets": {
      "of01": {
        "mode": "recolor",
        "color": "#1F2937",
        "texture": null,
        "strength": 0.85,
        "preserve_logo": true
      }
    }
  },
  "overrides": {
    "s03": {"outfit": {"mode": "keep"}}
  }
}
```

---

## 6. 分阶段实施

| 阶段 | 时间 | 交付 | 状态 |
|---|---|---|---|
| **M-1 审计** | 1–2 天 | capability audit + gap list + endpoint | ✅ 2026-11-09 |
| **M0a 本地 L1 核心** | 2–3 天 | LAB 换色/羽化/商品排除 + 单测 | 🟡 核心已写，待接 mask |
| **M0b 生成引擎 benchmark** | 2–3 天 | Atlas video_edit 跑 3 镜，和本地 L1 对比 | ⛔ 缺 API key |
| **M1 mask 管线** | 3–4 天 | garment mask 来源 + 缓存 + 风险分级 | 待 M0 |
| **M2 静帧预览** | 3–4 天 | `/frame` + UI Before/After | 待 M1 |
| **M3 单镜预演** | 3–4 天 | 3s 低清 + 时序稳定 | 待 M2 |
| **M4 全片合成** | 3–4 天 | 逐镜 edit → stitch/compose → render_report | 待 M3 |
| **M5 Windows** | 2–3 天 | 模型/ffmpeg 随包；sidecar；安装包 | 待 M4 |

v1 总计约 **16–22 个工作日**（不含 L2 换版型）。

### M0b 决策门

3 个镜头：

- A 全身体、衣服清晰；
- B 腿部/脚部，衣服只占一部分；
- C 手持商品特写（应该 `keep`）。

评分：

| 指标 | 目标 |
|---|---|
| 商品 mask SSIM | ≥0.99 |
| 身份/脸 | 不变 |
| 背景 | 不变 |
| 切点/时长/音频 | 不变 |
| 时序 | 不闪 |
| 成本 | 记录 $/镜 |
| 审核 | 真实人物是否被拒 |

不过门 → 不做云主链路，回本地 L1 + keep。

---

## 7. 质量门

- `safe`：自动换；
- `review`：只出预览，人工通过才换；
- `keep`：商品/手/接触家具/低置信度，原样保留；
- 渲染后 `visual_qa` + 商品 SSIM；不过门自动回退；
- 单镜回退，不整段重来。

---

## 8. 测试

- `tests/test_restyle_outfit.py`：换色/商品保护/羽化/覆盖率；
- `tests/test_restyle_capabilities.py`：审计/端点；
- M1：garment mask 边界、皮肤/手/商品遮挡；
- M2：`/frame` 缓存、plan revision 失效；
- M3：时序抖动、丢帧；
- M4：时长/音频/切点与源一致；
- Windows CI：同一套单测 + synthetic smoke。

---

## 9. 当前阻塞

1. **没有 API key**：`.env` 中 Atlas/Runway/ARK/MiniMax 均为空，`video_edit` 无法跑。
2. **没有 garment mask 模型**：`bg_remove` 未安装且不是衣服分割；需要 SCHP/CIHP ONNX 或可用云端。
3. **没有 restyle manifest**：v1 复用 `hybrid`，不阻塞。

### 需要你提供/确认

- Atlas 或 Runway 的可用 key（M0b）；
- 是否接受 3 镜 benchmark 费用（Atlas $0.14/s，3 镜约 $1–3）；
- 是否允许把真实人物视频发到云端 benchmark。

---

## 10. 本轮已实施

- `adplus/restyle/capabilities.py`：真实工具审计；
- `scripts/restyle_capability_audit.py`：命令行审计；
- `GET /api/restyle/capabilities`：API；
- `scripts/restyle_edit_benchmark.py`：Atlas video_edit benchmark（缺 key 时明确报阻塞）；
- `adplus/restyle/outfit.py`：LAB 换色/羽化/商品排除核心；
- `tests/test_restyle_outfit.py` / `tests/test_restyle_capabilities.py`。

### 下一步（按顺序）

1. 配 key → 跑 M0b，产出 3 镜对比；
2. 同时补 `garment_mask` 来源（SCHP ONNX 或人工/颜色兜底）；
3. M1 把 mask + `outfit.py` 包成 `outfit_edit_local` BaseTool；
4. M2 接 `/frame` 和 UI Before/After；
5. 云引擎只作为 `review`/hero 提升，默认本地 L1 + keep。
