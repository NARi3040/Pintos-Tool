#!/usr/bin/env bash
# thread-viz를 GitHub Release로 배포함. 사용법: tools/release-thread-viz.sh "변경 내용"
# tools/thread-viz/VERSION 값이 릴리스 태그(v<N>)가 됨. 올리기 전에 VERSION을 먼저 올릴 것.
set -euo pipefail
REPO="${THREAD_VIZ_REPO:-NARi3040/Pintos-Tool}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
VER="$(tr -d '[:space:]' < "$HERE/tools/thread-viz/VERSION")"
[[ $VER =~ ^[0-9]+$ ]] || { echo "VERSION이 정수가 아님: $VER"; exit 1; }
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
cd "$HERE"
# 실행 결과물(traces, data.js, progress.json)은 빼고 도구 파일만 담음. 디렉터리 항목 없이 파일만
tar -czf "$OUT/thread-viz.tar.gz" --owner=0 --group=0 \
    tools/thread-viz/{run.sh,update.py,trace.py,viewer.html,README.md,baseline.js,VERSION} \
    tools/thread-viz/bin/qemu-system-x86_64 \
    --transform 's#^LICENSE$#tools/thread-viz/LICENSE#' LICENSE
(cd "$OUT" && sha256sum thread-viz.tar.gz > thread-viz.tar.gz.sha256)
gh release create "v$VER" "$OUT/thread-viz.tar.gz" "$OUT/thread-viz.tar.gz.sha256" \
    --repo "$REPO" --title "thread-viz v$VER" --notes "${1:-thread-viz v$VER}"
echo "배포함: https://github.com/$REPO/releases/tag/v$VER"
