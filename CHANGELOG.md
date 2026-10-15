# 변경 이력

릴리스 노트 원본임. 태그를 만들 때 해당 버전 절을 태그 메시지로 씀 (CONTRIBUTING.md 5절).
첫 줄은 구버전 `update.py`가 업데이트할 때 보여주는 한 줄이므로, 사용자가 꼭 알아야 할 변화를 담음.

## v16

Project 2 자동 검사 추가: fd 반환값, 파일 이중 닫기, 커널 스택 넘침, 시간 초과 때 데드락/lock 주인 분석

새 검사 (uprog.html ⚠)
- fd 반환값: open이 이미 열린 fd를 줌, 빈 이름 open 성공, 열린 파일 없이 fd 반환, 안 열린 fd의 read/write가 -1이 아님, read/write가 요청보다 큼, 콘솔 write 반환값, 실패한 exec의 반환값
- 같은 `struct file`을 두 번 `file_close` (해제된 메모리 사용)
- 시스템 콜에서 돌아올 때 `struct thread`의 magic이 깨짐 (커널 스택 넘침)
- 시간 초과/중단 때 멈춘 스레드마다 호출 경로를 보여 주고, lock 데드락, 끝난 스레드가 쥔 lock 대기, 같은 lock 재획득을 짚어 줌
- fork 자식이 부모의 열린 파일을 `file_duplicate`하지 않은 것 같으면 참고로 표시
- 흔한 panic ASSERT에 원인 후보를 붙임

## v15

Project 2를 과제 시작 전 코드에서 돌리면 트레이스가 하나도 안 남던 문제 수정

고친 것
- `syscall.c`가 아직 `SYS_*`를 안 쓰는 커널에서 `uprog.py`가 바로 죽어, 모든 테스트가 FAIL에 트레이스 없음, `uprog.html`은 "udata.js가 없음"만 보이던 문제
- 이 상태처럼 유저 프로그램이 끝나기 전에 커널이 꺼지면, 누수 오류 대신 "끝나기 전에 커널이 꺼짐 (process_wait가 기다리지 않음)"을 보여 줌
- 트레이서가 에러로 죽으면 `run.sh`가 gdb 출력 끝부분을 보여 주고, 전체는 `utraces/<테스트>.gdb`(Project 1은 `traces/`)에 남김

## v14

인자 없이 run.sh를 실행하면 이제 테스트 선택 페이지가 열림 (전부 실행은 run.sh threads). Project 2 지원 추가

바뀐 동작
- `tools/thread-viz/run.sh`(인자 없음)는 서버를 띄우고 `http://localhost:8000/index.html`을 엶. 페이지에서 Project 1 / Project 2와 테스트를 골라 실행·중지할 수 있음
- 예전처럼 Project 1 테스트 전부를 바로 돌리려면 `tools/thread-viz/run.sh threads` (mlfqs 포함은 `MLFQS=1 ... threads`)
- 테스트 이름을 주는 실행(`run.sh priority-donate-nest` 등)은 그대로임
- 뷰어 서버가 `python3 -m http.server`에서 `server.py`로 바뀜. 예전 서버가 떠 있으면 자동으로 교체함. 끄는 명령은 `pkill -f "server.py 8000"`

새 기능: Project 2 (User Programs)
- `run.sh userprog`(전부) 또는 `run.sh args-single fork-once`처럼 Project 2 테스트 이름을 주면 userprog 모드로 돎. 결과는 `uprog.html`
- 시스템 콜(인자, 문자열, write 내용, 반환값), fork/exec/wait/exit 프로세스 트리와 타임라인, argument passing 직후 유저 스택 덤프, page fault와 예외(유저 코드 위치까지), 프로세스별 fd 표, 페이지/파일 누수를 보여줌
- 자동 검사(⚠): 인자 전달 스택, fork 자식 rax/rip/rsp, wait 반환값, 잘못된 포인터 처리, 종료 메시지 `이름: exit(N)`, 누수
- Project 2는 기본 `REPLAY=0` (QEMU 기록 모드가 디스크 I/O에서 매우 느림). 채점 실행과 트레이스 실행이 따로라 출력이 다르면 뷰어에 표시함
- `multi-oom`은 기본 목록에서 빠짐 (프로세스 수천 개). 이름을 직접 주면 앞부분 `TRACE_MAX_EVENTS`(기본 30000)개 이벤트만 기록함

고친 것
- README: 정글 Docker 이미지에 없는 `curl` 설치 방법과, curl 없이 `python3`로 받는 명령 추가
- 수집 중 Ctrl-C를 누르면 run.sh가 `fin: unbound variable`로 exit 1 하던 문제 (이제 130으로 정상 중단)
- gcc 14 이상 호스트에서 유저 프로그램 라이브러리(`lib/user/console.c`) 빌드가 implicit-function-declaration 에러로 실패하던 문제
