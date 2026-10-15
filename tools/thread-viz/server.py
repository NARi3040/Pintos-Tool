#!/usr/bin/env python3
"""thread-viz 뷰어 서버. 정적 파일(viewer.html, uprog.html, index.html ...)에 더해, 런처 페이지(index.html)가
테스트를 고르고 run.sh를 돌릴 수 있게 작은 API를 붙임.

  GET  /api/tests   테스트 목록과 지난 결과 (Project 1 / Project 2)
  GET  /api/status  실행 중인지, run.sh 출력 끝부분
  POST /api/run     {"mode": "threads"|"userprog", "tests": [...], "mlfqs": bool}
  POST /api/stop    실행 중인 run.sh에 Ctrl-C(SIGINT)를 보냄 -> 그때까지 트레이스를 저장하고 끝남

사용법: python3 server.py <포트> [바인드 주소]
"""
import json, os, re, signal, subprocess, sys, threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PINTOS = os.path.normpath(os.path.join(HERE, "..", "..", "pintos"))
LOG = os.path.join(HERE, "traces", "launcher.log")
NAME = re.compile(r"^[a-z0-9-]+$")
lock = threading.Lock()
proc = None   # 이 서버가 띄운 run.sh


def cks(sub):
    """그 폴더의 .ck 중 Make.tests에 등록된 테스트만 (tests/userprog/null.ck처럼 make check 대상이 아닌 것은 뺌)"""
    d = os.path.join(PINTOS, "tests", sub)
    try:
        names = sorted(f[:-3] for f in os.listdir(d) if f.endswith(".ck"))
    except OSError:
        return []
    try:
        with open(os.path.join(d, "Make.tests"), errors="replace") as f:
            mk = f.read()
    except OSError:
        return names
    return [n for n in names if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(n), mk)]


def result(outdir, t):
    """지난 실행의 PASS/FAIL. 없으면 None"""
    try:
        with open(os.path.join(HERE, outdir, t + ".result"), errors="replace") as f:
            return f.readline().strip() or None
    except OSError:
        return None


def tests():
    # run.sh와 같은 기준: Project 1은 alarm/priority/bench (+ mlfqs), Project 2는 tests/userprog, no-vm, filesys/base
    p1 = [t for t in cks("threads") if re.match(r"(alarm|priority|bench)-", t)]
    groups = {
        "threads": [("alarm / priority / bench", p1), ("mlfqs (오래 걸림)", cks("threads/mlfqs"))],
        "userprog": [("userprog", cks("userprog")), ("no-vm (multi-oom: 수천 개 프로세스, 앞부분만 기록)", cks("userprog/no-vm")),
                     ("filesys/base", cks("filesys/base"))],
    }
    out = {}
    for mode, gs in groups.items():
        outdir = "traces" if mode == "threads" else "utraces"
        out[mode] = [{"group": g, "tests": [{"name": t, "result": result(outdir, t)} for t in ts]} for g, ts in gs if ts]
    return out


def external_run():
    """터미널에서 직접 돌린 run.sh가 실행 중인지 (progress.json의 pid가 살아 있는지)"""
    try:
        with open(os.path.join(HERE, "progress.json")) as f:
            p = json.load(f)
        if p.get("running") and p.get("pid"):
            os.kill(int(p["pid"]), 0)
            return True
    except (OSError, ValueError):
        pass
    return False


def running():
    return (proc is not None and proc.poll() is None) or external_run()


def tail(n=60):
    try:
        with open(LOG, errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return ""


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def log_message(self, *a):
        pass

    def end_headers(self):
        # data.js, progress.json이 실행마다 바뀌므로 캐시하지 않음
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self.send_response(302)
            self.send_header("Location", "/index.html")
            self.end_headers()
        elif self.path.startswith("/api/tests"):
            self.reply(200, tests())
        elif self.path.startswith("/api/status"):
            self.reply(200, {"running": running(), "mine": proc is not None and proc.poll() is None,
                             "exit": None if proc is None else proc.poll(), "log": tail()})
        else:
            super().do_GET()

    def do_POST(self):
        global proc
        # 다른 사이트의 페이지가 localhost로 요청을 보내 실행시키지 못하게 막음. 이 헤더가 붙은 교차 출처 요청은
        # 브라우저가 사전 요청(preflight)부터 보내는데, 서버가 CORS를 허용하지 않으니 본 요청이 안 옴
        if self.headers.get("X-Thread-Viz") != "1":
            return self.reply(403, {"error": "forbidden"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
        except ValueError:
            return self.reply(400, {"error": "잘못된 요청"})
        with lock:
            if self.path == "/api/stop":
                if proc is not None and proc.poll() is None:
                    proc.send_signal(signal.SIGINT)
                    return self.reply(200, {"ok": True})
                return self.reply(409, {"error": "이 페이지에서 시작한 실행이 없음 (터미널에서 돌린 것은 터미널에서 Ctrl-C)"})
            if self.path != "/api/run":
                return self.reply(404, {"error": "없는 API"})
            if running():
                return self.reply(409, {"error": "이미 실행 중임. 끝나거나 중지한 뒤 다시 할 것"})
            mode = req.get("mode")
            names = req.get("tests") or []
            if mode not in ("threads", "userprog") or not isinstance(names, list) \
                    or not all(isinstance(t, str) and NAME.match(t) for t in names):
                return self.reply(400, {"error": "잘못된 요청"})
            # 테스트를 안 고르면 그 모드 전체. 업데이트 확인은 서버를 띄울 때 이미 했으므로 건너뜀
            args = [os.path.join(HERE, "run.sh"), "--no-update"] + (names or [mode])
            env = dict(os.environ, AUTO="0" if names else os.environ.get("AUTO", "1"),
                       MLFQS="1" if req.get("mlfqs") else "0", NO_OPEN="1")
            os.makedirs(os.path.dirname(LOG), exist_ok=True)
            log = open(LOG, "w")
            log.write("$ tools/thread-viz/run.sh %s\n" % " ".join(args[2:]))
            log.flush()
            # 새 세션으로 띄워 서버 쪽 Ctrl-C가 실행 중인 run.sh까지 가지 않게 함
            proc = subprocess.Popen(args, cwd=os.path.dirname(PINTOS), stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=env, start_new_session=True)
            log.close()
            return self.reply(200, {"ok": True, "page": "uprog.html" if mode == "userprog" else "viewer.html"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    bind = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    # run.sh가 nohup ... &로 띄우면 SIGINT가 무시(SIG_IGN) 상태로 상속되고, 그대로 두면 자식 run.sh도 무시한 채로 시작해
    # trap을 못 걸어서 중지가 안 됨. 처리기를 걸어 두면 exec된 자식에서는 기본 동작으로 돌아감
    signal.signal(signal.SIGINT, signal.default_int_handler)
    ThreadingHTTPServer((bind, port), Handler).serve_forever()
