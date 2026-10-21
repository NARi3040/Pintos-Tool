# 기여 가이드

Pintos-Tool은 학기가 바뀌어도 계속 쓰는 도구예요. 그래서 속도보다 **배포된 도구가 깨지지 않는 것**과 **나중에 온 사람이 이력을 읽을 수 있는 것**을 우선해요.

## 0. 먼저 알아 둘 것

- **`main`에 머지된 것은 사용자에게 가요.** `run.sh`는 실행할 때마다 최신 릴리스를 받아 자동 적용해요. 릴리스를 잘못 올리면 쓰는 사람 전원의 도구가 바로 깨져요.
- **Pintos 커널 코드는 수정하지 않아요.** thread-viz는 gdb로 밖에서 관찰만 해요. 커널 쪽에 무언가 넣어야 하는 기능은 들이지 않아요 (벤치 테스트 등록처럼 사용자 동의를 받고 되돌릴 수 있는 것은 예외예요).
- **과제 풀이나 Pintos 소스를 올리지 않아요.** 저장소는 공개이고 MIT예요. 디버깅용으로 쓴 풀이 코드, 트레이스 결과물(`traces/`, `data.js`)도 커밋하지 마세요.

## 1. 브랜치 전략 — GitHub Flow

```
main ←─ PR (리뷰 1명) ←─ feat/bench-scale
  └─ 릴리스는 main의 특정 커밋에서 따로 만듦 (5절)
```

- **`main`** : 항상 릴리스할 수 있는 상태예요. 직접 push는 금지예요. 저장소가 공개라 GitHub 브랜치 보호(Settings → Branches)로 막아요.
- **작업 브랜치** : `main`에서 따고 `main`으로 PR을 올려요. 머지한 뒤 삭제해요. 1주 넘게 살아 있는 브랜치는 `main`을 rebase로 따라가 주세요.
- `develop` 브랜치는 두지 않아요. 미완성 기능은 머지하지 말고 브랜치에 둬요.

### 브랜치 이름

```
<타입>/<짧은-설명>          # 이슈가 있으면 <타입>/#<번호>-<설명>
```

예: `feat/bench-scale`, `fix/#14-stale-donation`, `docs/contributing`

## 2. 커밋 컨벤션 — Conventional Commits

```
<타입>: <제목>

<본문: 왜 바꿨는지. 무엇을은 diff가 보여줌>
```

| 타입 | 용도 |
| --- | --- |
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 동작 변화 없는 정리 |
| `docs` | 문서 |
| `test` | 벤치 테스트·검사 추가 |
| `chore` | 버전 올림, 빌드·설정 |
| `merge` | 머지 커밋 제목 |

- 제목은 한글로 써도 되고, 명사형으로 끝내요 (예: `fix: 빈 kernel.lds.s 때문에 링크가 실패하던 문제 자동 복구`).
- **본문에 "왜"를 적어 주세요.** 1년 뒤 `git blame`을 본 사람이 이유를 알 수 있어야 해요. 증상, 원인, 고른 방법이 있으면 충분해요.
- 한 커밋에는 한 가지 변경만 담아요. 리팩터링과 기능 추가를 섞지 않아요.

## 3. 작업 흐름

1. **이슈** — 버그, 기능 제안은 이슈로 남겨요. 오타 수정처럼 작은 건 바로 PR을 올려도 돼요.
2. **브랜치** — `git switch -c fix/#14-stale-donation`
3. **확인** — 4절의 체크를 돌려요.
4. **PR** — 본문에 무엇을, 왜, 어떻게 확인했는지 적어요. 관련 이슈는 `closes #14`로 걸어요.
5. **리뷰** — 1명 이상 approve해야 해요. 혼자 관리하는 기간에는 셀프 리뷰 후 머지할 수 있지만, PR은 반드시 거쳐요 (이력을 남기기 위해서예요).
6. **머지**
   - 커밋 1~2개짜리 작은 PR: **Squash merge**, PR 제목을 커밋 컨벤션대로.
   - 커밋이 여러 개고 각각 의미가 있는 PR: **Merge commit**, 제목은 `merge: <요약>`.

## 4. 머지 전 확인

자동 테스트가 없으므로 실제로 돌려 봐요. 정글 Pintos Docker 이미지가 기준이에요.

- [ ] Pintos 저장소 루트에서 `tools/thread-viz/run.sh --no-update <바꾼 부분과 관련된 테스트>`가 끝까지 돌아가요
- [ ] viewer에서 해당 테스트를 열어 바뀐 부분이 의도대로 보여요
- [ ] 트레이스 수집 로직(`trace.py`)을 건드렸으면 `alarm-*`, `priority-*` 전체를 한 번 돌려요
- [ ] 벤치 관련이면 `python3 tools/thread-viz/bench.py remove` 한 뒤 다시 설치까지 확인해요
- [ ] 정답 구현과 **틀린 구현 둘 다**에서 확인해요 (검사·판정 로직은 틀린 걸 잡아야 의미가 있어요)
- [ ] 사용자에게 보이는 동작이 바뀌었으면 `README.md`, `tools/thread-viz/README.md`를 갱신해요
- [ ] 새 실행 결과물이 생기면 `.gitignore` 두 곳(루트, `tools/thread-viz/`)과 릴리스 스크립트의 제외 목록을 갱신해요

## 5. 릴리스

릴리스는 사용자 전원에게 자동 배포되므로 PR 머지와 분리해요.

1. 배포할 변경이 모두 `main`에 머지된 상태에서 시작해요.
2. `tools/thread-viz/VERSION`의 정수를 1 올리고 `chore: thread-viz v<N>`으로 커밋해요 (PR 경유).
3. 최신 `main`에서 태그를 만들어 push해요. GitHub Actions(`.github/workflows/release.yml`)가 태그 커밋을 checkout해서 tarball, sha256, `latest.json`을 올려요. 태그 메시지(제목 + 본문)가 릴리스 노트가 돼요.
   릴리스 노트는 `CHANGELOG.md`에 버전 절(`## v<N>`)로 먼저 써서 PR에 넣고, 그 절 내용을 태그 메시지로 써요. 첫 줄은 구버전 `update.py`가 업데이트할 때 보여 주는 한 줄이므로 사용자가 꼭 알아야 할 변화를 담아 주세요.
   ```bash
   git switch main && git pull
   awk '/^## v<N>$/{f=1; next} /^## v/{f=0} f' CHANGELOG.md | sed '/./,$!d' > /tmp/notes.txt   # 그 버전 절만 꺼내요
   git tag -a v<N> -F /tmp/notes.txt && git push origin v<N>
   ```
   태그와 `VERSION`이 다르면 Actions가 실패하고 릴리스는 만들어지지 않아요. 로컬에서 `tools/release-thread-viz.sh`를 직접 돌리지 마세요 (커밋하지 않은 로컬 파일이 배포될 수 있어요).
4. Actions 탭에서 성공했는지 보고, 다른 Pintos 저장소에서 설치 명령(README의 `curl ... | tar`)과 자동 업데이트를 한 번씩 확인해요.

규칙:

- **새 파일을 도구에 추가하면 `tools/release-thread-viz.sh`의 tar 목록에도 넣어 주세요.** 빠뜨리면 릴리스에서만 깨져요.
- `update.py`와 `latest.json` 형식을 바꿀 때는 **구버전 `update.py`가 새 릴리스를 받을 수 있는지** 확인해 주세요. 업데이트 경로가 끊기면 사용자가 수동으로 다시 설치해야 해요.
- 문제가 있는 릴리스는 지우지 말고, 고친 버전을 `v<N+1>`로 바로 올려요. 버전은 되돌리지 않아요.

## 6. 코드 리뷰

**보는 순서**

1. **동작** — 의도한 테스트에서 실제로 맞게 보이는가
2. **사용자 환경** — Docker 이미지, 호스트 둘 다에서 도는가. 필요한 도구(`qemu`, `gdb`, bash 5.1+ 등)가 늘었는가
3. **호환성** — 자동 업데이트, 기존 `traces/`, 이미 설치된 벤치와 충돌하지 않는가
4. **범위** — 커널 수정이나 풀이 코드가 섞이지 않았는가
5. 가독성

**코멘트 접두어**

| 접두어 | 의미 | 머지 |
| --- | --- | --- |
| `P1:` | 버그, 호환성 깨짐, 위 0절 위반 | 반영 전 머지 불가 |
| `P2:` | 수정 권장 | 작성자 판단 |
| `nit:` | 사소한 제안 | 무시 가능 |
| `q:` | 질문 | — |

- 리뷰 요청은 2일 안에 봐요. 못 보면 다른 사람에게 넘긴다고 댓글로 남겨요.
- PR은 작게 만들어요. 400줄이 넘으면 쪼갤 수 있는지 먼저 봐요 (`viewer.html`처럼 한 파일이 큰 경우는 예외예요).

## 7. 이슈와 라벨

| 분류 | 라벨 |
| --- | --- |
| 타입 | `bug` `enhancement` `docs` `question` |
| 영역 | `trace` `viewer` `bench` `update/release` |
| 상태 | `good first issue` `help wanted` `wontfix` |

버그 이슈에는 실행 명령, 테스트 이름, `VERSION` 값, 실행 환경(Docker / 호스트), 에러 출력을 적어 주세요.

<details>
<summary>영역 라벨 만들기 (gh CLI)</summary>

```bash
gh label create "trace" -c "1d76db" -d "trace.py, gdb 수집"
gh label create "viewer" -c "1d76db" -d "viewer.html, baseline.js"
gh label create "bench" -c "1d76db" -d "벤치 테스트, bench.py"
gh label create "update/release" -c "1d76db" -d "update.py, 릴리스 스크립트"
```

</details>

## 8. 인수인계

오래 관리하는 도구라 사람이 바뀌어요. 관리자가 바뀔 때는 다음을 넘겨요.

- 저장소 admin 권한과 릴리스 권한 (`gh release create`가 되는 계정)
- 열린 이슈·PR 현황과 다음에 할 일
- 이 문서에 없는 암묵적 규칙이 있다면 이 문서에 추가
