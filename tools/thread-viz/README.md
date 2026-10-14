# thread-viz — Pintos 스레드 흐름 시각화

KAIST Pintos (x86-64) Project 1 (Threads)용 도구임. 테스트를 gdb로 추적해서 스레드 생성, ready_list,
sleep_list, lock / semaphore / condition 대기 리스트, donation 흐름을 웹페이지에서 한 단계씩 보여줌.
커널 코드는 수정하지 않음.

## 필요한 것

- `qemu-system-x86_64`, `gdb`(Python 지원 빌드), `python3`, `perl`
- 정글 Pintos Docker 이미지에는 다 들어 있음
- KAIST Pintos 원본 함수 이름이 그대로 있어야 함 (`init_thread`, `thread_launch`, `thread_block`, `power_off` 등)

## 설치

`pintos/` 폴더와 같은 높이에 `tools/thread-viz/`가 오게 풀면 됨.

```
<repo>/
├── pintos/
└── tools/thread-viz/
    ├── run.sh
    ├── bin/qemu-system-x86_64   (QEMU 래퍼: 기록/재생, gdb 포트)
    ├── trace.py
    ├── viewer.html
    └── README.md
```

```bash
tar -xzf thread-viz.tar.gz -C <repo 루트>
```

## 업데이트

`run.sh`를 실행할 때마다 먼저 새 버전을 확인하고, 있으면 받아서 적용한 뒤 새 `run.sh`로 다시 시작함. 결과(`최신 버전입니다!` 또는 업데이트 내역)를 한 줄로 보여줌. 오프라인이거나 5초 안에 응답이 없으면 실패했다고 알리고 지금 버전으로 계속함.

```bash
tools/thread-viz/run.sh --no-update ...      # 이번 실행은 업데이트 확인을 건너뜀 (NO_UPDATE_CHECK=1도 같음)
python3 tools/thread-viz/update.py           # 수동 업데이트
python3 tools/thread-viz/update.py --check   # 확인만
```

- GitHub Releases(`NARi3040/Pintos-Tool`)의 최신 `thread-viz.tar.gz`를 받아 sha256을 확인한 뒤 `tools/thread-viz/`에 덮어씀. 실패하면 지금 버전으로 계속 실행함
- `traces/`, `data.js`, `progress.json`은 건드리지 않음. `baseline.js`는 이미 있으면 덮어쓰지 않음
- 버전은 `VERSION` 파일의 정수임
- `pintos-bench/`의 벤치 테스트 소스와 `pintos/`는 업데이트 대상이 아님

## 사용법

repo 루트에서 실행함.

```bash
tools/thread-viz/run.sh                          # alarm-*, priority-*, bench-* 전부 (첫 실행 2~3분)
tools/thread-viz/run.sh priority-donate-nest     # 원하는 테스트만
tools/thread-viz/run.sh priority-sema priority-condvar
```

실행하면 처음에 접속 주소가 나옴. 수집 중에도 그 주소로 들어가면 진행도가 실시간으로 보이고, 끝나면 자동으로 새로고침됨.

```
진행 상황은 여기서 실시간으로 볼 수 있습니다: http://localhost:8000/viewer.html
```

- devcontainer 안에서 돌렸으면 VS Code가 포트를 자동으로 포워딩해서 같은 주소로 열림. 안 열리면 VS Code PORTS 탭에서 포워딩된 주소(예: `localhost:8001`)를 확인함
- 코드를 고친 뒤 다시 `run.sh`만 실행하면 됨. 실행할 때마다 커널을 처음부터 다시 빌드함(`make -B`)
  - `make clean`은 안 씀. `build/`를 통째로 지워 `make check` 결과까지 사라지기 때문임. `make -B`는 커널만 다시 빌드하고 `build/tests/`의 결과 파일은 그대로 둠

### 기록/재생 (트레이스 = 채점한 실행)

기본(`REPLAY=1`)으로 테스트마다 QEMU를 두 번 돌림.

1. **기록**: gdb 없이 `make check`와 같은 명령으로 돌리면서 QEMU record/replay(`-icount rr=record`)로 실행을 기록함. 이 출력으로 채점함
2. **재생**: 기록을 재생하면서 gdb로 트레이스를 수집함. 재생은 명령어 하나, 인터럽트 하나까지 기록과 똑같아서 gdb 훅이 아무리 멈춰도 결과가 안 바뀜

그래서 화면의 흐름, tick, 선점 지연이 채점한 실행 그대로임. 같은 기록을 다시 재생하면 트레이스도 똑같이 나옴.
gdb가 타이밍을 흔들지 않으니 테스트를 동시에 돌림 (`JOBS`, 기본 코어 수의 절반. 테스트마다 gdb 포트를 따로 씀).

- 기록 실행은 부팅이 실제 시간으로 ~10초 더 걸림 (로더가 디스크를 섹터 단위로 폴링하는 구간). 게스트가 보는 tick은 그대로임
- 기록/재생이 안 되는 QEMU면 `REPLAY=0`으로 예전 방식(트레이스 실행과 채점 실행을 따로, 하나씩)을 씀
- 기록은 실제 실행이라 실행마다 타이밍은 조금씩 다를 수 있음 (`make check`도 마찬가지). 재생이 결정적인 것임

### 벤치 테스트 (`bench-*`)

공식 테스트는 짧고 스레드가 적어서 맞게 짠 구현은 거의 다 100점이 나옴. 점수 차이를 보려고 부하 테스트 3개를 넣음.
`pintos/tests/threads/bench-*.c`, `tests.c`/`tests.h` 등록, `Make.tests`의 `threads_SRC`에만 추가해서 커널에는 들어가지만 `make check` 대상(`threads_TESTS`)은 아님.

| 테스트 | 하는 일 | 테스트 자체 검사 (FAIL 조건) |
|---|---|---|
| `bench-lock-storm` | priority가 다른 10개 스레드가 락 2개(A→B 중첩)를 쥔 채 잠들며 3번씩 경쟁. donation, 중첩 donation, 락 넘겨주기 | 락을 다 놓은 뒤 priority가 원래 값이 아님 |
| `bench-sleep-wave` | 12개 스레드가 같은 tick을 목표로 잠들었다 한꺼번에 깨어나기를 4번 | 같은 tick에 깬 스레드가 priority 높은 순서로 실행되지 않음 |
| `bench-cond-relay` | 8개 스레드가 cond에서 기다리고 가장 낮은 main이 하나씩 깨움. 깬 스레드는 donation을 거쳐 main을 선점. 3라운드 | 라운드마다 priority 높은 순서로 깨어나지 않음 |

### 효율 점수

정확성 점수와 따로 매기는 점수임. 기록/재생일 때만 나옴 (`REPLAY=0`이면 없음).

- 재생 중에 gdb의 `monitor info replay`로 QEMU가 센 실행 명령어 수를 읽어서 잼. 재생은 결정적이라 같은 코드면 거의 같은 값이 나옴 (실제 시간과 달리 호스트 부하에 안 흔들림)
- 지표 3개
  - **API 호출 명령어 합**: `lock_*`, `sema_*`, `cond_*`, `thread_set_priority`, `thread_yield`, `thread_unblock`, `timer_sleep`을 호출한 스레드가 진입~복귀 사이에 직접 실행한 명령어 수. 막혀서 다른 스레드가 돈 시간과 인터럽트 처리는 뺌. 바깥 호출만 합산 (lock_acquire 안의 sema_down을 두 번 안 셈)
  - **타이머 인터럽트 평균 명령어**: `timer_interrupt` 1번에 드는 명령어 수 (sleep_list 처리, `thread_tick`). tick이 20번 미만인 테스트에선 값이 흔들려서 점수에 안 씀
  - **컨텍스트 스위치 수**
- 점수 = 100 × (기준값 / 지금값)의 기하평균. 기준과 같으면 100, 덜 쓰면 100 초과. 정확성 실패(F)면 효율 점수 없음
- 기준은 `baseline.js`. 지금 구현을 기준으로 저장하려면 `BASELINE=1 tools/thread-viz/run.sh` (이번에 돌린 테스트만 덮어씀)
- 들어 있는 `baseline.js`는 이 저장소의 구현으로 만든 것임. 다른 구현과 비교할 때 그대로 두면 됨
- `thread_create`는 안 잼. 비용 대부분(~11만 명령어)이 원본 `palloc`의 페이지 채우기라 동기화 비용을 가림
- 메모리 사용량은 안 잼. 스레드마다 4KB 페이지 하나로 고정이라 구현마다 차이가 거의 없음
- 확인한 예 (효율을 일부러 나쁘게 바꾼 버전)
  - 타이머가 sleep_list를 끝까지 훑음: alarm 테스트 60~81점 (타이머 평균 +86~368%)
  - `sema_up`에서 매번 `list_sort`: bench-lock-storm 94점 (API 명령어 +21%)
  - 같은 priority에도 양보: alarm-single 90점 (스위치 +29%)
- 측정 훅이 늘어서 트레이스 수집이 ~40% 느려짐

### MLFQS 테스트

`mlfqs-*` 테스트는 하나에 수 분씩 걸려서 기본 목록에 없음. 이름을 직접 주거나 `MLFQS=1`을 붙임.
`-mlfqs` 커널 옵션과 긴 시간 초과(900초)는 자동으로 붙음.

```bash
tools/thread-viz/run.sh mlfqs-load-1 mlfqs-fair-2   # 원하는 것만
MLFQS=1 tools/thread-viz/run.sh                     # alarm/priority + mlfqs 전부 (수십 분)
```

MLFQS 모드로 돈 테스트는 화면에 MLFQS 패널이 생김: 스레드별 priority / recent_cpu / nice 그래프와 load_avg 그래프 (가로축 tick). 공식이 틀리면 해당 이벤트에 MLFQS 위반이 표시됨 (테스트가 PASS여도 잡히는 경우가 있음).

### 옵션 (환경 변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `VIEW_PORT` | `8000` | 뷰어 서버 포트 |
| `TRACE_TIMEOUT` | `60` (mlfqs는 `900`) | 테스트 하나가 이 시간(초) 안에 안 끝나면 멈춘 것으로 보고 그때까지 저장함 |
| `MLFQS` | `0` | `1`이면 mlfqs 테스트도 기본 목록과 자동 수집에 포함 |
| `REBUILD` | `1` | `1`이면 측정 전에 커널 전체를 다시 빌드(`make -B`). `0`이면 바뀐 파일만 빌드 |
| `AUTO` | `1` | `0`이면 트레이스가 없는 테스트를 자동으로 같이 수집하지 않고 지정한 테스트만 돌림 |
| `VIEW_BIND` | `127.0.0.1` | 뷰어 서버가 열리는 주소. 다른 기기에서 보려면 `0.0.0.0` (같은 네트워크에 소스가 노출됨) |
| `REPLAY` | `1` | `1`이면 기록/재생 (위 설명). `0`이면 예전 방식 |
| `JOBS` | 코어 수 / 2 | 동시에 돌릴 테스트 수 (`REPLAY=1`일 때만. `0`이면 1) |
| `GDB_BASE` | `1234` | gdb 포트 시작 번호. 동시 실행 슬롯마다 `GDB_BASE`, `+1`, ... 을 씀 |
| `BASELINE` | `0` | `1`이면 이번 효율 측정값을 `baseline.js`에 기준으로 저장 |
| `GRADE` | `1` | `REPLAY=0`일 때만 씀. `1`이면 채점용으로 트레이스 없는 실행을 따로 돌림(동시 실행). `seq`면 트레이스 수집 뒤에 따로 돌림(코어가 적어 채점 타이밍이 흔들릴 때). `0`이면 생략하고 트레이스 실행 출력으로 채점 (빠르지만 타이밍 테스트가 틀리게 FAIL 날 수 있음) |

```bash
VIEW_PORT=9000 TRACE_TIMEOUT=30 tools/thread-viz/run.sh
```

### 중단하기

수집 중에 Ctrl-C를 누르면 지금 돌던 테스트를 그 자리에서 멈추고, 그때까지의 트레이스를 `aborted`로 저장한 뒤 뷰어에 반영하고 끝남.
QEMU, gdb, 채점 실행도 같이 정리됨.

### 서버 끄기

```bash
pkill -f "http.server 8000"
```

### 결과 파일 (`traces/`)

| 파일 | 내용 |
|---|---|
| `<test>.json` | 트레이스 (이벤트, 스냅샷, 소스) |
| `<test>.output` | 채점용 실행(기록 실행, 트레이스 없음)의 출력. 이걸로 채점함 |
| `<test>.trace-output` | 트레이스 실행(재생)의 출력. 기록/재생이면 `.output`과 같아야 함 |
| `<test>.rr` | QEMU 기록 파일. 재생이 끝나면 지움 |
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
- 주소 뒤에 `#테스트이름/번호`를 붙이면 그 단계로 바로 열림 (예: `viewer.html#priority-donate-chain/60`)
- 이번 이벤트: 어떤 함수가 어디서 불렸는지, 규칙 위반이면 빨간 경고. 소스 패널(접기/펼치기)에서 호출한 줄 주변 코드
- 이벤트 직후 상태: CPU / ready_list / sleep_list / BLOCKED
- 동기화 객체: lock(holder, 대기자), semaphore(value, 대기자), condition(대기자)
- donation: 대기 체인(`high → L2 → medium → L1 → main`)과 스레드별 donations 리스트
- 효율 지표: 스위치 / yield 횟수, 스레드별 실행·대기 tick, 선점 지연, 재미용 점수, 효율 점수와 함수별 평균 명령어 수 (기준 → 지금)
- 채점 결과(.ck): FAIL이면 자동으로 펼쳐짐

## 주의사항

- **최종 채점은 `make check`로 할 것.** 여기 PASS/FAIL은 `make check`와 같은 명령(`pintos -v -k -T 60 -m 20 -- -q run ...`)을 기록 모드로 돌려 같은 `.ck`로 채점함 (기록 모드라 실제 시간 제한 `-T`만 넉넉히 늘림)
  - `REPLAY=0`이면 트레이스 실행은 gdb 훅 부하로 tick이 밀릴 수 있음 (예: `alarm-simultaneous`에서 `woke up 1 ticks later`). 출력이 다르면 "테스트 출력"에 두 출력을 같이 보여줌
- **점수는 재미용임.** 실제 채점과 무관함
  - 정확성 먼저: 채점 FAIL / PANIC / 시간 초과 / 중단이면 F, 0점
  - PASS면 100점에서 감점: 규칙 위반 **종류당** -15 (같은 버그가 이벤트 여러 개에서 반복돼도 한 번), busy wait yield 번당 -2 (최대 -30), 최대 선점 지연 = 깨어난 높은 스레드가 기다리는 동안 더 낮은 스레드가 남긴 이벤트 수 × 2 (최대 -20), 최대 선점 지연 tick × 5 (최대 -20. 더 낮은 스레드가 실제로 돈 경우만 셈. 이벤트 없이 도는 busy loop용)
  - 빈 ready_list에서의 타임슬라이스 yield는 감점 안 함 (원본 `thread_tick`도 그렇게 함)
- **`run.sh`를 동시에 두 개 돌리지 말 것.** gdb 포트(`GDB_BASE`부터)와 `traces/`를 같이 씀. 다른 `pintos --gdb`도 꺼 둘 것
  - 호스트와 컨테이너에서 동시에 돌리는 것도 안 됨. VS Code가 컨테이너의 1234 포트를 호스트 `localhost:1234`로 자동 포워딩해서 호스트 쪽 gdb가 컨테이너 QEMU에 붙음
  - 시작 전에 쓸 포트가 비어 있는지 확인하고, 10초 기다려도 안 비면 안내 메시지를 내고 멈춤 (엉뚱한 QEMU를 추적하거나 끄지 않게)
  - 호스트(gcc 15 등)에서는 원본 Pintos 코드가 빌드 안 될 수 있음. 컨테이너 안에서 돌릴 것
- 결과 파일은 `tools/thread-viz/traces/`에만 씀. `make check` 결과(`build/tests/...`)는 안 건드림
- 뷰어 서버는 기본으로 `127.0.0.1`에만 열림. devcontainer에선 VS Code 포워딩으로 `localhost:포트`가 열리지만, 컨테이너 IP(`172.17.0.x`)로 직접 접속하는 건 안 됨 (필요하면 `VIEW_BIND=0.0.0.0`)
- `traces/`에 트레이스가 없거나 오래된 테스트는 자동으로 같이 수집함. 그래서 테스트 하나만 지정해도 처음엔 전부 돌 수 있음
- 첫 테스트 로그의 `trace layout: ...` 줄에서 감지한 필드를 확인할 것. `없음`이면 그 기능만 꺼짐
  - base priority, 기다리는 락, donations는 타입과 이름 패턴으로 찾음 (예: `init_priority`, `original_priority`, `wait_on_lock`, `donations`, `donor_list`)
  - 패턴에 안 맞는 이름이면 못 찾음
- 규칙 위반 검사는 원인 찾기용 보조 도구임. 못 잡는 경우가 있음
  - 같은 priority끼리 FIFO 순서, 스냅샷 사이에 잠깐 생긴 위반, 인터럽트 안의 위반
  - 인터럽트 안인지는 커널의 `in_external_intr` 값으로 판정함 (예전 트레이스는 호출 스택으로 추정)
  - 생성 중인 스레드(init_thread ~ thread_unblock 사이)는 값이 덜 채워졌을 수 있어 일부 검사에서 뺌
  - 스케줄 선택은 "고른 스레드가 ready 중 가장 높은가"로 검사함. ready_list를 정렬해 두든 `list_max`로 고르든 구현 방식과 무관함
  - 출력 순서만 틀린 버그 (FAIL로는 나오지만 원인은 안 짚음)
- MLFQS
  - `nice`, `recent_cpu` 필드와 전역 `load_avg`는 이름 패턴으로 찾음 (typedef 고정소수점 타입도 됨)
  - 고정소수점 배율은 테스트 끝(`power_off`)에 커널의 `thread_get_load_avg()`, `thread_get_recent_cpu()`를 gdb로 호출해 원시값과 비교해서 알아냄. getter가 미구현(0 반환)이면 17.14(16384)로 가정하고 MLFQS 공식 검사는 끔
  - 배율을 알아낸 경우 자동 검사: priority 공식(4 tick마다), recent_cpu tick마다 +1, load_avg 갱신(1초마다), recent_cpu 재계산(1초마다). 고정소수점 반올림 차이와 갱신 순서(깨우기 전/후, 경계 tick의 +1 전/후)는 허용함
  - ready queue를 배열(`struct list ready_list[64]` 등)로 만든 경우 높은 인덱스부터 이어 붙여 하나의 ready_list로 보여줌
  - MLFQS 모드에선 donation 검사를 건너뜀. 선점 누락은 4 tick 이상 이어질 때만 셈 (4 tick마다 재계산되고 다음 타임슬라이스 끝에 바뀌는 구현도 있어서)
- `baseline.js`는 효율 점수 기준이라 커밋 대상임 (`BASELINE=1`로 다시 만들 때만 바뀜)
- `data.js`, `traces/`, `progress.json`은 생성물이라 커밋하지 말 것 (`.gitignore`에 있음)

## 문제 해결

| 증상 | 해결 |
|---|---|
| 페이지가 빈 화면 | PORTS 탭에서 실제 포워딩 주소 확인, Ctrl+Shift+R로 강력 새로고침 |
| `data.js가 없음` | `run.sh`를 한 번 끝까지 실행 |
| 테스트가 목록에 없음 | `traces/<test>.err`, `.output` 확인. 다시 `run.sh <test>` |
| `Address already in use` | 이미 서버가 떠 있는 것임. 출력된 주소로 바로 접속 |
| `trace warning: ... 함수가 없어` | 그 함수 이름이 바뀐 구현임. 해당 이벤트만 빠짐 |
| `gdb 포트 1234를 다른 프로그램이 쓰는 중임` | 다른 `pintos --gdb`를 끄거나, 호스트/컨테이너 한쪽에서만 실행 |
| `gdb 연결 실패` / 위쪽에 "수집 실패 N개" | 부하 등으로 gdb가 못 붙은 것. `run.sh`를 다시 실행하면 그 테스트만 다시 수집함 |
| 맞는 코드인데 트레이스 화면의 tick이 조금 다름 (`REPLAY=0`) | gdb 부하 때문임. 채점은 따로 돌린 실행 기준이라 영향 없음. "테스트 출력"에서 두 출력 비교 |
| 빌드 실패: ``undefined reference to `_end_bss'``, `relocation truncated to fit` | `build/threads/kernel.lds.s`가 빈 파일로 남은 것임 (예전 빌드가 중간에 실패하거나 끊김). `run.sh`는 자동으로 지우고 다시 만듦. `make`/`make check`를 직접 돌릴 땐 `rm pintos/threads/build/threads/kernel.lds.s` 후 다시 빌드 |
| `.err`에 `rr`/`replay`/`blkreplay` 관련 QEMU 에러 | 이 QEMU가 기록/재생을 지원 안 함. `REPLAY=0`으로 실행 |
| 트레이스를 걸면 가끔 PANIC (평소 `make check`는 PASS) | 타이밍이 바뀌어 숨어 있던 경쟁 조건이 드러난 것일 수 있음. PANIC 위치와 호출 스택 확인 |
