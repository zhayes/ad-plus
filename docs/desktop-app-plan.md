# OpenMontage 桌面应用 — 实施计划

> **路径说明（2026-11 拆分后）**：本文写于 Ad+ 独立成仓之前。当前布局为
> `~/AdPlus/`（Ad+ 代码：`adplus/`、`app/`、`frontend/`）+ `vendor/openmontage/`（上游 submodule）。
> 文中 `om_mcp.py` 现位于 `adplus/mcp/__main__.py`，`lib/{agent_bridge,quote,jobs}.py` 现位于 `adplus/`，
> `app/ui/*.html` 已由 `frontend/` 的 Solid 界面取代。


> 目标：把 OpenMontage 打包成桌面应用（Tauri 2 壳 + Pi 1.x agent），用户在一个窗口里对话式产出广告视频。
> 约束：安装包尽量小；模型 key 与媒体服务 key 全部可在界面配置；Pi 使用最新版。
>
> **状态（2026-11-04）**：MVP 已交付并验证 —— 见 [mvp-verification.md](mvp-verification.md)。
> 已落地：MCP 门面（10 工具）、设置页（模型/媒体 key/exposure/trust）、原生窗口（pywebview 先行）、对话与成片预览、费用遥测与预算熔断、`.app` 构建。
> 未落地：Tauri 替换、懒下载运行时分发、公证与自动更新、Backlot 嵌入。W2 的日期已不适用，按验证报告第 4 节推进。

## 0. 结论先行：key 现在能不能在页面配？

**不能，必须新增设置入口。** 现状：

| 部分 | 现在在哪 | 有无 UI |
|---|---|---|
| 媒体服务 key（FAL/ARK/ElevenLabs…） | 仓库根 `.env`（[.env.example](../.env.example) 60+ 项） | 无，只能手写文件 |
| Pi 的模型凭据 | `~/.pi/agent/auth.json` | 只有终端 `/login` / `pi config` |

两个有利事实（决定实现方式）：

1. `tools/tool_registry.py:87` 的 `_load_dotenv()` **只在 `key not in os.environ` 时才写入** —— 所以从应用进程注入环境变量不会被 `.env` 覆盖，**不需要往仓库写明文密钥**。
2. `tools/base_tool.py:500` 的 `env:` 依赖检查是**调用时实时读 `os.environ`** —— 保存 key 后可以立刻重算能力矩阵，不用重启应用。

## 1. 设置页设计

两块必须分开，混在一起会让用户搞不清"哪个 key 是干什么的"。

### A. 模型（驱动 agent 的 LLM）

- provider 选择：Anthropic / OpenAI / Google / DeepSeek / OpenRouter / 自建 OpenAI 兼容 endpoint
- 凭据：直接填 key，或走 OAuth 登录（Pi 原生支持）
- 模型下拉 + thinking level
- **测试连接**：发一次最小请求，2 秒内给结果
- 写入位置：交给 Pi 的 `AuthStorage`（`~/.pi/agent/auth.json`），不自己另存一份

### B. 媒体服务（OpenMontage 的 60+ key）

按能力分组展示，每行至少四件事：

| 列 | 内容 | 来源 |
|---|---|---|
| 能力组 | 图像 / 视频 / 语音 / 音乐 / 素材 / 分析 | registry `capability_catalog()` |
| Key 输入 | 密码框，只显示末 4 位 | — |
| 解锁什么 | "FAL_KEY 解锁 14 个工具（图 + 视频 + TTS + 音乐）" | registry `provider_menu_summary().setup_offers` |
| 状态灯 | available / unavailable + 原因 | 工具的 `get_status()` |
| 说明 | 去哪申请（不硬编码，读 `install_instructions`） | registry 字段 |

顶部固定一行"现在能做什么"：`图像 0/29 · 视频 0/33 · 语音 0/18 · 音乐 0/6`，以及"零 key 也能出图形广告"的提示。

### 安全与存储

- macOS **Keychain** 优先；无 Keychain 时回退到加密 JSON（AES-GCM，密钥存 Keychain）
- **永不回显**完整值、**永不进日志**、**永不写入仓库 `.env`**
- 注入路径：启动 python sidecar 时拼进 env；保存后调 `om_reload_env` 工具热更新
- 明确不采集：key 不上报、不进崩溃报告

## 2. 六周计划

### W1 — 可行性 spike（决定后面五周值不值得投）

| 任务 | 产出 |
|---|---|
| 写 `adplus/mcp/__main__.py`：`registry.discover()` → MCP `list_tools`/`call_tool` | 15 个门面工具：`om_capabilities` `om_start_project` `om_plan` `om_image` `om_video` `om_tts` `om_music` `om_compose` `om_job_status` `om_checkpoint` `om_reload_env` … |
| 长任务做 submit/poll 两段式 | 避免 MCP 默认 60s 超时掐断渲染 |
| 起 `pi --mode rpc`，`.pi/mcp.json` 指向 `om_mcp` | Pi 能看见 `openmontage` 的工具 |
| 端到端跑一条 | 一句"做 20 秒图形广告" → `projects/<id>/renders/final.mp4` |

**验收**：Pi 自己读 `.agents/skills/` 下的 director skill，按流水线调用工具，产物落在规范路径；中途 kill 掉渲染进程能重连续跑。
**风险**：Pi 1.x 的 MCP 工具命名规则、超时/取消语义必须先实测，名字会进 prompt。

### W2 — 设置页 + 能力矩阵（提前做，因为它决定 UI 骨架）

| 任务 | 产出 |
|---|---|
| 后端 | `GET /api/secrets`（掩码）、`PUT/DELETE /api/secrets`、`GET /api/capabilities`、`POST /api/test/{provider}` |
| 前端 | 模型 + 媒体两块、状态灯、"测试连接"、能力计数条 |
| 热更新 | 保存 → 注入 env → `om_reload_env` → 重算矩阵 |

**验收**：填入一个 `FAL_KEY`，图像从 `0/29` 变 `1/29`，无需重启；错误 key 给出可读原因。

### W3–W4 — Tauri 壳

| 任务 | 产出 |
|---|---|
| 窗口与生命周期 | 单实例、DPI、菜单、深色主题跟随系统 |
| sidecar 管理 | 拉起/守护/退出清理 `pi`、`om_mcp`、渲染进程；崩溃自动重启并保留会话 |
| React UI | 对话流、工具调用卡片（进度/耗时/成本）、Backlot iframe、产物画廊 |
| 事件流 | Pi RPC 的 JSONL 事件 → UI 状态机（在跑什么、花了多少） |

**验收**：关窗后无 orphan 进程；重开能恢复上次会话；渲染中 UI 不冻结。

### W5 — 运行时与首启

| 任务 | 产出 |
|---|---|
| 懒下载 | Remotion 依赖、ffmpeg：进度条 + 校验 + 断点续传 |
| 渲染浏览器策略 | 三段式：探测系统 Chrome/Edge → 命中且用户开启"复用系统浏览器"则用 `browserExecutable`；否则下载钉死版 `chrome-headless-shell`（Remotion 4.0.484 → `TESTED_VERSION=149.0.7790.0`，压缩 93 MB / 展开 193 MB） |
| 可写根 | `OPENMONTAGE_PROJECTS_DIR`、`.env` 读取路径、`.backlot/thumbs` 全部指向 Application Support |
| 首启向导 | 选工作目录 → 拉运行时 → 配 key（可跳过）→ 自动出一条 demo |

**验收**：全新 macOS 用户从零到出片 ≤ 6 分钟（含下载）；只读 App 包下无写入错误。

### W6 — 打包与上线准备

| 任务 | 产出 |
|---|---|
| 签名 + 公证 | Developer ID，notarytool 通过 |
| 自动更新 | Tauri updater + 签名校验 |
| 三条端到端验收片 | 零 key 图形广告 / 单 key 真广告 / 长任务中断恢复 |
| 文档 | 支持矩阵、已知限制、许可证声明 |

## 3. 里程碑

| 里程碑 | 时点 | 判定标准 |
|---|---|---|
| M0 技术可行 | W1 末 | 端到端出一片，且是 MCP 驱动而不是硬编码脚本 |
| M1 可配置 | W2 末 | 页面上配 key → 能力矩阵实时变化 |
| M2 可交互 | W4 末 | 窗口内完成"说一句 → 出片"全流程 |
| M3 可分发 | W6 末 | 未装过环境的机器能装、能跑、能出片 |

## 4. 仓库改动清单

| 文件 | 改动 | 性质 |
|---|---|---|
| `adplus/mcp/__main__.py`（或 `tools/mcp/`） | 新增：MCP 服务，包装 registry | 新增 |
| `vendor/openmontage/lib/paths.py` | 增加可写根解析（`OPENMONTAGE_APP_DATA`），`REPO_ROOT` 只读化 | 改 |
| `backlot/server.py:25` | 缩略图缓存目录改读可写根 | 改 |
| `tools/tool_registry.py:91` | `.env` 路径支持 `OPENMONTAGE_ENV_FILE` 覆盖 | 改 |
| `config.yaml` | 增加 `app:` 段（首个运行、运行时下载开关） | 改 |
| `.env.example` | 补一句"桌面应用里这部分由设置页管理" | 改 |

## 5. 验收标准（可测）

- 首包 ≤ 120 MB（不含首次下载的渲染栈：Chrome headless 93 MB + Remotion 依赖）
- 渲染浏览器：默认使用下载的钉死版本；开启"复用系统 Chrome"时若版本不匹配给出告警而非静默失败；无 Chrome 且无网时明确报错（不出黑屏成品）
- 冷启动到可对话 ≤ 8 s（M 系列 Mac）
- 20 秒图形广告渲染 ≤ 4 min；进度可见、可取消
- 零 key 首启不崩，能出无旁白图形广告
- 密钥只存 Keychain；日志脱敏测试通过（grep 全量日志无 key 子串）
- `om_mcp` 有单测 + 一条无网 mock 的端到端 CI

## 6. 风险清单

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| Pi 1.x API/工具命名变动 | 中 | 高 | W1 钉版本 + 记录版本号 + 启动时校验 |
| MCP 长任务超时/取消 | 中 | 中 | submit/poll 两段式，不依赖长连接 |
| 用户无 key 的首体验差 | 高 | 高 | 首启强制给一条零 key demo；内置引导"加一个 key 解锁什么" |
| AGPLv3 分发义务 | 确定 | 高 | 上架前决定开源或商用授权 |
| macOS 公证与沙箱 | 低 | 中 | W6 提前一周跑一次完整签发流程 |

## 7. 不在本期范围

- Windows / Linux 打包（架构同构，但签名与 webview 差异需单独排期）
- 账号体系与云端渲染（体积优化到 40 MB 档才需要）
- 多项目管理与团队协作
