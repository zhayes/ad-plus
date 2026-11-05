# MCP 探测结果（W1 第一步）

> **路径说明（2026-11 拆分后）**：本文写于 Ad+ 独立成仓之前。当前布局为
> `~/AdPlus/`（Ad+ 代码：`adplus/`、`app/`、`frontend/`）+ `vendor/openmontage/`（上游 submodule）。
> 文中 `om_mcp.py` 现位于 `adplus/mcp/__main__.py`，`lib/{agent_bridge,quote,jobs}.py` 现位于 `adplus/`，
> `app/ui/*.html` 已由 `frontend/` 的 Solid 界面取代。


日期：2026-11-04 · 环境：macOS arm64 / Python 3.11.15 / mcp SDK 2.3.0 / Remotion 4.0.484 / ffmpeg 9.0.1

结论先说：**OpenMontage 的 MCP 桥打通了，宿主端（Pi）无法验证。**

## 1. 已完成并验证

新增两个文件：

- [`adplus/mcp/__main__.py`](../adplus/mcp/__main__.py) — MCP stdio server，14 个门面工具
- [`scripts/om_mcp_probe.py`](../scripts/om_mcp_probe.py) — 按真实宿主顺序驱动的探测脚本

探测输出（`/tmp/probe.log`）：

| 检查项 | 结果 |
|---|---|
| `initialize` 握手 | ✅ 协议 `2025-11-25`，server `openmontage@0.1.0`，启动 2.9 s |
| `tools/list` | ✅ 9 个工具 |
| `om_capabilities` | ✅ 返回运行时有/无与各能力 `configured/total` |
| `om_list_tools(capability=video_post)` | ✅ 10 个工具 + 状态 |
| `om_start_project` | ✅ 建出 `projects/mcp-probe/{artifacts,assets,renders}` |
| `om_call_tool`（真实执行） | ✅ `video_trimmer.cut` 出片，产物落盘 |
| `om_submit` + `om_job`（异步） | ✅ 18.5 s 任务、10 次轮询、状态 `succeeded` |
| 错误路径 | ✅ 未知工具返回 `is_error: true` + 可读文案 |
| `om_artifacts` | ✅ 列出相对路径与字节数 |

**关键结论：门面工具 + submit/poll 这套设计成立。** 慢工具不会掐死宿主连接，客户端按秒轮询即可，不需要依赖 MCP 的长超时或任务协议。

## 2. 推翻的旧结论

**HyperFrames 其实是可用的。** 之前判定 "不可用" 完全是因为沙箱下 `~/.npm` 不可写导致 `npm view` 失败；放开文件权限后：

```
render_engines: {'ffmpeg': True, 'remotion': True, 'hyperframes': True}
hyperframes: npm 0.9.10, CLI doctor = ok
```

对计划的影响：**W3 的渲染运行时选项从 2 个变回 3 个**，产品里可以按提案阶段让用户二选一，不需要“先证明 HyperFrames 能装”。

## 3. 发现的真实缺陷（重要）

`video_trimmer` 的 `cut` 在默认参数下会**静默产出没有视频轨的文件**，且 `success: true`：

```
operation=cut, start_seconds=0, end_seconds=2, codec=copy(默认)
→ 输出只有 aac 音频，80 KB，无 h264 流
```

用裸 ffmpeg 复现，确认是参数组合问题而非工具包装问题：

```bash
ffmpeg -i demo.mp4 -ss 0 -to 2 -c copy out.mp4   # → 只有音频
ffmpeg -i demo.mp4 -ss 3 -to 5 -c copy out.mp4   # → 正常（音视频都有）
```

规避：`codec: "libx264"`（重编码）后输出正常（实测 2.000 s，含音视频）。

**对计划的直接影响**：`om_mcp` 必须加一层产物校验 —— 任何返回 `artifacts` 的调用，用 ffprobe 检查流是否存在、时长是否合理，不通过就把 `success` 降级为 `false` 并附原因。否则 agent 会拿着“成功”的空壳文件继续往下渲染，用户最后拿到一条黑屏或纯音频的广告。

## 4. Pi 1.5.0 验证结果（全局安装后补测）

`pi` 1.5.0 位于 `~/.local/bin/pi`，包名 `@earendil-works/pi-coding-agent`（注意：不是 `@mariozechner/*`，本地随包带完整 `docs/`）。

| 项 | 结果 |
|---|---|
| 内置 MCP | ✅ 存在 `--no-mcp` 开关与 `pi mcp` 子命令，证实 MCP 是核心能力 |
| 注册我们的 server | ✅ `pi mcp add openmontage --cwd … -- python -m om_mcp` |
| 连接结果 | ✅ `openmontage: connected, 9 tools (codemode, global)` |
| 工具命名 | ✅ `mcp__<server>__<tool>`（非字母数字下划线替换为 `_`；`-` 与 `_` 视为同一 server 名） |
| 超时字段 | ✅ `mcp.json` 支持 `timeout`（秒，默认 60），写入 `900` 后重连正常；**进度通知会重置计时** |
| 暴露模式 | ✅ `codemode`(默认) / `deferred` / `direct` / `hidden`，另有 `toolExposure` 逐工具覆盖 |
| 技能发现 | ✅ `.agents/skills` 在当前目录或祖先目录会被发现，但**受 project trust 限制**（需 `--approve` 或信任弹窗）；本仓库 91 个 `SKILL.md` |
| 模型凭据 | ❌ `auth.json` 为 `{}`，无 provider 环境变量 → `pi --list-models` 报 "No models available" |

**由此推翻的第二条结论：60 秒超时不是问题。**
- `codemode` 脚本自带 `// @options: {"timeout_ms": …}`，默认不限时；
- `direct` 直调走 `timeout`（默认 60 s），但进度通知会重置，且我们的 `om_submit` 立即返回 job id。

### 暴露模式怎么选

默认的 `codemode` 意味着 **9 个工具根本不声明给模型**，模型要靠 `searchTools()` / `describeNamespace()` / `ALL_TOOLS` 发现，并写 JS 脚本调用（QuickJS 沙箱）。

| 方案 | 优点 | 代价 |
|---|---|---|
| `direct`（建议 MVP） | 9 个工具直接进工具表，行为可预测，好调试 | 每次请求都带 9 个 schema（很小） |
| `codemode`（默认） | 模型可在一个脚本里串起"查能力 → 生成 → 轮询 → 合成"，大结果不进上下文 | 模型要会写 JS；失败面更隐蔽 |

建议 MVP 先用 `direct`，把 `codemode` 当成后续优化项，而不是默认就吃它的复杂度。

## 5. W1 端到端验收：通过

模型：`deepseek/deepseek-flash`（复用现有 `DEEPSEEK_API_KEY`，一次性会话，`--no-session --approve`）。

**任务**：15 秒竖屏 1080×1920 产品广告，纯文字与图形，不用素材、不用生成图、无旁白。

**结果**：`projects/echo-ad/renders/echo-ad.mp4` —— 1080×1920 / 30 fps / **450 帧 / 15.000 s** / h264 / 1.6 MB / 无音轨（刻意的：无可用音乐源，静音 AAC 轨被丢弃）。

| 指标 | 实测 |
|---|---|
| 端到端墙钟时间 | **6 分 47 秒**（14:26:46 建项目 → 14:33:33 出片） |
| 其中 Remotion 渲染 | 65 s（16 s 素材，`renderer_family: product-reveal`） |
| 工具调用 | `video_compose` ×2、`video_trimmer` ×2 |
| 产物 | 9 个 canonical artifact + 6 个 checkpoint + `decision_log.json`（7 条决策）+ `events.jsonl` |

模型的自我组织远超预期：它自己选了 `animation` 流水线、写了全部阶段产物、做了渲染后抽帧自审（4/4 帧、无黑帧）、并把"为什么丢弃静音轨"写进了报告。

### 验收暴露的 4 个真实缺口

1. **缺 `om_write_checkpoint`。** 门面只有读 checkpoint 的工具，模型只好自己写 `projects/echo-ad/.build/write_checkpoints.py` 再执行 —— 这是绕过契约，必须补写工具，否则每个宿主都要重新发明一遍。
2. **`edit_decisions` 的 schema 与渲染器冲突。** 该 artifact 是 `additionalProperties: false`，拒收 `type`/`text` 字段，而 Remotion 渲染器恰好读这两个字段。模型被迫把真正的 scene payload 放进非规范的 `composer_payload.json`，并在 `metadata.type_payload_gap` 里说明。**这是仓库级契约 bug，不是模型取巧。**
3. **research 阶段无法完成。** 流水线要求 `web_search`，但 MCP 面没有暴露任何检索工具，模型只能降级为“读本地源码 + 不做外部断言”，并写进 `metadata.not_done`。要么把检索能力挂进门面，要么在提案阶段就允许跳过。
4. **产物没有机器校验。** 这次靠模型自觉抽帧检查；但结合第 3 节那个 `video_trimmer` 静默丢视频轨的缺陷，必须由 `om_mcp` 做 ffprobe 校验，而不是指望模型。

### 结论

W1 的核心假设**成立**：MCP 门面 + Pi 1.5 + `.agents/skills` 能让模型在无人干预下跑完整条流水线，产出一条合规的竖屏广告。剩下的都是工程补齐，不是方向问题。

## 6. 工程细节备忘（写代码时会再遇到）

MCP Python SDK 2.x 与 1.x 差异较大，`adplus/mcp/__main__.py` 已按 2.x 写：

- `FastMCP` 已改名为 `MCPServer`（`mcp.server.mcpserver`）
- 低层 `Server` 用 `add_request_handler(method, params_type, handler)`，handler 签名是 `(ctx, params)`
- **`params_type` 必须传 `CallToolRequestParams` / `PaginatedRequestParams`**，传 `CallToolRequest` 会因缺少必填字段被拒（`Invalid request parameters`）
- 模型字段是 snake_case（`is_error`、`server_info`、`protocol_version`），对外 JSON 仍是 camelCase

## 7. 下一步（W1 收尾，全部不依赖外部条件）

| 优先级 | 任务 | 估时 |
|---|---|---|
| P0 | 门面加 `om_write_checkpoint`（阶段产物 + 状态 + 人类审批位） | 0.5 天 |
| P0 | `om_call_tool` / `om_submit` 返回前 ffprobe 校验产物，失败即降级 `success=false` | 0.5 天 |
| P1 | 修 `edit_decisions` schema 与 Remotion 渲染器的字段冲突（仓库级） | 0.5 天 |
| P1 | 读 checkpoint 时回填 `pipeline_type`，避免模型自己猜阶段顺序 | 0.5 天 |
| P2 | 决定检索能力的归属：门面挂 `om_search`，还是允许 research 阶段显式跳过 | 决策 |
| P2 | `codemode` 与 `direct` 同条件对比（同一条 brief 各跑一次） | 1 天 |

W2（设置页）在这 6 项之后启动 —— 尤其 P0 两项，它们决定后面所有调用是否可信。
