# Ad+ 重构 v5：生产控制台实施状态

## 已落地

### 1. 数据契约
- `adplus/production.py`：7 阶段 `brief → proposal → script → scene → assets → compose → review`。
- 阶段状态 `locked | ready | running | review | approved | failed | stale`，由项目产物派生。
- 路线 `local_motion`（animation/remotion，可用）与 `hybrid`（依赖媒体 key / 素材，暂不可用）。
- `GET /api/projects/{id}/production`、`POST /route`、`POST /script`、`POST /stages/{stage}/approve`。
- 旧项目兼容：已有成片但无 Ad+ approvals 的项目直接映射到审片阶段。

### 2. 生产控制台
- `Studio` 从顶部 tabs 重写为 Stage Rail + 阶段工作区 + Inspector + 单一 Action Bar。
- URL 即阶段：`/studio/:id/brief|proposal|script|scene|assets|compose|review`。
- 旧 URL `plan/canvas/storyboard` 自动映射，已锁阶段回退到当前阶段。
- 阶段 01：简报 + 路线选择 + 确认后生成方案。
- 阶段 02：方案/报价；确认后进入脚本，不再进入分镜。
- 阶段 03：脚本行编辑 + 时长预估 + 确认。
- 阶段 04：分镜工作区复用原有排序/编辑能力；未建版本时从方案镜头自动引导。
- 分镜允许删到空草稿；删除改为卡片内两步确认，避免 Tauri WebView 的 `window.confirm` 无反馈问题。
- 阶段 05：素材按镜确认；本地动效路线明确“无需外部素材”。
- 阶段 06：本地动效真实渲染（Remotion 模板 → job → 成片）。
- 阶段 07：QA、逐镜审片、导出交付。

### 3. 本地动效闭环
- `adplus/local_motion.py` 由已确认分镜生成确定性 Remotion 工程。
- 调用现有 `om_render` 任务系统；完成后写回 `version.render`、项目状态与 `final_review.json`。
- QQ糖项目已跑通：15.06s / 1080×1920 / h264 / 1.2MB，并完成审片与导出。

### 4. 项目与全局
- 项目卡片改为 `repeat(auto-fill, minmax(300px, 1fr))`，1180/1440 自适应。
- 新增表格视图（卡片/表格切换持久化）。
- 项目摘要带 `route_label / stage_label / next_action`。
- 底部 48px 全局 Dock：项目 / 制作 / 资产 / 任务 + 设置；Settings 也接入。
- 全局 palette 提升对比度，最小文字尺寸做可读性下限。

## 响应式断点
- `< 1280`：Stage Rail 横向单行、主工作区全宽；右侧详情改为主区「详情」抽屉，避免竖排轨道占满整页。
- `>= 1280`：Stage Rail 左侧竖排 + 主工作区 + 右侧 Inspector。
- 1180 与 1280 均已截图复测；项目卡片在 1180 为 3 列、1440 为 4 列。

## 验证
- Python：`43 tests OK`。
- Frontend：`14 tests OK`，`typecheck`、`build` 通过。
- `.app` 已重建并冷启动，`/api/health` 正常；前端新资源已打进 `app/desktop/web`。
- 旧项目 `vertical-ad-15s` 映射到审片/交付且全部阶段 approved，未破坏已有产物。
- UI 源内无 `navigate("/chat")` / `href="/chat"`；`/chat` 仅作为直接访问的兼容路由存在。
- 证据截图：`docs/verification/board-complete-v5.png`、`projects-cards-1440-v5.png`、`projects-table-960-v5.png`、`board-960-v5.png`、`board-1180-v5.png`、`board-1280-v5.png`、`board-1180-details-v5.png`、`chat-free-create-clean-v5.png`、`chat-free-create-panel-v5.png`。

## 自由创作入口（/chat）
- 底部 Dock 新增 **自由创作**，图标 `sparkles`，进入全局 `/chat`。
- 定位是**沙盒**：不先建项目、不经过 Brief/报价/gate；适合概念片、视觉实验、自由对话生成。
- 项目制作仍走七阶段控制台；两种模型并存，不把 `/chat` 作为主流程入口。
- 聊天页沿用 AppShell 的 Ad+ 标题，不再重复「自由创作 / 回到项目」；入口状态由底部 Dock 表达。
- 新对话留在 `/chat`，不再跳回首页。
- 空态说明边界，并提示产物/任务位置，以及如何转成可管理项目。
- 右侧产物/任务面板默认收起，需要时用右上角面板按钮展开。
- 任务面板只显示当前会话产物拥有的终态任务；无产物的失败/残留任务不再常驻。
- 仍保留旧 `/chat` 会话能力与右侧产物/任务面板。

## 入口收口
- Studio 内不再出现 `/chat` 跳转；`开始做方案` 直接进入 Brief/Route。
- 删除未再引用的旧 `PlanSheet`。
- Settings 移除“导演对话（旧版）”快捷键。
- 旧 `Workspace` 路由仍保留为直接访问的兼容页，但不再有 UI 入口；后续可单独重构或删除。

## 后续增强（不阻塞 v5 目标）
1. hybrid 路线接入（媒体 key、素材导入、每镜生产方式）。
2. 1180 以下 Inspector 抽屉；目前右侧细节在 xl 以下隐藏。
3. 导演页项目上下文与返回项目；当前入口已收口，页面本身仍是旧版。
4. 本地动效模板仍是占位级排版；需要把方案视觉方向映射成更强的版式/转场。
5. 方案报价按镜头/工具拆分；当前仍是渲染级报价。
