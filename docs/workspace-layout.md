# Ad+ 工作区结构（2026-11 拆分后）

> **路径说明（2026-11 拆分后）**：本文写于 Ad+ 独立成仓之前。当前布局为
> `~/AdPlus/`（Ad+ 代码：`adplus/`、`app/`、`frontend/`）+ `vendor/openmontage/`（上游 submodule）。
> 文中 `om_mcp.py` 现位于 `adplus/mcp/__main__.py`，`lib/{agent_bridge,quote,jobs}.py` 现位于 `adplus/`，
> `app/ui/*.html` 已由 `frontend/` 的 Solid 界面取代。


## 为什么拆

拆分前 Ad+ 的代码直接长在上游仓库里：`git status` 有 20 个未跟踪路径（`app/`、`frontend/`、
`adplus/mcp/__main__.py`、`adplus/agent_bridge.py`…）加 3 个被改过的上游文件。一次 `git pull` 就可能冲突或覆盖。

拆分后：**Ad+ 是外层仓库，OpenMontage 是 `vendor/` 下的 submodule**，上游目录 `git status` 永远干净。

## 目录

```
~/AdPlus/                        Ad+ 仓库
├── adplus/                      Ad+ 的 Python 包
│   ├── __init__.py              bootstrap：vendor 入 sys.path
│   ├── paths.py                 WORKSPACE / VENDOR / COMPOSER / PROJECTS
│   ├── agent_bridge.py          报价/闸门/作业文件契约
│   ├── quote.py  jobs.py
│   └── mcp/__main__.py          ← 原 om_mcp.py，入口 `python -m adplus.mcp`
├── app/                         FastAPI 后端 + Tauri 外壳（app/desktop）
├── frontend/                    SolidJS 界面
├── vendor/openmontage/          上游（submodule，保持 pristine）
├── projects/  uploads/          用户数据（gitignore）
├── schemas/adplus/              quote / approval / job 三个 schema
├── scripts/                     build_app.sh / make_dist.sh / upstream.sh / verify_upstream.py / migrate_paths.py
├── docs/
├── .venv/                       Python 3.14 虚拟环境（pyenv 管理）
└── 符号链接 → vendor（给 agent 读文档用）
      AGENT_GUIDE.md  PROJECT_CONTEXT.md  skills/  pipeline_defs/  styles/
```

## 路径解析（单一来源）

`adplus/paths.py`：

| 变量 | 默认值 | 覆盖用环境变量 |
|---|---|---|
| `WORKSPACE` | `adplus/` 的父目录 | `ADPLUS_HOME` |
| `VENDOR` | `WORKSPACE/vendor/openmontage` | `OPENMONTAGE_HOME` |
| `COMPOSER` | `VENDOR/remotion-composer` | `OPENMONTAGE_COMPOSER_DIR` |
| `PROJECTS` | `WORKSPACE/projects` | `OPENMONTAGE_PROJECTS_DIR` |
| `UPLOADS` | `WORKSPACE/uploads` | `OPENMONTAGE_UPLOADS_DIR` |

后端、MCP 门面、渲染工具全部从这里取路径，不再各写一份 `Path(__file__).parent.parent`。

`adplus/__init__.py` 负责把 `VENDOR` 插进 `sys.path`，所以 `import tools.tool_registry`、
`import lib.checkpoint` 在上游成为依赖后依然可用，且只在一处做。

## agent 的 cwd

Pi 以**工作区根目录**启动，`AGENT_GUIDE.md` / `skills/` / `pipeline_defs/` 通过符号链接指向 vendor。
这样 agent 既能读到上游文档，写入又落在 `projects/`、`uploads/`，不会污染 vendor。

## 上游依赖契约

`scripts/verify_upstream.py` 会逐项断言：

- `tools.tool_registry.registry`（`discover()` / `get()`）
- 工具的 `estimate_cost` / `estimate_runtime` 覆写（≥50 个）
- `lib.checkpoint` 的 `get_completed_stages / get_next_stage / get_latest_checkpoint / write_checkpoint`
- `pipeline_defs/*.yaml`、`remotion-composer/package.json`、`AGENT_GUIDE.md`、`skills/`

## 日常操作

```bash
scripts/upstream.sh status     # 当前 commit、落后多少
scripts/upstream.sh pull       # 拉上游 + 记录 commit
scripts/verify_upstream.py     # 契约检查（失败会指出具体哪一项）
scripts/migrate_paths.py       # 会话里旧绝对路径 → 新工作区路径（--dry-run 可预览）
```

## 打包

`scripts/make_dist.sh` 会排除 `vendor/openmontage/.git`、所有 `node_modules`、`.venv`、
`app/desktop/target`；`install.command` 从 `vendor/openmontage/requirements.txt` +
`requirements-adplus.txt` 装依赖，并在 `vendor/openmontage/remotion-composer` 里跑 `npm install`。
