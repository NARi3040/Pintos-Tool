#!/usr/bin/env bash
# 사용법: tools/thread-viz/run.sh [테스트 이름...]   (기본: alarm/priority/bench 테스트 전부)
#         MLFQS=1 tools/thread-viz/run.sh           (mlfqs-* 테스트까지 전부. 오래 걸림)
#         tools/thread-viz/run.sh --no-update ...   (시작할 때 하는 자동 업데이트를 건너뜀)
# 결과: tools/thread-viz/traces/<test>.json, tools/thread-viz/data.js -> viewer.html 열기
set -u
# 동시 실행 관리에 wait -n -p를 씀 (bash 5.1 이상. 정글 Docker 이미지 ubuntu 22.04는 5.1)
if (( BASH_VERSINFO[0] * 100 + BASH_VERSINFO[1] < 501 )); then echo "bash 5.1 이상이 필요함 (지금 $BASH_VERSION)"; exit 1; fi
HERE="$(cd "$(dirname "$0")" && pwd)"
PINTOS="$HERE/../../pintos"
BUILD="$PINTOS/threads/build"
export PATH="$PATH:$PINTOS/utils"
mkdir -p "$HERE/traces"
# Windows git(core.autocrlf=true)로 받은 저장소는 utils/pintos 등의 shebang이 'python3\r'이 돼서 실행이 안 됨.
# 사용자 파일은 그대로 두고, shebang의 인터프리터로 직접 실행하는 래퍼를 traces/.shim에 만들어 PATH 맨 앞에 둠
SHIM="$HERE/traces/.shim"; rm -rf "$SHIM"
for f in "$PINTOS"/utils/*; do
    IFS= read -r first < "$f" 2>/dev/null || continue
    [[ $first == '#!'*$'\r' ]] || continue
    first="${first#\#!}"; mkdir -p "$SHIM"
    printf '#!/bin/sh\nexec %s "%s" "$@"\n' "${first%$'\r'}" "$f" > "$SHIM/${f##*/}" && chmod +x "$SHIM/${f##*/}"
done
[ -d "$SHIM" ] && export PATH="$SHIM:$PATH"
# 시작할 때 새 버전이 있으면 받아서 적용하고 새 run.sh로 다시 시작함 (네트워크가 안 되면 실패했다고 알리고 계속함).
# 건너뛰려면 --no-update 인자 또는 NO_UPDATE_CHECK=1
skip="${NO_UPDATE_CHECK:-0}"; args=()
for a in "$@"; do if [ "$a" = --no-update ]; then skip=1; else args+=("$a"); fi; done
set -- ${args[@]+"${args[@]}"}
if [ "$skip" != 1 ]; then
    python3 "$HERE/update.py" --auto; rc=$?
    [ "$rc" = 10 ] && THREAD_VIZ_UPDATED=1 exec "$HERE/run.sh" --no-update "$@"
    [ "$rc" != 0 ] && echo "업데이트 실패 (위 메시지 참고). 지금 버전으로 계속함"
elif [ -z "${THREAD_VIZ_UPDATED:-}" ]; then
    echo "[thread-viz] v$(cat "$HERE/VERSION" 2>/dev/null || echo '?') - 업데이트 확인 건너뜀"
fi

# 벤치 테스트(bench/): 처음 한 번 설치할지 묻고 대답을 bench.choice에 저장함. BENCH=1이면 설치, BENCH=0이면 안 함.
# 설치하면 pintos/tests/threads/의 tests.c, tests.h, Make.tests가 바뀌므로 빌드 전에 함. 지우려면 python3 tools/thread-viz/bench.py remove
python3 "$HERE/bench.py" auto || true

# 측정 전에 커널을 처음부터 다시 빌드함 (make -B). 다른 환경(호스트/컨테이너 gcc)에서 만든 오래된 오브젝트가 섞이지 않게.
# make clean은 build/를 통째로 지워 make check 결과까지 사라지므로 쓰지 않음. REBUILD=0이면 바뀐 파일만 빌드
[ "${REBUILD:-1}" = 1 ] && MFLAGS="-B" || MFLAGS=""
# gcc 14부터 원본 Pintos 코드의 경고 두 개(mmu.c의 int-conversion, stdio.c의 incompatible-pointer-types)가 에러가 됨.
# 그런 gcc(최신 호스트)에서만 경고로 되돌림. Make.config의 WARNINGS를 그대로 쓰고 끝에 덧붙임
WARN=()
if [ "$(gcc -dumpversion 2>/dev/null | cut -d. -f1)" -ge 14 ] 2>/dev/null; then
    WARN=("WARNINGS=-Wall -W -Wstrict-prototypes -Wmissing-prototypes -Wsystem-headers -Wno-error=int-conversion -Wno-error=incompatible-pointer-types")
fi
# kernel.lds.s는 make 내장 규칙(cpp threads/kernel.lds.S > threads/kernel.lds.s)으로 만들어짐.
# Windows 폴더를 마운트한 컨테이너(대소문자 구분 없음)에서는 build/threads/kernel.lds.s가 있으면 make가 그걸 kernel.lds.S로 잡아서
# 자기 자신을 읽으며 덮어써 빈 파일이 됨 (make -B마다 발생). 그러면 링크에서 _start_bss 등이 undefined가 되고 이후 make도 계속 재사용함.
# 빌드 전에 항상 지우면 VPATH로 원본(../../threads/kernel.lds.S)을 찾아 제대로 만듦
rm -f "$BUILD/threads/kernel.lds.s"
# 빌드 출력(원래 있던 경고 포함)은 traces/build.log에 두고, 실패했을 때만 보여줌
if ! make -s $MFLAGS -C "$PINTOS/threads" ${WARN[@]+"${WARN[@]}"} > "$HERE/traces/build.log" 2>&1; then
    grep -E "error|Error" "$HERE/traces/build.log" | head -20
    grep -q "undefined reference to \`_end_bss'" "$HERE/traces/build.log" \
        && echo "링커 스크립트(build/threads/kernel.lds.s) 생성 실패. 'cd pintos/threads && make clean && make' 후 다시 실행할 것"
    echo "빌드 실패: 위 컴파일 에러를 먼저 고칠 것 (전체 로그: tools/thread-viz/traces/build.log)"; exit 1
fi

# bench-*: thread-viz용 부하 테스트 (make check 대상 아님. 점수 차이를 보려고 넣음)
all=($(ls "$PINTOS/tests/threads"/{alarm,priority,bench}-*.ck 2>/dev/null | xargs -n1 basename | sed 's/\.ck$//'))
mlfqs=($(ls "$PINTOS/tests/threads/mlfqs"/mlfqs-*.ck 2>/dev/null | xargs -n1 basename | sed 's/\.ck$//'))
# mlfqs 테스트는 하나에 수 분씩 걸려서 기본 목록에서 뺌. MLFQS=1이면 포함
[ "${MLFQS:-0}" = 1 ] && all+=(${mlfqs[@]+"${mlfqs[@]}"})
tests=("$@")
[ ${#tests[@]} -eq 0 ] && tests=("${all[@]}")
for t in "${tests[@]}"; do
    [[ $t =~ ^[a-z0-9-]+$ ]] || { echo "테스트 이름이 이상함: $t"; exit 1; }
done

# 트레이스가 없거나, 예전 형식(status 없음)이거나, 깨졌거나, gdb 연결에 실패했거나, 채점 결과가 없는 테스트는 자동으로 같이 수집함
valid() {
    [ -f "$HERE/traces/$1.result" ] && python3 -c '
import json, sys
st = json.load(open(sys.argv[1])).get("status")
sys.exit(0 if st and st != "attach_failed" else 1)' "$HERE/traces/$1.json" 2>/dev/null
}
for t in "${all[@]}"; do   # AUTO=0이면 자동 수집 안 함 (지정한 테스트만)
    if [ "${AUTO:-1}" = 1 ] && [[ " ${tests[*]} " != *" $t "* ]] && ! valid "$t"; then
        tests+=("$t"); auto+=("$t")
    fi
done
[ -n "${auto+x}" ] && echo "트레이스 없음/오래됨 -> 자동 수집: ${auto[*]}"
rm -f "$HERE/traces"/*.tmp

# 뷰어 서버: 이미 떠 있으면 재사용, 없으면 백그라운드로 띄움. 수집 중에도 진행도를 볼 수 있게 먼저 띄움
# 기본은 127.0.0.1에만 열어서 같은 네트워크의 다른 기기에 소스가 노출되지 않게 함 (VIEW_BIND=0.0.0.0으로 변경 가능)
PORT="${VIEW_PORT:-8000}"
if ! (exec 3<>/dev/tcp/127.0.0.1/"$PORT") 2>/dev/null; then
    # 서브셸에서 띄워 이 스크립트의 작업 목록에서 빼둠 (중단 시 정리할 때 서버까지 꺼지지 않게)
    (nohup python3 -m http.server "$PORT" --bind "${VIEW_BIND:-127.0.0.1}" -d "$HERE" >/dev/null 2>&1 &)
    sleep 0.5
fi
# 포트를 다른 프로그램(VS Code 포트 포워딩 등)이 쓰고 있으면 뷰어가 안 뜨므로 알려줌
python3 -c 'import sys,urllib.request as u; u.urlopen("http://127.0.0.1:%s/viewer.html" % sys.argv[1], timeout=3)' "$PORT" 2>/dev/null \
    || echo "경고: 포트 $PORT에서 viewer.html이 안 열림. 다른 프로그램이 쓰는 중일 수 있음. VIEW_PORT=9000 처럼 바꿔서 다시 실행할 것"
URL="http://localhost:$PORT/viewer.html"
echo "진행 상황은 여기서 실시간으로 볼 수 있습니다: $URL"

# 뷰어가 1초마다 읽는 진행 상태 파일 (테스트 이름은 위에서 [a-z0-9-]만 허용해서 그대로 넣어도 JSON이 안 깨짐)
STARTED=$(date +%s); RESULTS=""; DONE=0; FINISHED=0
progress() {   # $1=running(true/false) $2=현재 테스트 $3=finished 스탬프(null 가능)
    printf '{"running":%s,"total":%d,"done":%d,"current":"%s","started":%d,"finished":%s,"results":[%s]}\n' \
        "$1" "${#tests[@]}" "$DONE" "$2" "$STARTED" "$3" "$RESULTS" > "$HERE/progress.json.tmp"
    mv "$HERE/progress.json.tmp" "$HERE/progress.json"
}

# traces/*.json을 data.js 하나로 합침 (Ctrl-C로 중단할 때도 불러서, 지금까지 수집한 것을 뷰어에서 볼 수 있게 함)
merge_data() {
STAMP=$(date +%s%3N)
python3 - "$HERE" "$STAMP" <<'EOF'
import json, os, sys
here, stamp = sys.argv[1], sys.argv[2]
d = os.path.join(here, "traces")
data = {}
for f in sorted(os.listdir(d)):
    if f.endswith(".json"):
        try:
            data[f[:-5]] = json.load(open(os.path.join(d, f)))
        except ValueError:
            print("경고: 깨진 트레이스 건너뜀:", f)
read = lambda p: open(p, errors="replace").read() if os.path.exists(p) else None
for name in data:
    data[name]["output"] = read(os.path.join(d, name + ".output")) or ""
    data[name]["trace_output"] = read(os.path.join(d, name + ".trace-output")) or ""
    res = read(os.path.join(d, name + ".result"))
    data[name]["result"] = {"pass": res.startswith("PASS"), "detail": res} if res else None
# 다 쓴 뒤에 이름을 바꿔서, 쓰는 도중에 새로고침해도 반쯤 쓴 data.js를 읽지 않게 함
out = os.path.join(here, "data.js")
with open(out + ".tmp", "w") as fp:
    fp.write("window.TRACES = " + json.dumps(data) + ";\nwindow.TRACES_STAMP = %s;\n" % stamp)
os.replace(out + ".tmp", out)
print("data.js:", ", ".join("%s(%d)" % (k, len(v["events"])) for k, v in data.items()))
r = [v["result"]["pass"] for v in data.values() if v["result"]]
print("PASS %d / %d" % (sum(r), len(data)))
EOF
}

# Ctrl-C나 에러로 끝나도 진행도가 "수집 중"으로 남지 않게 하고, 남은 QEMU/채점 실행을 정리함.
# Ctrl-C를 누르면 gdb가 커널을 멈추고 그때까지의 트레이스를 aborted로 저장한 뒤 여기로 옴
cleanup() {
    [ "$FINISHED" = 1 ] && return
    for j in $(jobs -p); do kill_tree "$j"; done   # 테스트 작업 아래의 timeout/pintos/QEMU/gdb까지 끔
    merge_data >/dev/null 2>&1 && progress false "" "$STAMP" || progress false "" null
    echo "중단됨. 지금까지 수집한 트레이스를 뷰어에 반영함: $URL"
}
trap cleanup EXIT
# Ctrl-C: 바로 끝내지 않고 중단 파일을 만들어 trace.py가 지금까지의 트레이스를 저장하게 한 뒤 종료함
STOPF="$HERE/traces/.stop"; rm -f "$STOPF"; INTERRUPTED=0
trap 'INTERRUPTED=1; touch "$STOPF"' INT TERM
stop_if_interrupted() { [ "$INTERRUPTED" = 1 ] && { rm -f "$STOPF"; exit 130; }; }

# 프로세스와 그 자손을 전부 끔. timeout은 자기 프로세스 그룹을 따로 만들어서 Ctrl-C나 그룹 kill이 안 닿음
kill_tree() { local c; for c in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$c"; done; kill "$1" 2>/dev/null; }

# gdb 포트가 LISTEN 중인지 /proc/net/tcp로 확인함. 접속해서 확인하면 QEMU가 gdb가 떠난 것으로 보고 커널을 돌려버려서 안 됨
port_listening() {   # IPv6가 꺼져 tcp6이 없어도 되게 cat으로 합쳐서 읽음
    cat /proc/net/tcp /proc/net/tcp6 2>/dev/null | awk -v p=":$(printf '%04X' "$1")$" '$4 == "0A" && $2 ~ p { found = 1 } END { exit !found }'
}

# 기록/재생(REPLAY=1, 기본): 채점용 실행을 QEMU로 기록하고, 트레이스는 그 기록을 재생하며 수집함 -> 트레이스 = 채점한 실행 그대로.
# 재생은 gdb가 멈춰도 결과가 같아서 여러 테스트를 동시에 돌려도 됨 (테스트마다 gdb 포트를 따로 씀).
# REPLAY=0: 예전 방식. 트레이스 실행과 채점 실행이 따로라 타이밍이 다를 수 있고, 동시에 돌리면 더 흔들려서 하나씩 돌림
REPLAY="${REPLAY:-1}"
if [ "$REPLAY" = 1 ]; then JOBS="${JOBS:-$(( $(nproc) / 2 ))}"; else JOBS=1; fi
[ "$JOBS" -ge 1 ] 2>/dev/null || JOBS=1
GDB_BASE="${GDB_BASE:-1234}"
export PATH="$HERE/bin:$PATH"   # QEMU 래퍼: RR/GDB_PORT가 없으면 원래 QEMU를 그대로 실행함

# 백그라운드 작업이 끝날 때까지 기다림. 중단 파일이 생기면 작업을 끔 (기록 실행엔 gdb가 없어서 직접 꺼야 함)
wait_or_stop() { while kill -0 "$1" 2>/dev/null; do [ -e "$STOPF" ] && { kill_tree "$1"; break; }; sleep 0.3; done; wait "$1" 2>/dev/null; }

# 테스트 하나: (기록) -> 트레이스 -> .ck 채점. 결과 요약은 traces/<test>.summary에 남기고 메인 루프가 출력함
run_one() {
    local t=$1 gport=$2 flags ck to gto line res st rr=() gpid=
    rm -f "$HERE/traces/$t".{json,out,output,err,result,trace-output,grade-err,rr,summary}
    # mlfqs 테스트: make check처럼 -mlfqs 옵션을 붙이고, 오래 걸리므로 시간 초과를 길게 잡음
    if [[ $t == mlfqs-* ]]; then flags="-mlfqs"; ck="$PINTOS/tests/threads/mlfqs/$t.ck"; to="${TRACE_TIMEOUT:-900}"; gto=480
    else flags=""; ck="$PINTOS/tests/threads/$t.ck"; to="${TRACE_TIMEOUT:-60}"; gto=60; fi
    # 채점용 실행은 make check와 같은 명령. timeout으로 감싸서 중단할 때 timeout만 끄면 그 아래 pintos와 QEMU까지 같이 꺼짐
    grade() { timeout $((gto + 30)) pintos -v -k -T $gto -m 20 -- -q $flags run "$t" > "$HERE/traces/$t.output" 2> "$HERE/traces/$t.grade-err" < /dev/null & gpid=$!; }
    local GRADE_MODE="${GRADE:-1}"
    if [ "$REPLAY" = 1 ]; then
        # 기록 모드는 부팅(로더가 디스크를 섹터 단위로 폴링)이 실제 시간으로 ~10초 더 걸림. 게스트가 보는 tick은 그대로라
        # pintos의 실제 시간 제한(-T)만 늘려 잡음
        timeout $((gto * 3 + 60)) env RR=record RR_FILE="$HERE/traces/$t.rr" \
            pintos -v -k -T $((gto * 3 + 30)) -m 20 -- -q $flags run "$t" > "$HERE/traces/$t.output" 2> "$HERE/traces/$t.grade-err" < /dev/null &
        wait_or_stop $!
        [ -e "$STOPF" ] && return
        rr=(env RR=replay RR_FILE="$HERE/traces/$t.rr")
        GRADE_MODE=replay
    fi
    [ "$GRADE_MODE" = 1 ] && grade
    timeout $((to + 120)) env GDB_PORT="$gport" ${rr[@]+"${rr[@]}"} pintos -v --gdb -m 20 -- -q $flags run "$t" \
        > "$HERE/traces/$t.trace-output" 2> "$HERE/traces/$t.err" < /dev/null &
    local qpid=$!
    # QEMU가 gdb 포트를 열 때까지 기다림 (고정 1초 대기는 부하가 크면 모자람). QEMU가 이미 죽었으면 안 기다림
    for _ in $(seq 120); do port_listening "$gport" && break; kill -0 $qpid 2>/dev/null || break; sleep 0.5; done
    # 멈춘 커널은 trace.py가 TRACE_TIMEOUT 뒤 멈추고, finish()가 그때까지의 트레이스를 저장함
    line=$(TRACE_OUT="$HERE/traces/$t.json" TRACE_TIMEOUT="$to" TRACE_STOP="$STOPF" timeout $((to + 120)) gdb -q -batch kernel.o \
        -ex "target remote localhost:$gport" -x "$HERE/trace.py" -ex continue -ex 'python finish()' 2>&1 | grep -E '^trace')
    # gdb가 끝났는데 QEMU가 남아 있으면(연결 실패 등) 정리함
    kill_tree $qpid; wait $qpid 2>/dev/null
    case "$GRADE_MODE" in
        1) wait_or_stop $gpid ;;
        seq) grade; wait_or_stop $gpid ;;
        replay) rm -f "$HERE/traces/$t.rr" ;;   # 기록은 재생 한 번에만 씀 (mlfqs는 수십 MB)
        *) cp "$HERE/traces/$t.trace-output" "$HERE/traces/$t.output" ;;
    esac
    # 채점: make check와 같은 .ck 사용. 결과 파일은 traces/에만 써서 make check 결과를 덮어쓰지 않음
    perl -I"$PINTOS" "$ck" "$HERE/traces/$t" "$HERE/traces/$t.result" >/dev/null 2>&1
    res=$(head -1 "$HERE/traces/$t.result" 2>/dev/null || echo '채점 실패')
    st=$(echo "$line" | sed -n 's/.* events, \([a-z_]*\) ->.*/\1/p')
    { echo "$line"; echo "RESULT $res"; echo "STATUS ${st:-none}"; } > "$HERE/traces/$t.summary"
}

cd "$BUILD"
# 슬롯마다 gdb 포트 하나 (GDB_BASE, GDB_BASE+1, ...). 다른 QEMU가 쓰는 포트면 그쪽에 붙어 엉뚱한 실행을 추적하거나 끄게 되므로 막음
for ((s = 0; s < JOBS; s++)); do
    p=$((GDB_BASE + s))
    for _ in $(seq 20); do port_listening $p || break; sleep 0.5; stop_if_interrupted; done
    if port_listening $p; then
        echo "gdb 포트 $p를 다른 프로그램이 쓰는 중임 (다른 pintos --gdb, 또는 VS Code가 컨테이너 포트를 포워딩한 것). 끄거나 GDB_BASE로 다른 포트를 줄 것"
        exit 1
    fi
done
[ "$JOBS" -gt 1 ] && echo "동시 실행: $JOBS개 (JOBS로 조절)"
declare -A slot_of=() test_of=()
free=($(seq 0 $((JOBS - 1)))); next=0; LAYOUT_SHOWN=0
running() { echo "${test_of[*]}" | tr ' ' ','; }
while [ $next -lt ${#tests[@]} ] || [ ${#test_of[@]} -gt 0 ]; do
    # 빈 슬롯에 다음 테스트를 띄움 (중단되면 새로 안 띄움)
    while [ $INTERRUPTED = 0 ] && [ $next -lt ${#tests[@]} ] && [ ${#free[@]} -gt 0 ]; do
        s=${free[0]}; free=("${free[@]:1}"); t=${tests[$next]}; next=$((next + 1))
        run_one "$t" $((GDB_BASE + s)) &
        slot_of[$!]=$s; test_of[$!]=$t
        progress true "$(running)" null
    done
    [ ${#test_of[@]} -eq 0 ] && break
    fin=""; wait -n -p fin "${!test_of[@]}" 2>/dev/null   # Ctrl-C를 받으면 bash가 fin을 unset한 채로 돌아옴 (set -u라 ${fin:-}로 읽음)
    [ -n "${fin:-}" ] && [ -n "${test_of[$fin]+x}" ] || continue
    t=${test_of[$fin]}; free+=(${slot_of[$fin]}); unset "test_of[$fin]" "slot_of[$fin]"
    sum="$OUTDIR/$t.summary"
    [ -f "$sum" ] || { echo "== $t: 중단됨"; continue; }
    res=$(sed -n 's/^RESULT //p' "$sum"); st=$(sed -n 's/^STATUS //p' "$sum")
    echo "== $t"
    # 감지한 구조(layout)는 처음 한 번만 보여줌
    if [ $LAYOUT_SHOWN = 0 ]; then grep '^trace layout' "$sum"; LAYOUT_SHOWN=1; fi
    grep '^trace' "$sum" | grep -v '^trace layout'
    echo "   $res"
    [ "$st" = attach_failed ] && echo "   gdb 연결 실패: 다음 실행 때 자동으로 다시 수집함"
    rm -f "$sum"
    DONE=$((DONE + 1))
    RESULTS="$RESULTS${RESULTS:+,}{\"test\":\"$t\",\"result\":\"$res\",\"status\":\"$st\"}"
    progress true "$(running)" null
done
stop_if_interrupted
progress true "(결과 합치는 중)" null

merge_data

# BASELINE=1: 이번 효율 측정값을 기준(baseline.js)으로 저장. 뷰어의 효율 점수는 이 기준 대비 비율임 (기준 = 100)
# 이미 있는 기준에 이번에 돌린 테스트만 덮어씀. PASS이고 측정값이 있는 테스트만 저장
if [ "${BASELINE:-0}" = 1 ]; then
python3 - "$HERE" "${tests[@]}" <<'EOF'
import json, os, re, sys
here, tests = sys.argv[1], sys.argv[2:]
out = os.path.join(here, "baseline.js")
base = {}
if os.path.exists(out):
    base = json.loads(re.sub(r"^window\.BASELINE = |;\s*$", "", open(out).read()))
for t in tests:
    p = os.path.join(here, "traces", t)
    try:
        d = json.load(open(p + ".json"))
        ok = open(p + ".result").read().startswith("PASS")
    except (OSError, ValueError):
        continue
    if ok and d.get("perf"):
        base[t] = d["perf"]
with open(out, "w") as fp:
    fp.write("window.BASELINE = " + json.dumps(base, sort_keys=True) + ";\n")
print("baseline.js: %d개 테스트 기준 저장" % len(base))
EOF
fi

progress false "" "$STAMP"
FINISHED=1
echo
echo "검사 완료. 브라우저에서 여기로 접속하면 볼 수 있습니다: $URL"
echo "(서버 종료: pkill -f \"http.server $PORT\")"
