#!/usr/bin/env bash
# Build a double-clickable macOS .app for the OpenMontage desktop MVP.
#
# Preferred shell: Tauri 2 (app/desktop) — a 5 MB native binary using the
# system WebKit. If the Rust shell has not been compiled, fall back to the
# thin pywebview launcher so the app still runs.
#
#   scripts/build_app.sh              # assemble from what is available
#   scripts/build_app.sh --rebuild    # cargo build --release first
#   scripts/build_app.sh --open
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

# Tauri embeds frontendDist at compile time; keep it in sync with the SPA build.
if [ -d "$REPO/frontend/dist" ]; then
  rm -rf "$REPO/app/desktop/web"
  cp -R "$REPO/frontend/dist" "$REPO/app/desktop/web"
fi

APP="$REPO/dist/Ad+.app"
TAURI_BIN="$REPO/app/desktop/target/release/openmontage-desktop"
PYTHON="$REPO/.venv/bin/python"
REQUIREMENTS_ADPLUS="$REPO/requirements-adplus.txt"

REBUILD=0; OPEN_AFTER=0
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
    --open) OPEN_AFTER=1 ;;
  esac
done

# OM_SHELL=launcher skips the Rust shell entirely (used by the installer, so a
# recipient never needs a Rust toolchain).
if [ "${OM_SHELL:-}" = "launcher" ]; then
  TAURI_BIN=""
fi

if [ "$REBUILD" = "1" ] || [ ! -x "$TAURI_BIN" ]; then
  if command -v cargo >/dev/null 2>&1 && [ -f "$REPO/app/desktop/Cargo.toml" ]; then
    echo "==> building Tauri shell (cargo --release)…"
    ( cd "$REPO/app/desktop" && cargo build --release ) || echo "warn: cargo build failed; falling back to pywebview launcher"
  fi
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

if [ -x "$TAURI_BIN" ]; then
  MODE="tauri"
  cp "$TAURI_BIN" "$APP/Contents/MacOS/AdPlus"
else
  MODE="launcher"
  if [ ! -x "$PYTHON" ]; then
    echo "ERROR: neither the Tauri shell nor $PYTHON is available. Run 'make setup' first." >&2
    exit 1
  fi
  cat > "$APP/Contents/MacOS/AdPlus" <<LAUNCHER
#!/bin/bash
set -euo pipefail
cd "$REPO"
export PATH="\$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:\$PATH"
LOG="\$HOME/Library/Application Support/Ad+/app.log"
mkdir -p "\$(dirname "\$LOG")"
exec "$PYTHON" -u -m app.main >> "\$LOG" 2>&1
LAUNCHER
fi
chmod +x "$APP/Contents/MacOS/AdPlus"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Ad+</string>
  <key>CFBundleDisplayName</key><string>Ad+</string>
  <key>CFBundleIdentifier</key><string>com.adplus.desktop</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>AdPlus</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSApplicationCategoryType</key><string>public.app-category.video</string>
</dict>
</plist>
PLIST

ICON_SRC="$REPO/assets/icon-1024.png"
[ -f "$ICON_SRC" ] || ICON_SRC="$REPO/app/desktop/icons/icon.png"
if [ -f "$ICON_SRC" ]; then
  ICONSET="$(mktemp -d)/AppIcon.iconset"; mkdir -p "$ICONSET"
  "$PYTHON" - "$ICON_SRC" "$ICONSET" <<'PYICON' 2>/dev/null || true
import sys, os
from PIL import Image
src, out = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGBA")
for size in (16, 32, 128, 256, 512):
    im.resize((size, size), Image.LANCZOS).save(os.path.join(out, f"icon_{size}x{size}.png"))
    im.resize((size * 2, size * 2), Image.LANCZOS).save(os.path.join(out, f"icon_{size}x{size}@2x.png"))
PYICON
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns" 2>/dev/null || true
fi

codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || echo "warn: ad-hoc codesign failed (app still runnable locally)"

SIZE=$(du -sh "$APP" | awk '{print $1}')
echo "built: $APP  (shell=$MODE, $SIZE)"
echo "  launch: open \"$APP\""

if [ "$OPEN_AFTER" = "1" ]; then open "$APP"; fi
