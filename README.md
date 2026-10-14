# Pintos-Tool

KAIST Pintos (x86-64) 과제용 도구 모음임.

## thread-viz

Project 1 (Threads) 테스트를 gdb로 추적해서 스레드 생성, ready_list, sleep_list, lock / semaphore / condition 대기 리스트, donation 흐름을 웹페이지에서 한 단계씩 보여주는 도구임. 커널 코드는 수정하지 않음.

### 설치

Pintos 저장소 루트(`pintos/` 폴더가 있는 곳)에서 실행함.

```bash
curl -fL https://github.com/NARi3040/Pintos-Tool/releases/latest/download/thread-viz.tar.gz | tar -xzf -
```

`tools/thread-viz/`가 생김. `qemu-system-x86_64`, `gdb`(Python 지원), `python3`, `perl`, bash 5.1 이상이 필요함. 정글 Pintos Docker 이미지에는 다 들어 있음.

### 실행

```bash
tools/thread-viz/run.sh                       # alarm-*, priority-*, bench-* 전부
tools/thread-viz/run.sh priority-donate-nest  # 원하는 테스트만
```

실행하면 `http://localhost:8000/viewer.html` 주소가 나옴. 포트가 이미 쓰이고 있으면 `VIEW_PORT=9000 tools/thread-viz/run.sh`처럼 바꿈. 자세한 사용법과 옵션은 [tools/thread-viz/README.md](tools/thread-viz/README.md)에 있음.

### 업데이트

`run.sh`를 실행할 때마다 새 버전을 확인하고 있으면 자동으로 받아서 적용함. 건너뛰려면 `--no-update`를 붙임. 수동으로 하려면 `python3 tools/thread-viz/update.py`임. 버전은 [Releases](https://github.com/NARi3040/Pintos-Tool/releases)에서 볼 수 있음.

### 벤치 테스트

`pintos-bench/`에 부하 테스트 3개(`bench-lock-storm`, `bench-sleep-wave`, `bench-cond-relay`) 소스가 있음. `pintos/tests/threads/`에 복사하고 `tests.c`, `tests.h`, `Make.tests`에 등록해야 함. 없어도 나머지 테스트는 돌아감. 각 테스트 설명은 [tools/thread-viz/README.md](tools/thread-viz/README.md)의 "벤치 테스트" 절에 있음.

## 라이선스

MIT. [LICENSE](LICENSE) 참고. 이 저장소에는 Pintos 소스나 과제 풀이가 들어 있지 않음.
