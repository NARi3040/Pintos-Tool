# Pintos-Tool

KAIST Pintos (x86-64) 과제용 도구 모음임.

## thread-viz

Project 1 (Threads) 테스트를 gdb로 추적해서 스레드 생성, ready_list, sleep_list, lock / semaphore / condition 대기 리스트, donation 흐름을 웹페이지에서 한 단계씩 보여주는 도구임. 커널 코드는 수정하지 않음.

### 설치

Pintos 저장소 루트(`pintos/` 폴더가 있는 곳)에서 실행함.

```bash
curl -fL https://github.com/NARi3040/Pintos-Tool/releases/latest/download/thread-viz.tar.gz | tar -xzf -
```

정글 Pintos Docker 이미지에는 `curl`이 없음. `curl: command not found`가 나오면 먼저 설치함.

```bash
sudo apt-get update && sudo apt-get install -y curl
```

설치하기 싫으면 `python3`만으로도 받을 수 있음 (위 명령과 결과가 같음).

```bash
python3 -c "import io,tarfile,urllib.request as u; tarfile.open(fileobj=io.BytesIO(u.urlopen('https://github.com/NARi3040/Pintos-Tool/releases/latest/download/thread-viz.tar.gz').read())).extractall()"
```

`tools/thread-viz/`가 생김. `qemu-system-x86_64`, `gdb`(Python 지원), `python3`, `perl`, bash 5.1 이상이 필요함. 정글 Pintos Docker 이미지에는 다 들어 있음 (`curl`은 설치에만 쓰고, 도구 자체는 안 씀).

### 실행

```bash
tools/thread-viz/run.sh                       # 런처 페이지를 엶. 거기서 Project 1/2와 테스트를 골라 실행
tools/thread-viz/run.sh threads               # Project 1: alarm-*, priority-*, bench-* 전부
tools/thread-viz/run.sh priority-donate-nest  # 원하는 테스트만
```

인자 없이 실행하면 `http://localhost:8000/index.html`이 열리고, 페이지에서 테스트를 골라 실행·중지할 수 있음. 인자를 주면 지금처럼 터미널에서 바로 돌림.

`mlfqs-*` 테스트는 오래 걸려서 기본 목록에 없음. `MLFQS=1 tools/thread-viz/run.sh threads`로 포함하거나 이름을 직접 줌.

테스트마다 QEMU 기록/재생으로 채점한 실행 그대로를 추적하고, 정확성 점수와 별개로 효율 점수(실행 명령어 수 기준)도 매김. 결과는 `tools/thread-viz/traces/`에 저장됨. 수집 중 Ctrl-C를 누르면 그때까지의 트레이스를 저장하고 끝남.

실행하면 `http://localhost:8000/viewer.html` 주소가 나옴. 포트가 이미 쓰이고 있으면 `VIEW_PORT=9000 tools/thread-viz/run.sh`처럼 바꿈. 자세한 사용법과 옵션은 [tools/thread-viz/README.md](tools/thread-viz/README.md)에 있음.

주의:
- 화면의 점수는 재미용임. 최종 채점은 `make check`로 할 것.
- `run.sh`를 동시에 두 개 돌리지 말 것. 호스트와 컨테이너에서 같이 돌리는 것도 안 됨. gdb 포트(1234~)와 `traces/`를 같이 씀.

### Project 2 (User Programs)

```bash
tools/thread-viz/run.sh userprog                  # Project 2 테스트 전부
tools/thread-viz/run.sh args-multiple fork-once   # 원하는 테스트만
```

시스템 콜(인자, 반환값), fork/exec/wait/exit 프로세스 트리, argument passing 직후 유저 스택, page fault, 프로세스별 fd 표, 페이지/파일 누수를 `http://localhost:8000/uprog.html`에서 보여줌. 인자 전달, fork 반환값, wait 반환값, 잘못된 포인터 처리, 종료 메시지, 누수는 자동으로 검사해서 ⚠로 표시함. 자세한 내용은 [tools/thread-viz/README.md](tools/thread-viz/README.md)의 "Project 2" 절에 있음.

### 업데이트

`run.sh`를 실행할 때마다 새 버전을 확인하고 있으면 자동으로 받아서 적용함. 건너뛰려면 `--no-update`를 붙임. 수동으로 하려면 `python3 tools/thread-viz/update.py`임. 버전은 [Releases](https://github.com/NARi3040/Pintos-Tool/releases)에서 볼 수 있음.

### 벤치 테스트

`tools/thread-viz/bench/`에 부하 테스트 4개(`bench-lock-storm`, `bench-sleep-wave`, `bench-cond-relay`, `bench-scale`)가 있음. `bench-scale`은 리스트 길이에 따라 비용이 느는지 보는 복잡도 판정용임. `run.sh`를 처음 실행할 때 설치할지 물어보고, `y`면 `pintos/tests/threads/`에 복사한 뒤 `tests.c`, `tests.h`, `Make.tests`(`threads_SRC`에만. `make check` 대상은 아님)에 등록함. 대답은 저장돼서 다시 묻지 않음. `BENCH=1` / `BENCH=0`으로 정할 수 있고, 지우려면 `python3 tools/thread-viz/bench.py remove`임. 설치 안 해도 공식 테스트는 돌아감. 각 테스트 설명은 [tools/thread-viz/README.md](tools/thread-viz/README.md)의 "벤치 테스트" 절에 있음.

## 기여

버그 제보, 기능 제안, PR 모두 환영함. 브랜치·커밋 규칙, 머지 전 확인, 릴리스 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)에 있음. `main`은 보호돼 있어서 직접 push가 안 되고 PR로만 들어감.

## 라이선스

MIT. [LICENSE](LICENSE) 참고. 이 저장소에는 Pintos 소스나 과제 풀이가 들어 있지 않음.
