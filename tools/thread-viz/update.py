#!/usr/bin/env python3
"""thread-viz 온라인 업데이트. GitHub Releases의 최신 thread-viz.tar.gz로 이 폴더를 덮어씀.

  python3 tools/thread-viz/update.py            새 버전이 있으면 받아서 적용
  python3 tools/thread-viz/update.py --check    확인만
  python3 tools/thread-viz/update.py --auto     run.sh가 시작할 때 부름. 새 버전이 있으면 바로 적용(종료 코드 10).
                                                최신이면 "최신 버전이에요", 네트워크가 안 되면 실패했다고 알리고 끝남

환경 변수: THREAD_VIZ_REPO (기본 NARi3040/Pintos-Tool), THREAD_VIZ_BASE (기본 https://github.com/<repo>/releases/latest/download)
버전은 릴리스 파일 latest.json으로 확인함 (GitHub API가 아니라 호출 횟수 제한이 없음)
"""
import hashlib, json, os, sys, tarfile, tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("THREAD_VIZ_REPO", "NARi3040/Pintos-Tool")
BASE = os.environ.get("THREAD_VIZ_BASE", f"https://github.com/{REPO}/releases/latest/download")
PREFIX = "tools/thread-viz/"
KEEP = {"baseline.js"}  # 이미 있으면 덮어쓰지 않음 (BASELINE=1로 저장한 기준값 보존)


def get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "thread-viz-update"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download(url, timeout):
    """받으면서 진행도를 보여줌. 터미널이면 한 줄을 덮어쓰고, 아니면 25%마다 한 줄씩 찍음"""
    req = urllib.request.Request(url, headers={"User-Agent": "thread-viz-update"})
    buf, shown = bytearray(), -1
    with urllib.request.urlopen(req, timeout=timeout) as r:
        total = int(r.headers.get("Content-Length") or 0)
        while True:
            chunk = r.read(16384)
            if not chunk:
                break
            buf += chunk
            pct = len(buf) * 100 // total if total else -1
            line = f"  받는 중 [{'#' * (pct // 5):<20}] {pct}% ({len(buf) // 1024}/{total // 1024} KB)" if total else f"  받는 중 {len(buf) // 1024} KB"
            if sys.stdout.isatty():
                print("\r" + line, end="", flush=True)
            elif total and pct // 25 != shown // 25:
                print(line, flush=True)
            shown = pct
    if sys.stdout.isatty():
        print()
    return bytes(buf)


def local_version():
    try:
        return int(open(os.path.join(HERE, "VERSION")).read().strip())
    except (OSError, ValueError):
        return 0


def latest(timeout):
    info = json.loads(get(f"{BASE}/latest.json", timeout))
    return int(info["version"]), (info.get("notes") or "").strip()


def apply(data):
    with tempfile.TemporaryDirectory() as tmp:
        tgz = os.path.join(tmp, "t.tgz")
        open(tgz, "wb").write(data)
        with tarfile.open(tgz) as tf:
            members = [m for m in tf.getmembers() if not m.isdir()]
            for m in members:
                # 일반 파일만, tools/thread-viz/ 아래만 허용 (.. 이나 절대경로, 링크 거부)
                if not m.isfile() or not m.name.startswith(PREFIX) or ".." in m.name.split("/"):
                    sys.exit(f"업데이트 파일에 허용되지 않는 항목이 있어요: {m.name}")
            names = []
            for m in members:
                rel = m.name[len(PREFIX):]
                dst = os.path.join(HERE, rel)
                if rel in KEEP and os.path.exists(dst):
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                part = dst + ".new"
                with open(part, "wb") as f:
                    f.write(tf.extractfile(m).read())
                os.chmod(part, m.mode & 0o777)
                os.replace(part, dst)  # update.py 자신도 이 방식으로 안전하게 교체됨
                names.append(rel)
    return names


def main():
    check = "--check" in sys.argv
    auto = "--auto" in sys.argv
    cur = local_version()
    try:
        ver, body = latest(5 if auto or check else 15)
    except Exception as e:
        if auto:
            print(f"[thread-viz] v{cur} - 업데이트를 확인하지 못했어요 ({e}). 지금 버전으로 실행해요")
        if check or auto:
            sys.exit(0)
        sys.exit(f"업데이트 서버에 연결하지 못했어요: {e}")
    if ver <= cur:
        if not check:
            print(f"[thread-viz] v{cur} - 최신 버전이에요")
        return
    if check:
        print(f"[thread-viz] 새 버전 v{ver}이 있어요 (지금 v{cur}). 업데이트: python3 tools/thread-viz/update.py")
        return
    print(f"[thread-viz] 새 버전 v{ver}을 찾았어요 (지금 v{cur}). 업데이트할게요")
    if body:
        # 첫 줄이 요약, 나머지는 자세한 내용 (빈 줄은 건너뜀)
        lines = body.splitlines()
        print("  변경 내용: " + lines[0])
        for l in lines[1:]:
            if l.strip():
                print("    " + l)
    data = download(f"{BASE}/thread-viz.tar.gz", 120)
    want = get(f"{BASE}/thread-viz.tar.gz.sha256", 15).decode().split()[0]
    if hashlib.sha256(data).hexdigest() != want:
        sys.exit("  sha256이 맞지 않아요. 받은 파일이 깨져서 적용하지 않았어요")
    print("  sha256을 확인했어요. 파일을 교체하는 중이에요")
    names = apply(data)
    for n in names:
        print(f"    - {n}")
    print(f"[thread-viz] v{cur} -> v{ver} 업데이트를 마쳤어요 (파일 {len(names)}개)")
    if auto:
        sys.exit(10)


if __name__ == "__main__":
    main()
