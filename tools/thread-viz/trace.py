# gdb 안에서 실행되는 트레이서. 커널 함수에 멈추지 않는 브레이크포인트를 걸고,
# 매 이벤트마다 ready_list / sleep_list / 스레드 상태 스냅샷을 JSON으로 저장함.
# 스냅샷은 함수 "진입 시점" 상태임. 뷰어는 다음 이벤트의 스냅샷을 "이후 상태"로 씀.
import gdb, json, os, re, signal, struct, threading

OUT = os.environ["TRACE_OUT"]
# 무한루프/데드락 대비: 이 시간(초)이 지나도 power_off에 못 가면 SIGINT로 멈추고 그때까지 저장함
TIMEOUT = float(os.environ.get("TRACE_TIMEOUT", "60"))
inf = gdb.selected_inferior()

def off(expr):
    return int(gdb.parse_and_eval("(long)&(%s)" % expr))

# ---- 구조 자동 감지 ----
# 원본 Pintos에 있는 필드(tid, status, name, priority, elem, magic)는 이름 그대로 씀.
# 사람마다 이름이 다른 필드(base priority, 기다리는 락, donations)는 타입과 이름 패턴으로 찾고, 없으면 그 기능만 끔.
# 타입은 typedef를 벗겨서 비교함 (예: fixed_t, int32_t -> int)
TFIELDS = [(f.name, str(f.type.strip_typedefs()).strip(), f.bitpos // 8) for f in gdb.lookup_type("struct thread").fields()]

def pick(type_, pattern, exclude=()):
    """타입이 맞는 필드 중 이름이 pattern에 맞는 것. 없으면 None."""
    for name, t, o in TFIELDS:
        if t == type_ and name not in exclude and re.search(pattern, name, re.I):
            return name
    return None

O = {k: next(o for n, _, o in TFIELDS if n == k) for k in ("tid", "status", "name", "priority", "elem", "magic")}
LAYOUT = {
    "base": pick("int", r"(init|orig|base|real|old|saved|default|own).*pri|pri.*(init|orig|base|real|old|saved)"),
    "wait_lock": pick("struct lock *", r"wait|lock"),
    "donations": pick("struct list", r"don"),
    "donation_elem": pick("struct list_elem", r"don", exclude=("elem",)),
}
if not (LAYOUT["donations"] and LAYOUT["donation_elem"]):
    LAYOUT["donations"] = LAYOUT["donation_elem"] = None
for k in ("base", "wait_lock", "donations", "donation_elem"):
    if LAYOUT[k]:
        O[k] = next(o for n, _, o in TFIELDS if n == LAYOUT[k])

def find_sleep_list():
    """전역 struct list 변수 중 잠든 스레드 리스트로 보이는 것. (file, name) 또는 None."""
    out = gdb.execute('info variables -q -n -t "struct list"', to_string=True)
    cur, cands = None, []
    for line in out.splitlines():
        m = re.match(r"File (.+):$", line)
        if m:
            cur = os.path.basename(m.group(1))
            continue
        m = re.search(r"struct list (\w+);$", line)
        if m and cur:
            cands.append((cur, m.group(1)))
    for f, n in cands:
        if re.search(r"sleep|alarm|wait|block", n, re.I) and n != "ready_list":
            return f, n
    return None

_sl = find_sleep_list()
SLEEP_SYM = "'%s'::%s" % _sl if _sl else None
# sleep 리스트에 쓰는 list_elem: 이름에 sleep이 들어간 별도 elem이 있으면 그것, 아니면 elem
_se = pick("struct list_elem", r"sleep|alarm|timer", exclude=("elem",))
SLEEP_ELEM = next(o for n, _, o in TFIELDS if n == _se) if _se else O["elem"]
LAYOUT["sleep_list"] = _sl[1] if _sl else None
LAYOUT["sleep_elem"] = _se or "elem"

# ---- MLFQS ----
# nice / recent_cpu 필드, 전역 load_avg. recent_cpu와 load_avg는 17.14 고정소수점 int라고 가정하고 원시값을 저장함
for _k, _pat in (("nice", r"nice"), ("recent_cpu", r"recent")):
    _n = pick("int", _pat)
    LAYOUT[_k] = _n
    if _n:
        O[_k] = next(o for n, _, o in TFIELDS if n == _n)

def find_global(pattern, type_re, skip=r"sleep"):
    r"""이름이 pattern(gdb BRE, 또는은 \|)에 맞고 선언이 type_re에 맞는 전역 변수
    -> ("'파일'::이름", 이름, 배열 크기 또는 None)."""
    out = gdb.execute("info variables -q -n " + pattern, to_string=True)
    cur = None
    for line in out.splitlines():
        m = re.match(r"File (.+):$", line)
        if m:
            cur = os.path.basename(m.group(1))
            continue
        m = re.search(type_re + r"\s+\**(\w+)(?:\[(\d+)\])?;$", line)
        if m and cur and not re.search(skip, m.group(1)):
            return "'%s'::%s" % (cur, m.group(1)), m.group(1), int(m.group(2)) if m.group(2) else None
    return None

_la = find_global("load_avg", r"(?:int|int32_t|int64_t|long|\w+_t)")
LOAD_SYM = _la[0] if _la else None
LAYOUT["load_avg"] = _la[1] if _la else None

# ready queue: 보통 ready_list 하나. MLFQS를 큐 배열로 만든 경우(ready_list[64] 등)는 높은 인덱스부터 이어 붙임
_rq = find_global("ready", r"struct list") or find_global(r"queue\|mlfq", r"struct list")
if _rq and _rq[2]:
    READY_SYMS = ["%s[%d]" % (_rq[0], i) for i in range(_rq[2] - 1, -1, -1)]
    LAYOUT["ready"] = "%s[%d]" % (_rq[1], _rq[2])
else:
    READY_SYMS = [_rq[0] if _rq else "ready_list"]
    LAYOUT["ready"] = _rq[1] if _rq else "ready_list"
ROOT = os.path.realpath(os.path.join(os.getcwd(), "../.."))   # build 디렉터리 기준 pintos 루트
sources = set()   # 이벤트 위치로 등장한 소스 파일 (pintos 루트 기준 상대 경로)
HOLDER = off("((struct lock *)0)->holder")
LOCK_SEMA = off("((struct lock *)0)->semaphore")
SEMA_WAITERS = off("((struct semaphore *)0)->waiters")
COND_WAITERS = off("((struct condition *)0)->waiters")
SE_SEMA = off("((struct semaphore_elem *)0)->semaphore")
LIST_TAIL = off("((struct list *)0)->tail")
STATUS = ["RUNNING", "READY", "BLOCKED", "DYING"]

threads = {}   # 주소 -> 고유 id (같은 페이지 재사용 대비)
info = []      # id -> {name, addr}
dead = set()
objs = {}      # 동기화 객체 주소 -> {"id": "L1"/"S1"/"C1", "kind", "sys"}
test_started = False   # run_test 이전에 만든 객체는 커널 내부용(sys)으로 표시
events = []

def u64(addr):
    return struct.unpack("<Q", bytes(inf.read_memory(addr, 8)))[0]

def obj_id(addr, kind="lock", reinit=False):
    if not addr:
        return None
    if reinit or addr not in objs:
        sys_ = not test_started
        # 번호는 kind별로 늘어나기만 함 (같은 주소가 재초기화돼도 다른 객체와 id가 겹치지 않게)
        n = _obj_n[(kind, sys_)] = _obj_n.get((kind, sys_), 0) + 1
        label = "%s%s%d" % ("k" if sys_ else "", kind[0].upper(), n)
        # 전역/정적 변수면 이름을 붙임 (스택 변수는 이름을 알 수 없음)
        sym = gdb.execute("info symbol %d" % addr, to_string=True)
        if " in section " in sym and "+" not in sym.split(" in section ")[0]:
            label += " (%s)" % sym.split(" in section ")[0].strip()
        objs[addr] = {"id": label, "kind": kind, "sys": sys_}
    return objs[addr]["id"]

_obj_n = {}

def lock_id(addr):
    return obj_id(addr, "lock")

def tid_of(addr):
    return threads.get(addr)

def read_thread(addr):
    raw = bytes(inf.read_memory(addr, O["magic"] + 4))
    i32 = lambda o: struct.unpack_from("<i", raw, o)[0]
    wl = struct.unpack_from("<Q", raw, O["wait_lock"])[0] if "wait_lock" in O else 0
    holder = u64(wl + HOLDER) if wl else 0
    return {
        "tid": i32(O["tid"]),
        "status": STATUS[i32(O["status"])] if 0 <= i32(O["status"]) < 4 else "?",
        "name": raw[O["name"]:O["name"] + 16].split(b"\0")[0].decode(errors="replace"),
        "pri": i32(O["priority"]),
        **({"nice": i32(O["nice"])} if "nice" in O else {}),
        **({"rcpu": i32(O["recent_cpu"])} if "recent_cpu" in O else {}),
        "base": i32(O["base"]) if "base" in O else i32(O["priority"]),
        "lock": lock_id(wl),
        "holder": tid_of(holder),
        # donations를 모르면(필드 없음, 리스트 손상) None. 뷰어는 None이면 donation 계산 검사를 건너뜀
        "dons": thread_list(addr + O["donations"], O["donation_elem"]) if "donations" in O else None,
    }

def walk(sym, elem_off=O["elem"]):
    if not sym:
        return []
    head = int(gdb.parse_and_eval("(long)&" + sym))
    tail = head + LIST_TAIL
    out, e = [], u64(head + 8)  # head.next
    while e and e != tail and len(out) < 200:
        out.append(tid_of(e - elem_off))
        e = u64(e + 8)
    return out

def walk_addr(head, limit=64):
    """리스트 원소(list_elem) 주소 목록. 망가진 리스트(해제된 스택 등)면 None."""
    tail = head + LIST_TAIL
    out, e = [], u64(head + 8)
    while e != tail:
        if not e or len(out) >= limit:
            return None
        out.append(e)
        e = u64(e + 8)
    return out

def thread_list(head, elem_off=O["elem"]):
    """스레드가 elem(또는 donation_elem)으로 들어간 리스트 -> 스레드 id 목록. 모르는 원소가 있으면 None."""
    es = walk_addr(head)
    if es is None:
        return None
    ids = [tid_of(e - elem_off) for e in es]
    return None if any(i is None or i in dead for i in ids) else ids

def read_obj(addr, o):
    if o["kind"] == "lock":
        h = u64(addr + HOLDER)
        w = thread_list(addr + LOCK_SEMA + SEMA_WAITERS)
        if w is None or (h and (tid_of(h) is None or tid_of(h) in dead)):
            return None
        return {"kind": "lock", "holder": tid_of(h), "waiters": w}
    if o["kind"] == "sema":
        w = thread_list(addr + SEMA_WAITERS)
        if w is None:
            return None
        return {"kind": "sema", "value": struct.unpack("<I", bytes(inf.read_memory(addr, 4)))[0], "waiters": w}
    es = walk_addr(addr + COND_WAITERS)
    if es is None:
        return None
    # cond의 원소는 semaphore_elem. 각 원소의 세마포어에서 기다리는 스레드를 꺼냄
    ws = [thread_list(e + SE_SEMA + SEMA_WAITERS) for e in es]
    return None if any(w is None for w in ws) else {"kind": "cond", "waiters": ws}

def cur_addr():
    return int(gdb.parse_and_eval("$rsp")) & ~0xfff

last_ths = {}
last_sync = {}
last_lists = {}

def snapshot():
    ths = {}
    for addr, i in threads.items():
        if i not in dead:
            try:
                ths[i] = read_thread(addr)
            except gdb.MemoryError:
                pass
    try:
        tick = int(gdb.parse_and_eval("'timer.c'::ticks"))
    except gdb.error:
        tick = None
    sync = {}
    for addr, o in objs.items():
        try:
            r = read_obj(addr, o)
        except gdb.MemoryError:
            r = None
        if r is not None:
            if o["sys"]:
                r["sys"] = True
            sync[o["id"]] = r
    lists = {}
    for key, fn in (("ready", lambda: [k for sym in READY_SYMS for k in walk(sym)]), ("sleep", lambda: walk(SLEEP_SYM, SLEEP_ELEM))):
        try:
            lists[key] = fn()
        except gdb.MemoryError:   # 리스트가 망가졌으면 직전 값을 유지
            lists[key] = last_lists.get(key, [])
    # 스레드 상태는 바뀐 것만 저장함 (MLFQS 테스트는 스레드가 많고 길어서). 뷰어가 다시 펼침
    delta = {i: t for i, t in ths.items() if last_ths.get(i) != t}
    gone = [i for i in last_ths if i not in ths]
    # sync도 바뀐 객체만, ready/sleep은 직전과 같으면 생략 (load-60에서 크기의 대부분이 sync였음)
    sdelta = {i: o for i, o in sync.items() if last_sync.get(i) != o}
    sgone = [i for i in last_sync if i not in sync]
    snap = {"tick": tick, "cur": tid_of(cur_addr()), "threads": delta, "sync": sdelta}
    for key, val in lists.items():
        if last_lists.get(key) != val:
            snap[key] = val
    if gone:
        snap["gone"] = gone
    if sgone:
        snap["sync_gone"] = sgone
    if LOAD_SYM:
        try:
            snap["load"] = int(gdb.parse_and_eval(LOAD_SYM))
        except gdb.error:
            pass

    def commit():
        """이벤트가 실제로 추가된 뒤에만 델타 기준을 갱신함 (중간에 실패한 스냅샷이 기준을 바꾸지 않게)"""
        last_ths.clear(); last_ths.update(ths)
        last_sync.clear(); last_sync.update(sync)
        last_lists.update(lists)
    return snap, commit

def caller():
    """호출자 프레임 3개의 (함수 이름, "경로:줄") 목록."""
    f = gdb.selected_frame().older()
    names, locs = [], []
    while f and len(names) < 3:
        names.append(f.name() or "??")
        sal = f.find_sal()
        loc = None
        if sal.symtab and sal.line:
            path = os.path.relpath(sal.symtab.fullname(), ROOT)
            if not path.startswith(".."):
                sources.add(path)
                loc = "%s:%d" % (path, sal.line)
        locs.append(loc)
        f = f.older()
    return names, locs

# 훅은 함수 첫 명령어(*func)에 걸리므로 인자는 SysV 호출 규약 레지스터에 그대로 있음
def arg(n):
    return int(gdb.parse_and_eval("(long)$" + ("rdi", "rsi", "rdx", "rcx")[n]))

def argi(n):
    """int 인자. SysV에서 상위 32비트는 정해지지 않아서 하위 32비트만 부호 있게 읽음"""
    return int(gdb.parse_and_eval("(int)$" + ("rdi", "rsi", "rdx", "rcx")[n]))

# 외부 인터럽트(타이머 등) 처리 중인지. 호출 스택 깊이와 무관하게 정확히 판정하려고 커널 변수를 직접 읽음
try:
    INTR_ADDR = int(gdb.parse_and_eval("(long)&'interrupt.c'::in_external_intr"))
except gdb.error:
    INTR_ADDR = None

def in_intr():
    if INTR_ADDR is None:
        return None
    try:
        return bytes(inf.read_memory(INTR_ADDR, 1)) != b"\0"
    except gdb.MemoryError:
        return None

# 커널 내부(콘솔 출력, 페이지 할당, tid 발급)용 락. 뷰어에서 기본으로 숨김.
SYS_CALLERS = {"acquire_console", "release_console", "palloc_get_multiple",
               "palloc_free_multiple", "allocate_tid", "console_locked"}

def record(kind, **kw):
    stack, locs = caller()
    ev = {"kind": kind, "by": tid_of(cur_addr()), "stack": stack, "locs": locs, **kw}
    if ev["stack"] and ev["stack"][0] in SYS_CALLERS:
        ev["sys"] = True
    it = in_intr()
    if it is not None:
        ev["intr"] = it
    ev["snap"], commit = snapshot()
    events.append(ev)
    commit()

# ---- 훅 ----
def on_init_thread():
    addr = arg(0)
    i = len(info)
    tname = gdb.parse_and_eval("(char *)$rsi").string()
    try:
        # 새 스레드 페이지는 아직 0으로 채워진 상태라, 등록 전에 스냅샷을 찍어야 가짜 RUNNING 스레드가 안 생김
        record("create", target=i, pri=argi(2))
        if events and events[-1]["kind"] == "create" and events[-1]["stack"][:1] != ["thread_create"]:
            events[-1]["by"] = i   # 부팅 스레드(main)는 자기 자신을 만듦. 등록 전이라 by가 비어 있어서 채움
    finally:
        threads[addr] = i
        info.append({"name": tname, "addr": hex(addr)})

def on_unblock(): record("unblock", target=tid_of(arg(0)))
def on_block():   record("block", target=tid_of(cur_addr()))
def on_yield():   record("yield", target=tid_of(cur_addr()))
def on_launch():  record("switch", target=tid_of(arg(0)))
def on_set_pri(): record("set_priority", target=tid_of(cur_addr()), pri=argi(0))
def on_sleep():   record("sleep", target=tid_of(cur_addr()), ticks=arg(0))

def on_exit():
    i = tid_of(cur_addr())
    record("exit", target=i)
    dead.add(i)

def lock_ev(kind):
    def f():
        la = arg(0)
        lid = lock_id(la)
        extra = {"sys": True} if objs[la]["sys"] else {}
        record(kind, lock=lid, holder=tid_of(u64(la + HOLDER)), **extra)
    return f

def sema_ev(kind):
    def f():
        # lock/cond 내부에서 부르는 sema는 lock/cond 이벤트로 이미 보이므로 생략
        if (gdb.selected_frame().older().name() or "") in ("lock_acquire", "lock_release", "lock_try_acquire",
                                                            "cond_wait", "cond_signal"):
            return
        record(kind, sema=obj_id(arg(0), "sema"))
    return f

def on_run_test():
    global test_started
    test_started = True
    record("run_test", test=gdb.parse_and_eval("(char *)$rdi").string())

def on_lock_init(): obj_id(arg(0), "lock", reinit=True)
def on_cond_init(): obj_id(arg(0), "cond", reinit=True)

def on_sema_init():
    # lock 안의 세마포어, cond_wait의 semaphore_elem 세마포어는 따로 보여주지 않음
    if (gdb.selected_frame().older().name() or "") not in ("lock_init", "cond_wait"):
        obj_id(arg(0), "sema", reinit=True)

def cond_ev(kind):
    def f():
        record(kind, cond=obj_id(arg(0), "cond"), lock=lock_id(arg(1)))
    return f

# ---- 효율 측정 (기록/재생일 때만) ----
# QEMU가 재생 중 센 실행 명령어 수(icount)를 gdb monitor로 읽음. 재생은 결정적이라 같은 기록이면 값도 같음.
# 스레드별 CPU 명령어 수를 따로 쌓아서, 함수 호출 비용 = 그 스레드가 진입~복귀 사이에 직접 실행한 명령어 수
# (막혀서 다른 스레드가 돈 시간, 인터럽트 처리 시간은 뺌)
def icount():
    try:
        m = re.search(r"instruction count = (\d+)", gdb.execute("monitor info replay", to_string=True))
    except gdb.error:
        return None
    return int(m.group(1)) if m else None

PERF = icount() is not None
PERF_FUNCS = ("lock_acquire", "lock_release", "sema_down", "sema_up", "cond_wait", "cond_signal",
              "cond_broadcast", "thread_set_priority", "thread_yield", "timer_sleep", "thread_unblock")
# thread_create는 뺌: 비용 대부분(~11만 명령어)이 원본 palloc의 페이지 0 채우기라 동기화 비용을 가림
perf = {"calls": {}, "tick": [0, 0, 0], "top": 0, "sw": 0, "instr": 0}   # calls/tick: [횟수, 합, 최대]
cpu, pend, excl = {}, {}, set()   # 스레드별 CPU 명령어 수, 진행 중인 호출 스택, intr_handler 안에 있는 스레드
acct = {"run": None, "mark": 0, "start": None}

def settle():
    """지난 표시 이후 실행분을 실행 중이던 스레드에 넘기고 지금 icount를 돌려줌"""
    ic = icount()
    r = acct["run"]
    if r is not None and r not in excl:
        cpu[r] = cpu.get(r, 0) + ic - acct["mark"]
    acct["mark"] = ic
    return ic

def stat(s, c):
    s[0] += 1; s[1] += c; s[2] = max(s[2], c)

def perf_on(f):
    def g():
        if acct["start"] is not None:
            f()
    return g

def p_run_test():
    acct["run"] = tid_of(cur_addr())
    acct["start"] = acct["mark"] = icount()

def p_switch():
    settle()
    acct["run"] = tid_of(arg(0))
    perf["sw"] += 1

def p_intr(enter):
    def f():
        settle()
        (excl.add if enter else excl.discard)(tid_of(cur_addr()))
    return f

tick0 = [None]
def p_tick_in():  tick0[0] = icount()
def p_tick_out():
    if tick0[0] is not None:
        stat(perf["tick"], icount() - tick0[0])
        tick0[0] = None

def p_call(fn, enter):
    def f():
        t = tid_of(cur_addr())
        settle()
        if t in excl:   # 인터럽트 처리 중 호출(타이머가 깨우는 unblock, 복귀 시 yield)은 tick 비용 쪽으로 봄
            return
        st = pend.setdefault(t, [])
        if enter:
            st.append((fn, cpu.get(t, 0)))
        elif st and st[-1][0] == fn:
            c = cpu.get(t, 0) - st.pop()[1]
            stat(perf["calls"].setdefault(fn, [0, 0, 0]), c)
            if not st:
                perf["top"] += c   # 바깥쪽 호출만 합산 (lock_acquire 안의 sema_down을 두 번 세지 않게)
    return f

def p_end():
    perf["instr"] = settle() - acct["start"]

def ret_addr(fn):
    """복귀 훅 위치. -O0 빌드라 함수마다 끝이 'leave(또는 pop %rbp); ret' 하나뿐임. 아니면 None(측정 안 함).
    ret 자체에 걸면 thread_create/thread_yield에서 재생이 어긋나 커널이 멈춤(원인 미확인). 바로 앞 명령어에 걸면 괜찮음"""
    # 붙은 시점엔 페이징 전이라 타깃 메모리에서 코드를 못 읽음. 읽기 전용 섹션은 kernel.o 파일에서 읽게 함
    gdb.execute("set trust-readonly-sections on")
    try:
        out = gdb.execute("disassemble " + fn, to_string=True)
    finally:
        gdb.execute("set trust-readonly-sections off")
    ls = out.splitlines()
    r = [i for i, l in enumerate(ls) if re.search(r"\sret\s*$", l)]
    if len(r) != 1 or r[0] == 0 or not re.search(r"\s(leave|pop\s+%rbp)\s*$", ls[r[0] - 1]):
        return None
    return ls[r[0] - 1].split()[0]

saved = False
panicked = False

def save(status):
    """status: ok / panic / timeout / aborted / attach_failed. 한 번만 저장함."""
    global saved
    if saved:
        return
    saved = True
    src = {p: open(os.path.join(ROOT, p), errors="replace").read() for p in sorted(sources)}
    try:
        mlfqs = bool(int(gdb.parse_and_eval("thread_mlfqs")))
    except gdb.error:
        mlfqs = False
    text = json.dumps({"threads": info, "events": events, "sources": src, "status": status,
                       "layout": LAYOUT, "mlfqs": mlfqs, "delta": 2, "fp_scale": fp_scale,
                       "perf": perf if PERF and status == "ok" else None})
    with open(OUT + ".tmp", "w") as fp:   # 다 쓴 뒤에 이름을 바꿔서 반쯤 쓴 JSON이 남지 않게 함
        fp.write(text)
    os.replace(OUT + ".tmp", OUT)
    gdb.write("trace: %d events, %s -> %s\n" % (len(events), status, OUT))

HOOKS = []
fp_scale = None

def detect_scale():
    """고정소수점 배율 감지. 커널의 getter(값×100을 반올림한 정수)와 원시값을 비교함.
    getter가 미구현(0 반환)이거나 값이 작아 오차가 크면 None. 훅은 finish()에서 이미 꺼 둠."""
    pairs = []
    try:
        if LOAD_SYM:
            pairs.append((int(gdb.parse_and_eval(LOAD_SYM)), int(gdb.parse_and_eval("thread_get_load_avg ()"))))
        if "recent_cpu" in O:
            raw = struct.unpack("<i", bytes(inf.read_memory(cur_addr() + O["recent_cpu"], 4)))[0]
            pairs.append((raw, int(gdb.parse_and_eval("thread_get_recent_cpu ()"))))
    except gdb.error as ex:
        gdb.write("trace warning: getter 호출 실패 (%s)\n" % ex)
    for raw, g in sorted(pairs, key=lambda p: -abs(p[1])):
        if abs(g) >= 50 and raw:
            est = raw * 100 / g
            # 흔한 배율(2^10~2^20, 10^3~10^6) 중 3% 안쪽이면 그 값으로 맞춤
            for c in [1 << n for n in range(10, 21)] + [10 ** n for n in range(3, 7)]:
                if abs(est - c) / c < 0.03:
                    return c
            return round(est)
    return None

ended = False

def on_power_off():
    """끝 이벤트만 기록하고 멈춤. 저장과 배율 감지(커널 함수 호출)는 브레이크포인트 처리 밖인 finish()에서 함"""
    global ended
    try:
        record("end")
    finally:
        ended = True
    return True

def on_panic():
    global panicked
    panicked = True
    s = lambda n: gdb.parse_and_eval("(char *)$" + ("rdi", "rsi", "rdx", "rcx")[n]).string()
    msg = s(3)
    if msg.startswith("assertion `%s'"):   # ASSERT는 PANIC("assertion `%s' failed.", "조건식") 형태라 5번째 인자(r8)가 조건식
        try:
            msg = msg.replace("%s", gdb.parse_and_eval("(char *)$r8").string(), 1)
        except gdb.error:
            pass
    record("panic", file=s(0), line=argi(1), func=s(2), msg=msg)

def finish():
    """run.sh가 continue 다음에 부름. 상태를 정해 저장하고 QEMU를 끝냄.
    ok/panic: power_off까지 감. timeout: 시간 초과로 멈춤. aborted: 연결 끊김/중단(Ctrl-C)/QEMU 비정상 종료.
    attach_failed: 이벤트가 하나도 없음 (gdb 연결 실패 등)"""
    global fp_scale
    if saved:
        return
    for h in HOOKS:   # 이제부터는 기록하지 않음 (배율 감지의 커널 함수 호출, 남은 종료 과정)
        h.enabled = False
    if ended:
        status = "panic" if panicked else "ok"
        if LAYOUT.get("load_avg") or LAYOUT.get("recent_cpu"):
            try:
                fp_scale = detect_scale()
            except BaseException as ex:
                gdb.write("trace warning: 배율 감지 실패 (%r)\n" % ex)
    else:
        status = "attach_failed" if not events else ("timeout" if timed_out and not interrupted else "aborted")
        for _ in range(3):   # SIGINT가 늦게 도착해 KeyboardInterrupt가 끼어들 수 있어 재시도
            if status == "attach_failed":
                break
            try:
                if events[-1]["kind"] != status:
                    record(status, secs=TIMEOUT)
                break
            except KeyboardInterrupt:
                continue
            except Exception as ex:
                gdb.write("trace error at %s: %r\n" % (status, ex))
                break
    for _ in range(3):
        try:
            save(status)
            break
        except KeyboardInterrupt:
            globals()["saved"] = False
    if ended:
        # power_off 첫 명령어에서 멈춰 있음. 나머지(통계, "Powering off..." 출력)를 커널이 직접 마치게 둠.
        # 그래야 트레이스 실행 출력도 make check와 같은 형태가 됨 (GRADE=0일 때 이 출력으로 채점함)
        try:
            gdb.execute("continue")
            return
        except BaseException:
            pass   # QEMU가 꺼지면서 연결이 끊기는 것도 여기로 옴
    try:
        gdb.execute("kill")
    except BaseException:
        pass

# 시간 초과/중단: 먼저 플래그만 세워 다음 훅에서 깔끔하게 멈춤. 훅이 안 걸리는 무한루프면 5초 뒤 SIGINT
# 중단(Ctrl-C)은 run.sh가 TRACE_STOP 파일을 만들어 알려줌 (QEMU/gdb는 SIGINT를 무시하거나 놓칠 수 있어서 파일로 받음)
timed_out = False
interrupted = False
stopped = False
STOP_FILE = os.environ.get("TRACE_STOP")

def _force():
    if not saved and not stopped:
        os.kill(os.getpid(), signal.SIGINT)   # gdb가 원격 타깃(QEMU)을 멈춤

def _watch():
    global timed_out, interrupted
    import time
    start = time.time()
    while not saved and not stopped:
        if STOP_FILE and os.path.exists(STOP_FILE):
            interrupted = True
        if time.time() - start >= TIMEOUT:
            timed_out = True
        if timed_out or interrupted:
            time.sleep(5)
            _force()
            return
        time.sleep(0.5)

threading.Thread(target=_watch, daemon=True).start()

class Hook(gdb.Breakpoint):
    def __init__(self, spec, fn):
        super().__init__("*" + spec, internal=True)
        self.fn = fn
    def stop(self):
        global stopped
        if timed_out or interrupted:
            stopped = True
            return True   # 시간 초과/중단: 여기서 멈추면 continue가 끝나고 finish()가 저장함
        try:
            if self.fn() is True:   # 훅이 멈추라고 하면(power_off) 멈춤
                stopped = True
                return True
        except KeyboardInterrupt:
            stopped = True
            return True
        except Exception as ex:
            gdb.write("trace error at %s: %r\n" % (self.location, ex))
        return False

for spec, fn in [
    ("init_thread", on_init_thread), ("thread_unblock", on_unblock),
    ("thread_block", on_block), ("thread_yield", on_yield),
    ("thread_launch", on_launch), ("thread_exit", on_exit),
    ("thread_set_priority", on_set_pri), ("timer_sleep", on_sleep),
    ("lock_acquire", lock_ev("lock_acquire")), ("lock_release", lock_ev("lock_release")),
    ("sema_down", sema_ev("sema_down")), ("sema_up", sema_ev("sema_up")),
    ("run_test", on_run_test), ("lock_init", on_lock_init),
    ("sema_init", on_sema_init), ("cond_init", on_cond_init),
    ("cond_wait", cond_ev("cond_wait")), ("cond_signal", cond_ev("cond_signal")),
    ("cond_broadcast", cond_ev("cond_broadcast")),
    ("debug_panic", on_panic), ("power_off", on_power_off),
]:
    try:
        HOOKS.append(Hook(spec, fn))
    except gdb.error:
        gdb.write("trace warning: %s 함수가 없어 이 이벤트는 기록 안 함\n" % spec)

if PERF:
    specs = [("run_test", p_run_test), ("thread_launch", perf_on(p_switch)), ("power_off", perf_on(p_end))]
    # (함수, 진입 훅, 복귀 훅). 진입/복귀는 짝으로만 검
    for fn, a, b in [("intr_handler", p_intr(True), p_intr(False)), ("timer_interrupt", p_tick_in, p_tick_out)] + \
                    [(fn, p_call(fn, True), p_call(fn, False)) for fn in PERF_FUNCS]:
        try:
            r = ret_addr(fn)
        except gdb.error:
            r = None
        if r is None:
            gdb.write("trace warning: %s의 ret을 못 찾아 효율 측정에서 뺌\n" % fn)
            continue
        specs += [(fn, perf_on(a)), (r, perf_on(b))]
    for spec, fn in specs:
        try:
            HOOKS.append(Hook(spec, fn))
        except gdb.error:
            gdb.write("trace warning: %s 효율 측정 훅 실패\n" % spec)

gdb.write("trace layout: " + ", ".join("%s=%s" % (k, v or "없음") for k, v in LAYOUT.items()) + "\n")
