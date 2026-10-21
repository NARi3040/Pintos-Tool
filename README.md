# Pintos-Tool

KAIST Pintos (x86-64) 과제용 도구 모음이에요.

## thread-viz

Pintos 테스트를 gdb로 추적해서 웹페이지에서 한 단계씩 보여 주는 도구예요. Project 1 (Threads)은 스레드 생성, ready_list, sleep_list, lock / semaphore / condition 대기 리스트, donation 흐름을, Project 2·3은 시스템 콜, 프로세스 트리, 가상 메모리를 보여 줘요. 커널 코드는 수정하지 않아요.

### 빠른 시작

Pintos 저장소 루트(`pintos/` 폴더가 있는 곳)에서 실행해요. 첫 줄은 `curl`이 없는 정글 Pintos Docker 이미지용이에요. 이미 있으면 건너뛰어도 돼요.

```bash
sudo apt-get update && sudo apt-get install -y curl
curl -fL https://github.com/NARi3040/Pintos-Tool/releases/latest/download/thread-viz.tar.gz | tar -xzf -
tools/thread-viz/run.sh
```

`http://localhost:8000/index.html`이 열리면 Project 1·2·3 중 하나를 고르고, 테스트를 골라 **선택한 테스트 실행**을 눌러 주세요. 끝나면 **결과 보기**로 뷰어에 들어가요.

### 시작하기

Windows 사용자는 [WINDOWS.md](WINDOWS.md)를 먼저 봐 주세요.

#### 필요한 것

`qemu-system-x86_64`, `gdb`(Python 지원), `python3`, `perl`, bash 5.1 이상이 필요해요. 정글 Pintos Docker 이미지에는 다 들어 있어요.

#### 설치

Pintos 저장소 루트에서 실행해요. `tools/thread-viz/`가 생겨요.

```bash
curl -fL https://github.com/NARi3040/Pintos-Tool/releases/latest/download/thread-viz.tar.gz | tar -xzf -
```

정글 Pintos Docker 이미지에는 `curl`이 없어요. 먼저 설치하거나,

```bash
sudo apt-get update && sudo apt-get install -y curl
```

`python3`만으로 받아도 돼요 (위 명령과 결과가 같아요). `curl`은 설치에만 쓰고, 도구 자체는 쓰지 않아요.

```bash
python3 -c "import io,tarfile,urllib.request as u; tarfile.open(fileobj=io.BytesIO(u.urlopen('https://github.com/NARi3040/Pintos-Tool/releases/latest/download/thread-viz.tar.gz').read())).extractall()"
```

#### 실행

```bash
tools/thread-viz/run.sh                       # 런처 페이지를 열어요. 거기서 프로젝트와 테스트를 골라 실행
tools/thread-viz/run.sh threads               # Project 1: alarm-*, priority-*, bench-* 전부
tools/thread-viz/run.sh priority-donate-nest  # 원하는 테스트만
```

인자 없이 실행하면 런처 페이지(`http://localhost:8000/index.html`)에서 테스트를 골라 실행·중지할 수 있어요. 인자를 주면 터미널에서 바로 돌리고, 진행 상황을 볼 수 있는 뷰어 주소를 알려 줘요.

- `mlfqs-*` 테스트는 오래 걸려서 기본 목록에 없어요. `MLFQS=1 tools/thread-viz/run.sh threads`로 포함하거나 이름을 직접 주세요.
- 포트가 이미 쓰이고 있으면 `VIEW_PORT=9000 tools/thread-viz/run.sh`처럼 바꿔 주세요.
- 수집 중 Ctrl-C를 누르면 그때까지의 트레이스를 저장하고 끝나요. 결과는 `tools/thread-viz/traces/`에 저장돼요.

테스트마다 QEMU 기록/재생으로 채점한 실행 그대로를 추적하고, 정확성 점수와 별개로 효율 점수(실행 명령어 수 기준)도 매겨요. 자세한 사용법과 옵션은 [tools/thread-viz/README.md](tools/thread-viz/README.md)에 있어요.

#### 주의

- 화면의 점수는 재미용이에요. 최종 채점은 `make check`로 해 주세요.
- `run.sh`를 동시에 두 개 돌리지 마세요. 호스트와 컨테이너에서 같이 돌리는 것도 안 돼요. gdb 포트(1234~)와 `traces/`를 같이 써요.

### Project 2 (User Programs)

```bash
tools/thread-viz/run.sh userprog                  # Project 2 테스트 전부
tools/thread-viz/run.sh args-multiple fork-once   # 원하는 테스트만
```

시스템 콜(인자, 반환값), fork/exec/wait/exit 프로세스 트리, argument passing 직후 유저 스택, page fault, 프로세스별 fd 표, 페이지/파일 누수를 `http://localhost:8000/uprog.html`에서 보여 줘요. 인자 전달, fork 반환값, wait 반환값, 잘못된 포인터 처리, 종료 메시지, 누수는 자동으로 검사해서 경고로 표시해요. 자세한 내용은 [tools/thread-viz/README.md](tools/thread-viz/README.md)의 "Project 2" 절에 있어요.

### Project 3 (Virtual Memory)

```bash
tools/thread-viz/run.sh vm                        # tests/vm 전부 (VM 빌드)
tools/thread-viz/run.sh lazy-anon swap-anon       # 원하는 테스트만
tools/thread-viz/run.sh vm args-single            # Project 2 테스트를 VM 빌드로
```

Project 2 화면(`uprog.html?vm`)에 **가상 메모리** 탭이 붙어요. 이벤트 시점의 프로세스별 페이지 표(종류, 쓰기 가능, lazy / 메모리 / swap / 파일로 내보냄)와 프레임 사용량을 보여 주고, page fault마다 `vm_try_handle_fault`가 무엇을 했는지(lazy 로딩, swap in, 스택 확장, 다른 페이지 내보냄)를 붙여요. 처리 실패, 매핑 안 된 채 true 반환, rsp 아래·1MB 넘는 스택 확장, 읽기 전용 페이지 쓰기 허용 등은 경고로 표시해요. swap 테스트는 fault가 많아 트레이스가 수 분~십여 분 걸려요. 자세한 내용은 [tools/thread-viz/README.md](tools/thread-viz/README.md)의 "Project 3" 절에 있어요.

### 디버거

뷰어에서 이벤트를 고르고 **이 시점부터 디버그**를 누르면, 채점한 실행을 QEMU로 다시 재생해서 그 시점에 gdb로 멈춘 화면(`debug.html`)이 열려요. 소스를 보며 한 줄씩 실행(next, step, finish), breakpoint, 변수·식 보기, 호출 스택을 쓸 수 있고, **거꾸로 실행**(이전 줄, 호출한 곳, 거꾸로 계속)도 돼요. 터미널 gdb나 VS Code로 넘길 수도 있어요. 자세한 내용은 [tools/thread-viz/README.md](tools/thread-viz/README.md)의 "디버거" 절에 있어요.

### 업데이트

`run.sh`를 실행할 때마다 새 버전을 확인하고, 있으면 자동으로 받아서 적용해요. 건너뛰려면 `--no-update`를 붙여 주세요. 수동으로 하려면 `python3 tools/thread-viz/update.py`를 실행해요. 버전은 [Releases](https://github.com/NARi3040/Pintos-Tool/releases)에서 볼 수 있어요.

### 벤치 테스트

`tools/thread-viz/bench/`에 부하 테스트 4개(`bench-lock-storm`, `bench-sleep-wave`, `bench-cond-relay`, `bench-scale`)가 있어요. `bench-scale`은 리스트 길이에 따라 비용이 느는지 보는 복잡도 판정용이에요. `run.sh`를 처음 실행할 때 설치할지 물어보고, `y`면 `pintos/tests/threads/`에 복사한 뒤 `tests.c`, `tests.h`, `Make.tests`(`threads_SRC`에만. `make check` 대상은 아니에요)에 등록해요. 대답은 저장돼서 다시 묻지 않아요. `BENCH=1` / `BENCH=0`으로 정할 수 있고, 지우려면 `python3 tools/thread-viz/bench.py remove`를 실행해요. 설치하지 않아도 공식 테스트는 돌아가요. 각 테스트 설명은 [tools/thread-viz/README.md](tools/thread-viz/README.md)의 "벤치 테스트" 절에 있어요.

## 기여

버그 제보, 기능 제안, PR 모두 환영해요. 브랜치·커밋 규칙, 머지 전 확인, 릴리스 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)에 있어요. `main`은 보호돼 있어서 직접 push할 수 없고 PR로만 들어가요.

## 라이선스

MIT. [LICENSE](LICENSE)를 참고해 주세요. 이 저장소에는 Pintos 소스나 과제 풀이가 들어 있지 않아요.
