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

### 4.5 Provider 策略：MiniMax-first（测试结果：No-Go 主链路）

可以只**启用** MiniMax，但不建议把代码写成“只支持 MiniMax”。

现状：

- `minimax_video` 已注册，key 为空；
- 能力是 `text_to_video / image_to_video / first_last_frame_to_video / reference_to_video`，**没有 `video_edit`**；
- 所以换装只能走 `reference_to_video`：给目标服装参考图，整段重生成；
- 这会改商品/手/背景，必须本地商品 mask 回贴 + QA，不能直接交付。

推荐：

| 层 | 做法 |
|---|---|
| 产品配置 | `RESTYLE_PROVIDERS=minimax`，v1 只启用 MiniMax |
| 代码 | 保留 provider 接口；不删其它 adapter，只是禁用 |
| 本地 | 保留 L1 作为离线/失败兜底 |
| 质量门 | MiniMax 只用于 `review`/hero；safe 走本地 L1；商品/手镜头 keep |
| 未来 | 如果 MiniMax 出真正的 video_edit/区域重绘，再加 `video_edit` capability |

只支持一家的代价：

- 没有第二家兜底，API 故障/改版/涨价都直接卡住；
- 商品保真只能靠本地合成，不能靠模型；
- 真实人物审核策略由一家决定。

**实测（2026-11-09）**：MiniMax H3 `reference_to_video` 能把白睡衣换成深青针织，但 4s 内会重新生成场景/字幕/镜头，商品桶也有变化；输出 4.459s vs 输入 4.0s。证据见 [minimax/README.md](verification/restyle-spike/minimax/README.md)。

**结论**：MiniMax 可以保留为“测试/hero 参考”provider，但**不能作为“同一条广告只换装”的主链路**。v1 主链路必须是本地 L1 + 语义 mask；MiniMax-only 也不能替代本地控制面。

### 4.4 生成引擎（M0b）

Atlas / Runway 的 key **暂时拿不到**，所以它们从 v1 关键路径移除，只保留脚本备用。

M0b 改为两条路：

1. **有 MiniMax key**：用 `minimax_video` 的 `reference_to_video` 跑 3 镜；
   - 输入：原视频/镜头 + 目标服装参考图 + “只换衣服、保留商品/手/背景/节奏”的 prompt；
   - 整段会重生成，必须本地商品 mask 回贴 + QA；
   - 不能当主链路，只能做 `review`/hero。
2. **没有任何视频 key**：跳过云端，直接走本地 L1：
   - `bg_remove` / rembg 人像 mask；
   - 颜色/区域 + 人工画笔得到 garment mask；
   - [outfit.py](../adplus/restyle/outfit.py) 换色；
   - 先出静帧，再谈视频。

> 不把 Atlas/Runway 当阻塞项。没有 key 就本地，先做出可控的 L1 预览。

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
| **M0a 本地 L1 核心** | 2–3 天 | LAB 换色/羽化/商品排除 + 单测 | 🟡 核心已写，s03 预览验证；mask 仍会带到膝盖 |
| **M0b 生成引擎 benchmark** | 2–3 天 | MiniMax H3 4s 单镜实测 | ❌ 换装成功，但结构/背景/字幕被重生成；No-Go 主链路 |
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

## 6.5 口播 / 旁白自动判断（虚拟人前置）

不是所有广告都需要对口型。很多改写片是**背景旁白**，人物只是展示/反应；如果每镜都做 lip-sync，会浪费时间、钱，还会把嘴型做坏。

### 四种镜头模式

| 模式 | 判断 | 虚拟人处理 |
|---|---|---|
| `on_camera` | 有语音 + 人脸可见 + 嘴部有明显运动 / 与音频相关 | 需要口型同步（avatar/lip-sync） |
| `voiceover` | 有语音 + 人脸不可见，或人脸可见但嘴基本不动 | 不需要口型；虚拟人做展示/反应即可 |
| `no_speech` | 该镜头没有语音（纯音乐/环境声/静音） | 不需要口型，也不需要音频替换 |
| `unknown` | 人脸/嘴部检测不可用或置信度低 | 出预览，人工确认；默认不自动 lip-sync |

### 检测信号

1. **音频**：VAD / ASR（`transcriber` / faster-whisper），得到语音区间；
2. **人脸**：`face_tracker`（MediaPipe/OpenCV），逐镜判断是否可见；
3. **嘴部运动**：face landmarks 的嘴开合方差，和语音能量做相关；
4. **画面**：商品特写/腿部特写通常没有人脸 → 直接 `voiceover`/`no_speech`。

### 数据模型

```json
{
  "shots": [
    {
      "id": "s03",
      "speech": {
        "mode": "on_camera",
        "confidence": 0.82,
        "face_visible": true,
        "mouth_motion": 0.61,
        "speech_segments": [[2.9, 4.6]]
      }
    }
  ]
}
```

plan：

```json
{
  "cast": {
    "lip_sync": {"mode": "auto"}
  },
  "audio": {"mode": "keep"}
}
```

- `auto`：按 shot 的 `speech.mode` 决定；
- `on`：强制口型；
- `off`：全部不做口型（纯旁白/展示片）。

### 虚拟人流程

```text
shot.speech.mode
  ├─ on_camera  → 生成虚拟人口播 / lip-sync
  ├─ voiceover  → 生成虚拟人展示镜头，不需要对口型
  ├─ no_speech  → 只换人物外观，不动音频
  └─ unknown    → 预览 + 人工选
```

这样可以避免：

- 背景旁白镜头也做 lip-sync；
- 腿部/商品特写强行找脸；
- 嘴部不动却生成假口型。

### 当前依赖

- `face_tracker` 当前 `unavailable`（缺 mediapipe/opencv）；需要安装或换本地人脸检测；
- `transcriber` 需要 faster-whisper；
- 没有这些依赖时，先按 `no_speech` / `unknown` 处理，不自动 lip-sync。

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
- `tests/test_restyle_outfit.py` / `tests/test_restyle_capabilities.py`；
- `scripts/restyle_local_preview.py`：无 key 的 s03 本地预览；
- 预览结果：`docs/verification/restyle-spike/l1_prototype_s03.jpg`。

s03 预览结论：

- 白色睡衣可以稳定换成深青色；
- 商品桶像素未被改；
- 但颜色 seed mask 会把膝盖高光带进去（右图膝盖有一小块青色），说明 **M1 必须有语义 garment mask 或人工画笔**，不能只靠颜色。

### 下一步（按顺序）

1. 配 key → 跑 M0b，产出 3 镜对比；
2. 同时补 `garment_mask` 来源（SCHP ONNX 或人工/颜色兜底）；
3. M1 把 mask + `outfit.py` 包成 `outfit_edit_local` BaseTool；
4. M2 接 `/frame` 和 UI Before/After；
5. 云引擎只作为 `review`/hero 提升，默认本地 L1 + keep。
