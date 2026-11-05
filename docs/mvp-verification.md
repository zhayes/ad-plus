# 桌面 MVP 验证报告

> **路径说明（2026-11 拆分后）**：本文写于 Ad+ 独立成仓之前。当前布局为
> `~/AdPlus/`（Ad+ 代码：`adplus/`、`app/`、`frontend/`）+ `vendor/openmontage/`（上游 submodule）。
> 文中 `om_mcp.py` 现位于 `adplus/mcp/__main__.py`，`lib/{agent_bridge,quote,jobs}.py` 现位于 `adplus/`，
> `app/ui/*.html` 已由 `frontend/` 的 Solid 界面取代。


日期：2026-11-04 · 环境：macOS arm64 · Pi 1.5.0 · Python 3.11.15 · Remotion 4.0.484 · ffmpeg 9.0.1

## 1. 交付物

| 交付 | 位置 |
|---|---|
| 可双击的桌面应用 | `dist/OpenMontage.app`（**Tauri 2 壳**，6.7 MB，`scripts/build_app.sh` 生成） |
| 可分发包 | `dist/OpenMontage-0.1.0-mac.zip`（14 MB，含 `install.command` 引导安装） |
| Tauri 工程 | `app/desktop/`（`src/main.rs`，5.4 MB release 二进制） |
| 桌面后端（设置 + 对话 + 媒体） | `app/settings_server.py`、`app/main.py` |
| 密钥存储 | `app/secrets_store.py`（钥匙串 + `0600` 镜像） |
| 能力清单（从注册表派生） | `app/capabilities.py` |
| Pi RPC 桥 | `app/pi_bridge.py` |
| UI | `frontend/src/routes/Settings.tsx` |
| MCP 门面（11 个工具，含 `om_render`） | `adplus/mcp/__main__.py` |
| 指标采集 | `scripts/collect_run_metrics.py` |

启动：`open dist/OpenMontage.app`，或 `.venv/bin/python -m app.main`。冷启动到 `/api/health` 可用实测 **4 秒**。

## 2. 功能验证（逐项实测）

| # | 验证项 | 方法 | 结果 |
|---|---|---|---|
| 1 | 应用启动 | `open dist/OpenMontage.app` → `curl /api/health` | ✅ 4 s 内 `{"ok":true,"version":"0.1.0"}` |
| 1b | Tauri 壳拉起后端 | 壳内 `Command::spawn` + 健康轮询 | ✅ 自动起 `python -u -m app.main --no-window --parent-pid <pid>` |
| 1c | 退出回收子进程 | `osascript ... quit` 后查进程 | ✅ 后端随之退出，无孤儿进程 |
| 1d | 父进程死亡兜底 | `kill -TERM` 壳后观察 | ✅ `--parent-pid` 看门狗 2 s 内退出后端 |
| 1e | 可分发包 | `make_dist.sh` → 解压校验 | ✅ 14 MB，2666 文件，`install.command` 可执行且语法通过 |
| 2 | 后端复用 | 已有一个后端时再次启动 | ✅ 走 `existing_backend()`，只开窗口不重复起服务 |
| 3 | 设置页渲染 | 原生 webview 内 `evaluate_js` | ✅ 标题、7 个能力 chip、10 个模型 provider、23 个媒体 key |
| 4 | 保存 key → 能力变化 | `POST /api/keys {FAL_KEY}` | ✅ 图像 `0/29 → 9/29`，视频 `0/33 → 9/33`，语音 `0/18 → 1/18` |
| 5 | 钥匙串写入/读取 | `security find-generic-password -s openmontage` | ✅ 命中；镜像文件 `-rw-------` |
| 6 | 删除 key → 回退 | `DELETE /api/keys/FAL_KEY` | ✅ 回到 `0/29`（首版有 stale env bug，已修） |
| 7 | 密钥注入到工具进程 | `OPENMONTAGE_SECRETS_FILE` → `om_capabilities` | ✅ 镜像里的 key 生效，MCP 进程看到 `9/29` |
| 8 | MCP 门面 | `scripts/om_mcp_probe.py` | ✅ 初始化 2.9 s、10 个工具、真实调用、submit/poll、错误路径 |
| 9 | checkpoint 写入 | `om_write_checkpoint` | ✅ 写出 `checkpoint_compose.json`，状态与阶段正确 |
| 10 | 产物校验 | 坏切片（`copy` + start=0）与好切片对比 | ✅ 坏的 `success:false` + `no video stream`，好的通过 |
| 11 | edit_decisions schema | 真实产物 / 纯场景 cut / 孤儿 cut | ✅ 分别 通过 / 通过 / 拒绝 |
| 12 | 对话链路 | WS → `pi --mode rpc` → 模型 → `agent_settled` | ✅ 回复 “OK”，正常 settle |
| 13 | 费用遥测 | 每轮 assistant 结束上报 usage | ✅ `input 3065 / output 144 / total 35209 / $0.00128` |
| 14 | 成片预览 | `/api/media` 内联播放 + 穿越防护 | ✅ 200（1.6 MB）/ 403 / 404 |
| 15 | 最近成片列表 | `GET /api/projects` | ✅ 列出项目与渲染文件 |
| 16 | 暴露方式切换 | `POST /api/pi/integration` | ✅ direct ⇄ codemode 写入 `~/.pi/agent/mcp.json` |
| 17 | **渲染收口** | `om_render` 渲染 `type0-ad` 的手写合成 | ✅ 15.0 s 出 600 帧；超时预算 4 s 时被杀死并返回 `rendered:false` |
| 18 | 会话规则注入 | `--append-system-prompt app/agent-hints.md` | ✅ 模型自述「`om_render` 渲染、`om_write_checkpoint` 推进阶段」 |
| 19 | **应用内对话真正调到 MCP** | WebSocket → Pi RPC → 工具 | ✅ 实际调用 `mcp__openmontage__om_capabilities`，答案正确（图像 0/29） |

## 2.5 界面改版验证（P1 / P2 / P2.5）

| # | 验证项 | 方法 | 结果 |
|---|---|---|---|
| 20 | 未配模型不可进工作台 | `curl /` | ✅ `307 → /onboarding` |
| 21 | 启动页与引导页可访问 | `curl /splash /onboarding` | ✅ 均 200 |
| 22 | Tauri 先显示启动页 | 壳内 `WebviewUrl::App` + 健康后 `navigate` | ✅ 窗口先出 splash，后端就绪后跳转 |
| 23 | 工作台顶栏控件 | 真窗口内 DOM 查询 | ✅ 模型胶囊 `deepseek · deepseek-flash`、新对话/历史/设置齐全 |
| 24 | 面板折叠 | 点 `›` + `⌘\` | ✅ 侧栏 `display:none`，右侧手柄出现 |
| 25 | 历史抽屉 | 点时钟图标 | ✅ 打开并列出 1 条会话（标题取自首条用户消息） |
| 26 | 会话落盘 | `--session-dir` 下 `*.jsonl` | ✅ `2026-11-04T08-16-16-318Z_om-selftest1.jsonl` |
| 27 | 恢复会话 | 点抽屉条目 → `--session <path>` + `get_messages` | ✅ 历史回放（用户气泡 + 助手气泡），上下文续跑 |
| 28 | 新对话 | 点「新对话」 | ✅ 消息清空、新 session、输入框可用 |

## 2.6 对话体验修复

| # | 问题 | 修法 | 验证 |
|---|---|---|---|
| 29 | Markdown 没渲染（`**`、`##`、表格原样显示） | 内置轻量渲染器（标题/粗体/行内码/列表/引用/代码块/**表格**），流式增量用 rAF 节流 | CDP 实测：`rawStars:false`、`strongs:2`、表格渲染为 `<table>` |
| 30 | 每次工具调用一张大卡，刷屏 | 连续工具调用合并成一行「已调用 N 个工具 · x.xs」，可点开看明细，完成自动收起 | `groups:1 rows:5 openGroups:0` |
| 31 | 生成中跳设置页，回来进度消失 | 服务端 `SessionHub`：一个会话一个 Pi 进程，断开只是取消订阅；页面重连 `attached` 并回放 `get_messages`；前端记住 `om.session` 自动续上 | 断 socket 后重连：`attached:true running:true`，仍收到 `read`/`bash` 工具事件；跳转设置再回来 session id 不变、消息仍在 |
| 32 | 流式光标残留 | 结束时取消待执行的 rAF 并重渲染 | `cursors:0` |

## 2.7 设置与顶部栏

| # | 需求 | 实现 | 验证 |
|---|---|---|---|
| 33 | 媒体 key 要写清是哪个厂商 | `capabilities.vendor_label()` 映射 + 兜底美化，标题显示厂商名，副行显示环境变量名与解锁工具数 | `/api/state` 返回 `Fal.ai / Atlas Cloud / Kling / 腾讯混元 TokenHub` |
| 34 | 顶部栏无效标题清除 | 移除顶栏的「最新项目标题」，只留 logo 与模型 | `{project:false, bar:"deepseek · deepseek-flash"}` |
| 35 | 运行中的会话要有 loading | 会话行渲染 `running` 时显示旋转指示；服务端 `/api/sessions` 附带 `running`（来自 SessionHub），前端 4s 轮询 + 自身运行时立即反馈 | 发消息后 1.5s：`spinners: 1` |
| 36 | 模型要能切换 | 点模型胶囊弹分组菜单（按 provider 分组、当前项打勾），切换时停掉旧 Pi 进程、以新模型续同一会话 | 切到 deepseek-v4-pro：胶囊更新 + 「已切换到 …，当前会话继续」 |

## 2.8 空态收敛

| # | 需求 | 实现 | 验证 |
|---|---|---|---|
| 37 | 没有选中/没有产出时右侧不该出现 | 右栏加 `idle` 态默认为空；首次工具调用（`markWork`）或已存在成片时才显示 | 空闲 `display:none`，跑工具后 `flex` |
| 38 | 没有产物时不要显示提示文案 | 删除「还没有成片 —— 让它做一条试试」与流水线占位 | 空态右栏无任何文案 |

## 2.9 打包后 key 明明正确却「列不出模型」

| 项 | 内容 |
|---|---|
| 现象 | 引导页粘贴正确 key，提示「保存了，但这个 key 没能列出任何模型」 |
| 真因 | `spawn_env(secrets_store.merged_env())` 里 `merged_env` 自带的 `PATH` 覆盖了刚补好的 PATH，`pi` 的 `#!/usr/bin/env node` 找不到 node，返回 `env: node: No such file or directory` |
| 影响面 | 不止设置页：`PiBridge` 同样调用该函数，Finder 启动的应用里**聊天也起不来** |
| 修法 | `spawn_env` 先合并 `extra`、最后写 PATH；启动时用钥匙串刷新镜像；`/api/pi/models` 为空时把 `pi` 的 stderr 一并返回，引导页直接显示真实原因 |
| 验证 | 最小化环境（`env -i PATH=/Users/chad/.local/bin:/usr/bin:/bin`）下 `_pi('--version')` → `1.5.0`；应用内 `/api/pi/models` → 2 个模型；聊天 → 「可以」 |

## 2.10 素材上传

| 项 | 内容 |
|---|---|
| 结论 | OpenMontage 支持「按素材生成」：`talking-head`（口播原片 → 转录 → 剪辑决策 → 字幕 → 混音 → 合成）、`clip-factory`（长内容切多条短视频），以及 `video_trimmer` / `auto_reframe` / `green_screen_composite` / `caption_burn` 等吃本地文件的工具 |
| 之前缺什么 | 应用里没有上传入口，只能让用户自己把文件放好再告诉 agent 路径 |
| 现在 | 输入框左侧回形针 + 拖拽到窗口 + 粘贴图片/视频；上传后落 `uploads/<日期>/<名字>-<hash>.<ext>`，发送时把**绝对路径**带进 prompt |
| 验证 | 上传 17 KB 测试片 → agent 用 bash 读取后回答「640×360，2.0 秒」，路径与文件一致 |

## 2.11 去掉默认寒暄

| 项 | 内容 |
|---|---|
| 改动 | 删除两处合成消息：「新对话已开始。说个想法…」与首屏「今天想做点什么？…」 |
| 连带 | 空对话时输入框改为垂直居中（无任何文案），发送后自动回落到底部 |
| 注意 | `renderHistory` 原先靠「删除第一条 ai 气泡」来清空，现改为只在有 `resumeNotice` 时移除，避免误删真实回复 |
| 验证 | 空态 `col.children.length = 0`、`body.chat-empty` 生效、`.stream` 隐藏 |

## 2.12 历史回显与分页

| 项 | 内容 |
|---|---|
| 现象 | 点开正在运行的会话，只显示「已连回上次的会话。」，历史不出来 |
| 真因 | 历史靠 Pi RPC 的 `get_messages`，而 Pi 在一轮未结束时**不会**处理新命令，回放请求被排队 |
| 修法 | 改为直接解析会话 JSONL（`GET /api/sessions/messages`），与 agent 是否忙碌无关；按 30 条一页倒序取，顶部「加载更多」 |
| 细节 | `before` 是"从哪条往前翻"的索引；插入历史时固定 anchor，否则批次会被反转 |
| 验证 | 40 条合成会话：首屏 30 条 + 按钮；点一次 → 40 条、按钮消失；顺序 11→19 递增；滚动保持在底部 |

## 2.13 顶栏与左栏控件归位

| 项 | 内容 |
|---|---|
| 需求 | 右栏开关挪到左上角与左栏开关并排；设置图标放左栏底部 |
| 实现 | 顶栏左上两个图标（左栏 / 右栏，右栏关闭时图标变暗）；右栏贴边悬浮手柄删除；设置齿轮移到左栏底部（`.rail-foot`） |
| 顺手修的 bug | 删除手柄 CSS 时留下一个孤立选择器 `body.panel-off `，把后面的 `.sidebar{display:flex}` 整条吞掉 —— 左栏退化成 block，底部设置按钮跑到列表下面 |
| 验证 | 右栏 `display` 由 none → flex、图标变亮；左栏 `display:flex`、齿轮贴底 |

## 2.14 产物面板面向普通用户

| 项 | 内容 |
|---|---|
| 问题 | 产物里混着 `world-runtime.js` / `index.html` / `world.json` 等工程文件，非技术用户看不懂 |
| 改法 | `/api/artifacts` 给每个文件打 `kind`（video/image/audio/doc/code）；面板默认只展示**视频 / 图片 / 音频**，工程文件收进「工程文件 N 个 · 显示」 |
| 呈现 | 视频/图片渲染成卡片（视频用首帧当封面 + ▶ 角标），点开灯箱内联播放；卡片上「目录」在 Finder 显示、「删除」二次确认后进废纸篓 |
| 验证 | 3D 世界会话：12 个文件 → 面板只出 6 张图片卡片，6 个代码文件折叠；视频卡片点开灯箱正常播放 |

## 2.15 执行过程改成一条时间线

| 项 | 内容 |
|---|---|
| 原状 | 思考是一块、工具卡片是另一块，两套视觉语言，回放时尤其乱 |
| 现模型 | 每个用户回合 = **一条时间线**，按发生顺序排列「思考 / 工具」步骤；答案文字在时间线下方独立呈现 |
| 步骤行 | 图标 + 类型徽标 + 摘要（思考取前 70 字，工具取名称）+ 耗时；点击展开详情（参数 + 输出），详情自带滚动 |
| 运行态 | 当前步骤图标脉冲、标题「执行中 · N 次工具」、时间线自动展开；结束后自动收起为「51 次思考 · 94 次工具」 |
| 溢出 | 时间线主体 `max-height:300px; overflow:auto`，长任务不会把答案顶走 |
| 回放 | 与实时共用同一套时间线组件，历史会话展开后与刚跑完的一致 |
| 详情位置 | 展开内容在步骤行**下方**、与类型徽标左对齐；整行可点，chevron 旋转 90° 表示展开 |
| 修复 | `.step` 与流水线阶段列表类名冲突（`display:flex`），导致行被压成 86px、标签截断；已用 `.tl .step{display:block}` 限定作用域 |

## 2.16 报价 + 人工闸门（P0）

| # | 验证项 | 方法 | 结果 |
|---|---|---|---|
| 39 | MCP 工具注册 | `_facade()` | 14 个（新增 `om_quote` / `om_gate` / `om_preview`） |
| 40 | schema 校验 | jsonschema 合法/非法样本 | 合法通过，非法（负数金额/未知状态）被拒 |
| 41 | 原子写入 | tmp + `os.replace` | 并发读不到半截 JSON |
| 42 | 阻塞与超时 | `wait_for_decision` 单测 | 批准 1.0s 返回；无响应 1.0s 落 `timeout` |
| 43 | 报价聚合 | `adplus/quote.py` | kling 给真价；fal 标「待询价」；本地工具 `free` |
| 44 | 真实 agent 调用 | 对话 → `om_quote` | agent 主动调用，卡片出现，API 批准后继续 |
| 45 | 闸门打回 | UI 点「打回」+ 意见 | 记录写 `rejected` + comment，agent 收到后改方案 |

## 2.17 低成本预览（P1）

| # | 验证项 | 方法 | 结果 |
|---|---|---|---|
| 46 | 关键帧 | `om_preview(xiaozhangben-ad, frames=[0,90,180])` | 25.9s 出 3 张 + contact sheet |
| 47 | 预览卡 | 聊天流 `showPreviewCard` | 3 图网格，点击进灯箱 |
| 48 | agent 串起来 | 对话要求「先预览再确认」 | agent 先 `om_preview` 再 `om_gate(previews=…)` |

## 2.18 渲染作业化（P2）

| # | 验证项 | 方法 | 结果 |
|---|---|---|---|
| 49 | 异步渲染 | `om_render(wait=false)` | 返回 job_id，状态落盘 |
| 50 | 进度 | 解析 `Rendered N/M` | 0→360 帧，UI 进度条 4%/11%/…/100% |
| 51 | 完成校验 | ffprobe + mtime | `done`，12.05s / 1.1 MB 文件有效 |
| 52 | 取消 | UI 点取消 | 5s 内 `cancelled`，进程已退出 |
| 53 | 取消不丢文件 | 末帧后才取消 | 输出新鲜且合法时判 `done`（不误杀） |
| 54 | 崩溃恢复 | 重启应用 | 进程已死的 `running` 作业 → `interrupted` |

## 2.19 实现期修掉的三个竞态

1. **进度覆盖取消标志**：runner 每秒全量写 job，会把后端写的 `cancel_requested` 冲掉 → `jobs.update()` 现在先从磁盘合并该字段。
2. **旧成片冒充新结果**：同一输出路径上一次的 mp4 让"取消后校验"误判成功 → 作业启动前删除目标文件，且要求 `mtime >= started`。
3. **Popen 失败留死作业**：进程起不来时线程静默退出、作业永远 `running` → 整个启动段包 try/except 并落 `failed`。

## 3. 可靠性（真实 brief，零媒体 key）

| 项目 | Brief | 流水线 | 模式 | 墙钟 | 成片 | 检查点 | 产物 | 结论 |
|---|---|---|---|---|---|---|---|---|
| `echo-ad` | 15 s 竖屏 1080×1920，AI 笔记 App | animation | 模板 | **6.8 min** | 450 帧 / 15.000 s / 1080×1920 / 1.53 MB / 无音轨 | 7/8（缺 publish） | 9 | ✅ 通过 |
| `type0-ad` | 20 s 横屏 1920×1080，机械键盘 | animation | **atelier**（手写 Remotion 合成） | **23.0 min** | 600 帧 / 20.000 s / 1920×1080 / 0.69 MB / 无音轨 | 8/8 | 12 | ✅ 通过 |
| `xiaozhangben-ad` | 12 s 竖屏 1080×1920，中文文案，记账 App | animation | **atelier** | **22.0 min** | 360 帧 / 12.05 s / 1080×1920 / 1.14 MB / 静音轨 | 8/8 | 12 | ✅ 通过 |

**成功率 3/3**，零媒体 key，全部由模型在无人干预下完成（两条 atelier、一条模板）。

三条都选择了 `animation` 流水线并自评通过。差异全在**创作模式**：模板路径 6.8 分钟，atelier 路径 22–23 分钟 —— 慢约 3.3 倍。

### 观察到的行为（值得写进后续设计）

1. **模型会自己选 atelier。** `type0-ad` 读到 `AGENT_EDITOR` 的「hero work 默认 atelier」规则后，手写了 29 KB 的 `Composition.tsx`，而不是拼 `text_card`。质量更好，但墙钟和 token 显著上升。
2. **`om_write_checkpoint` 被真正用起来了。** 首次运行（无此工具）时模型自己写 Python 绕过；这次 8 个阶段全部走门面写入，产物 schema 合法。
3. **审批位没被乱用。** `scene_plan` 是 gated 阶段，模型先写 `decision_log` 的 `d-005 approval_policy / Full-run pre-authorization`，再置 `human_approved: true` —— 与 `AGENT_GUIDE` 的规定一致，不是伪造。
4. **MCP 面只被部分使用。** `type0-ad` 的 4 条工具事件里只有 `video_compose`；atelier 渲染实际是通过 `bash` 跑 Remotion 完成的。说明门面覆盖了「项目与检查点管理」，但**渲染路径仍绕过了工具面** —— 这是下一版要收的口子。
5. **静音是主动决策而非缺陷。** 三条都因「无音乐源」处理了静音轨（两条丢弃、一条保留以兼容平台校验），并写进报告。
6. **中文渲染实测通过。** 抽帧确认宋体/黑体正常渲染、无豆腐块，金额等宽数字对齐（见 `xiaozhangben-ad` 第 4 秒帧）。
7. **模型会自己修视觉缺陷。** `xiaozhangben-ad` 在渲染中自查出「双重曝光 / 首帧文字不可读 / 竖线穿字标」三个问题并重渲；`type0-ad` 在 assets 阶段自查出「红色十字像医疗标志」并改图。

## 4. 已知限制

- `.app` 是**原生 Tauri 壳（6.7 MB）**，但仍依赖仓库里的 `.venv`：分发靠 `install.command` 首次安装，不是自包含单文件。
- 只有 macOS；ad-hoc 签名，未公证。
- Tauri 壳需要 Rust 才能编译（本机 cargo 1.94 可用，crates.io 通过 sparse 索引可达）；没有 Rust 时脚本自动退回 pywebview。
- 无墙钟/费用硬上限：atelier 路径可跑到 20+ 分钟。
- 成本口径不完整：CLI 运行的 token/费用没有回读，目前只有应用内对话有 usage。
- Backlot 故事板尚未嵌入窗口（仍是独立页面）。

## 5. 结论

**可安装、可对话、可出片、key 可在界面配置 —— MVP 目标达成，3/3 可靠性通过，19 项验证全绿。**

关键闭环已打通：应用窗口里的对话 → Pi RPC → `mcp__openmontage__*` 工具 → 产物 → 窗口内预览。

距「可分发」还差三步，都不是方向问题：

1. **自包含运行时**：现在 `.app` 是 6.7 MB 的原生壳，但后端仍要仓库里的 `.venv`。把 python-build-standalone + Node + ffmpeg 做成 sidecar（或继续现方案：`install.command` 首次安装）
2. **收口渲染路径**：atelier 渲染目前由模型 shell 出去跑 `npx remotion`，工具事件里只剩 `video_compose`。要让渲染也走门面，才能被审计和限流
3. **atelier 预算**：22 分钟是自由发挥的产物，需要墙钟上限而不只是费用熔断

已完成的那部分（Tauri 壳、可分发包、进程回收）都在上面第 2 节 1b–1e 四条验证里。
