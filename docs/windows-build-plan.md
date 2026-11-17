# Windows 构建计划（Restyle / Ad+）

> 2026-11-07 · Windows 10/11 x64 为主平台

## 目标

干净 Windows 机器安装 Ad+ 后，不依赖系统 Python / ffmpeg / tesseract，能：

1. 上传一条广告视频；
2. 读片（切镜 / 关键帧 / OCR / 分组）；
3. 打开 `/restyle/:id` 工作台；
4. 后续 P2 的静帧预览 / relight 也能跑。

## 目标架构

```text
Ad+ (Tauri 2, Windows)
  ├─ WebView2 前端（Vite 构建产物）
  ├─ Python 3.12 sidecar（PyInstaller）
  │    ├─ FastAPI（app.main --no-window --port 0）
  │    ├─ OpenCV / ONNX Runtime
  │    └─ bundled models
  └─ resources/
       ├─ ffmpeg.exe / ffprobe.exe
       ├─ tesseract.exe + tessdata/chi_sim.traineddata
       ├─ fonts/NotoSansSC-Bold.otf
       └─ models/segmenter.onnx
```

## 任务

### 1. Python sidecar

- 固定 **Python 3.12**；不要用 3.14 打 Windows 包（MediaPipe / onnxruntime wheel 覆盖不稳）。
- `py -3.12 -m venv .venv-restyle`；安装 `requirements-adplus.txt` + `requirements-restyle.txt`。
- PyInstaller：已提供 `scripts/build_backend.py`
  - 入口 `scripts/backend_entry.py` → `app.main`；
  - `--onedir --noconsole`；
  - 收集 `tools` / `lib` / `app` / `adplus`；
  - 复制 `pipeline_defs` / `schemas` / `skills` / `styles` 到 `app/desktop/resources/vendor/openmontage`；
  - 输出 `app/desktop/binaries/backend/adplus-backend/adplus-backend.exe`。
- 环境变量：
  - `ADPLUS_FFMPEG` / `ADPLUS_FFPROBE`
  - `ADPLUS_TESSERACT`
  - `ADPLUS_HOME`
  - `ADPLUS_SEGMENTER` / `ADPLUS_SEGMENTER_MODEL`

### 2. Tauri

- `bundle.targets` 增加 `nsis`（或 `msi`）；准备 `.ico`（16–256）。
- `externalBin` / `resources` 带 sidecar 和 `resources/`。
- Windows 10/11 需要 WebView2 Runtime；NSIS 可选 `webview2` bootstrapper。
- app data：`%APPDATA%\Ad+\`；日志同目录。
- 代码签名证书（EV/OV）另配。

### 3. 路径与进程

- API / JSON 全部 **POSIX 相对路径**（`as_posix()`）；Windows 大小写不敏感，避免同名。
- 长路径：>260 字符时用 `\\?\` 前缀；项目根尽量短。
- ffmpeg / tesseract 子进程 `CREATE_NO_WINDOW`，避免黑框。
- 原子写 `os.replace` 在 Windows 可用；注意 ffmpeg 读文件时的文件锁。

### 4. 分割后端

- 默认 `PersonSegmenter`：MediaPipe（轻）或 ONNX（MODNet 等待法务确认）。
- macOS Vision 只作可选增强；Windows 不依赖。
- 模型许可先审：RVM 是 GPL-3.0，商业分发需谨慎；MediaPipe Apache-2.0；MODNet 需确认。
- 无后端时硬镜头默认 `keep`，不阻塞读片/UI。

### 5. CI

已提供 `.github/workflows/windows.yml`：

- `test` job：Python 3.12 + ffmpeg + 读片 smoke + focused tests + 前端 build；
- `build-backend` job：PyInstaller sidecar + 启动 `adplus-backend.exe` 做 `/api/health` 检查 + 上传 artifact。

`scripts/restyle_smoke.py`：用仓库内小 fixture 视频跑 create → analyze → plan，断言 3 镜以上。

### 6. 验收

- 干净 Windows 10/11 VM：安装 → 启动 → 上传参考片 → 读片 → 工作台；
- 读片 ≤ 90s（中端 CPU）；
- 不弹出控制台窗口；
- 卸载后 `%APPDATA%\Ad+` 可选择保留/删除；
- 安装包体积目标 < 300MB（ffmpeg 80MB + tesseract 30MB + Python 60MB + 模型 20–50MB）。

## 风险

| 风险 | 应对 |
|---|---|
| Python 3.12 与现有 3.14 代码差异 | CI 双版本跑测试；固定 3.12 |
| MediaPipe / onnxruntime wheel 缺失 | ONNX Runtime 优先；模型可换 |
| ffmpeg 许可 | 确认 LGPL/GPL 构建；H.264 编码方案 |
| 模型许可 | RVM 慎用；MODNet/MediaPipe 先审 |
| 杀软误报 PyInstaller | 代码签名 + 白名单说明 |
| WebView2 未安装 | NSIS bootstrapper |

## 时间

- W0：3–5 天（安装包 + 读片 smoke + CI）；
- 通过后再做 P2 的 Windows 预览。
