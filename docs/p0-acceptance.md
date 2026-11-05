# Ad+ P0 验收记录

日期：2026-11-05
范围：M0–M6，P0 单机 macOS 版
结论：**P0 验收通过**。核心旅程（项目 → 方案/报价 → 分镜 → 生成 → 审片 → 导出）已可在打包后的 `.app` 中完成；剩余 4 项为非阻塞 P1，列在最后。

## 1. 环境与产物

| 项 | 值 |
|---|---|
| 系统 | macOS，单机 |
| Python | 3.14.10（`.venv`） |
| 前端 | Solid + Vite，`frontend/dist` |
| 桌面壳 | Tauri 2.12.5，`app/desktop` |
| 打包产物 | `dist/Ad+.app`（6.6M，tauri shell） |
| 发行 zip | `dist/Ad+-0.1.0-mac.zip` |
| 数据 | 9 个真实项目；1 个真实渲染 job |

## 2. 自动化验证

```bash
.venv/bin/python -m unittest discover -s tests     # 26 passed
cd frontend && pnpm test                           # 14 passed
cd frontend && pnpm typecheck && pnpm build        # passed
cd app/desktop && cargo check                      # passed
```

覆盖：项目/版本/镜头排序与增删、时间重算、品牌快照、报价决策、方案闸门、审片通过/打回、导出、素材上传/复用/删除、品牌 CRUD/默认/应用、job 列表/重试、配置/通知参数、SPA 深链。

## 3. DoD 清单

| DoD | 结果 | 证据 |
|---|---|---|
| 新建项目、简报、删除撤销 | 通过 | M1 截图 + 项目 API 测试 |
| 方案与报价：概念/交付物/逐项报价/ETA/假设，确认或改一下 | 通过 | M3 `plan-m3.png`；`test_plan_review_export` |
| 分镜：排序、增删、时长、描述、锁定 | 通过 | M2 `storyboard-drag-m2.png`；15 个 Python 测试中的镜头用例 |
| 画布/分镜/审片共享选中状态与真实视频 | 通过 | `canvas-m2.png`；E2E 审片页实际 `<video>` poster |
| 生成：agent → MCP → 渲染 | 通过 | `agent-render-m6.txt`；job `j_...1eef2b` 450/450，15.06s |
| 审片：QA、逐镜标问题、通过/打回 | 通过 | `e2e-review-m6.png`；真实成片审片通过 |
| 导出：抖音/小红书 1080、720、原片 | 通过 | E2E 导出 `m6-e2e.mp4` 2.1MB，h264 1080×1920 + aac |
| 资产：上传、筛选、详情、替换镜头/参考 | 通过 | `assets-m4.png`、`asset-drawer-m4.png` |
| 品牌：品牌包、检查、应用、快照 | 通过 | `brands-m4.png`；品牌 store 测试 |
| 任务：真实 job、失败展开、日志、取消/重试 | 通过（重试为排队） | `tasks-m5.png`、`tasks-failed-m5.png`、`tasks-m6-agent.png` |
| 设置：7 个 tab、存储、通知、快捷键、Pi | 通过 | `settings-m5.png`、`settings-notifications-m5.png` |
| ⌘K 命令面板、⌘N/⌘O/⌘, | 通过 | `command-palette-m5.png` |
| 原生菜单 | 通过 | 冷启动菜单 `Apple, Ad+, 文件, 视图, 帮助`；点击 视图→任务 触发 `/api/jobs` |
| 旧项目可打开 | 通过 | 9 个真实项目；`vertical-ad-15s` 渲染/审片可读 |
| 旧 `/chat` 链接 | 通过 | `/chat/legacy-session` → 200 SPA |
| 1440/1180/960 无横向滚动 | 通过 | M1/M2 截图 |
| 打包与冷启动 | 通过 | `packaged-coldstart-m6.txt`；健康检查 2s |
| 无 P0 阻塞缺陷 | 通过 | 下面 4 项均不阻塞核心旅程，归 P1 |

## 4. 真实端到端

1. Pi 1.5.0 + DeepSeek 通过 app 的 `/ws/chat` 启动；MCP `openmontage` connected。
2. agent 调用 `mcp__openmontage__om_capabilities`，确认 ffmpeg/Remotion/HyperFrames ready。
3. agent 调用 `mcp__openmontage__om_render`：`vertical-ad-15s` / `FlowSugarAd` / 450 帧 → job done，15.061s，1080×1920，h264+aac，2.5MB。
4. 复制项目为 `m6-e2e`，审片通过（final_review pass），项目进入 delivered。
5. 导出 `douyin_1080` → `deliverables/m6-e2e.mp4`，2.1MB，15.061s，1080×1920，h264+aac。
6. 任务页显示真实渲染 job（`tasks-m6-agent.png`）；审片页显示真实成片与 QA（`e2e-review-m6.png`）。

## 5. 性能

| 路径 | 耗时 |
|---|---|
| `GET /api/projects` | 10.8ms |
| `GET /api/projects/vertical-ad-15s` | 4.3ms |
| `GET /api/assets` | 12.3ms |
| `GET /api/jobs` | 2.2ms |
| `GET /chat/legacy-session` | 2.7ms |

项目列表、详情、任务轮询均在可接受范围；无 N+1 阻塞。

## 6. M6 修掉的阻塞问题

| 问题 | 影响 | 修复 |
|---|---|---|
| `/api/jobs` import 不存在的 `lib.jobs` | 任务页 500 | 改用 `adplus.jobs` |
| MCP 渲染 job 写 `lib.jobs`，UI 读 `adplus.jobs` | 渲染完成但任务页看不到 | MCP 统一 `adplus.jobs` |
| `om_render` 相对 output/public-dir 按 composer cwd 解析 | 渲染 404 `public/music/bed.wav` | output/public 全部绝对化 |
| SPA 深链 `/projects /studio /tasks /assets` 404 | 刷新/深链白屏 | 补 SPA fallback |
| build_app 不复制 `frontend/dist` 到 Tauri `web` | 打包后资源缺失/旧页面 | 构建前同步 `app/desktop/web` |
| 旧 job output 指向旧 checkout | “打开”失效 | `/api/jobs` 归一化到当前 projects 根 |

## 7. 非阻塞 P1

1. **重试只排队**：`POST /api/jobs/{id}/retry` 写入 `queued`，需要 agent 接单才会真正执行；没有常驻队列消费者。
2. **自动通知未接事件**：设置页可开关/测试 macOS 通知，但 job 完成/失败、待审批还没有自动触发。
3. **未重新跑“新 brief → 新方案 → 新分镜”的完整付费生成**：本轮用已有真实 15s 项目做了 agent 渲染、审片、导出；链路真实，但新创意起点未再走一遍。
4. **原生菜单没有窗口截图**：本会话 `screencapture` 无法取窗口；用 AppleScript 菜单项 + 点击后 `/api/jobs` 请求证明运行时。
5. 无 Windows/Linux 打包与 CI。

## 8. 复现命令

```bash
# 开发
.venv/bin/uvicorn app.settings_server:app --port 8765
cd frontend && pnpm dev

# 打包
./scripts/build_app.sh --rebuild
open -n "dist/Ad+.app"

# 测试
.venv/bin/python -m unittest discover -s tests
cd frontend && pnpm test && pnpm typecheck && pnpm build
cd app/desktop && cargo check
```

证据目录：`docs/verification/`（M1–M6 截图、`agent-render-m6.txt`、`packaged-coldstart-m6.txt`、`agent-smoke-m6.txt`）。
