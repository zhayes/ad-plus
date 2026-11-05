#!/usr/bin/env bash
# Manage the vendored OpenMontage checkout.
#
#   scripts/upstream.sh status          # pinned commit, branch, how far behind
#   scripts/upstream.sh pull            # fetch + fast-forward to origin/main
#   scripts/upstream.sh pin             # record the current commit for reference
#   scripts/upstream.sh check           # verify Ad+ still fits this upstream (runs verify_upstream.py)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UP="$ROOT/vendor/openmontage"
PIN="$ROOT/vendor/openmontage.commit"

[ -d "$UP/.git" ] || { echo "vendor/openmontage is not a git checkout" >&2; exit 1; }

case "${1:-status}" in
  status)
    printf '当前 commit : %s\n' "$(git -C "$UP" rev-parse --short HEAD)"
    printf '分支        : %s\n' "$(git -C "$UP" rev-parse --abbrev-ref HEAD)"
    [ -f "$PIN" ] && printf '上次记录    : %s\n' "$(cat "$PIN")"
    git -C "$UP" fetch -q origin 2>/dev/null || echo "（无法访问远端，跳过落后检查）"
    git -C "$UP" rev-list --count "HEAD..origin/main" 2>/dev/null | sed 's/^/落后上游    : /' || true
    ;;
  pull)
    git -C "$UP" pull --ff-only
    git -C "$UP" rev-parse HEAD > "$PIN"
    echo "已更新到 $(git -C "$UP" rev-parse --short HEAD)，记录写入 vendor/openmontage.commit"
    echo "提示：如果外层仓库用 submodule 跟踪，记得 git add vendor/openmontage 并提交"
    ;;
  pin)
    git -C "$UP" rev-parse HEAD > "$PIN"
    echo "pinned $(cat "$PIN")"
    ;;
  check)
    "$ROOT/.venv/bin/python" "$ROOT/scripts/verify_upstream.py"
    ;;
  *)
    echo "usage: $0 status|pull|pin|check" >&2; exit 2 ;;
esac
