# Ad+ 前端改造计划：SolidJS + TypeScript + Vite + Tailwind

> **路径说明（2026-11 拆分后）**：本文写于 Ad+ 独立成仓之前。当前布局为
> `~/AdPlus/`（Ad+ 代码：`adplus/`、`app/`、`frontend/`）+ `vendor/openmontage/`（上游 submodule）。
> 文中 `om_mcp.py` 现位于 `adplus/mcp/__main__.py`，`lib/{agent_bridge,quote,jobs}.py` 现位于 `adplus/`，
> `app/ui/*.html` 已由 `frontend/` 的 Solid 界面取代。


> 版本核对时间：2026-11-05（`npm view <pkg> version` 实测，非记忆）
> 目标：把 1643 行单文件 `workspace.html` 迁到可扩展的组件化前端，保持现有交互与视觉不变。

---

## 1. 版本矩阵（已核对 peer 依赖与 engines）

| 包 | 版本 | 说明 |
|---|---|---|
| `solid-js` | **1.9.18** | 细粒度响应式，无 VDOM |
| `@solidjs/router` | **1.0.1** | 1.0 正式版，peer 要求 `solid-js ^1.8.6` ✓ |
| `vite` | **8.3.5** | engines: node `^20.19 \|\| >=22.12`；本机 node **26.12.1** ✓ |
| `vite-plugin-solid` | **2.11.15** | peer 支持 `vite ^8` ✓、`solid-js ^1.7.2` ✓ |
| `typescript` | **7.0.2** | `latest` 标签；7.1 尚在 beta |
| `tailwindcss` | **4.3.4** | v4 CSS-first，配 `@tailwindcss/vite` |
| `@tailwindcss/vite` | **4.3.4** | peer 支持 `vite ^8` ✓ |
| `vitest` | **5.1.0** | 单测 |
| `@solidjs/testing-library` | **0.8.10** | 组件测试 |
| `@kobalte/core` | **0.13.14** | 无样式可访问性原语（Dialog/Select/Tabs/Tooltip）；peer `solid-js ^1.9.8` ✓ |
| `pnpm` | **12.16.1** | 本机是 10.3.0，用 `packageManager` 字段 + corepack 锁定 |
| `@types/node` | **26.6.6** | 与 node 26 对齐 |

**兼容性结论：这套组合的 peer 范围互相覆盖，没有冲突。**

两个需要留意的点：

1. **TypeScript 7 是 Go 重写的原生编译器（tsgo）**。Vite 不做类型检查（只剥类型），所以构建不受影响；只有 `pnpm typecheck` 跑 `tsc --noEmit` 时才是 TS7。若 Solid 的类型定义或插件在 TS7 下报错，降级路径是 `typescript@5.9`（改一行即可），不影响其它选型。
2. **Tailwind v4 没有 `tailwind.config.js`**，改成在 CSS 里用 `@theme` 定义令牌。现有 327 行 CSS 里的 `--bg/--surface/--accent/...` 会原样搬进 `@theme`，保证视觉零变化。

---

## 2. 目标与非目标

**目标**
- 组件化：时间线、消息流、Dock、右栏各自独立，回放与实时共用同一套组件（现在写了两遍且漂移过）
- 路由化：`/chat/:id`、`/settings`、`/onboarding`、`/splash` 进同一个 SPA，加新页面不再复制 HTML
- 类型化：API/WS 事件有 TS 类型，前后端字段改动能在编译期暴露
- 状态收敛：WS 流、轮询、pending 卡片统一进 store，不再散落全局变量

**非目标**
- 不改后端 Python 结构（FastAPI 只增加静态托管与 SPA fallback）
- 不改视觉设计与交互流程
- 不引入 SSR / 不做多端

---

## 2.5 已定决策

| 议题 | 决定 |
|---|---|
| 构建产物入库 | **不入库**，`.gitignore` 掉 `frontend/dist`；由 `scripts/*.sh` 生成 |
| 设置页迁移时机 | **P4** 与引导/启动页一起并入 SPA，之前保持旧 HTML |
| 组件库 | **引入 `@kobalte/core`**，只用在需要键盘/焦点管理的地方（弹层、下拉、标签页） |
| 复用策略 | 三层拆分，见 §3.5 —— 公共组件必须"一层只做一件事" |

**pnpm 版本说明（实测偏差）**：计划目标是 `pnpm@12.16.1`，但本机 corepack 从 registry 拉取该二进制时长时间无响应，
因此 P0 实际使用 **11.28.5**（DSH 运行时自带），`packageManager` 字段同步为 `pnpm@11.28.5` 以保证
`corepack`/CI 不报版本不匹配。升级到 12.x 只需改这一行并 `pnpm install`，不影响其它选型。

## 3. 目录结构

```
frontend/
  package.json            # "packageManager": "pnpm@12.16.1"
  pnpm-lock.yaml
  vite.config.ts          # solid + tailwind 插件，dev 代理 /api /ws → :8765
  tsconfig.json           # jsx: preserve, jsxImportSource: solid-js
  index.html              # SPA 宿主
  src/
    main.tsx              # render(() => <App/>, root)
    App.tsx               # <Router> 路由表
    routes/
      Workspace.tsx       # /chat/:sessionId?
      Settings.tsx        # /settings
      Onboarding.tsx      # /onboarding
      Splash.tsx          # /splash
    components/
      layout/AppShell.tsx       # 顶栏 + 侧栏 + 主区
      chat/Transcript.tsx
      chat/Turn.tsx
      chat/Timeline.tsx         # 实时 + 回放共用
      chat/Composer.tsx
      chat/AskDock.tsx          # 报价/闸门轮播
      panel/JobsPanel.tsx
      panel/ArtifactsPanel.tsx
      panel/PipelinePanel.tsx
      ui/Button.tsx, Card.tsx, Spinner.tsx ...
    stores/
      session.ts        # 当前会话、会话列表、切换
      transcript.ts     # 消息流 + 时间线
      asks.ts           # quotes / approvals 轮询 + 决策
      jobs.ts           # 任务进度轮询
      artifacts.ts      # 产物
      settings.ts       # 设置页数据
    lib/
      api.ts            # fetch 封装（复用现有端点）
      ws.ts             # WS 客户端，自动重连，事件类型
      types.ts          # 与后端对齐的 DTO
    styles/app.css      # @import "tailwindcss"; @theme { ... }
  dist/                 # 构建产物，由 FastAPI 托管
```

### 3.5 组件与公共代码的分层规则

四层，依赖只能单向向下，**禁止跨层引用**：

```
routes/         只负责取数 + 组布局，不写样式细节
  ↑
components/     业务组件（Transcript/Timeline/AskDock/JobsPanel…）
  ↑
ui/             无业务语义的原语（Button/Card/Spinner/Field…），内部可包 Kobalte
  ↑
lib/            api / ws / types / format（纯函数与 IO，不含 JSX）
```

| 层 | 放什么 | 复用规则 |
|---|---|---|
| `lib/api.ts` | 所有 `fetch` 调用，统一错误包装 | **全应用唯一出口**，组件里不出现裸 `fetch` |
| `lib/types.ts` | `Session` / `Quote` / `Approval` / `Job` / `Turn` 等 DTO | 与后端字段一一对应，改动先改这里 |
| `lib/format.ts` | `fmtTime` / `fmtBytes` / `fmtEta` / `fmtDur` | 现在 `workspace.html` 里各写一份，迁移后只留一处 |
| `ui/*` | 纯展示 + 交互原语 | 不含业务词（不出现"报价""会话"） |
| `components/*` | 有业务语义的组合 | 允许调 store，但**不直接 new WebSocket / fetch** |
| `stores/*` | 状态与副作用 | 只有 store 能写全局状态；组件只读 + 调 action |

**Kobalte 的边界**：`ui/Dialog.tsx`、`ui/Select.tsx`、`ui/Tabs.tsx` 内部封装 Kobalte，
业务层只 import 我们的 `ui/*`。这样以后换库（或不用库）只改 `ui/` 一层，
不会出现 Kobalte 的 API 散落在 30 个组件里。

**必须抽公共件的重复代码清单**（迁移时逐项消除）：

| 重复点 | 现状 | 目标 |
|---|---|---|
| 时间线渲染 | 实时 `tlStep` + 回放 `buildTurn` 两套 | 单个 `<Timeline turns>` |
| 格式化函数 | `fmtTime`/`fmtBytes`/`fmtEta` 散落 | `lib/format.ts` |
| 卡片壳 | 报价卡/闸门卡/预览卡各自拼 DOM | `components/chat/AskCard` + 变体 |
| 轮询 | 会话 4s、任务 1.2/4s、asks 各自 setInterval | `lib/poller.ts` 统一注册/清理 |
| 请求封装 | `api()` 内联在页面脚本 | `lib/api.ts` |

**为什么独立 `frontend/`**：Python 仓库不引入 `package.json` 依赖污染；`dist/` 单独可被 `.gitignore` 或提交（当前策略：构建产物不入库，靠 build 脚本生成）。

---

## 4. 与后端集成

### 4.1 开发期（双端口）

```
pnpm dev   →  Vite :5174
             proxy /api  → http://127.0.0.1:8765
             proxy /ws   → ws://127.0.0.1:8765
```

打开 `http://127.0.0.1:5174/` 调试，热更新毫秒级；后端仍跑在 8765。

### 4.2 生产（Tauri / 分发）

- `pnpm build` → `frontend/dist/`
- FastAPI：`app.mount("/assets", StaticFiles(directory=UI_DIST/"assets"))`
- 路由 fallback：`/`, `/chat/*`, `/settings`, `/onboarding`, `/splash` 全部返回 `dist/index.html`（其余 `/api/*` 不受影响）
- 过渡期开关：环境变量 `ADPLUS_UI=next|legacy`，默认 `legacy`，P2 完成后切 `next`，P5 删除 `legacy`

### 4.3 构建脚本

`scripts/make_dist.sh` 增加一步：

```bash
(cd frontend && pnpm install --frozen-lockfile && pnpm build)
```

`scripts/build_app.sh` 同理（Tauri 包依赖 dist 存在）。

---

## 5. Tailwind 设计令牌迁移

现有 CSS 变量 → `@theme`（值不变，保证像素级一致）：

```css
@import "tailwindcss";

@theme {
  --color-bg: #08090d;
  --color-surface: #0e1118;
  --color-surface-2: #141824;
  --color-line: #22283a;
  --color-line-soft: #1a2030;
  --color-text: #e8eaf0;
  --color-dim: #9aa3b5;
  --color-faint: #6b7385;
  --color-accent: #e0338a;
  --color-violet: #8b2fc9;
  --color-ok: #3ddc97;
  --color-warn: #f2b544;
  --color-bad: #ff6b6b;
  --font-sans: -apple-system, "PingFang SC", ...;
  --font-mono: ui-monospace, SFMono-Regular, ...;
  --radius-card: 12px;
}
```

规则：
- 颜色只用 `bg-surface` / `text-dim` 这类语义类，不再写十六进制
- 组件内部不写 `<style>`，例外仅"必须用伪元素/动画关键帧"时用 `@layer components`
- 深色是唯一主题，不引入 `dark:` 变体（省一半类名）

---

## 6. 状态设计

```
session.ts
  ✓ sessions[]          来自 GET /api/sessions（4s 轮询 → 后续可换 SSE）
  ✓ currentId           路由参数 :sessionId 为唯一真源
  ✓ select(id)          切会话：清空 transcript、加载历史

transcript.ts
  ✓ turns[]             { role, text, timeline?: TimelineStep[] }
  ✓ appendDelta(kind)   WS 事件：text/thinking/toolcall → 就地更新最后一个 turn
  ✓ finishTurn()        折叠时间线

asks.ts
  ✓ pending[]           quotes + approvals
  ✓ current             轮播索引
  ✓ decide(id, ok, cmt)

jobs.ts
  ✓ list[]  running    1.2s / 4s 自适应轮询（现有逻辑照搬）
```

**路由与状态的关系**：会话 id 放在 URL（`/chat/om-abc123`），刷新/前进后退都能还原；这是引入 router 的最大收益，也顺手解决了"刷新回到默认会话"的问题。

---

## 6.5 P0 实施记录（已完成）

| 项 | 结果 |
|---|---|
| 脚手架 | `frontend/`：`vite.config.ts` / `tsconfig.json` / `index.html` / `src/{main,App}.tsx` / `src/routes/Workspace.tsx` / `src/styles/app.css` |
| 依赖 | solid 1.9.18、@solidjs/router 1.0.1、@kobalte/core 0.13.14、vite 8.3.5、vite-plugin-solid 2.11.15、typescript 7.0.2、tailwind 4.3.4 |
| 构建 | `vite build` 1.08s；JS 32.3 KB（gzip 12.4 KB）、CSS 7.8 KB（gzip 2.3 KB） |
| 类型检查 | `tsc --noEmit` 通过（TS 7） |
| 后端 | `/?ui=next` 返回 SPA，`/assets/*` 200，`/chat/:id?ui=next` 深链接 200；默认仍是 `legacy` |
| 开发 | `pnpm dev` → 127.0.0.1:5174，`/api` 代理到 8765 验证通过 |

**实测踩到的三个坑（已修，写进脚本）**

1. **TS 7 移除了 `baseUrl`**：`tsconfig` 里必须删掉，`paths` 改成 `{"~/*": ["./src/*"]}`，否则 `tsc` 直接报 TS5102/TS5090。
2. **pnpm 12.16.1 拉不下来**：corepack 从 registry 下载该二进制长时间无响应，改用运行时自带的 **11.28.5**（`packageManager` 同步）。
3. **registry 极慢/被重置**：默认源出现 70s 级延迟与 ECONNRESET，改用 `https://registry.npmmirror.com` 后 8.4s 装完；脚本里用 `NPM_REGISTRY` 变量可覆盖。

另外 **Vite 8 dev server 在 macOS 只监听 `[::1]`**，`curl 127.0.0.1:5174` 会空响应 ——
配置里已固定 `host: "127.0.0.1"`。

## 6.6 P1–P4 实施记录（已完成）

| 阶段 | 交付 | 验证 |
|---|---|---|
| P1 | `ui/`：Button/Spinner/Card/Badge/Field + Kobalte 封装 `Dialog`/`Select`/`Tabs`；`layout/AppShell` | `tsc` 通过；设置页 Select 与产物灯箱实测可用 |
| P2 | `lib/{format,types,api,ws,poller,markdown}` + `stores/{session,transcript,asks,jobs}`；Transcript/Turn/Timeline/Composer/Rail | 真实对话：发消息 → 4s 内出现回答；时间线折叠 |
| P3 | JobsPanel / ArtifactsPanel（媒体优先、代码折叠）/ AskDock 轮播 / Kobalte Dialog 灯箱 | 产物 12 张真实图片 + 灯箱打开 1920px；任务进度条 |
| P4 | `/settings` 路由（模型、23 个媒体 key、运行时、数据目录） | 页面渲染 23 行 key，含「解锁 N」计数 |
| P5(部分) | 默认 UI 切到 `next`；`?ui=legacy` 保留回退；vitest 8 个用例 | `/?ui=legacy` 仍返回旧页；`pnpm test` 全绿 |

**迁移中修掉的真实 bug**

1. **路由切换重挂载导致重复开会话**：`startedFor` 是组件内变量，`navigate()` 后组件重建、状态丢失，于是又发了一次 `start`。
   改成模块级 `started` Map（id → provider/model），并把首条 prompt 排队到后端 `session` 事件之后再发。
2. **provider 传错**：模型下拉的 value 用 `model` 而不是 `provider/model`，导致 `provider=deepseek-flash`。
3. **`/settings` 路由不生效**：FastAPI 先注册的旧 `/settings` 抢了匹配，新路由永远不触发 —— 改成让旧 handler 判断 `ui_mode`。
4. **打包漏掉 SPA**：`rsync --exclude dist` 把 `frontend/dist` 一起排除了，zip 里没有构建产物；已单独补拷。

### 收尾（P4/P5 完成）

- **上传已接入**：回形针 → 选文件 → `POST /api/upload` → 附件 chip 可移除；发送时把 repo 相对路径附在 prompt 末尾。
- **最终实测**（发布的 `.app`，默认 UI）：发一句「只回复 OK」→ **4 秒**内出现回答；URL 变为 `/chat/om-meh2yo5s`；侧栏 11 个按钮、右栏任务 5 条、产物面板正常。

- **引导页已迁移**：`/onboarding` 用 Solid 重写，10 个 provider 排序、推荐标记、保存并验证、`has_model` 后才能继续。
- **旧页面已删除**：`frontend/src/routes/Workspace.tsx`（旧版 workspace.html 已删除）、`index.html`、`onboarding.html` 全部移除（`splash.html` 保留，
  它是原生外壳启动时的加载页）。`/?ui=legacy` 现在是 no-op，只返回 SPA。
- **缺构建时的行为**：`_require_spa()` 返回 503 并提示 `cd frontend && pnpm install && pnpm build`，
  不再静默退回旧页。

| 路由 | 实测 |
|---|---|
| `/` | 侧栏 11 个按钮（新对话 + 9 会话 + 设置） |
| `/settings` | 标题「设置」，23 行媒体 key |
| `/onboarding` | 标题「先接入一个模型」，10 个 provider |
| `/chat/om-f4202049` | 从磁盘回填 2 个 assistant 回合 |
| `/splash` | 仍为原生启动页 |

### 性能实测（与计划预算对比）

| 指标 | 预算 | 实测 |
|---|---|---|
| 首屏 JS（gzip） | < 90 KB | 16.4 KB 主包 + 30 KB 共享 + 14 KB 工作区 ≈ **60 KB** |
| 首屏 CSS（gzip） | < 20 KB | **5.2 KB** |
| 构建耗时 | — | 1.4 s |
| 单测 | — | 8 个用例 192 ms |

## 7. 分阶段实施

| 阶段 | 内容 | 估时 | 验收 | 回滚 |
|---|---|---|---|---|
| **P0 脚手架** | `frontend/` 初始化、依赖、vite/ts/tailwind 配置、FastAPI 托管 dist、`ADPLUS_UI` 开关 | 1 天 | `pnpm dev` 能跑一个 "Hello Ad+" 页面；`pnpm build` 后 8765 返回 SPA | 开关回 `legacy` |
| **P1 设计系统** | `@theme` 令牌、Button/Card/Spinner/AppShell、Tailwind 类替换 327 行 CSS | 1.5 天 | 静态骨架与现有截图逐像素对比（diff 工具） | 同上 |
| **P2 工作区** | 侧栏（keyed 列表）、消息流、时间线（实时+回放共用）、输入框、上传 | 3–4 天 | 逐条对齐现有行为：流式更新、折叠、滚动、粘贴上传 | `legacy` |
| **P3 右栏 + Dock** | 任务进度、产物网格/灯箱、流水线、报价/闸门轮播 | 2 天 | 三个确认卡片轮播、任务进度、产物打开 | `legacy` |
| **P4 路由页面** | 设置/引导/启动页并入 SPA，`/settings` 等直达 | 2 天 | 刷新不丢状态、深链接可用 | 保留旧 HTML |
| **P5 收尾** | vitest + CDP 冒烟、性能预算、删旧文件、改打包脚本 | 1.5 天 | 包体达标、CI 脚本全绿 | git revert |

**合计 11–13 个工作日。** 每阶段结束都可独立发布 —— `ADPLUS_UI=next` 灰度，出问题一键回 `legacy`。

---

## 8. 性能预算与验证

| 指标 | 目标 | 测法 |
|---|---|---|
| 首屏 JS（gzip） | < 90 KB | `vite build` 报告 |
| 首屏 CSS（gzip） | < 20 KB | 同上 |
| 首屏可交互 | < 300 ms（本地） | CDP `performance.timing` |
| 流式更新 | 单次 delta < 2 ms | `performance.measure` 包住 signal 写入 |
| 1000 条消息滚动 | 60 fps | CDP tracing，或长会话回放 |

时间线组件必须做到：**只在新增步骤时创建节点**，已有步骤的耗时文本原地更新（Solid 天然满足，但要避免在 `For` 里用非 keyed 索引）。

---

## 9. 测试策略

| 层 | 工具 | 覆盖 |
|---|---|---|
| 单元 | vitest 5 | 时间线折叠逻辑、轮播索引、格式化函数 |
| 组件 | @solidjs/testing-library | AskDock 决策回调、Composer 快捷键 |
| 端到端 | 现有 CDP 脚本（headless chrome） | 切会话、报价卡批准、任务进度、取消 |
| 视觉 | 截图对比 | 关键页面 3 张（工作区/设置/引导） |

---

## 10. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| TS7（原生编译器）与 Solid 类型/插件不兼容 | `typecheck` 失败 | 选型隔离：构建不依赖 tsc；必要时 `typescript@5.9` 一行回退 |
| Tailwind v4 与旧 CSS 混用导致样式冲突 | 视觉漂移 | P1 一次性替换全部令牌，旧 CSS 删除；不混用两套 |
| Router 1.0 破坏性变更 | 路由重写 | 只用 `Router/Route/A` 三个基础 API，不用实验特性 |
| pnpm 版本漂移（本机 10.3 vs 12.16） | lockfile 不一致 | `packageManager: "pnpm@12.16.1"` + corepack；CI 用 `pnpm install --frozen-lockfile` |
| dist 未构建导致 Tauri 白屏 | 发版失败 | `build_app.sh` 里先 build 再打包；CI 加"dist 存在性"检查 |
| 双轨期两套 UI 行为不一致 | 用户困惑 | `ADPLUS_UI` 只影响工作区；设置页保持旧版直到 P4 |

---

## 11. 迁移期间的硬规则

1. **新功能只写 Solid 组件**，不再往 `workspace.html` 加逻辑
2. 旧文件只修 bug，不加功能；每次修复同步到新组件（P2 完成后旧文件冻结）
3. 每个 PR 只迁一个面板，保持 `legacy` 可用
4. 删除旧文件是 P5 的最后一步，且需一次完整回归

---

## 12. 需要拍板的三件事

1. **构建产物是否入库**：建议不入库（`.gitignore`），靠脚本生成；代价是首次 clone 要 `pnpm install`
2. **设置页是否一起迁**：建议 P4 再迁（收益低、风险小）；如果想让"加新页面"立刻见效，可提前到 P2 之后
3. **是否引入组件库**（可选）：`@kobalte/core`（无样式、可访问性完善）能省下 Dialog/Select/Tabs 的实现；但会增加依赖与学习成本。建议**先不用**，等 P3 需要 Select（模型选择）时再评估
