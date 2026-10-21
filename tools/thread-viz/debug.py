"""thread-viz 디버거 세션. server.py가 씀.

run.sh가 남긴 기록(<test>.rr, .rr.d*.qcow2, .cmd)을 QEMU로 다시 재생하고, gdb(MI)를 붙여 조작함.
재생은 기록과 똑같이 흘러가므로 트레이스의 이벤트마다 남긴 icount(실행한 명령어 수)로 그 시점에 정확히 멈출 수 있음.

되감기: 기록할 때 래퍼(bin/qemu-system-x86_64)가 2초마다 스냅샷을 남김. 뒤로 가야 하면 목표 직전 스냅샷에서
QEMU를 새로 띄우고(RRSNAP) 앞으로 감음. QEMU 자체의 reverse-step/replay_seek은 실행 중에 중간 스냅샷을 불러오다
멈춰서(6.2, 10.2 모두) 쓰지 않고, 거꾸로 실행은 여기서 "앞으로 다시 돌려 보며 찾기"로 구현함.

재생 중에는 메모리/레지스터를 바꾸거나 커널 함수를 부르면 기록과 어긋나므로 gdb에서 막아 둠.
"""
import ctypes, hashlib, os, re, shutil, socket, subprocess, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
PINTOS = os.path.realpath(os.path.join(HERE, "..", "..", "pintos"))
if not os.path.isdir(os.path.join(PINTOS, "utils")) and os.path.isdir(os.path.join(HERE, "..", "..", "threads")):   # pintos/ 안에 설치한 경우
    PINTOS = os.path.realpath(os.path.join(HERE, "..", ".."))   # gdb가 주는 경로도 realpath라 맞춰 둠
MODES = {"threads": ("traces", "threads"), "userprog": ("utraces", "userprog"), "vm": ("vtraces", "vm")}
STEPS = {"continue": "-exec-continue", "next": "-exec-next", "step": "-exec-step", "finish": "-exec-finish",
         "stepi": "-exec-step-instruction", "nexti": "-exec-next-instruction"}
SRC_EXT = (".c", ".h", ".S", ".s", ".lds", ".ld")


class DebugError(Exception):
    pass


# ---- gdb/MI 출력 파싱 ----
def mi_value(s, i):
    """s[i]부터 MI 값 하나(c-string, {튜플}, [리스트])를 읽어 (값, 다음 위치)"""
    c = s[i]
    if c == '"':
        out, i = [], i + 1
        while s[i] != '"':
            if s[i] == "\\":
                i += 1
                out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(s[i], "\\" + s[i]))
            else:
                out.append(s[i])
            i += 1
        return "".join(out), i + 1
    if c in "{[":
        close, i = "}" if c == "{" else "]", i + 1
        d, lst = {}, []
        while s[i] != close:
            m = re.match(r"([\w-]+)=", s[i:])
            if m:
                v, i = mi_value(s, i + m.end())
                if c == "{":
                    d[m.group(1)] = v
                else:
                    lst.append(v)   # [frame={..},frame={..}] 꼴은 값만 모음
            else:
                v, i = mi_value(s, i)
                lst.append(v)
            if s[i] == ",":
                i += 1
        return (d if c == "{" else lst), i + 1
    raise ValueError("gdb MI 응답을 읽지 못했어요: %r" % s[i:i + 40])


def mi_results(s):
    """'k=v,k=v' -> dict"""
    d, i = {}, 0
    while i < len(s):
        m = re.match(r"([\w-]+)=", s[i:])
        if not m:
            break
        d[m.group(1)], i = mi_value(s, i + m.end())
        if i < len(s) and s[i] == ",":
            i += 1
    return d


def mi_quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def free_port():
    for p in range(1300, 1400):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise DebugError("디버거용 gdb 포트(1300~1399)가 모두 쓰이고 있어요")


# pintos 스크립트를 끄면 그 아래 QEMU는 고아가 되는데, 컨테이너의 PID 1(sleep 등)은 좀비를 안 거둠.
# 이 프로세스를 subreaper로 해 두면 고아가 여기로 와서 직접 거둘 수 있음 (PR_SET_CHILD_SUBREAPER = 36)
try:
    ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)
except (OSError, AttributeError):
    pass


def group_alive(pgid):
    """프로세스 그룹에 아직 살아 있는(좀비가 아닌) 프로세스가 있는지. 좀비는 거둠 (killpg(pgid, 0)는 좀비도 셈)"""
    alive = False
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                with open("/proc/%s/stat" % d) as f:
                    st = f.read().rsplit(")", 1)[1].split()
            except OSError:
                continue
            if int(st[2]) != pgid:
                continue
            if st[0] != "Z":
                alive = True
                continue
            try:   # 스레드가 남아 있으면 Z로 보여도 아직 못 거둠 (0을 돌려줌)
                if os.waitpid(int(d), os.WNOHANG)[0] == 0:
                    alive = True
            except ChildProcessError:
                pass   # 우리 자식이 아님 (subreaper가 안 된 환경). 거둘 수 없으니 끝난 것으로 봄
    return alive


def snapshots(qcow):
    """qcow2의 스냅샷 [(icount, 이름)] (같은 이름이 두 줄씩 보일 수 있어 합침)"""
    out = subprocess.run(["qemu-img", "snapshot", "-l", "-U", qcow], capture_output=True, text=True).stdout
    snaps = {}
    for l in out.splitlines()[2:]:
        f = l.split()
        if len(f) >= 3 and f[-1].isdigit():
            snaps[f[1]] = int(f[-1])
    return sorted((ic, tag) for tag, ic in snaps.items())


class Session:
    def __init__(self, mode, test, icount=None, external=False):
        if mode not in MODES or not re.match(r"^[a-z0-9-]+$", test or ""):
            raise DebugError("테스트 이름이 올바르지 않아요")
        outdir, kdir = MODES[mode]
        self.mode, self.test, self.external = mode, test, external
        self.rr = os.path.join(HERE, outdir, test + ".rr")
        self.build = os.path.join(PINTOS, kdir, "build")
        for f in ("", ".d0.qcow2"):
            if not os.path.exists(self.rr + f):
                raise DebugError("이 테스트의 실행 기록이 없어요. 기록 모드로 다시 실행해 주세요 (Project 2는 REPLAY=1)")
        if not os.path.exists(self.rr[:-3] + ".cmd"):
            raise DebugError("이 테스트의 실행 기록이 없어요. 기록 모드로 다시 실행해 주세요")
        try:
            want = open(self.rr[:-3] + ".kernel").read().strip()
        except OSError:
            want = None
        if want and want != hashlib.sha1(open(os.path.join(self.build, "kernel.bin"), "rb").read()).hexdigest():
            raise DebugError("기록한 뒤에 커널 코드가 바뀌었어요. 테스트를 다시 실행하면 같은 코드로 디버깅할 수 있어요")
        self.cmd = open(self.rr[:-3] + ".cmd", "rb").read().decode().split("\0")[:-1]
        self.user_prog = next((a.split(":")[0] for k, a in enumerate(self.cmd) if k and self.cmd[k - 1] == "-p"), None)
        self.console = os.path.join(HERE, outdir, test + ".debug-output")
        open(self.console, "w").close()
        self.tmp = None
        self.lock = threading.Lock()
        self.token = 0
        self.replies, self.q = {}, {}
        self.stopped = threading.Event()
        self.stop_info = {"reason": "start"}
        self.console_buf = []
        self.running = False
        self.closed = self.cancel = False
        self.gdb = self.qemu = None
        self.line_start = {}
        try:
            self._open(icount, external)
        except BaseException:
            self.close()
            raise

    def _open(self, icount, external):
        if external:
            # 외부 gdb는 QEMU의 reverse-step을 직접 씀. 그건 중간 스냅샷이 있으면 멈추므로 init만 남긴 사본으로 재생함
            self.tmp = tempfile.mkdtemp(prefix="tvz-ext-")
            src = self.rr
            self.rr = os.path.join(self.tmp, os.path.basename(src))
            for f in os.listdir(os.path.dirname(src)):
                if f.startswith(os.path.basename(src)):
                    shutil.copy(os.path.join(os.path.dirname(src), f), self.tmp)
            for f in os.listdir(self.tmp):
                if f.endswith(".qcow2"):
                    q = os.path.join(self.tmp, f)
                    for _ in range(4):   # 같은 이름이 둘씩 있으면 이름으로 지울 때 하나씩 지워짐
                        for _, tag in snapshots(q):
                            if tag != "init":
                                subprocess.run(["qemu-img", "snapshot", "-d", tag, q], capture_output=True)
        self.snaps = snapshots(self.rr + ".d0.qcow2") or [(0, "init")]
        self.port = free_port()
        self._launch(icount or 0)
        self._start_gdb()
        if icount:
            self._forward(int(icount))
            self.stop_info = {"reason": "goto"}
        if external:
            self.mi("-target-disconnect")
            self._kill_gdb()

    # ---- QEMU / gdb 프로세스 ----
    def _launch(self, ic):
        """ic 이하의 가장 가까운 스냅샷에서 재생하는 QEMU를 띄움 (멈춘 채로 gdb를 기다림)"""
        self.snap_ic, tag = max(s for s in self.snaps if s[0] <= ic) if any(s[0] <= ic for s in self.snaps) else self.snaps[0]
        env = dict(os.environ, RR="replay", RR_FILE=self.rr, RRSNAP=tag, GDB_PORT=str(self.port),
                   PATH=os.path.join(HERE, "bin") + ":" + os.path.join(PINTOS, "utils") + ":" + os.environ.get("PATH", ""))
        with open(self.console, "a") as out:
            self.qemu = subprocess.Popen(self.cmd, cwd=self.build, env=env, stdout=out, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, start_new_session=True)
        if self.closed:   # 다른 요청이 그사이 세션을 닫았으면 방금 띄운 것도 끔 (안 그러면 기록 파일을 잡은 채 남음)
            self._kill_qemu()
            raise DebugError("디버거가 닫혔어요")
        for _ in range(150):
            if self.qemu.poll() is not None:
                raise DebugError("QEMU가 바로 끝났어요: " + self.console_tail(3))
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", self.port)) == 0:
                    return
            time.sleep(0.1)
        raise DebugError("QEMU gdb 포트가 열리지 않았어요")

    def _kill_qemu(self):
        """pintos 스크립트와 그 아래 QEMU를 같이 끄고, QEMU가 디스크 잠금을 풀 때까지(그룹이 빌 때까지) 기다림"""
        if not self.qemu:
            return
        try:
            os.killpg(self.qemu.pid, 9)
        except OSError:
            pass
        self.qemu.wait()
        for _ in range(100):
            if not group_alive(self.qemu.pid):
                return
            time.sleep(0.05)

    def _restart(self, ic):
        """ic 직전 스냅샷부터 다시 재생. gdb는 그대로 두고 다시 붙음 (breakpoint 유지)"""
        try:
            self.mi("-target-disconnect")
        except DebugError:
            pass
        self._kill_qemu()
        self._launch(ic)
        self.mi("-target-select remote localhost:%d" % self.port, timeout=20)

    def _start_gdb(self):
        self.gdb = subprocess.Popen(["gdb", "--interpreter=mi3", "-q", "-nx", "kernel.o"], cwd=self.build,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1, start_new_session=True)
        threading.Thread(target=self._reader, args=(self.gdb,), daemon=True).start()
        for c in ("-gdb-set mi-async on", "-gdb-set pagination off", "-gdb-set confirm off",
                  # 재생 중 상태를 바꾸면 기록과 어긋남
                  "-gdb-set may-write-memory off", "-gdb-set may-write-registers off", "-gdb-set may-call-functions off",
                  "-gdb-set print elements 64"):
            self.mi(c)
        self.mi("-target-select remote localhost:%d" % self.port, timeout=20)
        if self.user_prog and self.mode != "threads" and os.path.exists(os.path.join(self.build, self.user_prog)):
            self.cli("add-symbol-file %s" % self.user_prog)
        # 끝까지 가면 QEMU가 꺼져서 세션이 끝나므로 power_off에서 멈춤 (panic도 결국 여기로 옴)
        self.end_bp = self.mi("-break-insert power_off").get("bkpt", {}).get("number")

    def _reader(self, gdb):
        for line in gdb.stdout:
            m = re.match(r"^(\d*)([\^*=~@&])(.*)$", line.rstrip("\n"))
            if not m:
                continue
            tok, kind, rest = m.groups()
            if kind == "^":
                cls, _, body = rest.partition(",")
                self.replies[tok] = (cls, mi_results(body) if body else {})
                ev = self.q.get(tok)
                if ev:
                    ev.set()
            elif kind == "*":
                cls, _, body = rest.partition(",")
                if cls == "running":
                    self.running = True
                    self.stopped.clear()
                elif cls == "stopped":
                    self.stop_info = mi_results(body)
                    self.running = False
                    self.stopped.set()
            elif kind in "~@":
                try:
                    self.console_buf.append(mi_value(rest, 0)[0])
                except (ValueError, IndexError):
                    pass
        self.running = False
        self.stopped.set()
        for ev in list(self.q.values()):   # gdb가 끝나면 기다리던 명령도 바로 깨움
            ev.set()

    def mi(self, cmd, timeout=30):
        gdb = self.gdb
        if gdb is None or gdb.poll() is not None:
            raise DebugError("gdb가 끝났어요. 디버거를 다시 시작해 주세요")
        self.token += 1
        tok = str(self.token)
        ev = self.q[tok] = threading.Event()
        try:
            gdb.stdin.write(tok + cmd + "\n")
            gdb.stdin.flush()
        except (OSError, ValueError):
            raise DebugError("gdb가 끝났어요. 디버거를 다시 시작해 주세요")
        if not ev.wait(timeout):
            raise DebugError("gdb가 응답하지 않아요: " + cmd)
        if tok not in self.replies:
            raise DebugError("gdb가 끝났어요. 디버거를 다시 시작해 주세요")
        cls, body = self.replies.pop(tok)
        del self.q[tok]
        if cls == "error":
            raise DebugError(body.get("msg", "gdb 오류"))
        return body

    def cli(self, cmd, timeout=30):
        """CLI 명령을 실행하고 콘솔 출력을 돌려줌"""
        self.console_buf = []
        self.mi("-interpreter-exec console " + mi_quote(cmd), timeout)
        return "".join(self.console_buf)

    def icount(self):
        m = re.search(r"instruction count = (\d+)", self.cli("monitor info replay"))
        return int(m.group(1)) if m else None

    def num(self, expr):
        return int(self.mi("-data-evaluate-expression " + mi_quote("(unsigned long)(%s)" % expr)).get("value")) & (2 ** 64 - 1)

    # ---- 앞으로 ----
    def _resume(self, cmd, wait=120):
        self.stopped.clear()
        self.mi(cmd)
        if not wait:   # 상태를 물었을 때 아직 안 멈춘 것으로 보이게 *running이 올 때까지 잠깐 기다림
            for _ in range(50):
                if self.running or self.stopped.is_set():
                    break
                time.sleep(0.01)
            return
        if not self.stopped.wait(wait):
            self.mi("-exec-interrupt")
            self.stopped.wait(10)

    def _bps(self):
        return self.mi("-break-list").get("BreakpointTable", {}).get("body", [])

    def _only(self, nums):
        """지정한 breakpoint만 켜고, 원래 켜져 있던 목록을 돌려줌"""
        on = [b["number"] for b in self._bps() if b.get("enabled") == "y"]
        off = [n for n in on if n not in nums]
        if off:
            self.mi("-break-disable " + " ".join(off))
        if nums:
            self.mi("-break-enable " + " ".join(nums))
        return on

    def _restore(self, on):
        allb = [b["number"] for b in self._bps()]
        off = [n for n in allb if n not in on]
        if off:
            self.mi("-break-disable " + " ".join(off))
        if on:
            self.mi("-break-enable " + " ".join(on))

    def _forward(self, ic, nums=()):
        """breakpoint는 nums만 켠 채로 ic까지 감. 도중에 멈춘 지점의 icount들을 돌려줌"""
        on = self._only(list(nums))
        hits = []
        try:
            while True:
                if self.cancel:
                    raise DebugError("멈췄어요")
                cur = self.icount() or 0
                if cur >= ic:
                    break
                self.cli("monitor replay_break %d" % ic)
                self._resume("-exec-continue")
                now = self.icount() or 0
                if now < ic:
                    if now <= cur or (self.stop_info or {}).get("reason") != "breakpoint-hit":
                        break   # 진행이 없거나(기록 끝) 시간 초과로 세운 것이면 breakpoint로 치지 않음
                    hits.append((now, self.num("$pc"), self.num("$rsp"), self.num("$rbp")))
        finally:
            self._restore(on)
        return hits

    def _goto(self, ic):
        ic = max(int(ic), 0)
        if ic < (self.icount() or 0):
            self._restart(ic)
        if ic > (self.icount() or 0):
            self._forward(ic)

    def _scan_back(self, cur, nums, want):
        """cur 이전에서 want(hit)를 만족하는 마지막 breakpoint 지점을 찾음. 가까운 스냅샷 구간부터 거슬러 올라감"""
        hi = cur
        for snap_ic, _ in sorted((s for s in self.snaps if s[0] < cur), reverse=True):
            self._restart(snap_ic)
            hits = [h for h in self._forward(hi, nums) if h[0] < cur and want(h)]
            if hits:
                return hits
            hi = snap_ic
        return []

    # ---- 화면에서 부르는 동작 ----
    def step(self, what, reverse=False):
        if what == "interrupt":
            # 락 없이: 거꾸로 실행/이동은 락을 쥔 채 오래 걸리므로 취소 표시를 남기고, 실행 중이면 gdb를 세움
            self.cancel = True
            if self.running:
                self.mi("-exec-interrupt")
            return
        with self.lock:
            self.cancel = False
            if self.running:
                raise DebugError("실행 중이에요. 먼저 멈춰 주세요")
            if what not in STEPS:
                raise DebugError("모르는 명령이에요")
            if not reverse:
                # continue는 오래 걸릴 수 있어서 기다리지 않고 바로 돌아감 (화면이 상태를 다시 물어봄)
                return self._resume(STEPS[what], None if what == "continue" else 60)
            cur = self.icount() or 0
            {"stepi": self._rev_stepi, "nexti": self._rev_stepi, "continue": self._rev_continue,
             "finish": self._rev_finish, "next": self._rev_next, "step": self._rev_step}[what](cur)
            self.stop_info = {"reason": "reverse-" + what}

    def _rev_stepi(self, cur):
        self._goto(cur - 1)

    def _rev_continue(self, cur):
        nums = [b["number"] for b in self._bps() if b.get("enabled") == "y" and b.get("number") != self.end_bp]
        hits = self._scan_back(cur, nums, lambda h: True) if nums else []
        self._goto(hits[-1][0] if hits else 0)
        if not hits:
            self.stop_info = {"reason": "no-history"}

    def _frame_info(self):
        """(함수 시작 주소, 현재 프레임의 CFA)"""
        pc = self.num("$pc")
        m = re.search(r"\+ (\d+)", self.cli("info symbol 0x%x" % pc))
        entry = pc - int(m.group(1)) if m else pc
        m = re.search(r"frame at (0x[0-9a-f]+)", self.cli("info frame"))
        if not m:
            raise DebugError("현재 프레임을 읽지 못했어요")
        return entry, int(m.group(1), 16)

    @staticmethod
    def _cfa(h, entry):
        # -O0, frame pointer 빌드: 함수 첫 명령어에선 rsp+8, 본문에선 rbp+16이 호출 직전 rsp (CFA)
        return h[2] + 8 if h[1] == entry else h[3] + 16

    def _temp_bps(self, addrs):
        return [self.mi("-break-insert *0x%x" % a).get("bkpt", {}).get("number") for a in addrs]

    def _rev_finish(self, cur):
        entry, cfa = self._frame_info()
        tmp = self._temp_bps([entry])
        try:
            hits = self._scan_back(cur, tmp, lambda h: h[1] == entry and h[2] + 8 == cfa)
        finally:
            self.mi("-break-delete " + " ".join(tmp))
        if not hits:
            raise DebugError("이 함수를 부른 곳을 기록에서 찾지 못했어요. 스레드 시작 함수이거나 인터럽트로 들어온 함수일 수 있어요")
        self._goto(hits[-1][0] - 1)   # 함수 첫 명령어 바로 전 = 호출한 call 명령어

    def _line_starts(self, entry):
        """함수 안 각 소스 줄의 시작 주소들"""
        body = self.mi("-data-disassemble -a 0x%x -- 1" % entry).get("asm_insns", [])
        starts = set()
        for blk in body:
            insns = blk.get("line_asm_insn") if isinstance(blk, dict) else None
            if insns:
                starts.add(int(insns[0]["address"], 16))
        return starts

    def _rev_next(self, cur):
        entry, cfa = self._frame_info()
        pc = self.num("$pc")
        tmp = self._temp_bps(sorted(self._line_starts(entry) | {entry}))
        try:
            hit = None
            hi = cur
            # 지금 줄의 시작만 잡힌 구간이면 더 앞 구간까지 봄
            while hit is None and hi > 0:
                hits = self._scan_back(hi, tmp, lambda h: self._cfa(h, entry) == cfa)
                if not hits:
                    break
                hit = self._prev_line(hits, pc)
                hi = hits[0][0]
        finally:
            self.mi("-break-delete " + " ".join(tmp))
        if hit is None:
            return self._rev_finish(cur)   # 함수 첫 줄이면 부른 곳으로 (gdb와 같음)
        self._goto(hit[0])

    def _line(self, pc):
        """pc의 (파일, 줄, 그 줄의 시작 주소인지)"""
        if pc not in self.line_start:
            out = self.cli("info line *0x%x" % pc)
            m = re.search(r'Line (\d+) of "([^"]+)"', out)
            st = re.search(r"starts at address (0x[0-9a-f]+)", out)
            self.line_start[pc] = (m and (m.group(2), int(m.group(1))), bool(st) and int(st.group(1), 16) == pc)
        return self.line_start[pc]

    def _is_line_start(self, pc):
        return self._line(pc)[1]

    def _prev_line(self, hits, cur_pc):
        """줄 시작 지점들 중 지금 줄의 것(줄 중간에서 거꾸로 가면 맨 끝에 붙는 것)은 빼고 마지막 것"""
        here = self._line(cur_pc)[0]
        while hits and self._line(hits[-1][1])[0] == here:
            hits = hits[:-1]
        return hits[-1] if hits else None

    def _rev_step(self, cur):
        """바로 전에 실행한 소스 줄의 시작 (다른 함수 안이어도 됨). 조금 앞에서부터 한 명령어씩 다시 실행해 보며 찾음"""
        for back in (200, 2000, 20000):
            self._goto(max(cur - back, 0))
            starts = []
            n = 0
            while True:
                ic = self.icount() or 0
                if ic >= cur:
                    break
                pc = self.num("$pc")
                if self._is_line_start(pc):
                    starts.append((ic, pc))
                self._resume("-exec-step-instruction", 10)
                n += 1
                if n > back + 10:
                    break
            hit = self._prev_line(starts, self.num("$pc"))
            if hit is not None:
                return self._goto(hit[0])
            if cur - back <= 0:
                break
        raise DebugError("바로 전 소스 줄을 찾지 못했어요")

    def goto(self, ic):
        """icount 시점으로 이동. 뒤면 그 직전 스냅샷에서 다시 재생함. 그 사이 breakpoint는 끔"""
        with self.lock:
            if self.running:
                raise DebugError("실행 중이에요. 먼저 멈춰 주세요")
            self.cancel = False
            self._goto(ic)
            self.stop_info = {"reason": "goto"}

    def breakpoint(self, loc, on):
        with self.lock:
            if self.running:
                raise DebugError("실행 중이에요. 먼저 멈춰 주세요")
            if on:
                # 함수 이름, 파일:줄, *주소만 받음 ("loc if 조건" 같은 식이 gdb로 가지 않게)
                if not re.match(r"^([\w./+-]+(:\d+)?|\*0x[0-9a-fA-F]+)$", loc):
                    raise DebugError("함수 이름이나 파일:줄만 쓸 수 있어요")
                return self.mi("-break-insert " + mi_quote(loc)).get("bkpt", {})
            for b in self._bps():
                if b.get("number") != self.end_bp and (b.get("original-location") == loc or b.get("number") == loc):
                    self.mi("-break-delete " + b["number"])

    def evaluate(self, expr, frame=0):
        # gdb 13+의 $_shell() 같은 편의 함수는 명령을 실행할 수 있어서 막음
        # gdb 13+의 $_shell()은 명령을 실행함. $f = $_shell 처럼 변수에 담아 부를 수도 있어서 $_ 자체를 막음
        if "$_" in expr or "\n" in expr:
            raise DebugError("$_로 시작하는 gdb 변수와 함수는 쓸 수 없어요")
        with self.lock:
            if self.running:
                raise DebugError("실행 중이에요. 먼저 멈춰 주세요")
            self.mi("-stack-select-frame %d" % int(frame))
            return self.mi("-data-evaluate-expression " + mi_quote(expr)).get("value")

    def state(self, frame=0):
        with self.lock:
            st = {"running": self.running, "ended": self.qemu is None or self.qemu.poll() is not None, "port": self.port,
                  "external": self.external, "test": self.test, "mode": self.mode, "console": self.console_tail(80)}
            if st["running"] or st["ended"] or self.external:
                return st
            info = self.stop_info or {}
            st["reason"] = info.get("reason") or info.get("signal-name") or ""
            if info.get("bkptno") == self.end_bp:
                st["reason"] = "power_off"
            st["icount"] = self.icount()
            try:
                frames = self.mi("-stack-list-frames 0 19").get("stack", [])
            except DebugError:
                frames = []
            st["frames"] = [{"level": int(f.get("level", 0)), "func": f.get("func", "??"), "addr": f.get("addr"),
                             "file": self.rel(f.get("fullname")), "line": int(f["line"]) if f.get("line") else None}
                            for f in frames]
            frame = min(int(frame), max(len(frames) - 1, 0))
            st["frame"] = frame
            try:
                self.mi("-stack-select-frame %d" % frame)
                st["vars"] = self.mi("-stack-list-variables --simple-values").get("variables", [])
            except DebugError:
                st["vars"] = []
            st["regs"] = {}
            for r in ("rip", "rsp", "rbp", "rax", "rdi", "rsi", "rdx"):
                try:
                    st["regs"][r] = "%#x" % self.num("$" + r)
                except (DebugError, ValueError, TypeError):
                    pass
            try:   # 지금 CPU를 쓰는 스레드 (커널 스택이면 그 페이지 바닥의 struct thread)
                if int(st["regs"].get("rsp", "0"), 16) >= 0x8004000000:
                    e = "((struct thread *)((unsigned long)$rsp & ~0xfffUL))"
                    st["thread"] = {"name": self.mi("-data-evaluate-expression " + mi_quote(e + "->name")).get("value"),
                                    "tid": self.mi("-data-evaluate-expression " + mi_quote(e + "->tid")).get("value")}
                else:
                    st["user"] = True
            except (DebugError, ValueError):
                pass
            if not st["frames"] or st["frames"][0]["file"] is None:
                try:
                    st["asm"] = self.cli("x/8i $pc")
                except DebugError:
                    pass
            st["breakpoints"] = [{"number": b.get("number"), "loc": b.get("original-location"), "file": self.rel(b.get("fullname")),
                                  "line": int(b["line"]) if b.get("line") else None, "enabled": b.get("enabled") == "y"}
                                 for b in self._bps() if b.get("number") != self.end_bp]
            return st

    def rel(self, path):
        if not path:
            return None
        p = os.path.relpath(os.path.realpath(path), PINTOS)
        return None if p.startswith("..") else p

    def console_tail(self, n):
        try:
            with open(self.console, errors="replace") as f:
                return "".join(f.readlines()[-n:])
        except OSError:
            return ""

    def _kill_gdb(self):
        if self.gdb and self.gdb.poll() is None:
            self.gdb.kill()
            self.gdb.wait()
        self.gdb = None

    def close(self):
        self.closed = self.cancel = True
        self._kill_gdb()
        self._kill_qemu()
        if self.tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)


def source(path):
    """pintos 안의 소스 파일 내용. 밖이거나 소스가 아니면 None"""
    full = os.path.realpath(os.path.join(PINTOS, path))
    if os.path.relpath(full, PINTOS).startswith("..") or not full.endswith(SRC_EXT) or not os.path.isfile(full):
        return None
    with open(full, errors="replace") as f:
        return f.read()
