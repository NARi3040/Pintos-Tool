# thread-viz — Pintos 스레드 흐름 시각화

KAIST Pintos (x86-64) Project 1 (Threads)용 도구예요. Project 2 (User Programs), Project 3 (Virtual Memory)도 지원해요 (아래 절). 테스트를 gdb로 추적해서 스레드 생성, ready_list,
sleep_list, lock / semaphore / condition 대기 리스트, donation 흐름을 웹페이지에서 한 단계씩 보여 줘요.
커널 코드는 수정하지 않아요.

## 필요한 것

- `qemu-system-x86_64`, `gdb`(Python 지원 빌드), `python3`, `perl`
- 정글 Pintos Docker 이미지에는 다 들어 있어요. `curl`은 없지만 처음 받을 때만 써요 (루트 README의 설치 절 참고). 업데이트는 `python3`로 받아요
- KAIST Pintos 원본 함수 이름이 그대로 있어야 해요 (`init_thread`, `thread_launch`, `thread_block`, `power_off` 등)

## 설치

`pintos/` 폴더와 같은 높이에 `tools/thread-viz/`가 오게 풀면 돼요.

Windows(Docker Desktop + VS Code)에서 설치나 실행이 막히면 [WINDOWS.md](https://github.com/NARi3040/Pintos-Tool/blob/main/WINDOWS.md)를 봐 주세요.

```
<repo>/
├── pintos/
└── tools/thread-viz/
    ├── run.sh
    ├── server.py                (뷰어 서버 + 런처 API)
    ├── index.html               (런처: 테스트 골라 실행)
    ├── ui.css                   (페이지 공통 스타일)
    ├── tl.js                    (뷰어 공통 타임라인: 확대/축소, 보이는 구간만 그림)
    ├── bin/qemu-system-x86_64   (QEMU 래퍼: 기록/재생, gdb 포트)
    ├── trace.py, viewer.html    (Project 1 트레이서, 뷰어)
    ├── uprog.py, uprog.html     (Project 2/3 트레이서, 뷰어)
    └── README.md
```

```bash
tar -xzf thread-viz.tar.gz -C <repo 루트>
```

## 업데이트

`run.sh`를 실행할 때마다 먼저 새 버전을 확인하고, 있으면 받아서 적용한 뒤 새 `run.sh`로 다시 시작해요. 결과(`최신 버전이에요` 또는 업데이트 내역)를 한 줄로 보여 줘요. 오프라인이거나 5초 안에 응답이 없으면 실패했다고 알리고 지금 버전으로 계속해요.

```bash
tools/thread-viz/run.sh --no-update ...      # 이번 실행은 업데이트 확인을 건너뛰어요 (NO_UPDATE_CHECK=1도 같아요)
python3 tools/thread-viz/update.py           # 수동 업데이트
python3 tools/thread-viz/update.py --check   # 확인만
```

- GitHub Releases(`NARi3040/Pintos-Tool`)의 최신 `thread-viz.tar.gz`를 받아 sha256을 확인한 뒤 `tools/thread-viz/`에 덮어써요. 실패하면 지금 버전으로 계속 실행해요
- `traces/`, `data.js`, `progress.json`은 건드리지 않아요. `baseline.js`는 이미 있으면 덮어쓰지 않아요
- 버전은 `VERSION` 파일의 정수예요
- `bench/`의 벤치 소스는 같이 갱신되고, 이미 설치한 사본은 다음 `run.sh` 때 바뀐 것만 다시 복사해요. `pintos/`의 다른 파일은 건드리지 않아요

## 사용법

repo 루트에서 실행해요.

```bash
tools/thread-viz/run.sh                          # 런처 페이지를 열어요. 거기서 Project 1/2와 테스트를 골라 실행
tools/thread-viz/run.sh threads                  # alarm-*, priority-*, bench-* 전부 (첫 실행 2~3분)
tools/thread-viz/run.sh priority-donate-nest     # 원하는 테스트만
tools/thread-viz/run.sh priority-sema priority-condvar
```

### 런처 (인자 없이 실행)

인자 없이 실행하면 서버(`server.py`)만 띄우고 `http://localhost:8000/index.html`을 브라우저로 열어요. 열 수 없는 환경이면 주소만 출력해요 (`NO_OPEN=1`이면 열지 않아요).
페이지에서 Project 1 / 2 / 3을 고르고 테스트를 체크해서 실행해요. 테스트 옆에는 지난 결과(PASS/FAIL)가 붙어요.

- 실행 중에는 진행도와 `run.sh` 출력이 보이고, "중지"는 터미널의 Ctrl-C와 같아요 (그때까지 저장해요)
- 실행이 끝나면 "결과 보기"로 뷰어로 가요
- 이미 실행 중이면(이 페이지에서 시작한 것이든 터미널에서 돌린 것이든) 새로 시작하지 않아요
- 실행 요청은 이 페이지에서만 받아요. 다른 사이트의 페이지가 localhost로 요청을 보내 실행시키지 못하게 막아 뒀어요
- 예전 버전이 띄운 정적 서버(`python3 -m http.server`)가 같은 포트에 있으면 끄고 새 서버로 바꿔요

### 터미널에서 바로 실행

인자를 주면 런처 없이 바로 돌려요. 실행하면 처음에 접속 주소가 나와요. 수집 중에도 그 주소로 들어가면 진행도가 실시간으로 보이고, 끝나면 자동으로 새로고침돼요.

```
진행 상황은 여기서 실시간으로 볼 수 있어요: http://localhost:8000/viewer.html
```

- devcontainer 안에서 돌렸으면 VS Code가 포트를 자동으로 포워딩해서 같은 주소로 열려요. 열리지 않으면 VS Code PORTS 탭에서 포워딩된 주소(예: `localhost:8001`)를 확인해 주세요
- 코드를 고친 뒤 다시 `run.sh`만 실행하면 돼요. 실행할 때마다 커널을 처음부터 다시 빌드해요(`make -B`)
  - `make clean`은 쓰지 않아요. `build/`를 통째로 지워 `make check` 결과까지 사라지기 때문이에요. `make -B`는 커널만 다시 빌드하고 `build/tests/`의 결과 파일은 그대로 둬요

### 기록/재생 (트레이스 = 채점한 실행)

기본(`REPLAY=1`)으로 테스트마다 QEMU를 두 번 돌려요.

1. **기록**: gdb 없이 `make check`와 같은 명령으로 돌리면서 QEMU record/replay(`-icount rr=record`)로 실행을 기록해요. 이 출력으로 채점해요
2. **재생**: 기록을 재생하면서 gdb로 트레이스를 수집해요. 재생은 명령어 하나, 인터럽트 하나까지 기록과 똑같아서 gdb 훅이 아무리 멈춰도 결과가 바뀌지 않아요

그래서 화면의 흐름, tick, 선점 지연이 채점한 실행 그대로예요. 같은 기록을 다시 재생하면 트레이스도 똑같이 나와요.
gdb가 타이밍을 흔들지 않으니 테스트를 동시에 돌려요 (`JOBS`, 기본 코어 수의 절반. 테스트마다 gdb 포트를 따로 써요).

- 기록 실행은 부팅이 실제 시간으로 ~10초 더 걸려요 (로더가 디스크를 섹터 단위로 폴링하는 구간). 게스트가 보는 tick은 그대로예요
- 기록/재생이 안 되는 QEMU면 `REPLAY=0`으로 예전 방식(트레이스 실행과 채점 실행을 따로, 하나씩)을 써요
- 기록은 실제 실행이라 실행마다 타이밍이 조금씩 다를 수 있어요 (`make check`도 마찬가지예요). 결정적인 건 재생이에요

### 벤치 테스트 (`bench-*`)

공식 테스트는 짧고 스레드가 적어서 맞게 짠 구현은 거의 다 100점이 나와요. 점수 차이를 보려고 부하 테스트 3개와, 복잡도 판정용 `bench-scale`을 넣었어요.
소스는 `tools/thread-viz/bench/`에 있어요. `run.sh`를 처음 실행할 때 설치할지 물어보고 대답을 `bench.choice`에 저장해요. `y`면 `pintos/tests/threads/bench-*.c`/`.ck`를 복사하고 `tests.c`, `tests.h`에 등록하고, `Make.tests`의 `threads_SRC`에만 추가해서 커널에는 들어가지만 `make check` 대상(`threads_TESTS`)은 아니에요. **이때 사용자 저장소의 이 세 파일이 바뀌어요** (`git diff`에 보여요).

```bash
BENCH=1 tools/thread-viz/run.sh              # 묻지 않고 설치 (BENCH=0이면 설치 안 함)
python3 tools/thread-viz/bench.py status     # 설치 상태
python3 tools/thread-viz/bench.py remove     # 파일과 등록을 되돌리고 다시 묻지 않아요
```

- 터미널이 아니면(파이프 등) 묻지 않고 설치하지 않아요. 예전에 직접 설치해 둔 사람은 동의한 것으로 보고 빠진 벤치만 채워요
- 등록할 위치를 찾지 못하면(파일 형식이 다름) 아무것도 바꾸지 않고 알려 줘요

| 테스트 | 하는 일 | 테스트 자체 검사 (FAIL 조건) |
|---|---|---|
| `bench-lock-storm` | priority가 다른 10개 스레드가 락 2개(A→B 중첩)를 쥔 채 잠들며 3번씩 경쟁. donation, 중첩 donation, 락 넘겨주기 | 락을 다 놓은 뒤 priority가 원래 값이 아님 |
| `bench-sleep-wave` | 12개 스레드가 같은 tick을 목표로 잠들었다 한꺼번에 깨어나기를 4번 | 같은 tick에 깬 스레드가 priority 높은 순서로 실행되지 않음 |
| `bench-cond-relay` | 8개 스레드가 cond에서 기다리고 가장 낮은 main이 하나씩 깨움. 깬 스레드는 donation을 거쳐 main을 선점. 3라운드 | 라운드마다 priority 높은 순서로 깨어나지 않음 |
| `bench-scale` | 스레드 48개로 sleep_list, 락 대기열, condition 대기열을 0에서 48까지 늘렸다 줄임 (복잡도 판정용, 아래 참고) | 일찍 깨어난 스레드가 있음 |

### 효율 점수

정확성 점수와 따로 매기는 점수예요. 기록/재생일 때만 나와요 (`REPLAY=0`이면 없어요).

- 재생 중에 gdb의 `monitor info replay`로 QEMU가 센 실행 명령어 수를 읽어서 재요. 재생은 결정적이라 같은 코드면 거의 같은 값이 나와요 (실제 시간과 달리 호스트 부하에 흔들리지 않아요)
- 지표 3개
  - **API 호출 명령어 합**: `lock_*`, `sema_*`, `cond_*`, `thread_set_priority`, `thread_yield`, `thread_unblock`, `timer_sleep`을 호출한 스레드가 진입~복귀 사이에 직접 실행한 명령어 수. 막혀서 다른 스레드가 돈 시간과 인터럽트 처리는 빼요. 바깥 호출만 합산해요 (lock_acquire 안의 sema_down을 두 번 세지 않아요)
  - **타이머 인터럽트 평균 명령어**: `timer_interrupt` 1번에 드는 명령어 수 (sleep_list 처리, `thread_tick`). tick이 20번 미만인 테스트에선 값이 흔들려서 점수에 쓰지 않아요
  - **컨텍스트 스위치 수**
- 점수 = 100 × (기준값 / 지금값)의 기하평균. 기준과 같으면 100, 덜 쓰면 100 초과예요. 정확성 실패(F)면 효율 점수는 없어요
- 기준은 `baseline.js`예요. 지금 구현을 기준으로 저장하려면 `BASELINE=1 tools/thread-viz/run.sh`를 실행해요 (이번에 돌린 테스트만 덮어써요)
- 들어 있는 `baseline.js`는 이 저장소의 구현으로 만든 거예요. 다른 구현과 비교할 때 그대로 두면 돼요
- `thread_create`는 재지 않아요. 비용 대부분(~11만 명령어)이 원본 `palloc`의 페이지 채우기라 동기화 비용을 가리기 때문이에요
- 메모리 사용량은 재지 않아요. 스레드마다 4KB 페이지 하나로 고정이라 구현마다 차이가 거의 없어요
- 확인한 예 (효율을 일부러 나쁘게 바꾼 버전)
  - 타이머가 sleep_list를 끝까지 훑음: alarm 테스트 60~81점 (타이머 평균 +86~368%)
  - `sema_up`에서 매번 `list_sort`: bench-lock-storm 94점 (API 명령어 +21%)
  - 같은 priority에도 양보: alarm-single 90점 (스위치 +29%)
- 측정 훅이 늘어서 트레이스 수집이 ~40% 느려져요

### 복잡도 판정 (절대 기준)

효율 점수가 기준 구현 대비 상대값이라면, 이쪽은 기준 없이 구현 자체가 효율적인지 판정해요. `bench-scale`을 돌렸을 때만 나와요 (기록/재생일 때만).

- 호출이 시작될 때 그 함수가 다루는 리스트의 길이(`timer_*`는 sleep_list, `sema_*`/`lock_*`/`cond_*`는 기다리는 줄, `thread_*`는 ready_list)와 그 호출의 명령어 수를 모아요
- 길이가 늘 때 비용이 얼마나 느는지로 **상수 / 선형 / 선형 초과**를 갈라요. 길이 최대일 때 늘어난 양이 길이 0 비용의 25% 미만이면 상수, 증가가 길이의 1.5제곱보다 가파르면 선형 초과, 그 사이는 선형이에요. n log n(`list_sort`)은 선형 초과와 구분되지 않을 수 있어요
- 허용 상한: `timer_interrupt`는 **상수** (깨울 스레드가 없으면 sleep_list를 훑지 않아야 해요), 나머지는 **선형** (순서대로 끼워 넣거나 가장 높은 priority를 고르는 건 정상이에요). 상한을 넘으면 ❌
- 길이가 16 이상이고 길이 종류가 4개 이상 나온 함수만 판정해요. 표본이 적은 함수(`thread_yield` 등)는 빠져요
- 확인한 예: 정렬된 sleep_list 구현은 `timer_interrupt` 상수(✅), 매 tick마다 sleep_list를 끝까지 훑게 바꾸면 선형(❌, 증가 +618%)

### MLFQS 테스트

`mlfqs-*` 테스트는 하나에 수 분씩 걸려서 기본 목록에 없어요. 이름을 직접 주거나 `MLFQS=1`을 붙여 주세요.
`-mlfqs` 커널 옵션과 긴 시간 초과(900초)는 자동으로 붙어요.

```bash
tools/thread-viz/run.sh mlfqs-load-1 mlfqs-fair-2   # 원하는 것만
MLFQS=1 tools/thread-viz/run.sh threads             # alarm/priority + mlfqs 전부 (수십 분)
```

MLFQS 모드로 돈 테스트는 화면에 MLFQS 패널이 생겨요. 스레드별 priority / recent_cpu / nice 그래프와 load_avg 그래프 (가로축 tick)를 보여 줘요. 공식이 틀리면 해당 이벤트에 MLFQS 위반이 표시돼요 (테스트가 PASS여도 잡힐 때가 있어요).

### 옵션 (환경 변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `VIEW_PORT` | `8000` | 뷰어 서버 포트 |
| `NO_OPEN` | `0` | `1`이면 인자 없이 실행할 때 브라우저를 열지 않고 주소만 출력 |
| `TRACE_TIMEOUT` | `60` (mlfqs는 `900`, Project 2는 Make.tests 제한 시간의 2배, 최소 `120`, Project 3은 최소 `900`, `REPLAY=1`이면 최소 `1800`) | 테스트 하나가 이 시간(초) 안에 끝나지 않으면 멈춘 것으로 보고 그때까지 저장 |
| `MLFQS` | `0` | `1`이면 mlfqs 테스트도 기본 목록과 자동 수집에 포함 |
| `REBUILD` | `1` | `1`이면 측정 전에 커널 전체를 다시 빌드(`make -B`). `0`이면 바뀐 파일만 빌드 |
| `AUTO` | `1` | `0`이면 트레이스가 없는 테스트를 자동으로 같이 수집하지 않고 지정한 테스트만 돌림 |
| `VIEW_BIND` | `127.0.0.1` | 뷰어 서버가 열리는 주소. 다른 기기에서 보려면 `0.0.0.0` (같은 네트워크에 소스가 노출돼요) |
| `REPLAY` | `1` | `1`이면 기록/재생 (위 설명). `0`이면 예전 방식 |
| `JOBS` | 코어 수 / 2 | 동시에 돌릴 테스트 수 (`REPLAY=1`일 때만. `0`이면 1) |
| `GDB_BASE` | `1234` | gdb 포트 시작 번호. 동시 실행 슬롯마다 `GDB_BASE`, `+1`, ... 을 씀 |
| `TRACE_MAX_EVENTS` | `30000` | Project 2/3만. 이벤트가 이만큼 쌓이면 기록을 멈추고 커널은 끝까지 돌림 (누수 검사는 안 함) |
| `BASELINE` | `0` | `1`이면 이번 효율 측정값을 `baseline.js`에 기준으로 저장 |
| `GRADE` | `1` | `REPLAY=0`일 때만 씀. `1`이면 채점용으로 트레이스 없는 실행을 따로 돌림(동시 실행). `seq`면 트레이스 수집 뒤에 따로 돌림(코어가 적어 채점 타이밍이 흔들릴 때). `0`이면 생략하고 트레이스 실행 출력으로 채점 (빠르지만 타이밍 테스트가 틀리게 FAIL 날 수 있어요) |

```bash
VIEW_PORT=9000 TRACE_TIMEOUT=30 tools/thread-viz/run.sh threads
```

### 중단하기

수집 중에 Ctrl-C를 누르면 지금 돌던 테스트를 그 자리에서 멈추고, 그때까지의 트레이스를 `aborted`로 저장한 뒤 뷰어에 반영하고 끝나요.
QEMU, gdb, 채점 실행도 같이 정리해요.

### 서버 끄기

```bash
pkill -f "server.py 8000"
```

### 결과 파일 (`traces/`)

| 파일 | 내용 |
|---|---|
| `<test>.json` | 트레이스 (이벤트, 스냅샷, 소스) |
| `<test>.output` | 채점용 실행(기록 실행, 트레이스 없음)의 출력. 이걸로 채점해요 |
| `<test>.trace-output` | 트레이스 실행(재생)의 출력. 기록/재생이면 `.output`과 같아야 해요 |
| `<test>.rr`, `<test>.rr.d*.qcow2`, `<test>.cmd` | QEMU 기록과 디스크(2초마다 스냅샷 포함), 재생 명령줄. 디버거가 써요. 다음 실행 때 지워져요. 테스트 하나에 수~수십 MB(Project 1 전체 약 150MB)라 공간이 모자라면 `rm -f tools/thread-viz/traces/*.rr* tools/thread-viz/utraces/*.rr*`로 지워도 돼요 (트레이스는 그대로 보이고, 디버거만 다시 실행하라고 해요) |
| `<test>.gdb` | 트레이스를 모은 gdb의 출력. 트레이스가 없을 때 원인이 여기 있어요 |
| `<test>.result` | `.ck` 채점 결과 (PASS/FAIL과 차이) |
| `<test>.err`, `.grade-err` | QEMU/pintos 에러 출력 |

### 트레이스 상태

| 상태 | 뜻 | 화면 |
|---|---|---|
| `ok` | `power_off`까지 정상 종료 | |
| `panic` | Kernel PANIC (위치와 ASSERT 조건식 기록) | `(PANIC)` 💥 |
| `timeout` | `TRACE_TIMEOUT` 안에 안 끝남 (무한루프/데드락 의심). 멈춘 시점까지 저장 | `(시간 초과)` ⏱ |
| `aborted` | power_off 전에 끝남 (Ctrl-C, QEMU 비정상 종료, 연결 끊김) | `(중단됨)` ⛔ |
| `attach_failed` | gdb가 QEMU에 못 붙어 이벤트가 0개 | 목록에서 빠지고 위쪽에 "수집 실패"로 표시. 다음 실행 때 자동으로 다시 수집 |

## 화면 보는 법

- 위쪽: 테스트 선택(✅ PASS / ❌ FAIL / ❔ 채점 없음, 재미용 점수), PASS 개수와 평균 점수, ◀ ▶ / ←→ 키로 한 단계씩, space 재생, `n` 키로 다음 규칙 위반으로 이동
- 주소 뒤에 `#테스트이름/번호`를 붙이면 그 단계로 바로 열려요 (예: `viewer.html#priority-donate-chain/60`)
- 이번 이벤트: 어떤 함수가 어디서 불렸는지, 규칙 위반이면 빨간 경고. 소스 패널(접기/펼치기)에서 호출한 줄 주변 코드
- 이벤트 직후 상태: CPU / ready_list / sleep_list / BLOCKED
- 동기화 객체: lock(holder, 대기자), semaphore(value, 대기자), condition(대기자)
- donation: 대기 체인(`high → L2 → medium → L1 → main`)과 스레드별 donations 리스트
- 타임라인: 스레드별 상태 막대. 누르면 그 이벤트로 가고, 올려 두면 설명이 떠요. `+`/`-` 키나 Ctrl(⌘)+휠로 확대·축소, `0` 키나 맞춤 버튼으로 전체 보기 (Project 2/3 뷰어도 같아요). 마우스로 끌면 옆으로 움직여요
- 효율 지표: 스위치 / yield 횟수, 스레드별 실행·대기 tick, 선점 지연, 재미용 점수, 효율 점수와 함수별 평균 명령어 수 (기준 → 지금)
- 채점 결과(.ck): FAIL이면 자동으로 펼쳐져요

## Project 2 (User Programs)

`userprog` 테스트도 gdb로 추적해요 (커널 코드는 수정하지 않아요). 결과는 `uprog.html`에서 봐요.

기본은 `REPLAY=0`이에요. QEMU 기록 모드가 디스크 I/O에서 극단적으로 느리기 때문이에요 (`syn-read`: 일반 5초, 기록 620초). 그래서 채점 실행과 트레이스 실행을 따로, 테스트끼리는 동시에 돌려요. 두 실행의 출력이 다르면 뷰어의 결과 옆에 "트레이스 실행은 출력이 다름"이 붙어요. `REPLAY=1`로 기록/재생을 쓸 수도 있지만 파일 시스템 테스트는 수십 분 걸려요.

```bash
tools/thread-viz/run.sh userprog                  # Project 2 테스트 전부 (tests/userprog, tests/filesys/base)
tools/thread-viz/run.sh args-multiple fork-once   # 원하는 테스트만. 이름이 Project 2 테스트면 자동으로 이 모드
```

- `pintos/userprog/build`에서 돌려요. 실행 명령(인자, `-p`로 넣는 파일, 제한 시간)은 `make check`가 쓰는 것을 make에서 그대로 받아와요
- Project 1 테스트와 한 번에 섞어 돌릴 수 없어요
- `multi-oom`은 프로세스를 수천 개 만들어서 기본 목록에서 뺐어요. 이름을 직접 주면 돌리지만 앞부분 `TRACE_MAX_EVENTS`개 이벤트만 기록해요
- 결과 파일은 `utraces/`, `udata.js`예요. 형식은 `traces/`와 같아요

### 기록하는 것

훅은 학생이 고치지 않는 원본 코드에만 걸어요. fd 테이블이나 자식 리스트를 어떻게 만들었는지와 상관없이 동작해요.

| 이벤트 | 훅 | 내용 |
|---|---|---|
| 시스템 콜 | `syscall_handler` 진입, `syscall_entry`의 복귀 지점 | 번호, 인자(문자열 인자는 내용, `write`는 버퍼 앞부분), 잘못된 포인터 여부, 반환값 |
| 유저 진입 | `do_iret` (유저 코드 세그먼트일 때만) | 레지스터와 rsp부터 `USER_STACK`까지의 스택 바이트 |
| 프로세스 | `init_thread`, `process_exec`, `process_wait`, `thread_exit` | 부모-자식 관계, exec 명령줄 |
| fault | `page_fault`, `kill` | 주소(cr2), rip, 유저/커널, 예외 종류. 유저 주소는 프로그램 ELF로 함수와 소스 줄을 찾아요 |
| 콘솔 출력 | `putchar_have_lock` | 어느 프로세스가 어떤 줄을 찍었는지 |
| 페이지/파일 | `palloc_get_multiple`/`palloc_free_multiple`, `file_open`/`file_duplicate`/`file_reopen`/`file_close` | 누수 검사용. 이벤트로는 보이지 않고 개수만 기록해요. 같은 `struct file`을 두 번 `file_close`하면 이벤트로 남겨요 |
| 커널 스택 | 시스템 콜 복귀 지점 | 그때 `struct thread`의 `magic`이 깨졌는지 |
| 멈춘 스레드 | 시간 초과/중단 때 한 번 | 살아 있는 스레드마다 저장된 `tf`의 rbp 체인으로 호출 경로를 풀어요. `lock_acquire`에서 멈췄으면 그 lock과 `holder` |

### 화면 (`uprog.html`)

- 프로세스 트리: 이벤트 직후 각 프로세스의 상태와, 진행 중인 시스템 콜(예: `wait(5)` 대기 중), 종료 코드
- 스케줄러 패널: Project 1 뷰어처럼 CPU / `ready_list` / `sleep_list` / BLOCKED 레인과 lock·semaphore 대기열을 카드로 보여 줘요 (직전 이벤트 뒤와 달라진 카드는 노란 배경). 그 아래에 donation 대기 체인(lock을 기다림 → 주인 → …, 순환이면 데드락 표시)과 스레드별 donations 리스트가 있어요. 프로세스 트리에도 우선순위를 붙여요. 이벤트 직후 `ready_list`, `sleep_list` 순서와 스레드마다 priority (base priority가 다르면 같이), 주인이 있는 lock과 기다리는 스레드가 있는 lock/semaphore를 보여 줘요. 리스트와 필드는 Project 1 뷰어와 같은 방식으로 자동 감지해요. 위쪽 "우선순위·대기열 보기"로 끄고 켤 수 있어요
- 타임라인: 프로세스별 RUNNING/READY/BLOCKED, 시스템 콜, fork(세로선), 종료(X), fault. 아래 그래프는 테스트 시작 뒤 할당한 페이지 수와 열린 파일 수예요
- 유저 스택 탭: `process_exec` 뒤 처음 유저로 들어갈 때의 스택을 8바이트 칸 단위로 보여 주고 각 칸에 의미를 붙여요 (문자열, 패딩, `argv[i]`, `argv[argc]`, 가짜 반환 주소)
- fd 테이블 탭: 시스템 콜 반환값으로 재구성한 프로세스별 fd 표 (open → 추가, close → 삭제, fork → 복사)
- page fault / 예외 탭, 누수 검사 탭, 채점 결과, 테스트 출력

### 자동 검사

| 검사 | 기준 |
|---|---|
| 인자 전달 | `rdi` = argc, `rsi`가 스택 안의 argv 배열, `argv[i]`가 명령줄 단어와 같음, `argv[argc]` = NULL, rsp 8바이트 정렬. `rsi != rsp + 8`이나 가짜 반환 주소가 0이 아닌 것은 참고로만 표시 |
| fork | 자식이 유저로 돌아갈 때 rax = 0, rip/rsp가 부모가 fork를 부른 위치와 같음, 부모가 받은 값 = 자식 tid |
| wait | 반환값 = 자식의 exit 코드 (커널이 죽였으면 -1). 자식이 아니거나 이미 wait한 pid면 -1 |
| 잘못된 포인터 | 포인터 인자가 매핑 안 됐거나 커널 영역인데 시스템 콜이 정상 반환하면 오류. 커널 모드에서 유저 주소 fault는 참고로 표시 |
| 종료 메시지 | 유저 프로세스가 끝날 때 `이름: exit(코드)`가 찍혔고 코드가 맞는지. `sys_exit`에서 찍든 `process_exit`에서 찍든 둘 다 정상 |
| fault | 유저 코드가 잘못된 주소를 건드렸으면 그 프로세스가 끝나야 함. 커널 코드 fault는 오류 |
| 누수 | `power_off` 때 테스트 시작 후 할당한 페이지가 남았거나, 연 파일이 안 닫혔거나, `malloc`한 블록을 `free` 안 했으면 오류. 블록이 남아서 같이 안 풀린 malloc arena 페이지는 페이지 표에서 빼고 블록 쪽(실제로 malloc한 곳)으로만 보여요. 이미 끝난 스레드의 `struct thread` 페이지는 스케줄러가 나중에 지우므로 제외해요. 누수 항목마다 할당 이벤트로 이동하는 링크와, 소유 프로세스가 이미 종료했는지(=종료 때 안 풀음)를 보여 줘요. exec한 프로세스가 안 끝난 채 꺼졌으면 누수 대신 그걸 오류로 보여 줘요 |
| fd 반환값 | 시스템 콜 반환값으로 다시 만든 fd 표 기준. open이 이미 열린 fd나 0/1을 줌, 빈 이름 open이 성공, open이 fd를 줬는데 열린 파일이 없음, 안 열린 fd의 read/write가 -1이 아님, read/write가 요청 크기보다 큼, 콘솔 `write(1, …, n)`이 n이 아님, exec이 -1 말고 다른 값으로 돌아옴. close 뒤에도 파일이 열려 있거나 열린 fd의 read/write가 -1이면 참고 |
| fork fd 복제 | 부모 fd가 가리키는 `struct file`을 자식이 `file_duplicate`/`file_reopen`하지 않았으면 참고 (같은 객체 공유) |
| 파일 이중 닫기 | 이미 `file_close`한 `struct file`을 다시 닫으면 오류 |
| 커널 스택 넘침 | 시스템 콜에서 돌아올 때 `magic`이 깨졌으면 오류 |
| 시간 초과 | 멈춘 스레드별 호출 경로를 보여 줘요. lock을 서로 기다리면 데드락, 이미 끝난 스레드가 쥔 lock을 기다리면 "lock을 놓지 않고 종료", 자기가 쥔 lock을 다시 잡으면 그것도 오류 |
| panic | 흔한 ASSERT(`is_thread`, `bitmap_all`, `!intr_context ()`, `lock_held_by_current_thread`, `is_interior` 등)는 원인 후보를 같이 보여 줘요 |

검사는 힌트예요. 판정은 `make check` 결과를 따라 주세요.

## Project 3 (Virtual Memory)

`vm` 테스트를 `pintos/vm/build`에서 Project 2와 같은 트레이서(`uprog.py`)로 돌려요. 결과는 `uprog.html?vm`에서 봐요 (`vtraces/`, `vdata.js`). Project 2 화면과 검사는 그대로고, **가상 메모리** 탭과 fault 처리 결과가 붙어요.

```bash
tools/thread-viz/run.sh vm                        # tests/vm, tests/vm/cow 전부
tools/thread-viz/run.sh lazy-anon mmap-read       # 이름이 전부 tests/vm 테스트면 자동으로 이 모드
tools/thread-viz/run.sh vm args-single fork-once  # Project 2 테스트를 VM 빌드로 (make check도 VM 빌드로 돌림)
```

- 기본은 Project 2처럼 `REPLAY=0`(채점 실행과 트레이스 실행을 따로)이에요
- fault마다 훅이 여러 번 멈춰서 느려요. lazy/mmap/pt 테스트는 수 초~수십 초지만 swap 테스트는 오래 걸려요 (`swap-anon`: fault 약 1만 개, 15분 안팎). 그래서 트레이스 시간 제한이 최소 900초(swap 테스트는 1800초)예요. 시간 제한에 걸리면 그때까지의 트레이스를 저장하고, 채점은 따로 돈 실행 기준이라 영향이 없어요
- 페이지 상태 변화는 그 변화를 일으킨 스레드의 다음 이벤트에 붙어요. fault 처리 중 디스크 I/O로 다른 프로세스가 돌아도 그 fault 이벤트에 붙어요

### 기록하는 것

학생이 만드는 SPT(해시 등)는 직접 읽지 않아요. 스켈레톤에 원래 있는 함수에만 훅을 걸어 페이지마다 상태를 다시 만들어요. 그래서 SPT를 어떤 자료구조로 만들었든 동작해요. 함수 이름을 바꿨으면 그 부분만 빠져요 (`trace warning`).

| 훅 | 알아내는 것 |
|---|---|
| `uninit_new` | SPT에 페이지가 들어감: va, 최종 타입(anon/file, MARKER 비트), 초기화 함수(`lazy_load_segment` 등). 쓰기 가능 여부는 `vm_alloc_page_with_initializer`의 `writable` 인자 |
| `anon_initializer`, `file_backed_initializer` | lazy 로딩 (uninit → anon/file) |
| `pml4_set_page`, `pml4_clear_page`, `pml4_destroy` | 프레임 매핑/해제 (kva, 쓰기 가능). pml4로 어느 프로세스 것인지 찾음 |
| `anon_swap_out`/`_in`, `file_backed_swap_out`/`_in` | swap out / in (file 페이지는 파일로 내보냄) |
| `uninit_destroy`, `anon_destroy`, `file_backed_destroy` | SPT에서 제거 |
| `vm_try_handle_fault` 복귀 | fault 주소, 유저/커널, 읽기/쓰기, 처리 결과(true/false). VM 빌드에서는 `page_fault` 대신 여기서 fault를 기록해요 |
| `mmap`/`munmap` 시스템 콜 | 인자와 반환값. 반환값은 포인터라 rax 전체를 써요 (`NULL (MAP_FAILED)`). length는 64비트 그대로 남겨요 (`mmap-kernel`) |

### 화면

- **가상 메모리 탭**: 이벤트 시점의 프로세스별 페이지 표예요. 연속 페이지는 범위로 묶어요. 종류(`uninit → anon` 등), 쓰기 가능, 상태(lazy / 메모리 / swap 디스크 / 파일로 내보냄 / 매핑 해제됨), 초기화 함수 또는 kva를 보여 줘요. 이번 이벤트에서 바뀐 줄은 노란색이에요. 위쪽에 프레임 사용량(/ user pool 크기), swap된 페이지 수, 누적 fault·swap 횟수가 있어요
- **page fault**: 처리했으면 무엇을 했는지 붙여요 (`lazy 로딩 (anon, lazy_load_segment)`, `swap in`, `파일에서 다시 올림`, `스택 확장`, `쓰기 권한 처리 (copy-on-write)`, `다른 페이지 n개 내보냄`). 스택 확장은 fault 중에 새 anon 페이지가 생긴 경우예요. swap in은 내보낸 적이 있는 페이지일 때만이고, lazy 로딩에 `file_backed_swap_in`을 다시 쓰는 구현도 lazy 로딩으로 보여요. 타임라인에서 처리된 fault는 작은 주황 표시예요
- 위쪽 "처리된 page fault 숨김"으로 정상 처리된 fault를 이벤트 목록에서 뺄 수 있어요 (swap 테스트처럼 fault가 수천 개일 때)

### 자동 검사

| 검사 | 기준 |
|---|---|
| 처리 안 됨 | SPT에 있는 페이지(아직 안 올림, swap됨, 파일로 내보냄)의 not-present fault인데 `vm_try_handle_fault`가 false |
| 매핑 없이 true | true를 반환했는데 그 페이지가 프레임에 매핑 안 됨 (같은 fault가 계속 남) |
| 잘못된 주소 처리 | NULL 근처나 커널 주소 fault에 true |
| 쓰기 금지 | `writable=false` 페이지의 쓰기 fault에 true, 또는 쓰기 fault를 처리하며 읽기 전용으로 매핑 |
| 스택 확장 | 유저 rsp - 8보다 아래 주소로 스택을 늘림 (`pt-grow-bad`), `USER_STACK - 1MB` 아래까지 늘림 |
| 스택 확장 안 함 | 유저 코드가 rsp - 8 이상, `USER_STACK - 1MB` 안의 SPT에 없는 주소에서 fault를 냈는데 false (`pt-grow-stack`) |
| 처리 중 종료 | `vm_try_handle_fault` 안(또는 그 전 `page_fault`)에서 exit하면 그 fault를 "처리 중 종료"로 남겨요 |
| swap in | 내보낸 적 없는 anon 페이지를 swap in (참고). file 페이지는 언제든 파일에서 다시 읽을 수 있어서 안 봐요 |
| 프레임 겹침 | 다른 페이지가 아직 쓰기 가능으로 매핑한 프레임(kva)을 또 쓰기 가능으로 매핑함. 내보낼 때 `pml4_clear_page`를 안 했거나 같은 프레임을 두 번 줌 (copy-on-write처럼 둘 다 읽기 전용이면 안 봐요) |
| mmap 반환값 | addr가 NULL이거나 4KB 경계가 아님, length 0, 커널 영역에 걸침, fd가 0·1이거나 안 열림, offset이 4KB 경계가 아님, 이미 SPT에 있는 페이지와 겹침 중 하나인데 성공. 성공했는데 요청한 addr가 아님, 범위의 페이지가 SPT에 없음 (참고) |
| mmap 실패 정리 | 실패한 mmap이 원래 SPT에 있던 페이지(코드, 스택, 다른 mmap)를 지움 (`mmap-over-*`, `mmap-overlap`) |
| munmap | `munmap` 뒤에도 그 매핑의 페이지가 SPT에 남음 |
| fork 복사 | fork한 자식이 처음 유저 모드로 갈 때 부모 SPT의 페이지가 자식 SPT에 없음 (`supplemental_page_table_copy`가 uninit 페이지를 빼먹는 등) |
| 종료 때 SPT | `pml4_destroy` 때 SPT에 destroy 안 된 페이지가 남음 (참고). `supplemental_page_table_kill`이 페이지마다 destroy를 불러야 해요 |
| load 실패 | 유저 프로그램이 못 뜨고 패닉이면 `uninit_new`, `pml4_set_page`가 불렸는지로 다음에 볼 곳을 알려 줘요 (과제 초반) |
| 누수 | Project 2와 같아요. 프레임(palloc), `struct page`/`struct frame`/해시 버킷(malloc)이 안 풀리면 잡혀요. `hash_clear`만 하고 `hash_destroy`를 안 해서 남은 버킷 배열은 따로 알려 줘요 |

## 디버거 (`debug.html`)

뷰어(`viewer.html`, `uprog.html`)의 "이번 이벤트" 옆 **이 시점부터 디버그**를 누르면 열려요. 채점한 실행의 기록을 QEMU로 다시 재생해서, 그 이벤트 시점에 gdb로 멈춰요. 기록이라 몇 번을 돌려도 같은 실행이 나와요.

| 동작 | 키 | 설명 |
|---|---|---|
| 계속 / 멈춤 | `c` | breakpoint나 테스트 끝(`power_off`)까지 |
| 다음 줄 / 들어가기 / 나오기 / 명령어 하나 | `n` `s` `f` `i` | gdb의 next, step, finish, stepi |
| 거꾸로: 이전 줄 / 바로 전 실행한 줄 / 호출한 곳 / 명령어 하나 / 거꾸로 계속 | `N` `S` `F` `I` `C` (Shift) | 뒤에서 설명 |
| breakpoint | 줄 번호 클릭, 또는 `process_wait`, `syscall.c:120` 입력 | |
| 식 보기 | `t->name`, `*lock`, `list_size` 같은 식 | 멈출 때마다 다시 계산 |
| 이벤트로 이동 | 오른쪽 이벤트 목록 클릭 | 그 이벤트 시점으로 앞/뒤로 이동 |

- 호출 스택, 지역 변수, 레지스터, 지금 CPU를 쓰는 스레드가 보여요. Project 2에서 유저 모드로 넘어가면 테스트 프로그램 소스(`lib/user/entry.c` 등)가 보여요. exec한 다른 프로그램은 심볼이 없어 `??`일 수 있어요
- 재생 중이라 값을 바꾸거나 커널 함수를 부르는 식(`thread_current ()` 등)은 막혀 있어요. 바꾸면 기록과 어긋나기 때문이에요
- **외부 gdb로 열기**: QEMU를 지금 시점에 멈춘 채 두고, 터미널 gdb나 VS Code가 붙을 명령과 `launch.json` 설정을 보여 줘요
- 디버거는 gdb 식을 실행하므로 이 컴퓨터에서 `localhost` 주소로 연 페이지에서만 동작해요 (`VIEW_BIND`로 다른 기기에서 연 뷰어에선 막혀요)
- 테스트를 다시 실행하면 기록이 바뀌어서 열려 있던 디버거는 닫혀요

### 거꾸로 실행

기록할 때 래퍼가 2초마다 QEMU 스냅샷을 남겨요. 거꾸로 갈 때는 목표 직전 스냅샷에서 QEMU를 새로 띄우고 앞으로 다시 돌려 보며 찾아요. 그래서 한 번에 Project 1은 1초 안팎, Project 2는 3~10초쯤 걸려요 (디스크를 쓰는 구간은 스냅샷을 못 만들어서 더 길어요).

- 이전 줄: 같은 함수 안에서 바로 전에 실행한 줄. 함수 첫 줄이면 호출한 곳으로
- 바로 전 실행한 줄: 다른 함수 안이어도 됨 (방금 돌아온 함수의 마지막 줄 등)
- 호출한 곳: 지금 함수를 부른 `call` 명령어
- 거꾸로 계속: 지금보다 앞에서 마지막으로 걸린 breakpoint. 없으면 기록의 처음

QEMU 자체의 `reverse-step`은 실행 중에 중간 스냅샷을 불러오다 멈춰서(QEMU 6.2, 10.2 모두) 쓰지 않아요. 외부 gdb 모드는 시작 스냅샷만 남긴 사본으로 재생해서 gdb의 `reverse-*` 명령이 되지만, 매번 부팅부터 재생해서 느려요. 외부 gdb에서 `monitor savevm`은 쓰지 마세요.

### 기록이 없을 때

Project 1은 기본이 기록/재생이라 바로 돼요. Project 2는 기본이 `REPLAY=0`(기록 없이 실행)이라, 디버거를 열면 **기록 모드로 다시 실행** 버튼이 나와요. 누르면 그 테스트만 기록 모드로 다시 돌린 뒤 디버거가 열려요. 터미널에서는 `REPLAY=1 tools/thread-viz/run.sh args-single`을 실행해요.

기록한 뒤 커널 코드를 고쳐 다시 빌드했으면(kernel.bin 내용이 다르면) 기록과 코드가 달라서 다시 실행하라고 나와요.

## 주의사항

- **최종 채점은 `make check`로 해 주세요.** 여기 PASS/FAIL은 `make check`와 같은 명령(`pintos -v -k -T 60 -m 20 -- -q run ...`)을 기록 모드로 돌려 같은 `.ck`로 채점해요 (기록 모드라 실제 시간 제한 `-T`만 넉넉히 늘려요)
  - `REPLAY=0`이면 트레이스 실행은 gdb 훅 부하로 tick이 밀릴 수 있어요 (예: `alarm-simultaneous`에서 `woke up 1 ticks later`). 출력이 다르면 "테스트 출력"에 두 출력을 같이 보여 줘요
- **점수는 재미용이에요.** 실제 채점과 상관없어요
  - 정확성 먼저: 채점 FAIL / PANIC / 시간 초과 / 중단이면 F, 0점
  - PASS면 100점에서 감점: 규칙 위반 **종류당** -15 (같은 버그가 이벤트 여러 개에서 반복돼도 한 번), busy wait yield 번당 -2 (최대 -30), 최대 선점 지연 = 깨어난 높은 스레드가 기다리는 동안 더 낮은 스레드가 남긴 이벤트 수 × 2 (최대 -20), 최대 선점 지연 tick × 5 (최대 -20. 더 낮은 스레드가 실제로 돈 경우만 셈. 이벤트 없이 도는 busy loop용)
  - 빈 ready_list에서의 타임슬라이스 yield는 감점하지 않아요 (원본 `thread_tick`도 그렇게 해요)
- **`run.sh`를 동시에 두 개 돌리지 마세요.** gdb 포트(`GDB_BASE`부터)와 `traces/`를 같이 써요. 다른 `pintos --gdb`도 꺼 두세요
  - 호스트와 컨테이너에서 동시에 돌리는 것도 안 돼요. VS Code가 컨테이너의 1234 포트를 호스트 `localhost:1234`로 자동 포워딩해서 호스트 쪽 gdb가 컨테이너 QEMU에 붙기 때문이에요
  - 시작 전에 쓸 포트가 비어 있는지 확인하고, 10초 기다려도 비지 않으면 안내 메시지를 내고 멈춰요 (엉뚱한 QEMU를 추적하거나 끄지 않게)
  - 호스트(gcc 15 등)에서는 원본 Pintos 코드가 빌드되지 않을 수 있어요. 컨테이너 안에서 돌려 주세요
- 결과 파일은 `tools/thread-viz/traces/`에만 써요. `make check` 결과(`build/tests/...`)는 건드리지 않아요
- 뷰어 서버는 기본으로 `127.0.0.1`에만 열려요. devcontainer에선 VS Code 포워딩으로 `localhost:포트`가 열리지만, 컨테이너 IP(`172.17.0.x`)로 직접 접속할 수는 없어요 (필요하면 `VIEW_BIND=0.0.0.0`)
- `traces/`에 트레이스가 없거나 오래된 테스트는 자동으로 같이 수집해요. 그래서 테스트 하나만 지정해도 처음엔 전부 돌 수 있어요
- 첫 테스트 로그의 `trace layout: ...` 줄에서 감지한 필드를 확인해 주세요. `없음`이면 그 기능만 꺼져요
  - base priority, 기다리는 락, donations는 타입과 이름 패턴으로 찾아요 (예: `init_priority`, `original_priority`, `wait_on_lock`, `donations`, `donor_list`)
  - 패턴에 맞지 않는 이름이면 찾지 못해요
- 규칙 위반 검사는 원인 찾기용 보조 도구예요. 못 잡는 경우가 있어요
  - 같은 priority끼리 FIFO 순서, 스냅샷 사이에 잠깐 생긴 위반, 인터럽트 안의 위반
  - 인터럽트 안인지는 커널의 `in_external_intr` 값으로 판정해요 (예전 트레이스는 호출 스택으로 추정해요)
  - 생성 중인 스레드(init_thread ~ thread_unblock 사이)는 값이 덜 채워졌을 수 있어 일부 검사에서 빼요
  - 스케줄 선택은 "고른 스레드가 ready 중 가장 높은가"로 검사해요. ready_list를 정렬해 두든 `list_max`로 고르든 구현 방식과 상관없어요
  - 출력 순서만 틀린 버그 (FAIL로는 나오지만 원인은 짚지 않아요)
- MLFQS
  - `nice`, `recent_cpu` 필드와 전역 `load_avg`는 이름 패턴으로 찾아요 (typedef 고정소수점 타입도 돼요)
  - 고정소수점 배율은 테스트 끝(`power_off`)에 커널의 `thread_get_load_avg()`, `thread_get_recent_cpu()`를 gdb로 호출해 원시값과 비교해서 알아내요. getter가 미구현(0 반환)이면 17.14(16384)로 가정하고 MLFQS 공식 검사는 꺼요
  - 배율을 알아낸 경우 자동 검사: priority 공식(4 tick마다), recent_cpu tick마다 +1, load_avg 갱신(1초마다), recent_cpu 재계산(1초마다). 고정소수점 반올림 차이와 갱신 순서(깨우기 전/후, 경계 tick의 +1 전/후)는 허용해요
  - ready queue를 배열(`struct list ready_list[64]` 등)로 만든 경우 높은 인덱스부터 이어 붙여 하나의 ready_list로 보여 줘요
  - MLFQS 모드에선 donation 검사를 건너뛰어요. 선점 누락은 4 tick 이상 이어질 때만 세요 (4 tick마다 재계산되고 다음 타임슬라이스 끝에 바뀌는 구현도 있어서요)
- `baseline.js`는 효율 점수 기준이라 커밋 대상이에요 (`BASELINE=1`로 다시 만들 때만 바뀌어요)
- `data.js`, `traces/`, `progress.json`은 생성물이라 커밋하지 마세요 (`.gitignore`에 있어요)

## 문제 해결

| 증상 | 해결 |
|---|---|
| 페이지가 빈 화면 | PORTS 탭에서 실제 포워딩 주소를 확인하고, Ctrl+Shift+R로 강력 새로고침해 주세요 |
| `data.js가 없어요` | `run.sh`를 한 번 끝까지 실행해 주세요 |
| 테스트가 목록에 없음 | `traces/<test>.err`, `.output`을 확인하고 다시 `run.sh <test>`를 실행해 주세요 |
| `Address already in use` | 이미 서버가 떠 있는 거예요. 출력된 주소로 바로 접속해 주세요 |
| `trace warning: ... 함수가 없어` | 그 함수 이름이 바뀐 구현이에요. 해당 이벤트만 빠져요 |
| `gdb 포트 1234를 다른 프로그램이 쓰는 중이에요` | 다른 `pintos --gdb`를 끄거나, 호스트/컨테이너 한쪽에서만 실행해 주세요 |
| `gdb 연결 실패` / 위쪽에 "수집 실패 N개" | 부하 등으로 gdb가 붙지 못한 거예요. `run.sh`를 다시 실행하면 그 테스트만 다시 수집해요 |
| 맞는 코드인데 트레이스 화면의 tick이 조금 다름 (`REPLAY=0`) | gdb 부하 때문이에요. 채점은 따로 돌린 실행 기준이라 영향이 없어요. "테스트 출력"에서 두 출력을 비교해 보세요 |
| 빌드 실패: ``undefined reference to `_end_bss'``, `relocation truncated to fit` | `build/threads/kernel.lds.s`가 빈 파일로 남은 거예요. Windows 폴더를 마운트한 컨테이너(대소문자 구분 없음)에서 `make -B`를 하면 생겨요. `run.sh`는 빌드 전에 항상 지우고 다시 만들어요. `make`/`make check`를 직접 돌릴 땐 `rm pintos/threads/build/threads/kernel.lds.s` 후 다시 빌드하고, Windows에선 `make -B` 대신 `make clean && make`를 써 주세요 |
| `make check`에서 `/usr/bin/env: 'python3\r'` | Windows git(`core.autocrlf=true`)으로 받아서 `pintos/utils/`가 CRLF가 된 거예요. `run.sh`는 파일을 고치지 않고 알아서 돌려요. `make check`까지 쓰려면 `git config --global core.autocrlf input` 후 다시 clone해 주세요 |
| `.err`에 `rr`/`replay`/`blkreplay` 관련 QEMU 에러 | 이 QEMU는 기록/재생을 지원하지 않아요. `REPLAY=0`으로 실행해 주세요 |
| 트레이스를 걸면 가끔 PANIC (평소 `make check`는 PASS) | 타이밍이 바뀌어 숨어 있던 경쟁 조건이 드러난 것일 수 있어요. PANIC 위치와 호출 스택을 확인해 주세요 |
