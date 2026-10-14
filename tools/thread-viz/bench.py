#!/usr/bin/env python3
"""thread-viz 벤치 테스트 설치/제거. 사용법: bench.py [auto|install|remove|status] [pintos 폴더]

벤치(bench/*.c, .ck)를 pintos/tests/threads/에 복사하고 tests.c, tests.h, Make.tests에 등록함.
make check 대상(threads_TESTS)에는 넣지 않음. 사용자 저장소 파일을 고치므로 auto는 처음 한 번 물어보고
대답을 bench.choice에 저장함 (BENCH=1 / BENCH=0 환경 변수로 덮어씀). 이미 설치해 둔 사람은 묻지 않고 빠진 것만 채움.
"""
import filecmp, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "bench")
CHOICE = os.path.join(HERE, "bench.choice")
PINTOS = os.path.join(HERE, "..", "..", "pintos")
names = sorted(f[:-2] for f in os.listdir(SRC) if f.endswith(".c")) if os.path.isdir(SRC) else []
func = lambda n: "test_" + n.replace("-", "_")

def read(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()

def write(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)

def insert_after(text, anchor_re, line):
    """anchor_re에 맞는 마지막 줄 바로 뒤에 line을 넣음. 못 찾으면 None"""
    ms = list(re.finditer(anchor_re, text, re.M))
    if not ms:
        return None
    end = text.index("\n", ms[-1].end()) + 1 if "\n" in text[ms[-1].end():] else len(text)
    return text[:end] + line + "\n" + text[end:]

def edits(tdir, remove):
    """(경로, 새 내용) 목록. 앵커를 못 찾는 파일이 있으면 (None, 파일 이름)"""
    h, c, m = (os.path.join(tdir, f) for f in ("tests.h", "tests.c", "Make.tests"))
    out = []
    # (이미 등록됐는지 보는 패턴, 새 줄을 넣을 앵커 패턴, 넣을 줄)
    for path, build in ((h, lambda n: (rf"^extern test_func {func(n)};", r"^extern test_func \w+;", f"extern test_func {func(n)};")),
                        (c, lambda n: (rf'^[ \t]*\{{"{n}", {func(n)}\}},', r'^[ \t]*\{"(alarm|priority)-[\w-]+", \w+\},', f'    {{"{n}", {func(n)}}},')),
                        (m, lambda n: (rf"^tests/threads_SRC \+= tests/threads/{n}\.c", r"^tests/threads_SRC \+= .*", f"tests/threads_SRC += tests/threads/{n}.c"))):
        s = read(path)
        for n in names:
            pat, anchor, line = build(n)
            if remove:
                s = re.sub(pat + r"[ \t]*\n?", "", s, flags=re.M)
            elif not re.search(pat, s, re.M):
                s = insert_after(s, anchor, line)
                if s is None:
                    return None, os.path.basename(path)
        out.append((path, s))
    return out, None

def installed(tdir):
    return [n for n in names if os.path.exists(os.path.join(tdir, n + ".ck"))]

def install(pintos):
    tdir = os.path.join(pintos, "tests", "threads")
    if not os.path.isdir(tdir):
        print("[bench] pintos/tests/threads가 없어 벤치 설치를 건너뜀"); return 1
    out, bad = edits(tdir, False)
    if out is None:
        print(f"[bench] {bad}에서 등록할 위치를 못 찾아 설치 안 함. README의 수동 설치를 볼 것"); return 1
    changed = [os.path.basename(p) for p, s in out if read(p) != s]
    for p, s in out:
        if read(p) != s:
            write(p, s)
    copied = []
    for n in names:
        for ext in (".c", ".ck"):
            dst = os.path.join(tdir, n + ext)
            if not os.path.exists(dst) or not filecmp.cmp(os.path.join(SRC, n + ext), dst, shallow=False):
                shutil.copyfile(os.path.join(SRC, n + ext), dst); copied.append(n + ext)
    if changed or copied:
        print(f"[bench] 벤치 {len(names)}개 설치/갱신함 (고친 파일: {', '.join(changed) or '없음'}, 복사: {len(copied)}개)")
    return 0

def remove(pintos):
    tdir = os.path.join(pintos, "tests", "threads")
    out, bad = edits(tdir, True)
    if out is None:
        print(f"[bench] {bad}를 못 고쳐서 제거 안 함"); return 1
    for p, s in out:
        write(p, s)
    for n in names:
        for ext in (".c", ".ck"):
            if os.path.exists(os.path.join(tdir, n + ext)):
                os.remove(os.path.join(tdir, n + ext))
    write(CHOICE, "no\n")
    print("[bench] 벤치를 제거함. 다시 설치하려면 BENCH=1 tools/thread-viz/run.sh 또는 python3 tools/thread-viz/bench.py install")
    return 0

def auto(pintos):
    tdir = os.path.join(pintos, "tests", "threads")
    if not names or not os.path.isdir(tdir):
        return 0
    env = os.environ.get("BENCH")
    choice = {"1": "yes", "0": "no"}.get(env or "") or (read(CHOICE).strip() if os.path.exists(CHOICE) else "")
    if not choice and installed(tdir):   # 예전에 직접 설치한 사람은 동의한 것으로 봄
        choice = "yes"
    if not choice:
        if not sys.stdin.isatty():
            print("[bench] 벤치 테스트(부하 테스트 + 복잡도 판정용)는 설치 안 함. 설치하려면 터미널에서 실행해 대답하거나 BENCH=1로 실행")
            return 0
        print("[bench] thread-viz 벤치 테스트를 설치할까?")
        print("  - 부하 테스트 3개와 복잡도 판정용 bench-scale을 pintos/tests/threads/에 복사하고,")
        print("    tests.c, tests.h, Make.tests에 등록함 (make check 대상은 아님). 안 하면 공식 테스트만 추적함")
        print("  - 나중에 지우려면: python3 tools/thread-viz/bench.py remove")
        try:
            ans = input("설치할까? [y/N] ").strip().lower()
        except EOFError:
            ans = ""
        choice = "yes" if ans in ("y", "yes") else "no"
    if env in ("0", "1") or not os.path.exists(CHOICE) or read(CHOICE).strip() != choice:
        write(CHOICE, choice + "\n")
    return install(pintos) if choice == "yes" else 0

def status(pintos):
    tdir = os.path.join(pintos, "tests", "threads")
    print("설치됨:", ", ".join(installed(tdir)) or "없음", "· 선택:", read(CHOICE).strip() if os.path.exists(CHOICE) else "아직 안 물음")
    return 0

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "auto"
    pintos = os.path.realpath(sys.argv[2] if len(sys.argv) > 2 else PINTOS)
    sys.exit({"auto": auto, "install": install, "remove": remove, "status": status}[cmd](pintos))
