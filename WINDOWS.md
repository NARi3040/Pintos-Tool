# Windows에서 쓰기

Windows + Docker Desktop + VS Code Dev Container(정글 Pintos 이미지) 기준이에요. 아래 명령은 전부 **VS Code의 컨테이너 터미널**에서 실행해요. PowerShell, cmd, Git Bash에서는 실행하지 마세요.

## 설치

컨테이너 터미널에서 저장소 루트(`pintos/` 폴더가 있는 곳)로 이동한 뒤 받아요.

```bash
cd /workspaces/<저장소 이름>
sudo apt-get update && sudo apt-get install -y curl
curl -fL https://github.com/NARi3040/Pintos-Tool/releases/latest/download/thread-viz.tar.gz | tar -xzf -
tools/thread-viz/run.sh
```

- 프롬프트가 `.../pintos$`로 끝나면 한 단계 안쪽이에요. `cd ..`로 올라와서 받아 주세요
- Windows 탐색기에서 zip을 받아 풀지 마세요. 줄 끝이 CRLF로 바뀌거나 실행 권한이 빠져서 `run.sh`가 실행되지 않아요. 꼭 컨테이너 안에서 `curl`로 받아 주세요

## 브라우저로 열기

- `run.sh`가 서버를 띄우면 VS Code가 8000번 포트를 Windows 쪽으로 자동 포워딩해요. Windows 브라우저에서 `http://localhost:8000/index.html`을 열어요
- 열리지 않으면 VS Code 아래쪽 **PORTS** 탭에서 포워딩된 주소(예: `localhost:8001`)를 확인해 주세요
- VS Code 없이 `docker run -p 8000:8000`으로 띄운 컨테이너에서는 서버가 컨테이너 안 127.0.0.1에만 열려 있어 Windows에서 접속이 안 돼요. `VIEW_BIND=0.0.0.0 tools/thread-viz/run.sh`로 실행해 주세요

## 자주 생기는 문제

### `line 23: .../pintos/tools/thread-viz/../../pintos/utils/*: No such file or directory`

`pintos/` 폴더 **안**에 풀어서 생겨요. 다음 버전부터는 이 위치에서도 동작하지만, 저장소 루트로 옮기는 게 좋아요.

```bash
cd /workspaces/<저장소 이름>
mv pintos/tools ./tools
```

### `mv: cannot move ... Permission denied` / `tools/tools/thread-viz`가 생김

루트에 `tools/thread-viz`가 이미 있어서 생겨요 (예전 실행 결과 `traces/`, `utraces/`만 남은 폴더). 이름을 바꿔 두고 옮겨요.

```bash
mv tools/thread-viz tools/thread-viz.old
mv tools/tools/thread-viz tools/
rmdir tools/tools
```

잘 동작하면 `rm -rf tools/thread-viz.old`로 지워요.

### 브라우저에 `Error code: 404 File not found`

폴더를 옮기기 전에 띄운 서버가 8000번 포트에 남아서, 이제 없는 폴더를 보고 있어요. 끄고 다시 실행해요.

```bash
pkill -f "thread-viz/server.py"
tools/thread-viz/run.sh
```

그다음 브라우저를 새로고침해요.

### Windows에서 `make -B` 뒤 빌드 실패 (`_end_bss`, `relocation truncated to fit`)

Windows 폴더를 마운트한 컨테이너는 대소문자를 구분하지 않아서 `kernel.lds.s`가 빈 파일로 남아요. `make -B` 대신 `make clean && make`를 써 주세요. `run.sh`는 빌드 전에 알아서 지워요.

### `run.sh`를 Windows와 컨테이너에서 같이 돌림

VS Code가 컨테이너의 gdb 포트(1234~)를 Windows 쪽으로 포워딩해서 서로 엉켜요. 컨테이너 한쪽에서만 실행해 주세요.
