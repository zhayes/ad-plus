# 改写（Restyle）模块实施计划

> 版本 v1 · 2026-11-07
> 参考片：32.07s / 720×1280 / 30fps / 约 22 镜 / 4 个场景 / 3 套造型 / 22 条字幕 / 1 个商品
> 目标：上传一条爆款广告，替换人物形象与背景，保留镜头结构、字幕、商品和节奏，输出“同一条广告”的新版本。

> **P0 / P0.5 已完成（2026-11-07）**：结论 **Conditional Go**。
> - 安全镜头（无手/商品接触）整间房替换可行；
> - 手部/商品/接触家具镜头**不承诺整间房替换**，默认 `keep` 或走“墙面/窗帘/地板重制”；
> - 直接生成 A/B 证明商品会被重画，商品/手部镜头不走生成。
> 详见 [P0 测试报告](verification/restyle-spike/REPORT.md)。
>
> **Windows 是主平台（2026-11-07 修订）**：P1 在 macOS 通过；下一步先做 W0 Windows 安装包 spike；P2 的分割后端改为 PersonSegmenter（Windows 默认 MediaPipe/ONNX），Vision 仅作为 macOS 可选增强。

---

## 0. 一句话方案

**不做整条视频重生成。** 以原片为时间线骨架，拆成 **人物 / 商品 / 背景 / 字幕** 四层：

- 商品：保留原像素，不重新生成；
- 人物：保留身体表演，只换外观（服装、发色、肤色、可选换脸）；
- 背景：按场景组替换成新的场景板；
- 字幕：旧字去除，同文案、同位置、同字体重打；
- 音频：保留原声，或用同脚本重配。

本地合成，云端只出场景图和可选换脸。成本低、商品真、节奏完全不变。

---

## 1. 范围

### 1.1 v1 做

- 视频上传 / 项目导入 / 拖拽 / 粘贴
- 探针、切镜、关键帧、字幕 OCR、场景分组、造型分组、风险提示
- 读片卡 + 改动幅度（轻改 / 推荐 / 全改）+ 分组批量
- 人物形象：只换外观（服装、发色、肤色、可选换脸），不换体型、不重演
- 声音：保留原声 / 静音 / 可选重配
- 输出：画幅默认跟随源片；质量可选 480p / 720p / 1080p，默认 720p
- 背景：场景板生成或选择，按组替换，单镜覆盖
- 商品：锁定原像素；可换 SKU（真实产品图 plate）
- 字幕：保留原文 / 编辑，旧字去除，同位置同字体重打
- 静帧预览、单镜预演、全片预演、审片对比、导出 480p / 720p / 1080p
- 自动保存、撤销、失败重试、权利确认门

### 1.2 v1 不做

- 换体型 / 重新表演 / 数字人重演（放到 P3 以后）
- 逐帧手工 roto、完整 NLE 时间线
- 多人物角色映射（剧情片）
- 整条视频 generative video-to-video
- Windows 专用视频抠像（先做 macOS；Windows 走 ONNX 备选）

### 1.3 验收片（golden fixture）

用这条参考片作为验收基准：

| 指标 | 目标 |
|---|---|
| 镜头 | 22 镜 ±1 |
| 分组 | 4 个场景组、3 个造型组 |
| 字幕 | 22 条，文案识别正确率 ≥ 90% |
| 读片 | ≤ 60s |
| 静帧预览 | ≤ 400ms p95 |
| 单镜 3s 预演 | ≤ 15s（360p） |
| 全片 720p 渲染 | ≤ 8min（M1/M2） |
| 导出 | 32.0s ±0.2s，720×1280，30fps，音画同步 |
| 商品 | 形状 / 颜色不变；标签不被重画 |
| 字幕 | 文案、位置、时间正确 |

---

## 2. 关键决策

### D1 轻改优先，不整条重生成

这条片的商品几乎每镜都在，手、脚、水都在和商品接触。生成模型最先崩的就是商品、手指、脚趾和水花。轻改保留原表演和商品像素，风险最低，也最像“同一条广告”。

### D2 复用项目底座，不新造存储

改写记录仍然是一个 `projects/<id>/`：

- `project.json` 里 `format_id = "reference_restyle"`，`pipeline_type = "hybrid"`；
- 复用 `project_store`、`jobs`、`/api/media`、`/api/thumb`、personas、products、quote；
- 改写专属状态放在 `projects/<id>/restyle/`，不污染 `versions/`；
- Projects 列表过滤掉改写项目，改写有自己的 `/restyle` 入口；`/studio/:id` 遇到 `reference_restyle` 重定向到 `/restyle/:id`，不显示制作阶段板；
- 这样后台任务、媒体服务、导出、回收站都不用重写。

### D3 跨平台本地优先

- 人像分割：`PersonSegmenter` 抽象；Windows 走 MediaPipe / ONNX，macOS Vision 只作为可选增强；
- 商品 / 字幕遮罩、inpaint、合成：OpenCV；
- 渲染 / 拼接 / 混音：ffmpeg；
- 场景板：现有 MiniMax image，或用户上传；
- 可选换脸：InsightFace ONNX（P2 再加）。

避免把整条视频发给云端，成本低、隐私好、可离线。任何分割后端缺失时，硬镜头默认 `keep`，不能阻塞分析。

### D4 结构锁定

源片的时间线、切点、时长、画幅、帧率只读。用户改的是层，不是剪辑。UI 顶部显示“逻辑已锁定”，高级模式才允许改切点。

### D5 分组，不逐镜

分析把镜头聚成 **场景组**（卧室 / 客厅 / 浴室 / 木地板）和 **造型组**（白浴袍 / 紫睡衣 / 米色开衫）。用户改“卧室”一次，5 个镜头一起变；单镜只做例外。

### D6 静帧先预览，视频后渲染

换人 / 换景先在当前帧合成，200–400ms 出图；用户满意后再预演视频。所有分析、预演、导出都在后台任务里跑，不阻塞 UI。

### D7 权利门

上传时必须确认“拥有该视频及人物肖像的使用权”。`source.json` 记录确认状态；未确认不允许导出。源片是竞品 / 真人时，UI 明确提示风险。

### D8 Windows 优先（2026-11-07 修订）

Windows 是主运行平台，macOS 是开发 / 次要平台。所有新能力先按 Windows 可用来设计：

- **分割后端**：`adplus/restyle/segment.py` 抽象；Windows 默认 MediaPipe（Apache-2.0，轻）或 ONNX（MODNet/RVM，质量更高）；macOS Vision 只能作为可选后端，不能成为唯一路径。
- **Python 版本**：Windows sidecar 固定 **Python 3.12**（MediaPipe / onnxruntime 的 wheel 覆盖更稳）；不要用 3.14 打包 Windows。
- **打包**：Tauri 2 + Python sidecar（PyInstaller）+ bundled ffmpeg / tesseract / Noto Sans SC / 分割模型；安装包目标 NSIS / MSI，图标 `.ico`。
- **路径**：API / JSON 一律用 POSIX 相对路径（`as_posix()`）；Windows 大小写不敏感，避免同名文件；长路径用 `\\?\` 前缀；不依赖 symlink。
- **子进程**：ffmpeg / tesseract 走 `CREATE_NO_WINDOW`；路径用 `ADPLUS_FFMPEG` / `ADPLUS_FFPROBE` / `ADPLUS_TESSERACT` 覆盖，便于打包。
- **OCR**：tesseract + `chi_sim` 随包；失败时标“需校对”，不阻塞。
- **CI**：GitHub Actions `windows-latest` 跑后端测试 + 参考片读片；`macos-latest` 跑 UI 构建。没有 Windows CI 前，不宣称 Windows 可用。
- **许可**：ffmpeg 的 LGPL/GPL、分割模型许可、tesseract（Apache-2.0）、字体（OFL）都要在打包前确认；RVM 是 GPL-3.0，商业分发需谨慎。

当前状态（2026-11-09）：`windows-restyle` #7 绿灯。`test` 在 Windows 3.12 上跑通读片 smoke、20 个 focused tests、前端 build；`build-backend` 成功构建 `adplus-backend.exe` 并通过 `/api/health`。代码已去掉对 Vision 的硬依赖，加入 `PersonSegmenter` 抽象、POSIX 路径、Windows 子进程 flags；`app/desktop/tauri.windows.conf.json`（NSIS + `.ico`）、`scripts/build_backend.py`、`scripts/restyle_smoke.py` 已就位。**剩余：NSIS 安装包、随包 ffmpeg/tesseract/字体、干净 Windows 机器安装验证。**

---

## 3. 用户流程与页面

### 3.1 入口

- 底栏新增「改写」→ `/restyle`（列表 + 拖拽上传）
- 项目页「用这条片子改写」
- 资产页视频详情「改写这条」
- 支持拖拽 / 粘贴视频直接进入工作台

### 3.2 状态机

```text
empty → analyzing → plan_ready → editing → previewing → review → exported
```

- `analyzing` 非阻塞：视频立刻播放，镜头条渐进出现；
- `plan_ready`：读片卡出现，建议改 / 保留；
- `editing`：随时可改，自动保存；
- `previewing`：单镜 / 全片后台渲染；
- `review`：原片 / 新片同步对比；
- 失败可回到 `editing`，不丢状态。

### 3.3 页面布局

```text
┌ 改写 / 小背心爆款 ─────────── 32.0s · 22 镜 · 逻辑已锁定      [预演] [导出] ┐
│ ┌────────────────────────────┐  ┌────────────────────────────────────┐ │
│ │                            │  │  全片 │ 选中镜头                    │ │
│ │       9:16 播放器           │  │                                    │ │
│ │   原片 ◀───┼───▶ 新片       │  │  人物  小夏（3 套造型）    [换人]    │ │
│ │                            │  │   ├ 白浴袍  ├ 紫睡衣  ├ 米色开衫    │ │
│ │                            │  │  背景  4 组场景           [换场景]   │ │
│ │                            │  │   ├ 卧室  ├ 客厅  ├ 浴室  ├ 木地板  │ │
│ │                            │  │  商品  泡脚桶 · 已锁定               │ │
│ │                            │  │  字幕  22 条 · 保留原文              │ │
│ │                            │  │  声音  原声 / 新配音                 │ │
│ └────────────────────────────┘  └────────────────────────────────────┘ │
│  改动幅度   轻改 ────●──── 推荐 ──── 全改    将改 15 镜 · 保留 7 镜       │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ 卧室 5   [01][02][03][04][05]   客厅 8   [06][07][08]...              │ │
│ │          缩略图 + 时长 + 状态点 + 风险标                               │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.4 核心交互

| 操作 | 反馈 |
|---|---|
| 拖入视频 | 立刻播放，后台读片 |
| 点镜头 | seek + 选中 + 右侧切换 |
| 空格（按住） | 看原片；松开看新片 |
| 拖播放器中间分割线 | 左右对比 |
| `[` / `]` | 上一镜 / 下一镜 |
| `A` | 应用到同组 |
| 双击字幕 | 就地编辑 |
| `Cmd+Z` | 撤销 |
| 点风险标 | 显示原因 + 建议 |

### 3.5 自适应工作台

| 片型 | 首屏重点 | 默认工作台 |
|---|---|---|
| 单人口播 | 人 + 景 + 声音 | 两张卡，极简 |
| 产品演示（这条） | 商品 + 场景组 + 字幕 | 分组工作台 |
| 剧情 / 多人物 | 角色映射 | 原角色 A → 新角色 A |
| 混剪 / 素材 | 逐镜表 | 默认保留，勾选替换 |

卡片只在相关时出现：没有商品特写不显示商品卡；没有字幕不显示字幕卡；只有一个人一个房间就不显示“组”。

---

## 4. 数据模型

### 4.1 目录

```text
projects/<id>/
  project.json                 # format_id = reference_restyle
  restyle/
    source.json
    blueprint.json
    plan.json
    thumbs/s01.jpg ...
    plates/sc01.png ...
    masks/s01_person.png ...   # 只存关键帧/预览用，不存全序列
    previews/
    variants/v1.json
  renders/restyle_v1_720p.mp4
  jobs/*.json                  # 复用 adplus.jobs
```

### 4.2 `project.json` 新增约定

- `format_id`: `reference_restyle`
- `pipeline_type`: `hybrid`
- `title` / `platform` / `aspect` / `duration_s` 从源片探针写入
- 状态复用 `draft / producing / review / delivered`

`project_summary` 增加 `format_id`，Projects 页据此过滤或显示“改写”徽标。

### 4.3 `source.json`

```json
{
  "path": "uploads/20261107/ref.mp4",
  "hash": "sha1:...",
  "duration_s": 32.067,
  "width": 720,
  "height": 1280,
  "fps": 30,
  "audio_path": "projects/r_xxx/restyle/source.wav",
  "rights": {
    "confirmed": true,
    "note": "自有素材 / 已获授权",
    "confirmed_at": "2026-11-07T21:30:00+0800"
  }
}
```

### 4.4 `blueprint.json`

```json
{
  "version": 1,
  "video_type": "product_demo",
  "shots": [
    {
      "id": "s01",
      "index": 1,
      "start_s": 0.0,
      "end_s": 1.533,
      "duration_s": 1.533,
      "keyframe": "restyle/thumbs/s01.jpg",
      "caption": {"text": "每天睡前泡个脚", "bbox": [120, 1000, 480, 70], "confidence": 0.86},
      "groups": {"scene": "sc01", "outfit": "of02", "product": "p01", "objects": ["ob01"]},
      "risk": {"score": 0.82, "reasons": ["water", "product_closeup"]},
      "suggested": "keep"
    }
  ],
  "groups": {
    "scenes": [
      {"id": "sc01", "label": "卧室", "shot_ids": ["s01", "s02"], "thumb": "restyle/thumbs/sc01.jpg"}
    ],
    "outfits": [
      {"id": "of01", "label": "白浴袍", "shot_ids": ["s01"], "swatch": "#e8e2d8"}
    ],
    "products": [
      {"id": "p01", "label": "泡脚桶", "shot_ids": ["s01"], "swatch": "#b9a6e8"}
    ],
    "objects": [
      {"id": "ob01", "label": "长凳", "type": "bench", "shot_ids": ["s01"], "default": "keep"}
    ]
  },
  "audio": {"mode": "keep", "has_speech": null, "transcript": null},
  "suggestions": {
    "change_shot_ids": ["s02", "s03"],
    "keep_shot_ids": ["s01"],
    "reason": "水花 / 手部特写 7 镜，合成风险高，建议保留"
  }
}
```

### 4.5 `plan.json`

```json
{
  "revision": 3,
  "change_level": "recommended",
  "cast": {
    "persona_id": "p_4d0b233d",
    "mode": "appearance",
    "outfit_targets": {
      "of01": {"mode": "tint", "value": "#d8c4a8"},
      "of02": {"mode": "hue", "value": 210},
      "of03": {"mode": "hue", "value": 35}
    },
    "hair": {"mode": "recolor", "value": "#2b1c17"},
    "skin": {"mode": "match", "strength": 0.25},
    "voice": {"mode": "keep", "voice_id": null}
  },
  "scenes": {
    "sc01": {"mode": "replace", "plate": "restyle/plates/sc01.png", "fit": {"scale": 1.0, "dx": 0, "dy": 0}},
    "sc02": {"mode": "relight", "wall": {"lab": [2, -3, -12]}, "curtain": {"lab": [7, -2, -9]}},
    "sc03": {"mode": "keep"}
  },
  "product": {"mode": "lock", "product_id": null},
  "objects": {
    "ob01": {"mode": "keep", "reason": "contact_furniture"}
  },
  "output": {
    "aspect": "source",
    "resolution": "720p",
    "fps": 30
  },
  "captions": {
    "mode": "keep",
    "style": {
      "font": "NotoSansSC-Bold",
      "size": 34,
      "fill": "#FFD400",
      "stroke": "#111111",
      "stroke_width": 3
    }
  },
  "overrides": {
    "s07": {"scene": "keep", "reason": "manual"}
  },
  "updated_at": "2026-11-07T21:35:00+0800"
}
```

`output.aspect = "source"` 表示画幅跟随源片（这条是 9:16）；不强制 9:16，也不裁切。质量预设 480p / 720p / 1080p；这条源片是 720×1280，选 1080p 是上采样，不会凭空增加细节，UI 要标出来。

### 4.6 `variants/v1.json`

```json
{
  "id": "v1",
  "plan_revision": 3,
  "render": "renders/restyle_v1_720p.mp4",
  "resolution": "720p",
  "duration_s": 32.0,
  "created_at": "2026-11-07T21:50:00+0800",
  "cost_usd": 0.12
}
```

### 4.7 缓存键

- 静帧：`sha1(source_hash + shot_id + t + plan_revision)`
- 单镜预演：`sha1(source_hash + shot_id + plan_revision + resolution)`
- 全片：`sha1(source_hash + plan_revision + resolution + audio_mode)`

---

## 5. 技术方案

### 5.1 流水线

```text
upload
  → probe（ffprobe）
  → cuts（ffmpeg scene）
  → keyframes + thumbs
  → caption OCR（tesseract）
  → groups（场景 / 造型 / 商品）
  → risk + suggestions
  → blueprint.json
  → plan.json（用户编辑）
  → masks（人像 / 商品 / 字幕）
  → compose（背景板 + 前景 + 换色 + 字幕）
  → preview（360p 静帧 / 短片段）
  → render（480p/720p/1080p 逐镜）
  → concat + mux audio
  → QA + export
```

### 5.2 分析

**切镜**

- `ffmpeg -vf "select='gt(scene,0.18)',showinfo"`，解析 `pts_time`；
- 合并间隔 <0.35s 的切点；补 0 和总时长；
- 兜底：若切点数 <2，按 2.5s 等分。

**关键帧**

- 每镜取中点帧，输出 320px 宽 JPEG；
- 存 `restyle/thumbs/<shot>.jpg`，供镜头条和场景板参考。

**字幕 OCR**

- 裁底部 30% 区域；
- 预处理：黄色文字掩膜（HSV）→ 灰度 → 反色 → 放大 2×；
- `tesseract -l chi_sim+eng --psm 6 tsv`，取文本 + bbox + confidence；
- 失败时整帧兜底；仍失败则标记“需手填”，不阻塞。

**场景分组**

- 取关键帧背景区域（排除底部字幕带和中心人物框）；
- HSV 直方图 + Bhattacharyya 距离，层次聚类；
- 距离阈值可调；输出 3–6 组，UI 支持合并 / 拆分 / 改名。

**造型分组**

- 取人物躯干区域的颜色直方图；
- 同样聚类；标签按主色命名（“浅紫睡衣”“白浴袍”“米色开衫”）。

**风险评分（建议，不是硬判断）**

- 商品覆盖率（颜色 + 面积）；
- 运动量（帧差）；
- 人脸存在；
- 水/透明区域启发式；
- 输出 `risk.score` 和 `reasons`；默认高风险镜头 `suggested=keep`，用户可改。

**音频**

- 提取 16k 单声道 WAV；
- v1 只判断“有/无音轨”，默认保留；
- ASR 放到 P3（可选 faster-whisper / 云端 ASR）。

### 5.3 遮罩

> **macOS Vision 是什么？跟“平台”有什么关系？**
>
> Vision 是 Apple 系统自带的计算机视觉框架（macOS/iOS），`VNGeneratePersonSegmentationRequest` 是其中的人像分割 API。它在本机运行，不下载模型、不走网络，用 Apple Silicon 的 GPU / Neural Engine。
>
> 这里说的“平台”是**运行 Ad+ 的操作系统**（macOS / Windows），不是抖音、小红书这类投放平台；跟视频比例、清晰度、投放渠道没有关系。
>
> **Windows 是主平台**，所以不能把 Vision 当唯一路径。`PersonSegmenter` 抽象：
>
> - Windows：MediaPipe selfie segmentation（Apache-2.0，轻）或 ONNX（MODNet / RVM 等，质量更高）
> - macOS：Vision 只作为可选增强
> - 缺失任何后端时，硬镜头默认 `keep`
>
> 合成层只依赖“帧 → alpha mask”的接口，不感知后端。影响的是包体、速度、依赖，不影响输出格式和投放平台。

**人像**

- `adplus/restyle/segment.py`：`MediaPipeSegmenter` / `OnnxSegmenter` / `VisionSegmenter`，按平台自动选；
- 逐帧输出 8-bit alpha；空间羽化 3–5px；禁止对二值 mask 做 EMA 累积；
- 时序稳定用 3–5 帧中值，不用“上一帧 + 当前帧再阈值”；
- 不持久化全序列；渲染时按帧计算，UI 只缓存关键帧 mask。

**商品**

- 从关键帧取主色（饱和度最高的聚类）作为种子；
- HSV 范围 + 形态学 + 最大轮廓 + 时序平滑；
- 失败时 UI 提供矩形框 / 点选，GrabCut 兜底；
- 商品与手/腿重叠处允许人工修边（P2 加画笔）。

**字幕**

- 用 OCR bbox 生成 mask，膨胀 4px；
- 旧字去除：OpenCV Telea inpaint（小区域够用）；效果不够再上 LaMa ONNX。

### 5.4 合成

- 新背景板按场景组加载，缩放到源分辨率；
- 每镜支持 `fit: {scale, dx, dy}`，默认 center-fit；
- 运动镜头：用背景特征点估计单应性，warp 场景板；估计不稳定或运动太大时标记 `keep`（不硬换背景）；
- 固定机位优先：这条参考片大多数镜头是固定机位，先保证这类镜头质量；
- 前景 = 人像 ∪ 商品，保留原像素；
- 服装换色：三种模式——`hue`（有彩色衣服换色相）、`tint`（白/灰衣服染色）、`pattern`（换纹理/参考图）；都保留亮度与纹理，只作用于服装 mask，避开商品；
- 发色 / 肤色同理，强度可调；
- 接触阴影：alpha 模糊 + 偏移 + multiply，避免“贴上去”；
- 边缘：2px feather + 去背景色溢色；
- 字幕：先 inpaint 旧字，再按 style 重绘；
- 逐帧输出 BGR，pipe 给 ffmpeg `rawvideo`，避免落盘 PNG 序列。

### 5.5 字幕重打

- 字体：内置 `NotoSansSC-Bold`（OFL，约 10MB），保证跨机器一致；
- 样式：黄色 `#FFD400` 填充、黑色 3px 描边、底部居中；
- 自动换行：最大宽度 = 源字幕 bbox 宽度 × 1.1；
- 时间：跟随镜头起止；不做逐字动画；
- 用户可改文案，行数变化时保持底部基线。

### 5.6 音频

- v1 默认 `keep`：直接 mux 原音轨；
- `mute`：静音输出；
- `tts`（P2）：用现有 `adplus/audio_generator` + persona voice；脚本来自字幕 / ASR；按镜头时长 trim / pad；
- 音乐版权：保留原音轨也有版权风险，UI 在导出前提示。

### 5.7 渲染与任务

- 任务类型：`restyle_analyze` / `restyle_preview` / `restyle_render`；
- 复用 `adplus.jobs`（按 project_id 存）；
- 进度：`shots_done / shots_total`；取消在镜头边界生效；
- 单镜渲染：无音轨 mp4；全片：concat + mux；
- 导出：`ffmpeg -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -c:a aac`；
- 输出 `renders/restyle_<variant>_<res>.mp4`，ffprobe 校验后写 variant。

### 5.8 依赖与打包

新增 `requirements-restyle.txt`：

```text
# Windows sidecar: Python 3.12（不要用 3.14 打 Windows 包）
opencv-python-headless>=4.10
onnxruntime>=1.18
numpy>=2.0
Pillow>=11

# 可选后端
# mediapipe>=0.10.14        # 轻量 selfie segmentation；需确认 Windows py3.12 wheel
# pyobjc-framework-Vision>=10.3 ; sys_platform == "darwin"
# insightface>=0.7
# onnxruntime-gpu / onnxruntime-directml
```

- Windows 主路径：ONNX Runtime + 许可兼容的 matting 模型（MODNet 等待法务确认）；MediaPipe 作为轻量备选；
- macOS 的 Vision 只是可选增强，不能成为唯一路径；
- 主 `.venv` 目前没有 cv2 / torch；不要直接把 torch 打进桌面包；
- 系统依赖：`ffmpeg`、`tesseract` + `chi_sim` 语言包；打包时随包并检测；
- 字幕字体放 `assets/fonts/NotoSansSC-Bold.otf`；
- Windows 安装包：NSIS/MSI + `.ico`；app data 走 `%APPDATA%\Ad+`；代码签名另列。

---

## 6. 接口

| Method | Path | 作用 |
|---|---|---|
| `POST` | `/api/restyle` | 从已上传视频创建改写项目 |
| `GET` | `/api/restyle` | 改写项目列表 |
| `GET` | `/api/restyle/{id}` | 工作台全量状态 |
| `POST` | `/api/restyle/{id}/analyze` | 启动读片任务 |
| `PATCH` | `/api/restyle/{id}/plan` | 保存 plan（带 revision 乐观锁） |
| `GET` | `/api/restyle/{id}/frame/{shot_id}?t=&rev=` | 静帧预览 JPEG |
| `POST` | `/api/restyle/{id}/preview` | 单镜 / 全片预演任务 |
| `POST` | `/api/restyle/{id}/render` | 全片渲染任务 |
| `POST` | `/api/restyle/{id}/export` | 导出交付文件 |
| `POST` | `/api/restyle/{id}/duplicate` | 再来一版 |
| `DELETE` | `/api/restyle/{id}` | 移入回收站 |
| `GET` | `/api/jobs?project_id=` | 复用现有任务查询 |
| `POST` | `/api/jobs/{job_id}/cancel` | 复用现有取消 |

### 6.1 创建

```json
POST /api/restyle
{
  "path": "uploads/20261107/ref.mp4",
  "title": "小背心爆款改写",
  "rights_confirmed": true
}
```

后端：校验文件存在、是视频、位于 uploads/projects 根内；ffprobe；创建项目；写 `source.json`；返回 `{project, restyle}`。

### 6.2 plan 保存

```json
PATCH /api/restyle/{id}/plan
{
  "revision": 3,
  "patch": {
    "change_level": "recommended",
    "scenes": {"sc01": {"mode": "replace", "plate": "restyle/plates/sc01.png"}},
    "cast": {"outfit_targets": {"of02": {"hue": 210}}}
  }
}
```

- revision 不匹配返回 `409` + 当前 plan；
- 后端合并、校验、递增 revision、写盘；
- 返回 `{plan, affected_shot_ids}`。

### 6.3 静帧

`GET /api/restyle/{id}/frame/{shot_id}?t=1.2&rev=3` → `image/jpeg`

- 服务端按缓存键生成 / 复用；
- 失败时返回原帧并加 `X-Restyle-Fallback: 1`。

### 6.4 任务返回

统一返回 `{job}`；进度用 `frames_done / frames_total`。

---

## 7. 前端

### 7.1 路由 / 导航

- `/restyle`：列表 + 拖拽上传
- `/restyle/:id`：工作台
- `ModuleDock` 增加 `restyle`（图标 `layers`），文案「改写」
- `ModuleKey` 增加 `"restyle"`

### 7.2 组件

```text
frontend/src/routes/Restyle.tsx              # 列表 / 上传
frontend/src/routes/RestyleWorkbench.tsx     # 工作台
frontend/src/components/restyle/
  Player.tsx            # 原片 / 新片 / 对比
  ShotStrip.tsx         # 分组镜头条
  AnalysisCard.tsx      # 读片卡
  ChangeLevel.tsx       # 轻改 / 推荐 / 全改
  Inspector.tsx         # 全片 / 选中镜头
  CastCard.tsx
  SceneCard.tsx
  ProductCard.tsx
  CaptionCard.tsx
  VoiceCard.tsx
  PreviewOverlay.tsx    # 静帧加载 / 失败
  ReviewDrawer.tsx
  ExportDialog.tsx
```

### 7.3 状态

- `detail`：project + source + blueprint + plan + variants
- `selectedShotId` / `selectedGroup`
- `panel`: `all | shot`
- `playerMode`: `source | preview | compare`
- `previewUrl`：由 shot / t / revision 计算，`img` 预加载
- `job`：轮询 `/api/jobs?project_id=`
- 自动保存：plan 变更 debounce 300ms；本地乐观更新；409 时 refetch
- 撤销：客户端保存最近 20 个 plan 快照

### 7.4 快捷键

`Space` 播放/暂停，按住 `B` 看原片，`[` `]` 切镜，`A` 应用同组，`Cmd+Z` 撤销，`?` 快捷键面板。

### 7.5 性能

- 缩略图 lazy load；
- 静帧用 `<img>`，避免解码视频；
- 预演只跑选中镜头；全片预演后台队列；
- 播放器用 360p proxy；导出才用 480p/720p/1080p；
- 切换镜头不重建视频元素，只 seek。

---

## 8. 实施阶段

> 估算按 1 名全栈工程师全职；前后端并行可压缩到 3 周左右。

### P0 — 技术 spike（2–3 天）· 已完成 2026-11-07

**结论：Conditional Go。** 详见 [P0 测试报告](verification/restyle-spike/REPORT.md)。

实际测试：

- 镜头：`s03`（人 + 长凳）、`s07`（人 + 黄沙发）、`s18`（手 + 桶 + 地毯）；
- 人像：Vision `VNGeneratePersonSegmentationRequest`；
- 商品：HSV + GrabCut；
- 背景板：MiniMax image（cn）；
- 合成：OpenCV；编码：ffmpeg。

结果：

- `s18` 单帧通过：商品完整、手部边缘可接受、阴影成立；
- `s18` 连续帧失败：Vision 在部分帧把沙发当人，alpha 覆盖全屏；
- `s03` 全背景替换出现长凳矩形补丁 / 人物漂浮；只换上半墙有横向接缝；
- `s07` 沙发占满画面，可替换区域很小，建议 `keep`；
- Vision 约 **0.15s/帧**（720p），32s 视频约 2.4 分钟，性能可行。

直接生成 A/B：

- Seedance `s18`：房间换了，但桶/手被重画，字幕消失；
- Seedance `s03`：真人输入被隐私策略拒绝；
- MiniMax `s03`：能跑，但人物/桶变了、背景没换；
- 结论：商品/手部镜头不走直接生成，继续分层合成。详见报告 §6。

**Go / No-Go**：有条件通过。继续 P1 骨架；P2 必须补 **mask fallback**、**支撑物层**、**`relight` 背景重制**；手部/商品镜头默认 `keep`；v1 不承诺 22 镜全部自动换背景。

### P1 — 骨架（4–5 天）· 已完成 2026-11-07

任务：

- `project_store` 支持 `format_id=reference_restyle`；Projects 列表过滤 / 徽标；
- `adplus/restyle/` 包：`store.py`、`analysis.py`、`plans.py`；
- 创建 / 列表 / 详情 / 分析 / plan API；
- 切镜、关键帧、OCR、分组、建议；
- `/restyle` 列表 + 拖拽上传；
- 工作台壳：播放器、镜头条、Inspector、读片卡、改动幅度；
- 自动保存 + revision。

实现：

- `adplus/restyle/{store,analysis,plans}.py`；
- `/api/restyle` 创建 / 列表 / 详情 / 读片 / plan；
- `/restyle` 列表 + 拖拽上传 + 权利确认；
- `/restyle/:id` 工作台壳：播放器、镜头条、读片卡、改动幅度、场景组、字幕/商品/声音卡；
- 自动保存 + revision 409 处理。

验收（2026-11-07 实测）：

- 参考片 **7.5–8s** 读出 22 镜、4 场景、3 造型；字幕 21/22（OCR 需校对）；
- 刷新页面状态不丢；
- plan revision 冲突返回 409；
- 前端 `pnpm build` 通过；后端 9 个新测试通过。

> Windows 验证属于 **W0**；当前 P1 只在 macOS 实测。

### W0 — Windows 构建 spike（3–5 天）· 先做

Windows 是主平台，安装包不能等到最后再补。

任务：

- Tauri 2 增加 `nsis` / `msi` 目标、`.ico` 图标；确认 Windows 10/11 WebView2；
- Python sidecar 固定 **3.12**，PyInstaller 打包 `app.main`；
- 随包：ffmpeg / ffprobe、tesseract + `chi_sim`、Noto Sans SC、分割模型；
- 路径：`ADPLUS_FFMPEG` / `ADPLUS_TESSERACT` 解析；JSON 全部 POSIX；`CREATE_NO_WINDOW`；
- 在 Windows 上跑参考片读片（22 镜 / 4 场景 / 3 造型 / OCR）；
- GitHub Actions `windows-latest`：`.github/workflows/windows.yml` + `scripts/restyle_smoke.py`；后端测试 + 读片 smoke + 前端 build。

验收：

- 干净 Windows 10/11 机器安装后，能上传视频、读片、打开工作台；
- 不依赖系统 Python / ffmpeg / tesseract；
- 读片 ≤ 90s（Windows 中端 CPU）。

**Go / No-Go**：W0 不过，不继续做 Windows 主平台的 P2；先修打包。

### P2 — 背景（5–6 天）

任务：

- 人像 mask：`PersonSegmenter`（Windows：MediaPipe / ONNX；macOS：Vision 可选）+ 空间羽化；**禁止二值 EMA 累积**；
- **mask fallback**：关键帧手绘 mask + GrabCut + 光流/跟踪；手部/商品镜头不能只靠 Vision；
- **支撑物层**：长凳 / 沙发 / 椅子 / 床单独成组，默认 `keep`；
- **背景重制 `relight`**：墙面 / 窗帘 LAB 调色 + 软 mask；接触家具镜头默认走这条，不换几何；地板调色需要几何/颜色 mask，放 P2 后半；
- 商品 mask：颜色 + 轮廓 + GrabCut；从 person mask 中扣除，只用于保留；
- 场景板上传 / 生成 / 选择；每镜 `fit`，运动镜头可加单应性，估不准默认 `keep`；
- 静帧合成 + `/frame` 缓存；
- 分组换景、单镜覆盖；
- 单镜 3s 预演 + 全片草稿；
- 接触阴影、边缘 feather、色温匹配。

验收：

- 换“卧室”组，5 镜一起变；
- 可替换镜头覆盖率 ≥ 60%；高风险镜头默认保留；
- 手部/商品镜头连续帧无明显跳变；
- 接触家具镜头走 `relight`：无接缝、不悬浮、不出矩形补丁；
- 静帧 < 400ms；3s 预演 < 15s。

### P3 — 人物外观 + 字幕（4–5 天）

任务：

- 服装换色（按造型组，LAB/HSV）；
- 发色 / 肤色（强度可调）；
- 场景板与人物光色匹配；
- 字幕 OCR 结果可视化、逐条编辑；
- 旧字 inpaint + 新字重打（字体 / 描边 / 换行）；
- 可选：InsightFace 换脸（P3 末，默认关闭）；
- 声音：保留 / 静音 / TTS 占位。

验收：

- 换装后商品附近不串色；
- 字幕位置 / 字体 / 文案正确；
- 露脸镜头可选换脸，不换也像另一个博主。

### P4 — 审片 / 导出（3–4 天）

任务：

- 全片渲染（按所选质量，默认 720p；逐镜 + concat + mux）；
- 审片模式：原片 / 新片同步对比、逐镜通过/重做；
- 导出预设 480p / 720p / 1080p、字幕烧录 / SRT；
- variant 记录、再来一版、回收站；
- 失败重试、取消、断点续跑；
- 权利门：未确认不允许导出。

验收：

- 32s 720p ≤ 8min；480p 更快，1080p 允许更久（上采样）；
- 导出时长 ±0.2s，音画同步；
- 失败可恢复，不丢 plan。

### P5 — 打磨（2–3 天）

任务：

- 快捷键、空状态、动效、骨架屏；
- 性能：缓存命中、并发限制、内存；
- 错误文案、日志、诊断；
- 文档 + 验收截图。

验收：

- 22 镜操作全程无阻塞；
- 新用户 3 分钟内能出第一版静帧；
- 10 分钟内能出全片草稿。

---

## 9. 测试与验收

### 9.1 单元

- `cuts`：合成 3 段视频，切点 ±0.1s；
- `group`：给定直方图，分组稳定；
- `plan`：change_level 推导、override 优先、revision 冲突；
- `compose_frame`：背景像素变化、商品像素保持、字幕绘制；
- `captions`：换行、bbox、描边。

### 9.2 集成

- `TestClient` 创建 → 分析（monkeypatch 分析结果）→ plan → frame → 渲染；
- 任务状态 / 取消 / 重试；
- 路径校验：拒绝 `../`、拒绝 workspace 外文件；
- 权利门：未确认导出 403。

### 9.3 Fixture

- `tests/fixtures/restyle/`：3 镜合成片（色块 + 移动矩形 + 字幕），不依赖参考片；
- 参考片手工验收，不入库（版权）。

### 9.4 手工验收清单

- [ ] 上传 32s 参考片，60s 内出 22 镜
- [ ] 读片卡建议 15 改 / 7 留
- [ ] 换卧室组，5 镜同步更新
- [ ] 单镜回退不影响其他
- [ ] 空格对比、分割线对比
- [ ] 字幕 22 条可编辑
- [ ] 导出 720p，时长 / 音画正确
- [ ] 刷新 / 重启后 plan 还在
- [ ] 未确认权利不能导出
- [ ] 失败镜头可重试

### 9.5 性能

- 分析 32s：≤ 60s
- 静帧 p95：≤ 400ms
- 单镜 3s 360p：≤ 15s
- 全片 720p：≤ 8min
- 内存峰值：≤ 2GB

---

## 10. 风险

| 风险 | 影响 | 应对 |
|---|---|---|
| 人像边缘（头发 / 手指）穿帮 | 高 | PersonSegmenter + 空间羽化；保留镜头兜底；P2 加画笔 |
| 手部/商品特写分割失效（把沙发当人） | 高 | Mask fallback：关键帧手绘 + GrabCut/光流；默认 `keep` |
| 接触家具导致人物悬浮/矩形补丁 | 高 | `objects` 层默认 `keep`；场景板需带同位置家具 |
| 商品与衣服颜色接近，mask 串色 | 高 | 颜色 + 轮廓 + 手工框；服装换色避开商品 mask |
| 场景板透视 / 光影不匹配 | 中 | 同机位场景板；`fit` 微调；接触阴影；色温匹配 |
| 字幕 inpaint 留痕 | 中 | 小区域 Telea；不行上 LaMa；允许保留原字幕镜头 |
| 换脸质量 / 肖像权 | 中 | 默认关闭；仅授权 persona；导出前提示 |
| 22 镜渲染慢 | 中 | 360p 预演；逐镜缓存；后台队列；并发 2 |
| Windows 优先 / 跨平台 | 高 | Tauri NSIS + Python 3.12 sidecar；Windows 默认 MediaPipe/ONNX，Vision 仅 macOS 可选；W0 先验安装包 |
| Windows wheel / 打包 | 高 | 固定 Python 3.12；模型许可先审；CI windows-latest；不依赖系统 ffmpeg/tesseract |
| 范围膨胀 | 高 | v1 明确不做换体型 / 重演 / NLE |
| 版权 / 商标 | 高 | 权利门 + 导出提示 + 来源记录；不内置参考片 |

---

## 11. 里程碑

| 周 | 交付 |
|---|---|
| W1（已完成） | P0 spike + P1 骨架；参考片读片、镜头条、读片卡 |
| W0（下一步，优先） | Windows 安装包 spike：Tauri NSIS + Python 3.12 sidecar + 随包 ffmpeg/tesseract；Windows 读片通过 |
| W2 | P2 背景：PersonSegmenter、静帧预览、relight；Windows 上跑通 |
| W3 | P3 人物外观 + 字幕；能出全片草稿 |
| W4 | P4 审片 / 导出 + P5 打磨；Windows + macOS 双平台验收 |

---

## 12. 待确认

已确认：

- 人物只换外观，不换体型、不重演；
- 商品保持原片这款，不换 SKU；商品层锁定原像素；
- 声音可选：保留原声 / 静音 / 重配；
- 画幅默认跟随源片；质量 480p / 720p / 1080p。

待确认：

1. 声音默认保留原声，UI 再给“静音 / 重配”，可以吗？
2. 1080p 是从 720p 源上采样，接受吗？还是只提供 480p / 720p？
3. Ad+ 是否只发 macOS？如果以后要 Windows，我按抽象层做，Windows 后端后补。
4. 这条参考片只放本地 `uploads/` 做测试、不提交仓库，可以吗？

---

## 13. 可直接开工的第一批任务

- [x] 参考片已放本地 `uploads/20261107/ref-footbath-32s.mp4`（gitignored）
- [x] 预期切点 / 镜头数 / 分组数写在 `tests/fixtures/restyle/reference_expected.json`
- [x] P0 spike：Vision + GrabCut + 场景板 + 静帧/片段；报告 `docs/verification/restyle-spike/REPORT.md`
- [x] P0.5 接触家具：`s03` 墙面/窗帘 `relight` 通过（无接缝、不悬浮）
- [ ] P0.5 手部镜头：`s18` 关键帧 + 光流仍不够干净；需要画笔/SAM2，v1 先默认 `keep`
- [x] P1：store / analysis / plan API + `/restyle` 列表 + 工作台壳（2026-11-07）
- [ ] P2：`GET /frame` 静帧 + Vision/商品 mask + relight 预览
- [ ] P2：支撑物层 + 硬镜头默认 `keep`
