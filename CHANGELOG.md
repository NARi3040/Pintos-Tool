# 변경 이력

릴리스 노트 원본이에요. 태그를 만들 때 해당 버전 절을 태그 메시지로 써요 (CONTRIBUTING.md 5절).
첫 줄은 구버전 `update.py`가 업데이트할 때 보여 주는 한 줄이므로, 사용자가 꼭 알아야 할 변화를 담아요.

## v20

Project 3 (Virtual Memory) 지원과 화면 전체 개편: `run.sh vm`으로 vm 테스트를 추적하고, 타임라인을 확대·축소하고 끌어서 볼 수 있어요

새 기능
- `run.sh vm` (또는 tests/vm 테스트 이름): `pintos/vm/build`에서 Project 2 트레이서로 실행해요. `run.sh vm args-single`처럼 Project 2 테스트를 VM 빌드로도 돌려요. 런처에 Project 3을 추가했어요
- `uprog.html?vm`의 가상 메모리 탭: 이벤트 시점의 프로세스별 페이지 표(종류, 쓰기, lazy / 메모리 / swap / 파일로 내보냄)와 프레임 사용량. 학생 SPT를 읽지 않고 스켈레톤 함수(`uninit_new`, `pml4_set_page` 등) 훅으로 재구성해서 SPT 구조와 상관없이 동작해요
- page fault마다 `vm_try_handle_fault` 결과와 한 일(lazy 로딩, swap in, 스택 확장, 다른 페이지 내보냄)
- 자동 검사: SPT에 있는 페이지인데 처리 실패, 매핑 없이 true, 커널/NULL 주소 처리, 읽기 전용 페이지 쓰기 허용, rsp 아래·1MB 넘는 스택 확장, 늘려야 할 스택을 안 늘림. fault 처리 중에 exit하면 그 fault도 남겨요
- 타임라인 확대·축소: −/+·맞춤 버튼, Ctrl+휠, `+` `-` `0` 키. 현재 위치 손잡이를 끌어 이벤트를 넘겨 보고, 빈 곳을 끌어 옆으로 이동해요. 마우스를 올리면 그 이벤트를 툴팁으로 보여 줘요
- 뷰어의 **다시 실행** 버튼: 지금 보고 있는 테스트만 다시 추적하고, 끝나면 같은 위치로 새로고침해요
- 런처와 뷰어 테스트 목록을 이름 앞부분(`args-`, `wait-` ...)으로 한 번 더 묶어서 보여 줘요

바뀐 것
- 화면 전체를 토스 디자인 시스템 스타일로 개편: 공통 `ui.css`(라이트/다크 토큰, 버튼, 탭, 아이콘), 테두리 대신 면 구분, 기호·이모지 대신 라인 아이콘, 화면 문장 해요체
- 런처의 프로젝트 선택을 드롭다운으로 바꿨어요
- 타임라인을 보이는 구간만 그리게 바꿔 긴 트레이스도 찌그러지지 않아요. 이름 칸은 가로로 스크롤해도 남아요. Project 2/3 표시는 막대 위 눈금(색으로 구분)과 자식 생성 화살표로 정리했어요
- README를 빠른 시작 / 시작하기로 나눴어요

고친 것
- Project 2/3 트레이서: QEMU가 같은 브레이크포인트를 가끔 두 번 알려서 콘솔 글자, fault, malloc/free 이벤트가 하나씩 더 찍히던 문제 (`mmap-over-ddata` 같은 종료 메시지 경고)
- 런처: 실행 중 출력이 갱신될 때마다 출력 상자 스크롤이 맨 위로 돌아가던 문제

## v19

Project 2 누수 검사가 free 안 한 malloc 블록도 잡고, 누수마다 할당 시점과 그 프로세스가 종료할 때 안 풀었는지를 보여 줘요

새 기능 (uprog.html)
- `malloc`/`calloc`으로 받고 `free` 안 한 블록을 크기, 할당한 프로세스, 호출 경로와 함께 표시 (예: wait 뒤에 안 푼 `child_info`). 블록 때문에 같이 남은 malloc arena 페이지는 페이지 표에서 빼서 두 번 세지 않아요
- 누수 표마다 할당 시점(누르면 그 이벤트로 이동)과 소유 프로세스가 이미 종료했는지(= 종료 때 안 풀음) 칸

## v18

Project 2 뷰어의 스케줄러 상태를 Project 1 뷰어처럼 레인과 카드로 보여 주고, donation 대기 체인과 donations 리스트도 보여 줘요

새 기능 (uprog.html)
- 이벤트 직후 CPU / ready_list / sleep_list / BLOCKED 레인과 스레드 카드. 직전 이벤트와 달라진 곳은 노란색
- lock 대기 체인 (`A (기다림 L →) B ...`). 서로 기다리면 데드락으로 표시해요
- 스레드마다 donations 리스트와 기부한 스레드. 리스트 이름은 Project 1처럼 자동 감지해요

## v17

Project 2 뷰어에서도 ready_list/sleep_list 순서, 우선순위, lock/semaphore 대기열을 볼 수 있어요

새 기능 (uprog.html)
- 프로세스 트리에 스레드마다 priority (base priority가 다르면 같이)
- 이벤트 직후 `ready_list`, `sleep_list` 순서. 이름과 필드는 Project 1 뷰어처럼 자동 감지해요
- 주인이 있는 lock, 기다리는 스레드가 있는 lock/semaphore와 대기 순서
- 위쪽 "우선순위·대기열 보기"로 끄고 켤 수 있어요

고친 것
- 트레이스 중 원본 `syscall-entry.S`의 `popq %rsp`~`sysretq` 틈에 타이머가 걸려 커널이 유저 스택에서 죽으면(syn-read 등에서 가끔), 기록 없이 돈 실행이면 트레이스를 한 번 더 돌려요. 뷰어도 이 panic이면 원인 후보로 보여 줘요

## v16

디버거 추가: 뷰어에서 이벤트를 고르면 그 시점에 gdb로 멈추고, 한 줄씩/거꾸로 실행할 수 있어요. Project 2 자동 검사도 늘었어요

새 기능: 디버거 (debug.html)
- 뷰어의 "이 시점부터 디버그 ↗": 채점한 실행의 기록을 QEMU로 다시 재생해서 그 이벤트 시점에 정확히 멈춰요
- 소스 보기, breakpoint(줄 번호 클릭), 계속/다음 줄/들어가기/나오기/명령어 하나, 호출 스택, 지역 변수, 식 보기, 레지스터, 이벤트로 이동
- 거꾸로 실행: 이전 줄, 바로 전 실행한 줄, 호출한 곳, 명령어 하나, 거꾸로 계속. 기록 중 2초마다 남긴 스냅샷에서 다시 재생해 찾아요
- 외부 gdb로 열기: 터미널 gdb나 VS Code가 그 시점에 붙을 수 있게 QEMU를 세워 둬요
- Project 2는 기본이 기록 없이 실행이라, 디버거에서 "기록 모드로 다시 실행"을 누르면 그 테스트만 기록해서 열려요

바뀐 동작
- 기록(`.rr`)과 디스크(`.rr.d*.qcow2`, 스냅샷 포함)를 재생 뒤에도 지우지 않고 남겨요. 테스트 하나에 수~수십 MB예요
- 업데이트 전에 띄운 뷰어 서버는 run.sh가 버전을 보고 새로 띄워요

새 검사 (uprog.html ⚠)
- fd 반환값: open이 이미 열린 fd를 줌, 빈 이름 open 성공, 열린 파일 없이 fd 반환, 안 열린 fd의 read/write가 -1이 아님, read/write가 요청보다 큼, 콘솔 write 반환값, 실패한 exec의 반환값
- 같은 `struct file`을 두 번 `file_close` (해제된 메모리 사용)
- 시스템 콜에서 돌아올 때 `struct thread`의 magic이 깨짐 (커널 스택 넘침)
- 시간 초과/중단 때 멈춘 스레드마다 호출 경로를 보여 주고, lock 데드락, 끝난 스레드가 쥔 lock 대기, 같은 lock 재획득을 짚어 줘요
- fork 자식이 부모의 열린 파일을 `file_duplicate`하지 않은 것 같으면 참고로 표시해요
- 흔한 panic ASSERT에 원인 후보를 붙여요

## v15

Project 2를 과제 시작 전 코드에서 돌리면 트레이스가 하나도 안 남던 문제를 고쳤어요

고친 것
- `syscall.c`가 아직 `SYS_*`를 안 쓰는 커널에서 `uprog.py`가 바로 죽어, 모든 테스트가 FAIL에 트레이스 없음, `uprog.html`은 "udata.js가 없음"만 보이던 문제
- 이 상태처럼 유저 프로그램이 끝나기 전에 커널이 꺼지면, 누수 오류 대신 "끝나기 전에 커널이 꺼짐 (process_wait가 기다리지 않음)"을 보여 줘요
- 트레이서가 에러로 죽으면 `run.sh`가 gdb 출력 끝부분을 보여 주고, 전체는 `utraces/<테스트>.gdb`(Project 1은 `traces/`)에 남겨요

## v14

인자 없이 run.sh를 실행하면 이제 테스트 선택 페이지가 열려요 (전부 실행은 run.sh threads). Project 2를 지원해요

바뀐 동작
- `tools/thread-viz/run.sh`(인자 없음)는 서버를 띄우고 `http://localhost:8000/index.html`을 열어요. 페이지에서 Project 1 / Project 2와 테스트를 골라 실행·중지할 수 있어요
- 예전처럼 Project 1 테스트 전부를 바로 돌리려면 `tools/thread-viz/run.sh threads`를 실행해요 (mlfqs 포함은 `MLFQS=1 ... threads`)
- 테스트 이름을 주는 실행(`run.sh priority-donate-nest` 등)은 그대로예요
- 뷰어 서버가 `python3 -m http.server`에서 `server.py`로 바뀌었어요. 예전 서버가 떠 있으면 자동으로 교체해요. 끄는 명령은 `pkill -f "server.py 8000"`이에요

새 기능: Project 2 (User Programs)
- `run.sh userprog`(전부) 또는 `run.sh args-single fork-once`처럼 Project 2 테스트 이름을 주면 userprog 모드로 돌아요. 결과는 `uprog.html`에서 봐요
- 시스템 콜(인자, 문자열, write 내용, 반환값), fork/exec/wait/exit 프로세스 트리와 타임라인, argument passing 직후 유저 스택 덤프, page fault와 예외(유저 코드 위치까지), 프로세스별 fd 표, 페이지/파일 누수를 보여 줘요
- 자동 검사(⚠): 인자 전달 스택, fork 자식 rax/rip/rsp, wait 반환값, 잘못된 포인터 처리, 종료 메시지 `이름: exit(N)`, 누수
- Project 2는 기본이 `REPLAY=0`이에요 (QEMU 기록 모드가 디스크 I/O에서 매우 느려요). 채점 실행과 트레이스 실행이 따로라 출력이 다르면 뷰어에 표시해요
- `multi-oom`은 기본 목록에서 빠졌어요 (프로세스 수천 개). 이름을 직접 주면 앞부분 `TRACE_MAX_EVENTS`(기본 30000)개 이벤트만 기록해요

고친 것
- README: 정글 Docker 이미지에 없는 `curl` 설치 방법과, curl 없이 `python3`로 받는 명령 추가
- 수집 중 Ctrl-C를 누르면 run.sh가 `fin: unbound variable`로 exit 1 하던 문제 (이제 130으로 정상 중단해요)
- gcc 14 이상 호스트에서 유저 프로그램 라이브러리(`lib/user/console.c`) 빌드가 implicit-function-declaration 에러로 실패하던 문제
