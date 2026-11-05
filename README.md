# Ad+

桌面版 AI 广告生成工具。上层是 Ad+（后端 `app/`、界面 `frontend/`、MCP 门面 `adplus/mcp/`），
上游的 [OpenMontage](https://github.com/calesthio/OpenMontage) 只作为依赖放在 `vendor/openmontage/`。

## 目录

```
adplus/           Ad+ 的 Python 包（paths / agent_bridge / quote / jobs / mcp）
app/              FastAPI 后端 + Tauri 外壳（app/desktop）
frontend/         SolidJS 界面（Vite + Tailwind + Kobalte）
vendor/openmontage  上游源码（git submodule，保持干净）
projects/         用户的广告工程与成片（不入库）
brands/           跨项目品牌包（不入库）
uploads/          上传素材（不入库）
scripts/          build_app.sh / make_dist.sh / upstream.sh / verify_upstream.py
```

根目录的 `AGENT_GUIDE.md`、`skills/`、`pipeline_defs/`、`styles/`、`PROJECT_CONTEXT.md` 是指向上游的符号链接，
让 agent 在读写用户工程时仍然能读到上游文档。

## 环境

Python **3.14**（pyenv 管理：`pyenv install 3.14.10 && pyenv global 3.14.10`），
依赖装在 `.venv/`（`python3 -m venv .venv && .venv/bin/pip install -r vendor/openmontage/requirements.txt -r requirements-adplus.txt`）。

## 开发

```bash
./.venv/bin/python -m app.main --no-window     # 后端 :8765
cd frontend && pnpm dev                        # 界面 :5174（/api 代理到 8765）
```

## 更新上游

```bash
scripts/upstream.sh status     # 当前 commit、落后多少
scripts/upstream.sh pull       # 拉取上游
scripts/verify_upstream.py     # 校验 Ad+ 依赖的上游接口没变
```

## 打包

```bash
scripts/build_app.sh           # dist/Ad+.app
scripts/make_dist.sh           # dist/Ad+-<version>-mac.zip
```
