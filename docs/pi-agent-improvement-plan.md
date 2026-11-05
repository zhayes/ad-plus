# Ad+ / Pi agent 改进实施计划（P0–P2）

> **路径说明（2026-11 拆分后）**：本文写于 Ad+ 独立成仓之前。当前布局为
> `~/AdPlus/`（Ad+ 代码：`adplus/`、`app/`、`frontend/`）+ `vendor/openmontage/`（上游 submodule）。
> 文中 `om_mcp.py` 现位于 `adplus/mcp/__main__.py`，`lib/{agent_bridge,quote,jobs}.py` 现位于 `adplus/`，
> `app/ui/*.html` 已由 `frontend/` 的 Solid 界面取代。


> 目标：把 Ad+ 从「能生成视频的 demo」推进到「能接单交付的工具」。
> 范围：报价与人工闸门（P0）、低成本预览（P1）、渲染作业化（P2）。
> 不在本计划内：品牌包、合规体检、A/B 变体（列为 Phase 3，见文末）。
>
> **状态：P0 / P1 / P2 已全部实施并验证（M1–M5 完成）。** 实现细节见
> 下方各节，验收证据见 `docs/mvp-verification.md` §2.16–2.19。

---

## 0. 现状盘点：不要重复造轮子

计划前先把仓库里**已有但没接上**的东西列清楚，后面所有方案都基于复用：

| 已有能力 | 位置 | 现状 |
|---|---|---|
| 成本治理（估算 / 预留 / 审批 / 退款 / 预算模式） | `tools/cost_tracker.py`（含 `ApprovalRequiredError`、`BudgetMode`） | **有实现、有单测，但没有任何地方实例化** |
| 单工具成本估算 | `tools/base_tool.py::estimate_cost()` / `estimate_runtime()` | **92 个工具已实现**，调用链里没被用于"先报价" |
| 供应商价目表 | `tools/atlas_models.py`（`cost_per_second` / `cost_per_image`）等 | 分散在各 provider 模块，未汇总 |
| 阶段检查点 | `lib/checkpoint.py`、`projects/<id>/checkpoint_<stage>.json` | 有写入/读取；GUI 无审批交互 |
| 后台作业 | `om_mcp._start_job` / `_job_view`（`om_submit` 用） | **有内存版作业**（状态/耗时），但无进度、无取消、无持久化；`om_render` 仍是同步阻塞 |
| 快照能力 | `tools/video/hyperframes_compose.py` 的 `snapshots: true` → `--snapshots` | 有，未用于"给客户看的分镜" |
| 会话常驻 | `SessionHub`（本次已实现） | 页面跳转不丢进度；但进程退出丢作业 |

**结论**：P0 真正要写的是「把 `CostTracker` 接进 MCP facade + 让 UI 能批准」，
而不是重新设计一套计费。P2 真正要写的是「把 `om_render` 从同步改成作业」，
而不是重写渲染。

---

## 1. 架构决策：用文件系统做进程间契约

三个进程：**Pi（MCP 子进程）**、**后端（FastAPI）**、**UI（WebView）**。
MCP 工具是同步阻塞调用，无法直接给 UI 推事件；后端也拿不到 Pi 的内部状态。

因此统一约定：**MCP 写文件 → 后端读文件并广播 → UI 渲染 → UI 写文件 → MCP 轮询读取**。

```
projects/<id>/
  quotes/<quote_id>.json        # 报价单（MCP 写，UI 读，UI 写决策）
  approvals/<approval_id>.json  # 闸门（同上）
  jobs/<job_id>.json            # 渲染作业（MCP 写进度，UI 读，UI 写 cancel）
```

好处：进程崩溃/重开不丢状态；UI 刷新能恢复；实现简单，无额外 IPC 依赖。
写入一律 **tmp 文件 + `os.replace()`** 原子替换，避免读到半个 JSON。

---

## 2. P0：报价 + 人工闸门（预计 2–3 天）

### 2.1 用户故事

> 我说「做一条 15 秒竖屏」，agent 先给我一张单子：**几个镜头、用哪个供应商、预计 $0.42 / 8 分钟**。
> 我点「开工」它才动手；跑到分镜阶段它停下来，把分镜图摆给我，我点「通过」或「换一版」。

### 2.2 服务端（MCP）

**新增工具 `om_quote`**（`adplus/mcp/__main__.py`）

```python
om_quote(
    project_id: str,
    shots: list[dict],       # [{kind:"image"|"video"|"tts"|"music", provider, model, count, duration_s}]
    render: dict | None,     # {composition_frames:int, fps:int} 用于估渲染时长
    wait: bool = True,       # 阻塞等待人工决策
    timeout_seconds: int = 900,
) -> dict
```

实现要点：
1. 每个 shot 通过 `_registry().get(tool_name)` 拿到工具实例，调用 `estimate_cost(inputs)` + `estimate_runtime(inputs)`；
2. 汇总成 `line_items[]` + `total_usd` + `eta_seconds`；
3. 用 `CostTracker` 记 `estimate()`，`mode=cap` 时 `reserve()`；
4. 写 `quotes/<id>.json`（status=`pending`），随后**轮询**该文件等待 `decision`；
5. 返回 `{"approved": bool, "quote": {...}, "reason": "user_rejected"|"timeout"}`。

**新增工具 `om_gate`**（阶段闸门，复用同一套轮询）

```python
om_gate(project_id, stage="scene_plan", artifacts=[...], note="...", timeout_seconds=900) -> dict
```
写 `approvals/<id>.json`，等待 `{decision: "approve"|"reject", comment: "..."}`；
被 reject 时把 comment 原样返回，agent 据此改方案（而不是硬着头皮往下做）。

**`om_start_project` / `om_write_checkpoint`** 增加 `require_gate: bool` 选项：
写 checkpoint 前自动调用 `om_gate`，保证"阶段完成必须有人看过"。

### 2.3 后端（`app/settings_server.py`）

| 端点 | 作用 |
|---|---|
| `GET /api/quotes?project_id=` | 列出待决策报价单 |
| `POST /api/quotes/{id}` | 写入 `{decision, comment}`，原子替换文件 |
| `GET /api/approvals?project_id=` | 同上，闸门 |
| `POST /api/approvals/{id}` | 同上 |
| `WS /ws/chat` 增加广播 | 后台线程 1s 扫描 `quotes/`、`approvals/`，新文件即推 `{"type":"quote_pending"|"gate_pending", ...}` |

### 2.4 前端（`frontend/src/routes/Workspace.tsx`（旧版 workspace.html 已删除））

**报价卡**（聊天流内，位于用户消息之后）：

```
┌ 预计 $0.42 · 约 8 分钟 ─────────────────┐
│ 4 张图  $0.18   fal/flux               │
│ 2 段视频 $0.20  kling/1.6              │
│ 1 段配音 $0.04  elevenlabs             │
│ [开工]  [改方案]                        │
└────────────────────────────────────────┘
```

**闸门卡**：分镜缩略图横排（3–6 张，点击放大）+ `[通过]` `[打回，说明原因]`。

交互细节：
- 决策按钮 POST 后卡片变灰、显示"已通过/已打回"；
- 打回时弹一个行内输入框（不用 `window.prompt`，app 内被禁用）；
- 轮询兜底：若 WS 断连，每 3s `GET /api/quotes`。

### 2.5 验收

- [ ] 单测：`om_quote` 对有价工具返回非零、对免费工具返回 0；超时返回 `approved=false, reason=timeout`
- [ ] 端到端：真实对话触发报价卡 → 点开工 → agent 继续；点打回 → agent 收到 comment 并换方案
- [ ] 崩溃恢复：报价单 pending 时重启 app，卡片仍在、仍可决策
- [ ] 成本准确度：与真实账单对比误差 < 30%（估算本就是区间，UI 显示 `$0.35–0.50`）

---

## 3. P1：低成本预览（预计 2 天）

### 3.1 用户故事

> 渲 8 分钟前，我先看到 6 张关键帧。方向不对，30 秒就能否掉。

### 3.2 方案：三级预览，逐级加钱

| 级别 | 产物 | 做法 | 耗时 |
|---|---|---|---|
| L1 静态故事板 | 6 张关键帧 | Remotion `still`（atelier 合成）或 `hyperframes_compose(snapshots=true)` | 20–40s |
| L2 动态分镜 | 480p / 无特效 | `remotion render --scale 0.5` 或低码率渲染 | 1–3 min |
| L3 成片 | 1080×1920 | 现有 `om_render` | 5–20 min |

**新增工具 `om_preview`**

```python
om_preview(project_id, mode="stills", frames=[0,15,30,45], scale=1.0) -> {
  "images": ["projects/x/previews/frame-0000.png", ...],
  "contact_sheet": "projects/x/previews/sheet.png"
}
```
- atelier（Remotion）项目：逐帧 `npx remotion still <entry> <comp> out.png --frame=N`
- HyperFrames 项目：`hyperframes_compose(snapshots=true)`，回收 snapshots 目录
- 用 Pillow 拼一张 2×3 contact sheet（UI 一屏看全）

### 3.3 前端

- 聊天内"预览卡"：6 张缩略图 + `[换一版]` `[按这个渲]`
- 点击单图 → 现有 lightbox（已实现）
- 「按这个渲」直接把 preview 决策写进 `approvals/`，agent 继续

### 3.4 验收

- [ ] 30 秒内出 6 张图（本地 3D/HyperFrames 用例）
- [ ] contact sheet 可在聊天内展示，点击可放大
- [ ] 预览失败（合成不存在）时降级为文案 storyboard，不死锁

---

## 4. P2：渲染作业化（预计 3 天）

### 4.1 用户故事

> 渲染放后台，我能一边等一边改下一版；关掉窗口再打开，进度还在。

### 4.2 后端/MCP 改造

**`om_render` 改为异步（复用并升级现有 `_start_job`）**

现有 `_start_job` 已经是"后台线程 + 内存状态 + `om_job` 轮询"，
缺的是：进度、取消、持久化、重启恢复。改造点如下：

```python
om_render(..., wait=False) -> {"job_id": "...", "status": "running", "output": "..."}
om_job(job_id) -> {"status": "running|done|failed|cancelled", "progress": 0.62, "eta_seconds": 180, ...}
```

- MCP 内启动 `subprocess.Popen`，后台线程读 `stderr`；
- 解析 Remotion 的 `Rendered 123/450` → 更新 `jobs/<id>.json` 的 `progress`；
- 解析不到就从输出文件大小/帧数兜底估算；
- 进程组 `start_new_session=True`，取消时 `killpg`；
- 作业记录含 `pid`、`started_at`、`log_tail`（最后 20 行）。

**取消**：`POST /api/jobs/{id}/cancel`（后端只写 `cancel_requested: true` 到文件，MCP 轮询到后 killpg —— 保持单一写入者）。

### 4.3 前端

右栏新增「任务」分区：

```
渲染中  62%  ▓▓▓▓▓▓░░░░  3:12 / 8:00   [取消]
已完成  lighthouse-9x16.mp4  8.4 MB    [播放] [目录]
```

- 进度条 + 已用/预计时间
- 完成后自动刷新「产物」
- 聊天里同名作业只显示一行紧凑状态（不刷屏）

### 4.4 验收

- [ ] 渲染中切到设置页再回来，进度不丢（后端读文件，不依赖 WS）
- [ ] 取消后进程真的结束（`ps` 验证无残留），作业状态 `cancelled`
- [ ] 应用重启后，`running` 作业被标记为 `interrupted` 并可重跑
- [ ] 同时跑 2 个作业，UI 两条进度互不干扰

---

## 5. 数据契约（新增文件）

```jsonc
// projects/<id>/quotes/<id>.json
{
  "id": "q_20261104_1", "project_id": "x", "status": "pending|approved|rejected|timeout",
  "currency": "USD", "total_usd": 0.42, "low_usd": 0.35, "high_usd": 0.52,
  "eta_seconds": 480,
  "line_items": [{"tool": "fal_image", "label": "4 张图", "usd": 0.18, "seconds": 40}],
  "decision": {"by": "user", "at": "…", "comment": ""}
}

// projects/<id>/approvals/<id>.json
{"id":"a_1","project_id":"x","stage":"scene_plan","status":"pending",
 "artifacts":["projects/x/artifacts/scene_plan.json"],"previews":["…/previews/sheet.png"],
 "decision":{"by":"user","at":"…","comment":"第二个镜头太快"}}

// projects/<id>/jobs/<id>.json
{"id":"j_1","project_id":"x","kind":"render","status":"running",
 "progress":0.62,"frames_done":279,"frames_total":450,
 "started_at":"…","pid":1234,"output":"…mp4","log_tail":["…"],"cancel_requested":false}
```

全部加进 `schemas/` 并在写入前校验（仓库已有 jsonschema 用法，见 `lib/checkpoint.py`）。

---

## 6. 里程碑

| 里程碑 | 内容 | 工期 | 可演示的结果 |
|---|---|---|---|
| **M1** | 报价单 + 开工闸门 + 后端 4 个端点 + 2 张卡片 | 2–3 天 | 对话里出报价，点开工才花钱 |
| **M2** | 阶段闸门（分镜/成片）+ 打回意见回流 | +1 天 | agent 会"停下来等人" |
| **M3** | 静态故事板 + contact sheet | 2 天 | 30 秒看到 6 张关键帧 |
| **M4** | 异步渲染 + 进度 + 取消 | 2 天 | 右栏进度条，可取消 |
| **M5** | 崩溃恢复 + 重启后作业重跑 | 1 天 | 关掉再开，状态一致 |

总计 **8–10 个工作日**（单人）。

---

## 7. 风险与兜底

| 风险 | 影响 | 兜底 |
|---|---|---|
| 阻塞式工具让 agent 长时间空转 | 用户离开 → 会话卡住 | 默认 15 分钟超时，返回 `approved=false, reason=timeout`，agent 主动收尾 |
| 报价与实际账单偏差大 | 客户信任受损 | 显示区间（low–high），并记录实际值进 `cost_log` 用于校准 |
| Remotion 进度格式变化 | 进度条卡住 | 解析失败时用"输出文件大小 / 预计字节"兜底，并显示"估算中" |
| 多进程同时写同一 JSON | 数据损坏 | 单写者原则 + tmp+`os.replace`；读方只读 |
| 取消不彻底 | 残留 node 进程吃 CPU | `start_new_session=True` + `killpg`，后端 30s 后校验 pid 是否消失 |
| 预览与成片不一致 | 审批过的分镜和最终不同 | 预览与成片必须同一 composition/参数，仅 `scale` 与特效不同 |

---

## 8. 测试计划

- **单测**：quote 计算（有价/免费/超时）、approval 轮询、job 状态机（running→done/cancelled/interrupted）
- **契约测试**：三个 JSON schema 的合法/非法样本
- **端到端（CDP 驱动）**：真实对话 → 报价卡 → 点开工 → 分镜闸门 → 打回 → agent 修改 → 通过 → 渲染作业 → 进度 → 完成
- **回归**：现有 `pytest tests/` 全绿；MCP 11 个旧工具签名不变（只加参数，默认值保持兼容）

---

## 9. Phase 3（暂不做，先记录）

1. **品牌包**（Brand Kit）：主色/辅色/字体/logo 安全区/口播语气/免责声明，按品牌注入
2. **合规体检**：广告法违禁词、平台规格（时长/画幅/码率/响度 -14 LUFS）、字幕溢出
3. **素材台账**：来源与授权，导出交付清单
4. **A/B 变体**：一稿多钩子批量渲染与对比
5. **模型分层**：规划用便宜模型、文案用强模型；长会话开启 Pi compaction

---

## 10. 需要你拍板的三件事

1. **报价粒度**：按"镜头数 × 供应商"报（准，但需要 agent 先出分镜），还是按"经验公式"报（快，误差大）？建议：**先出分镜再报价**，把报价放在 `scene_plan` 之后。
2. **预算策略**：`CostTracker` 的模式是 `OBSERVE / WARN / CAP`（没有 APPROVE）。
   审批由两个阈值控制：`single_action_approval_usd`（单笔超过即要人确认，建议 **0.50**）
   和 `require_approval_for_new_paid_tool`（首次用某个付费工具要确认，建议 **true**）。
   建议：模式 `CAP`，预算默认 **$10/项目**，预留 10%。
3. **作业并发**：本机建议 **1 个渲染 + 1 个预览** 并发上限，避免抢 CPU 导致渲染变慢。

---

## 11. M1 任务分解（可直接开工）

按顺序做，每项都可独立验收；前 6 项完成即可演示"报价 → 批准 → 继续"。

| # | 任务 | 文件 | 估时 | 完成标准 |
|---|---|---|---|---|
| 1 | 定义三类 JSON schema | `schemas/agent/quote.schema.json`、`approval.schema.json`、`job.schema.json`（新增） | 2h | 合法/非法样本各有单测 |
| 2 | 原子读写工具函数 | `adplus/agent_bridge.py`（新增）：`write_record()` / `read_record()` / `poll_decision()` | 2h | tmp+`os.replace`；并发写不损坏 |
| 3 | 报价聚合器 | `adplus/quote.py`（新增）：输入 shots → 调 92 个工具的 `estimate_cost()`，产出 line_items + 区间 | 4h | 对有价/免费/未知工具分别有测试 |
| 4 | `om_quote` MCP 工具 | `adplus/mcp/__main__.py`：注册 + 实现（写 quote、轮询决策、超时） | 4h | `pi -p` 能调用并返回 `approved` |
| 5 | 后端报价端点 + 广播 | `app/settings_server.py`：`GET/POST /api/quotes`、扫描线程、WS 事件 | 4h | curl 可读可写；WS 收到 `quote_pending` |
| 6 | 报价卡 UI | `frontend/src/routes/Workspace.tsx`（旧版 workspace.html 已删除）：卡片组件 + 批准/打回 + 状态灰化 | 6h | CDP 驱动点批准后 agent 继续 |
| 7 | `om_gate` + checkpoint 联动 | `adplus/mcp/__main__.py`：`om_gate`、`require_gate` 参数 | 3h | 分镜阶段停下来等人 |
| 8 | 闸门卡 UI（缩略图 + 打回意见） | `frontend/src/routes/Workspace.tsx`（旧版 workspace.html 已删除） | 4h | 打回意见原样进 agent 上下文 |
| 9 | 端到端脚本 | `scripts/agent_gate_e2e.py`（新增，CDP 驱动） | 3h | 一条命令跑通全流程 |
| 10 | 文档与默认值 | `docs/`、`app/README.md` | 1h | 默认预算 $10 / 单笔阈值 $0.50 写清 |

**M1 合计约 33 小时（4–5 个工作日，含调试）。** 若只做最小演示（1、2、4、5、6 项），
约 18 小时，可以先拿到"报价 → 开工"的闭环，闸门留到 M2。

### M1 的验收脚本（人工可复现）

```
1. 新对话 → "做一条 15 秒竖屏，产品是咖啡杯"
2. 期望：聊天出现报价卡（$x.xx–$y.yy、约 N 分钟、按供应商分行）
3. 点「开工」→ agent 继续往下做；点「改方案」→ agent 收到意见并重出方案
4. 期间关掉窗口再打开 → 报价卡仍在（证明文件状态持久）
5. 15 分钟不操作 → 卡片变「已超时」，agent 主动收尾（不无限等待）
```
