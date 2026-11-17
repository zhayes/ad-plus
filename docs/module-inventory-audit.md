# 模块盘点：能复用什么、该删什么

> 日期：2026-11-09
> 方法：静态分析（import 图 + 端点引用 + 前端引用），未运行 App。
> 结论：**能复用约 60% 的领域代码，该删约 2,400 行自有代码 + 197 个上游工具模块。**

---

## 0. 总账

| 资产 | 现在 | 目标 | 变化 |
|---|---|---|---|
| `adplus/` Python | 9,188 行 | ~7,800 行 | 删 ~1,300 行，改造 ~2,000 行 |
| `app/` Python | 3,523 行 | ~3,000 行 | 删 Pi/提案代理 |
| `frontend/src` | 13,734 行 | ~12,600 行 | 删 Workspace + chat |
| 上游工具模块 | 209 个 | 12 个（allowlist） | 启动从数秒降到亚秒 |
| 第三方依赖 | 13 个 | 8 个 | 去掉 google/openai/websockets |
| vendor 体积 | 741 MB | ~50 MB（不含 node_modules） | 去掉 backlot/ink-theater/assets/197 工具 |

---

## 1. 直接复用（逻辑不动，只接新入口）

| 模块 | 作用 | 为什么能直接用 |
|---|---|---|
| `adplus/paths.py` | 目录常量 | 无业务状态 |
| `adplus/jobs.py` | 任务记录/进度/取消 | 批次执行器直接复用 |
| `adplus/agent_bridge.py` | 文件级记录契约 | quote/approval/job 已跑通 |
| `adplus/capabilities.py` | 模型能力 + 预检 + 计费提示 | 批量报价的基础 |
| `adplus/quote.py` | 报价估算 | 加 `build_batch_quote` 即可 |
| `adplus/products.py` | 商品库 | 商品真相的起点 |
| `adplus/personas.py` / `assets.py` | 人设/素材库 | 身份一致性需要 |
| `adplus/product_composite.py` | 商品回贴 + 标签 QA | **核心差异点，必须留** |
| `adplus/oms_tools.py` | `product_plate` 工具注册 | 同上 |
| `adplus/restyle/analysis.py` | 切点/关键帧/字幕区分析 | B 的结构复用基础 |
| `adplus/restyle/segment.py` | 人像/服装分割 | B 的 mask 来源 |
| `adplus/restyle/outfit.py` | LAB 换色 + 羽化 + 商品排除 | B 的零成本变体 |
| `adplus/restyle/speech.py` | 口播/镜头分类 | 判断数字人/口播镜头 |
| `adplus/tts.py` | 本地/系统 TTS | 口播旁白 |
| `adplus/formats.py` | 三种广告格式预设 | A 的入口参数 |

**这部分大约 3,500 行，是真正值钱的家底。**

---

## 2. 改造后复用（形状不对，逻辑可留）

| 模块 | 现在的问题 | 改成 |
|---|---|---|
| `adplus/production.py` | 只读 `current_version`，阶段扁平 | 加 `version_id` 参数；审批按版本维度 |
| `adplus/project_store.py` | 版本 = 单一当前版本 | 加 `batch_id` / variant lineage；approvals 版本化 |
| `adplus/local_motion.py` | 写死文字卡版式 | 抽成模板渲染器（manifest + 槽位） |
| `adplus/pipeline_runner.py` | 单项目串行阶段 | 变成 batch runner 的一步 |
| `adplus/asset_generator.py` | 依赖单一版本 | 挂到变体上下文 |
| `adplus/audio_generator.py` | 同上 | 同上 |
| `adplus/restyle/plans.py` | 单份 plan | 加 `variants[]`（patch 派生） |
| `adplus/restyle/store.py` | 单 plan 读写 | 加变体读写与渲染 fan-out |
| `adplus/mcp/__main__.py` | 1,311 行，14 个 agent 工具 | 只留 `om_render`（约 200 行） |
| `app/capabilities.py` | `registry.discover()` 全量导入 209 个工具 | 改成 allowlist 加载 12 个 |

**改造重点：`discover()` 是启动慢和打包大的根源。** 不要改 vendor 子模块，在 AdPlus 侧加 `adplus/tools_loader.py`：

```python
TOOLS = ["seedance_ark", "minimax_video", "kling_avatar", "heygen_avatar",
         "lip_sync", "talking_head", "video_compose", "video_stitch"]
# 逐个 importlib.import_module + registry.register_module(...)
```

然后 `_warm_registry()` 和 `capabilities._registry()` 都走它。

---

## 3. 删除（按「先替换、后删除」顺序）

| 模块 | 行数 | 删除理由 | 前置条件 |
|---|---|---|---|
| `app/pi_bridge.py` | 190 | Pi agent 只服务 `/chat` 与提案生成 | 本地 Planner 上线 |
| `app/proposal_runner.py` | 306 | 通过 Pi 调 `om_proposal`，链路绕 | 同上 |
| `frontend/routes/Workspace.tsx` | 262 | 旧自由创作页 | `/create` 上线 |
| `frontend/components/chat/*` | 505 | 只被 Workspace 使用 | 同上 |
| `frontend/stores/{asks,session,transcript}.ts` | 360 | 同上 | 同上 |
| `adplus/digital_human.py` | 247 | avatar 路线默认不可用 | 确认不做本地数字人 |
| `adplus/persona_base.py` | 134 | 生成数字人底片 | 同上 |
| `adplus/persona_generator.py` | 112 | AI 生成模特图，非 A/B 必需 | 商品库改用真实模特照 |
| `adplus/local_tools.py` | 27 | Wav2Lip 无 license、禁止商用 | 换 LatentSync 或云口型 |
| `adplus/asset_compose.py` | 141 | 旧合成路径，被 asset_generator 取代 | 迁移 `/pipeline/complete` |

小计：**Python ~1,157 行 + 前端 ~1,127 行 + 两个 app 文件 496 行 ≈ 2,780 行**（与上面 2,400 的差值来自是否保留 request_probe）。

**降级而不是删除**：

- `adplus/request_probe.py`（164 行）：从产品 API 移到 `scripts/` 或内嵌到 `capabilities.preflight`；
- `adplus/proposals.py`：数据层保留，生成端从 Pi 换成本地 Planner；
- `adplus/canonical_artifacts.py` + `pipeline_adapter.py`：A+B 仍可用 canonical 产物；若彻底 Timeline 化，再评估是否值得留。

---

## 4. 依赖清理

| 依赖 | 现在 | 处理 |
|---|---|---|
| `pywebview` | Tauri 不可用时的窗口 fallback | 留 |
| `mcp` | MCP server | 若不再对外暴露 MCP，删 |
| `google-auth` / `google-genai` | 上游 Google TTS/Veo | **删**（Ad+ 代码零引用） |
| `openai` | 上游 Sora | **删** |
| `websockets` | ElevenLabs 实时音频 | **删** |
| `watchfiles` | 上游 backlot 热更 | **删** |
| `pyyaml` / `jsonschema` | 上游 pipeline/canonical 校验 | 留（vendor 用） |
| `fastapi` / `uvicorn` / `pydantic` | 后端 | 留 |
| `numpy` / `Pillow` | 图像/换色 | 留 |
| `opencv-python-headless` / `onnxruntime` / `mediapipe` | restyle | 留 |

净效果：依赖从 13 个降到 8 个，安装体积和冷启动都下降。

---

## 5. vendor（上游子模块）怎么处理

| 目录 | 体积 | 处理 |
|---|---|---|
| `tools/` 209 个模块 | 9.2 MB | 只加载 12 个；其余不删源码（子模块保持干净），靠 allowlist 不导入 |
| `backlot/` | 168 KB | 不用（自带 FastAPI board 服务） |
| `ink-theater/` | 2.1 MB | 不用 |
| `docs/` `tests/` | 大 | 不打包 |
| `assets/` | 21 MB | 确认渲染是否引用；不引用则不打包 |
| `remotion-composer/node_modules` | 568 MB | **不打包**，改安装时 `npm ci` 或预构建 bundle |
| `skills/` `styles/` `pipeline_defs/` | 1.6 MB | `styles`/`pipeline_defs` 留；`skills` 若 Pi 去掉可删 |

注意：子模块是 git submodule，**不要在里面改代码**；所有裁剪都在 AdPlus 侧的加载器与打包脚本里做。

---

## 6. 前端页面去留

| 页面 | 处理 |
|---|---|
| `Projects` | 留（加批次摘要） |
| `Studio`（七阶段） | 留，降级为「精修」 |
| `Create`（新增） | 默认入口 |
| `Batch`（新增） | 批次/变体 |
| `Restyle` / `RestyleWorkbench` | 留，加变体矩阵 |
| `Assets` / `Personas` / `Products` / `Brands` | 留（商品库核心） |
| `Tasks` | 留（按批次聚合） |
| `Settings` / `Onboarding` | 留 |
| `Workspace`（/chat） | **删** |
| `components/chat/*` | **删** |
| `components/panel/ArtifactsPanel` | 只被 chat 用则删 |

---

## 7. 顺序（重要）

1. **先建本地 Planner**（替换 Pi 的提案生成），否则删 `/chat` 会断掉提案。
2. **先把 `local_motion` 改成模板渲染器**，再删 `asset_compose`。
3. **先确认 avatar 不做**，再删 `digital_human` / `persona_base` / `local_tools`。
4. **先接 allowlist 并跑通 quote/capabilities**，再谈 vendor 裁剪。
5. **最后删前端 Workspace/chat**。

任何一步反了，都会出现「功能先用不了、代码先删了」的空窗。

---

## 8. 不能删的清单

- `product_composite` + `products` + 标签 QA（唯一护城河）
- `capabilities` + `quote`（成本与能力门禁）
- `restyle/analysis|segment|outfit`（B 的零成本变体）
- `project_store` 的兼容读取（老项目不能丢）
- 审批/审计记录（商用交付的信任基础）

---

## 9. 一句话

**复用的不是代码量，是「商品真相 + 成本门禁 + 改写分析」这三块；删的不是功能，是「Pi 聊天、Wav2Lip 数字人、旧合成路径、上游 197 个用不到的工具」。**
先替换、再删除，能省 2,700 行自有代码和 5 个重依赖，且不丢任何 A/B 需要的能力。
