# Ad+ Desktop（MVP）

一个窗口里对话产出广告视频：本地后端 + 原生 WebKit 窗口 + Pi 1.5 作为 agent + OpenMontage 的 MCP 工具面。

## 跑起来

```bash
make setup                        # 首次：venv + 依赖 + Remotion
./scripts/build_app.sh --rebuild --open   # 编译 Tauri 壳并打开 dist/Ad+.app
# 没有 Rust 也能跑（自动退回 pywebview 壳）：
./scripts/build_app.sh --open
# 或者直接从源码起后端 + 兜底窗口：
.venv/bin/python -m app.main
```

首次打开是**对话页**；右上角「设置」里配 key。冷启动到可用约 4 秒。

## 组成

| 文件 | 职责 |
|---|---|
| `app/desktop/` | Tauri 2 原生壳（5.4 MB 二进制），拉起后端并在窗口关闭时回收它 |
| `app/main.py` | 后端进程入口（`--no-window`）、pywebview 兜底窗口、自动写 Pi 的 MCP 配置 |
| `app/settings_server.py` | FastAPI：设置 API、媒体文件服务、对话 WebSocket |
| `app/pi_bridge.py` | 以 RPC 模式驱动 `pi --mode rpc`，转发事件、累计 token 与费用 |
| `app/secrets_store.py` | macOS 钥匙串为主、`0600` JSON 镜像为辅 |
| `app/capabilities.py` | 从工具注册表派生 key 清单与能力矩阵（不硬编码 provider） |
| `app/ui/` | `chat.html`（对话 + 成片预览 + 费用）、`index.html`（设置） |
| `../om_mcp.py` | MCP stdio 服务，10 个门面工具 |
| `../scripts/build_app.sh` | 构建可双击的 `.app`（优先 Tauri，缺 Rust 时退回 launcher） |
| `../scripts/make_dist.sh` | 打可分发包：仓库 + `install.command` 引导安装（约 14 MB） |

## 数据与密钥

- 密钥：钥匙串（service `adplus`）+ 镜像 `~/Library/Application Support/Ad+/secrets.json`（`0600`，仅供子进程读取）
- 项目产物：`projects/<id>/`（`artifacts/`、`assets/`、`renders/`）
- 日志：`~/Library/Application Support/Ad+/app.log`
- Pi 的 MCP 配置：`~/.pi/agent/mcp.json` 里的 `openmontage` 条目（启动时幂等写入，不动其他 server）

## 已验证

- 设置页保存 key → 能力矩阵实时变化（`FAL_KEY` 让图像从 `0/29` 到 `9/29`），删除后回退
- 对话：WebSocket → Pi RPC，实测拿到模型回复并正常 `agent_settled`
- 费用：每轮 assistant 结束上报 `input/output/cacheRead/totalTokens/cost`
- 成片预览：工具结果里的媒体路径经 `/api/media` 内联播放（含目录穿越防护）
- 端到端：一次真实会话在为 15 秒竖屏广告产出 `renders/echo-ad.mp4`（450 帧 / 15.000 s / 1080×1920）

## 已知限制

- 只有 macOS 打包脚本；Windows/Linux 需要各自的启动器（Tauri 跨平台，但未适配）
- `.app` 是原生壳（6.7 MB）但仍要求仓库内存在 `.venv`：运行时分发靠首次 `install.command`，不是自包含单文件
- Tauri 壳需要 Rust 工具链才能编译；没有时自动退回 pywebview 壳
- 未做代码签名/公证；`build_app.sh` 只做 ad-hoc 签名
- Pi 的 atelier 模式（模型自己写 Remotion 合成）耗时可能远超模板路径，尚无墙钟/费用硬上限
