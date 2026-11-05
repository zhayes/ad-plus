#!/usr/bin/env bash
# Build a distributable zip: repo + one-step installer, no venv / node_modules.
#
# Recipients unzip and double-click install.command. Python deps and Remotion
# are fetched on their machine, which keeps the download ~15 MB instead of 1 GB.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# --- frontend (Solid SPA) -------------------------------------------------
# Build before packaging: the app serves frontend/dist when ADPLUS_UI=next.
if [ -d "$REPO/frontend" ] && command -v node >/dev/null 2>&1; then
  PNPM_JS="${PNPM_JS:-/Applications/DeepSeek Harness.app/Contents/Resources/runtime/primary-runtime/dependencies/pnpm/bin/pnpm.cjs}"
  if [ -f "$PNPM_JS" ]; then
    ( cd "$REPO/frontend" \
      && node "$PNPM_JS" install --frozen-lockfile --registry="${NPM_REGISTRY:-https://registry.npmmirror.com}" >/dev/null 2>&1 \
      && node "$PNPM_JS" build >/dev/null 2>&1 ) || echo "warn: frontend build skipped"
  fi
fi

VERSION="$(python3 - <<'PY'
import re, pathlib
text = pathlib.Path("app/settings_server.py").read_text()
print(re.search(r'version="([^"]+)"', text).group(1))
PY
)"
OUT="$REPO/dist/Ad+-$VERSION-mac.zip"
STAGE="$(mktemp -d)/AdPlus"

mkdir -p "$STAGE" "$REPO/dist"
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '.venv-wan' --exclude 'node_modules' \
  --exclude 'vendor/openmontage/.git' --exclude 'vendor/openmontage/remotion-composer/node_modules' \
  --exclude 'remotion-composer/node_modules' --exclude 'projects' --exclude 'uploads' --exclude 'dist' \
  --exclude '.cache' --exclude '.backlot' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude '.DS_Store' --exclude 'music_library' --exclude 'output' \
  --exclude 'assets/*.mp4' --exclude 'assets/*.jpg' --exclude '*.mp4' --exclude '*.mov' \
  --exclude 'docs/images' --exclude '*/examples/assets' \
  --exclude 'app/desktop/target' --exclude '*.rlib' --exclude '*.dylib' \
  "$REPO/" "$STAGE/"

# The `dist` exclude above also drops frontend/dist, which is the built SPA the
# app serves. Copy it explicitly: recipients have no node toolchain.
if [ -f "$REPO/frontend/dist/index.html" ]; then
  mkdir -p "$STAGE/frontend"
  rsync -a --delete "$REPO/frontend/dist/" "$STAGE/frontend/dist/"
fi

mkdir -p "$STAGE/projects" "$STAGE/music_library"

cat > "$STAGE/install.command" <<'INSTALL'
#!/bin/bash
# Ad+ — one-step setup. Safe to run twice: finished steps are skipped.
set -euo pipefail
cd "$(dirname "$0")"
say() { printf "\n==> %s\n" "$1"; }
need() { command -v "$1" >/dev/null 2>&1; }

find_python() {
  for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
        echo "$candidate"; return 0
      fi
    fi
  done
  return 1
}
PYTHON_BIN="$(find_python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "需要 Python 3.10+（当前 $(python3 -V 2>&1)）：https://www.python.org/downloads/"; read -rp "回车退出"; exit 1
fi
if ! need node; then
  echo "需要 Node.js 18+：https://nodejs.org/"; read -rp "回车退出"; exit 1
fi
need ffmpeg || echo "提示：没检测到 ffmpeg（brew install ffmpeg），部分剪辑功能需要它"

[ -d .venv ] || { say "创建 Python 环境（$PYTHON_BIN）"; "$PYTHON_BIN" -m venv .venv; }

say "安装 Python 依赖（约 1–2 分钟）"
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q -r vendor/openmontage/requirements.txt
./.venv/bin/python -m pip install -q -r requirements-adplus.txt

if [ ! -d vendor/openmontage/remotion-composer/node_modules ]; then
  say "安装渲染依赖（约 1–3 分钟）"
  ( cd vendor/openmontage/remotion-composer && npm install --no-audit --no-fund )
fi

[ -f .env ] || cp .env.example .env

say "生成应用"
OM_SHELL=launcher ./scripts/build_app.sh >/dev/null
open "dist/Ad+.app"
say "完成。之后直接双击 dist/Ad+.app，不需要再跑这个脚本。"
INSTALL
chmod +x "$STAGE/install.command"

cat > "$STAGE/README.txt" <<'TXT'
Ad+ 桌面版（macOS）

首次使用：双击 install.command（或在终端运行 ./install.command）
之后：双击 dist/Ad+.app

需要：Python 3.10+、Node.js 18+、ffmpeg
密钥：首次打开后在「设置」页填写，保存在 macOS 钥匙串。
TXT

rm -f "$OUT"
( cd "$(dirname "$STAGE")" && zip -qry "$OUT" AdPlus )
rm -rf "$(dirname "$STAGE")"

echo "built: $OUT"
du -h "$OUT" | awk '{print "  size:", $1}'
