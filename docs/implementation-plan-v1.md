# Ad+ P0 落地实施计划 v1

| 项 | 内容 |
|---|---|
| 版本 | v1.0 |
| 日期 | 2026-11-05 |
| 范围 | 已确认的 P0（含分镜编排、品牌包） |
| 依据 | [模块与导航 v3.2](module-map-v3.md) · [页面规格 v3.3](page-specs-v3.md) · [入口地图 v3](entry-map-v3.md) |
| 目标 | 从“能跑通 demo”推进到“一个人能稳定做出一条可交付广告” |

---

## 0. 完成定义（DoD）

一个**没有 prompt 经验**的用户，在不看文档的情况下可以：

1. 新建项目，写一句话，选平台/时长。
2. 看到方案与报价（概念 + 3 帧 + 档位 + 价格），确认并生成。
3. 在分镜里拖拽排序、增删镜头、逐镜重做/锁定。
4. 在审片里默认全通过、只标问题镜，确认后只生成未锁定镜头。
5. 看片、切版本、导出成片（抖音预设）。
6. 在资产里上传素材、复用为参考/替换镜头；创建品牌包并应用到项目。
7. 在任务里看到失败原因并重试。
8. 全程不刷新、不丢状态；顶栏子 tab 居中；底栏四个模块可切换。

同时：Python 数据层测试通过；1440/1180/960 无横向滚动；旧项目可打开。

---

## 1. 已确认范围

### 1.1 P0

| 模块 | P0 |
|---|---|
| 项目 | 作品集、状态筛选、搜索排序、新建、卡片菜单、**右抽屉总览** |
| 制作 | 画布、分镜（**排序/增删**/逐镜返工/锁定）、审片、方案闸门、导演对话、版本、导出 |
| 资产 | 素材（上传/详情/复用）、**品牌包（列表/编辑/检查/应用）** |
| 任务 | 列表、汇总、项目筛选、取消、重试、日志 |
| 导航 | **底部 4 主模块 + 顶部居中子 tab**、原生菜单基础版、`⌘K` |
| 设置 | 模型、媒体、输出与存储、通知、快捷键、高级、关于 |

### 1.2 明确不做（P1/P2）

- 模板库、音乐库、批量分镜、版本对比、字幕/配音/配乐编辑、撤销/重做。
- 项目批量操作/归档视图、任务详情页/批量重试。
- 客户审片链接、多人协作、云端同步、模板市场。
- 自动更新（只保留入口）。

---

## 2. 现状与差距

| 层 | 已有 | 缺 |
|---|---|---|
| 数据 | `project.json` v1、`artifacts/scene_plan.json`、`final_review.json`、`quotes/`、`approvals/`、`jobs/` | `versions/`、`shots` 顺序、`brands/`、`deliverables/` |
| API | projects 列表、quotes、approvals、jobs、artifacts、workspace、sessions | 项目详情、版本/镜头 CRUD、品牌 CRUD/应用、导出 |
| 前端 | 聊天工作台（Workspace）、设置、Onboarding | 模块导航、项目页、制作三态、资产、任务 |
| 测试 | 前端 vitest 少量 | Python 数据层/API 测试（当前未安装 pytest，用 `unittest`） |
| 桌面 | Tauri 窗口/后端拉起 | 原生菜单、⌘K、通知 |

> 关键判断：**先把文件系统契约和 API 定稳，再做页面**；否则页面会被数据结构反复推翻。

---

## 3. 技术架构

### 3.1 文件系统契约（扩展）

```
projects/<id>/
  project.json                 # v2：status/platform/aspect/duration/tier/brand_id/brief
  versions/<vid>.json          # 版本 + shots[] + brand_snapshot
  renders/*.mp4
  deliverables/<did>.json      # 导出记录
  quotes/  approvals/  jobs/   # 已有
brands/<brand_id>.json         # 跨项目品牌包
```

规则：
- 所有写入 tmp + `os.replace` 原子替换。
- 镜头顺序 = `shots[]` 数组顺序；同时写 `index`，读取以数组为准。
- 版本不可变：改镜头 / 改品牌都生成新版本或只影响未开始版本；已交付版本保留 `brand_snapshot`。
- 旧 `project.json` v1 读取时补默认值，不写回；第一次写操作才升级为 v2。

### 3.2 API 契约

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/projects` | 列表（封面/状态/平台/时长/待办/版本数/花费） |
| POST | `/api/projects` | 新建（title/brief/platform/aspect/duration/tier） |
| GET | `/api/projects/{id}` | 详情：project + versions + current_version(shots) + pending + brand |
| PATCH | `/api/projects/{id}` | 标题/状态/简报/品牌/切当前版本 |
| GET | `/api/projects/{id}/versions` | 版本列表 |
| POST | `/api/projects/{id}/versions` | 从当前版本复制新版本 |
| PATCH | `/api/projects/{id}/versions/{vid}` | 设为当前/状态 |
| PATCH | `/api/projects/{id}/versions/{vid}/shots/reorder` | `{order:[shot_id]}` |
| POST | `/api/projects/{id}/versions/{vid}/shots` | 新增（after_id/role/description/duration） |
| PATCH | `/api/projects/{id}/versions/{vid}/shots/{sid}` | 改字段/锁/状态 |
| DELETE | `/api/projects/{id}/versions/{vid}/shots/{sid}` | 删除 |
| GET/POST | `/api/brands` | 品牌列表/新建 |
| GET/PATCH/DELETE | `/api/brands/{id}` | 品牌详情/编辑/删除 |
| POST | `/api/brands/{id}/default` | 设为默认 |
| POST | `/api/brands/{id}/apply` | `{project_id}` 应用到项目 |
| POST | `/api/export` | `{project_id, version_id, preset}` → deliverable |
| GET | `/api/deliverables?project_id=` | 交付物 |

### 3.3 前端路由

```
/                     → 项目（默认）
/projects             → 项目
/studio/:id/:tab?     → 制作（canvas|storyboard|review）
/assets/:tab?         → 资产（assets|brands|templates）
/tasks                → 任务
/settings             → 设置
/onboarding           → 首次配置
/chat/:sessionId      → 兼容旧链接，重定向到 /studio/:id
```

布局：`AppShellV2` = 底部模块栏 36 + 顶部上下文/子 tab 44 + 内容；右侧抽屉互斥。

---

## 4. 里程碑

> 以 1 人全职计；括号为估时。总计约 25 人日（4.5–5 周）。若 2 人并行，约 3 周。

### M0 · 数据层与 API（3d）

**交付**
- `adplus/paths.py` 增加 `BRANDS`。
- 新增 `adplus/project_store.py`：
  - 项目 v2 读写/迁移；列表与摘要。
  - 版本：读取/创建/切换；从 `scene_plan.json` 引导 v1。
  - 镜头：list/reorder/add/update/delete/重算时间。
  - 品牌：CRUD/默认/应用/快照。
- `app/settings_server.py` 增加项目 / 版本 / 镜头 / 品牌路由（export / deliverables 留到 M3）。
- `tests/test_project_store.py`、`tests/test_api_projects.py`（`unittest` + `TestClient`）。
- 旧项目迁移逻辑：v1 → v2 默认值；无版本时从 scene_plan 生成。

**验收**
- `python -m unittest discover -s tests` 全绿。
- 用现有 `projects/vertical-ad-15s` 调 `/api/projects/{id}` 返回 5 个镜头（来自 scene_plan）。
- 排序/增删后 `start_s/end_s` 与总时长正确。
- 品牌应用后新版本带 `brand_snapshot`；旧版本不变。

### M1 · 应用外壳 + 项目页（4d，已完成 2026-11-05）

**交付**
- `AppShellV2`：底部 4 模块、顶部居中子 tab、右侧抽屉容器。
- 路由改造：`/projects`、`/studio/:id/:tab`、`/assets`、`/tasks`；旧 `/chat/:id` 重定向。
- 项目页：卡片网格、搜索/筛选/排序、卡片菜单、新建项目模态、项目总览右抽屉。
- `stores/projects.ts`、`lib/api.ts` 扩展；空/加载/错误态。

**验收**
- 新建项目 ≤2 步；卡片进入正确项目。
- 子 tab 居中，切模块不位移。
- 删除可撤销；总览抽屉含简报/版本/交付/花费。
- 1440/1180/960 无横向滚动。

### M2 · 画布 + 分镜（5d，已完成 2026-11-05）

**交付**
- 画布：真实 `<video>`、transport、胶片条、镜头检查器、`⌘J` 导演抽屉（复用现有聊天组件）。
- 分镜：3×2 卡片、拖拽排序（HTML5 DnD + 插入线）、添加/删除、逐镜描述、总时长校验、单镜重做/锁定。
- 版本切换。
- 前端纯函数测试：`reorder`/`recomputeTimeline`。

**验收**
- 拖拽后时间轴重算并落盘；刷新后顺序保持。
- 添加/删除后总时长正确；少于 1 镜时阻止删除并提示。
- 画布/分镜/审片共享选中镜与时间码。
- 聊天抽屉不改变视频尺寸。

### M3 · 方案闸门 + 审片 + 导出（4d，已完成 2026-11-05）

**交付**
- 方案模态：概念、3 帧、档位、逐项价格、总价、ETA、假设；`确认并生成` / `改一下`。
- 审片：默认全通过、标问题、QA（时长/安全区/合规）、决策条；只生成未锁定镜头。
- 版本：切换/回滚。
- 导出模态：预设、封面、SRT（P1 可空）、文件名；`POST /api/export` 落 deliverables。
- 主操作状态矩阵。

**验收**
- 看方案与报价 → 确认 → 生成状态正确。
- 审片 5 镜默认全通过；标 1 镜 = 1 次点击。
- 导出文件可在 Finder 打开；记录可追溯。
- QA fail 时主操作变“修复并继续”。

### M4 · 资产 + 品牌（4d，已完成 2026-11-05）

**交付**
- 素材页：网格、类型/来源/项目筛选、上传/拖拽/粘贴、详情抽屉、用作参考/替换镜头、下载/重命名/删除。
- 品牌页：列表、编辑器、品牌检查、默认、应用到项目；禁用词进合规。
- 上传元数据（ffprobe：尺寸/时长/缩略图）。
- 品牌 API 联调。

**验收**
- 上传即见缩略图；失败可重试。
- 替换镜头禁用时写明原因。
- 品牌保存后新版本带快照；旧版本不变。
- 品牌检查命中禁用词时审片标黄。

### M5 · 任务 + 设置 + 菜单（3d，已完成 2026-11-05）

**交付**
- 任务页：汇总、筛选、项目筛选、取消/重试/日志、自动刷新。
- 设置：模型/媒体/输出与存储/通知/快捷键/高级/关于；Pi 集成进高级。
- 原生菜单（Tauri）：App/File/View/Project/Help 基础项；`⌘K` 命令面板。
- 通知：审批/完成/失败（P0 至少系统通知）。

**验收**
- 失败任务可重试；日志可打开；费用与列表一致。
- `⌘,` `⌘N` `⌘O` `⌘K` 可用。
- 设置缺失项补齐；`⌘K` 能搜到所有模块/页面/动作。

### M6 · 联调、验收、打包（2d，已完成 2026-11-05）

**交付**
- 端到端脚本/手工清单；真实项目跑一条 15s。
- 性能检查（项目列表、视频加载、轮询）。
- 打包 `dist/Ad+.app`；冷启动验证。
- 文档更新：PRD/页面规格/入口地图状态。

**验收**
- DoD 全部满足；无 P0 阻塞缺陷。
- 旧项目可打开；旧 `/chat` 链接可用。

---

## 5. 顺序与依赖

```
M0 数据/API
   ├── M1 外壳/项目页
   │      ├── M2 画布/分镜
   │      │      └── M3 方案/审片/导出
   │      └── M4 资产/品牌（依赖 M1 外壳 + M0 品牌 API）
   └── M5 任务/设置/菜单（依赖 M1 外壳 + 现有 jobs API）
          └── M6 联调
```

可并行：
- M2 与 M4 可两人并行（都依赖 M1）。
- M5 的 Tauri 菜单可与 M3 并行（Rust 独立）。

---

## 6. 测试策略

| 层 | 工具 | 覆盖 |
|---|---|---|
| 数据 | `unittest` | 项目迁移、版本引导、排序/增删/时间、品牌快照/默认 |
| API | `fastapi.testclient` | 项目详情、镜头 CRUD、品牌 CRUD/应用、错误码 |
| 前端纯函数 | `vitest` | 排序、时间重算、格式化 |
| 组件 | 手工/截图 | 三档宽度、空/加载/错误 |
| E2E | 手工 + headless Chrome | 新建→方案→分镜→审片→导出 |

- 不引入 pytest；`python -m unittest discover -s tests` 作为 CI 命令。
- API 测试使用临时目录，monkeypatch `project_store.PROJECTS/BRANDS` 与 `agent_bridge.PROJECTS_DIR`。
- 前端测试复用现有 vitest。

---

## 7. 风险与回退

| 风险 | 应对 |
|---|---|
| 旧项目数据格式不一 | 读取层补默认值；不写回；提供 `scripts/migrate_projects.py`（P1） |
| 品牌改动污染历史版本 | 版本创建时快照 `brand_snapshot`；历史只读 |
| 拖拽排序与 agent 冲突 | 后端以数组顺序为准；agent 写入前先读版本；冲突时 409/重读 |
| 前端重写影响现有聊天 | 保留 `/chat/:id` 重定向；聊天组件原样复用 |
| ffmpeg/导出失败 | 先复制原片到 deliverables；封面/SRT 失败不阻塞导出 |
| Tauri 菜单需重编译 | 放 M5，独立于 Python；失败可先保留页面入口 |
| 范围再次膨胀 | 任何新增先归入已有模块子 tab；不进 P0 除非替换现有项 |

---

## 8. 今天（M0）的具体动作

1. `adplus/paths.py`：加 `BRANDS`。
2. 新增 `adplus/project_store.py`：
   - `_atomic_write` / `_read_json`。
   - `load_project/save_project/list_projects/project_summary`。
   - `ensure_version`（从 `scene_plan.json` 引导）。
   - `reorder_shots/add_shot/update_shot/delete_shot/recompute_timeline`。
   - `list_brands/save_brand/delete_brand/set_default/apply_brand/snapshot_brand`。
3. `app/settings_server.py`：加项目详情、镜头 CRUD、品牌 CRUD/应用路由。
4. `tests/`：数据层 + API 测试。
5. 跑 `python -m unittest discover -s tests`，再用现有 `vertical-ad-15s` 做一次真实读取。

---

## 9. M0 完成记录（2026-11-05）

| 项 | 结果 |
|---|---|
| 数据层 | `adplus/project_store.py`：项目 v2、版本、镜头顺序/增删、品牌 CRUD/默认/应用/快照 |
| API | 项目列表/创建/详情/更新、版本、镜头 reorder/add/update/delete、品牌 CRUD/default/apply |
| 迁移 | 旧 `project.json` v1 读取补默认值；首次写回升级 v2 |
| 测试 | `python -m unittest discover -s tests` → **13 passed** |
| 真实项目 | `vertical-ad-15s` 的隔离副本：v1 / 5 镜 / 15.0s；原目录未改动 |
| 已知边界 | 导出与 deliverables 在 M3；前端页面在 M1–M4；批量分镜仍 P1 |

测试命令：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## 10. M1 完成记录（2026-11-05）

| 项 | 结果 |
|---|---|
| 外壳 | `AppShellV2`：44px 上下文栏、居中子 tab、36px 底部模块栏；`/projects` `/studio/:id/:tab` `/assets` `/tasks` |
| 项目页 | 真实 `/api/projects`；1440/1180 3 列、960 2 列；搜索/平台/排序；新建 2 步；卡片菜单；总览 420 抽屉；删除 8s 撤销 |
| 兼容 | 旧 `/chat/:sessionId?` 保留；Settings/Onboarding 保留；旧聊天不丢 |
| 制作桥 | 项目上下文 + 画布真实视频 + 分镜只读 + 审片占位；M2 补拖拽/增删/交互 |
| 测试 | 15 个 Python 测试；`tsc --noEmit`；`vite build` |
| 验收 | 1440/1180/960 无横向滚动；子 tab 居中；新建/总览/删除撤销实测 |
| 坑 | `.gitignore` 的 `projects/` 误伤 `frontend/src/components/projects/`，Tailwind 不扫描；已改为根锚定 |

证据：`docs/verification/projects-m1-1440.png`、`projects-1180.png`、`projects-960.png`、`project-overview-m1.png`、`studio-m1.png`、`storyboard-m1.png`。

## 11. M2 完成记录（2026-11-05）

| 项 | 结果 |
|---|---|
| 分镜 | HTML5 拖拽（网格内前插线）、添加镜、删除镜、改时长、双击改描述、锁定、时间轴点击选中 |
| 画布 | 真实 `<video>`、胶片条、选中镜 seek、当前镜头检查器 |
| 共享状态 | 画布/分镜共用 `selectedId`；切 tab 保持选中；视频 timeupdate 反选当前镜 |
| 乐观更新 | 排序先本地重算并落 UI，失败 `load()` 回滚；增删改以服务端 version 为准 |
| 测试 | 15 Python + 14 Vitest（storyboard 6）；`tsc`、`vite build` |
| UI 实测 | 临时项目：s2 拖到 s1 前、加 s5、删 s5、2.0→3.5s、改描述、锁定；已清理 |
| 证据 | `docs/verification/storyboard-drag-m2.png`、`canvas-m2.png` |
| 边界 | 审片仍占位，M3 接；批量分镜 P1；删镜未做 undo；画布暂用原生 transport |

> 网格里用“插到目标卡之前”的单线，避免最后一列右侧线无法表达下一行；移到末尾用末尾“添加镜头”卡承接拖放。

## 12. M3 完成记录（2026-11-05）

| 项 | 结果 |
|---|---|
| 方案闸门 | 读取最新 quote + proposal + 关键帧；概念/交付物/逐项报价/ETA/假设；`确认并生成` / `改一下`；quoted → storyboard |
| 审片 | 读取 final_review + render_report + 品牌禁用词；QA 检查、默认全通过、逐镜标问题；通过 → delivered，打回 → producing |
| 导出 | 抖音/小红书 1080、720 预览、原片；ffmpeg 转码失败回退复制；交付物元数据 + Finder；delivered |
| 版本 | 侧栏切换当前版本，画布/分镜随版本刷新 |
| 主操作 | 开始做方案 / 看方案与报价 / 看分镜 / 审片 / 导出 / 修复并继续 |
| 测试 | 21 Python + 14 Vitest；`tsc`、`vite build` |
| 证据 | `docs/verification/plan-m3.png`、`review-m3.png`、`export-done-m3.png` |
| 边界 | 实际生成与“只生成未锁定镜头”仍由 agent/MCP 执行；本层记录 quote/review 决策与项目状态，M6 做 agent 端到端 |

> 审片通过后项目进入 `delivered`（可导出）；导出会写 `deliverables/<name>.mp4 + <name>.json`，历史交付可回看、可 Finder 打开。

## 13. M4 完成记录（2026-11-05）

| 项 | 结果 |
|---|---|
| 素材 | 扫描 uploads / 项目 assets / 项目 renders；raw-body 上传；类型/来源/项目筛选与搜索；详情探测（尺寸/时长） |
| 复用 | 复制到项目 assets；“用作参考”写入 brief.reference_assets；“替换镜头”更新 shot.preview/status |
| 删除 | 上传/项目素材可删；渲染禁止从素材页删除 |
| 媒体 | `/api/media`、`/api/thumb` 扩展到 uploads；视频卡片缩略图 |
| 品牌 | 列表/编辑器/logo 上传/色板/字体/调性/口播/禁用词；默认、应用项目；品牌检查（logo/色板/对比度/字体/禁用词/口播） |
| 快照 | 应用品牌只影响以后生成的版本；已交付版本保留原 brand_snapshot |
| 测试 | 23 Python + 14 Vitest；`tsc`、`vite build` |
| 证据 | `docs/verification/assets-m4.png`、`asset-drawer-m4.png`、`brands-m4.png` |
| 边界 | 模板/音乐库 P1；素材重命名/集合 P1；删除无 undo；素材详情不显示颜色/EXIF 等深度元数据 |

## 14. M5 完成记录（2026-11-05）

| 项 | 结果 |
|---|---|
| 任务页 | 真实 `/api/jobs`；进行中/失败/完成/中断/排队；项目筛选；失败 inline 展开错误 + 日志尾部；取消、重试（queued）、输出 Finder |
| 汇总 | 进行中、失败/中断、今日已花、预算/剩余；按 `cost_usd` 累加，预算读 config |
| 设置 | 7 个 tab：模型 / 媒体服务 / 输出与存储 / 通知 / 快捷键 / 高级 / 关于 |
| 存储 | 输出目录读写、使用默认、应用数据与日志路径、Finder |
| 通知 | 待确认/完成/失败开关 + macOS `osascript` 测试通知；配置持久化 |
| 快捷键 | ⌘K ⌘N ⌘O ⌘, ⌘J Esc 列表 |
| 高级 | Pi 暴露方式、会话信任、运行时、重新检查、日志 |
| ⌘K | 全局 root 挂载命令面板；页面/动作搜索；↑↓/↵/Esc；⌘N/O/, 全局键 |
| 原生菜单 | Tauri 菜单：Ad+ / 文件 / 视图 / 帮助；⌘N/⌘O/⌘K；菜单事件经 `adplus-menu` 交给前端 |
| 测试 | 25 Python + 14 Vitest；`tsc`、`vite build`；`cargo check` 通过 |
| 证据 | `docs/verification/tasks-m5.png`、`tasks-failed-m5.png`、`settings-m5.png`、`settings-notifications-m5.png`、`command-palette-m5.png` |
| 边界 | 重试只入队，需 agent 接单；自动通知（job/approval 事件）留 M6；原生菜单运行时未截图；系统通知需 macOS 权限 |

## 15. M6 完成记录（2026-11-05）

| 项 | 结果 |
|---|---|
| 真实渲染 | Pi 1.5.0 + DeepSeek → MCP `om_render`：450/450 帧，15.061s，1080×1920 h264+aac，2.5MB |
| 审片/导出 | 复制项目审片通过 → `delivered` → `douyin_1080` 导出 2.1MB / 15.061s / 1080×1920 |
| 打包 | `dist/Ad+.app` 6.6M；冷启动 2s；Tauri 菜单（Ad+/文件/视图/帮助）；菜单点击“视图→任务”触发 `/api/jobs` |
| 发行包 | `dist/Ad+-0.1.0-mac.zip` 3.1M |
| 修复 | `/api/jobs` 与 MCP 统一 `adplus.jobs`；`om_render` 输出/public 绝对化；SPA 深链 fallback；build 同步 `frontend/dist → app/desktop/web`；旧 job output 归一化 |
| 测试 | 26 Python + 14 Vitest；`tsc`、`vite build`、`cargo check` 通过 |
| 证据 | `docs/p0-acceptance.md`；`tasks-m6-agent.png`、`e2e-review-m6.png`、`agent-render-m6.txt`、`packaged-coldstart-m6.txt` |
| 边界 | 重试只入队；自动通知未接事件；未重新跑“新 brief→新方案”的付费生成；原生菜单无窗口截图（AppleScript + 请求已证） |

## 16. 进度记录

| 里程碑 | 状态 | 备注 |
|---|---|---|
| M0 | 完成 | 2026-11-05；13 tests passed |
| M1 | 完成 | 2026-11-05；外壳/项目页/总览/删除撤销 |
| M2 | 完成 | 2026-11-05；拖拽/增删/时长/描述/胶片条 |
| M3 | 完成 | 2026-11-05；方案闸门/审片/导出/版本切换 |
| M4 | 完成 | 2026-11-05；素材上传/复用/品牌包 |
| M5 | 完成 | 2026-11-05；任务/设置/⌘K/原生菜单 |
| M6 | 完成 | 2026-11-05；agent 渲染/审片/导出/打包/冷启动 |
