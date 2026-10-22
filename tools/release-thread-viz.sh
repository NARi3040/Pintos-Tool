#!/usr/bin/env bash
# thread-viz를 GitHub Release로 배포함. 사용법: tools/release-thread-viz.sh "변경 내용"
# 보통은 v<X.Y.Z> 태그 push 시 .github/workflows/release.yml이 실행함. 로컬에서 직접 돌리면 커밋 안 된 파일이 배포될 수 있음
# tools/thread-viz/VERSION 값(MAJOR.MINOR.PATCH)이 릴리스 태그(v1.2.3)가 됨. 올리기 전에 VERSION을 먼저 올릴 것.
set -euo pipefail
REPO="${THREAD_VIZ_REPO:-NARi3040/Pintos-Tool}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
VER="$(tr -d '[:space:]' < "$HERE/tools/thread-viz/VERSION")"
# latest.json의 version은 정수로 비교하므로(v23 이하 update.py 포함) MINOR, PATCH는 100 미만이어야 순서가 맞음
[[ $VER =~ ^([0-9]+)\.([0-9]{1,2})\.([0-9]{1,2})$ ]] || { echo "VERSION이 MAJOR.MINOR.PATCH 형식(MINOR, PATCH는 100 미만)이 아니에요: $VER"; exit 1; }
CODE=$(( 10#${BASH_REMATCH[1]} * 10000 + 10#${BASH_REMATCH[2]} * 100 + 10#${BASH_REMATCH[3]} ))
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
cd "$HERE"
# 실행 결과물(traces, utraces, vtraces, data.js, udata.js, vdata.js, progress.json)은 빼고 도구 파일만 담음. 디렉터리 항목 없이 파일만
tar -czf "$OUT/thread-viz.tar.gz" --owner=0 --group=0 \
    tools/thread-viz/{run.sh,update.py,bench.py,trace.py,viewer.html,uprog.py,uprog.html,server.py,index.html,ui.css,tl.js,debug.py,debug.html,README.md,baseline.js,VERSION,.gitattributes} \
    tools/thread-viz/bin/qemu-system-x86_64 \
    tools/thread-viz/bench/bench-*.{c,ck} \
    --transform 's#^LICENSE$#tools/thread-viz/LICENSE#' LICENSE
(cd "$OUT" && sha256sum thread-viz.tar.gz > thread-viz.tar.gz.sha256)
# update.py가 GitHub API 대신 이 파일로 최신 버전을 확인함 (API는 비로그인 시간당 60회 제한)
python3 -c 'import json,sys; print(json.dumps({"version": int(sys.argv[1]), "name": sys.argv[2], "notes": sys.argv[3]}, ensure_ascii=False))' "$CODE" "$VER" "${1:-thread-viz v$VER}" > "$OUT/latest.json"
gh release create "v$VER" "$OUT/thread-viz.tar.gz" "$OUT/thread-viz.tar.gz.sha256" "$OUT/latest.json" \
    --repo "$REPO" --title "thread-viz v$VER" --notes "${1:-thread-viz v$VER}"
echo "배포했어요: https://github.com/$REPO/releases/tag/v$VER"
