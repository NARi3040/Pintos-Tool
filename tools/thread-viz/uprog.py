# Project 2 (User Programs)용 gdb 트레이서. trace.py와 같은 방식(멈추지 않는 브레이크포인트)으로
# 시스템 콜, 유저 프로그램 진입(스택), fork/exec/wait/exit, page fault, 콘솔 출력, 페이지/파일 할당을 기록함.
# 훅은 학생이 고치지 않는 원본 코드(syscall_entry, do_iret, page_fault, palloc, file, console)에만 걸어서
# 구현 방식(fd 테이블, 자식 리스트 구조 등)과 상관없이 동작함.
import gdb, json, os, re, signal, struct, subprocess, threading

OUT = os.environ["TRACE_OUT"]
TIMEOUT = float(os.environ.get("TRACE_TIMEOUT", "120"))
# 이벤트가 이만큼 쌓이면 기록을 멈추고 커널은 끝까지 돌게 둠 (multi-oom은 프로세스를 수천 개 만듦)
MAX_EVENTS = int(os.environ.get("TRACE_MAX_EVENTS", "30000"))
truncated = False
inf = gdb.selected_inferior()
ROOT = os.path.realpath(os.path.join(os.getcwd(), "../.."))   # build 디렉터리 기준 pintos 루트
USER_STACK = 0x47480000
KERN_BASE = 0x8004000000
SEL_UCSEG = 0x23

def off(expr):
    return int(gdb.parse_and_eval("(long)&(%s)" % expr))

def u64(addr):
    return struct.unpack("<Q", bytes(inf.read_memory(addr, 8)))[0]

def i32(addr):
    return struct.unpack("<i", bytes(inf.read_memory(addr, 4)))[0]

T_TID, T_STATUS, T_NAME, T_MAGIC = (off("((struct thread *)0)->" + f) for f in ("tid", "status", "name", "magic"))
T_TF = off("((struct thread *)0)->tf")
THREAD_MAGIC = 0xcd6abf4b
F = {r: off("((struct intr_frame *)0)->R." + r) for r in ("rax", "rdi", "rsi", "rdx", "r10", "r8", "r9")}
F.update({r: off("((struct intr_frame *)0)->" + r) for r in ("rip", "rsp", "cs", "error_code")})
STATUS = ["RUNNING", "READY", "BLOCKED", "DYING"]

# 인자 형태: i=int, u=unsigned, s=문자열 포인터, b=버퍼 포인터(다음 인자가 크기), p=포인터
SIG = {"halt": "", "exit": "i", "fork": "s", "exec": "s", "wait": "i", "create": "su", "remove": "s",
       "open": "s", "filesize": "i", "read": "ibu", "write": "ibu", "seek": "iu", "tell": "i", "close": "i",
       "mmap": "pziii", "munmap": "p", "chdir": "s", "mkdir": "s", "readdir": "ip", "isdir": "i",
       "inumber": "i", "symlink": "ss", "dup2": "ii", "mount": "sii", "umount": "s"}
# 시스템 콜 번호 -> 이름 (syscall-nr.h의 enum을 그대로 읽음). 아직 syscall.c가 SYS_*를 안 쓰면(과제 시작 전)
# 디버그 정보에 enum이 없으므로 syscall-nr.h 순서대로 적은 SIG의 키를 씀
try:
    SYSNAMES = [f.name[4:].lower() for f in gdb.parse_and_eval("SYS_HALT").type.fields()]
except gdb.error:
    SYSNAMES = list(SIG)
AREGS = ("rdi", "rsi", "rdx", "r10", "r8", "r9")

# ---- 스케줄러 리스트 (trace.py와 같은 자동 감지) ----
# Project 1 코드를 이어 쓰므로 priority, base priority, ready_list, sleep_list를 이벤트마다 남김
TFIELDS = [(f.name, str(f.type.strip_typedefs()).strip(), f.bitpos // 8) for f in gdb.lookup_type("struct thread").fields()]

def field_off(type_, pattern, exclude=()):
    """타입이 맞고 이름이 pattern에 맞는 struct thread 필드의 오프셋. 없으면 None."""
    return next((o for n, t, o in TFIELDS if t == type_ and n not in exclude and re.search(pattern, n, re.I)), None)

T_PRI = off("((struct thread *)0)->priority")
T_ELEM = off("((struct thread *)0)->elem")
T_BASE = field_off("int", r"(init|orig|base|real|old|saved|default|own).*pri|pri.*(init|orig|base|real|old|saved)")
T_SLEEP_ELEM = field_off("struct list_elem", r"sleep|alarm|timer", exclude=("elem",))
if T_SLEEP_ELEM is None:
    T_SLEEP_ELEM = T_ELEM
LIST_TAIL = off("((struct list *)0)->tail")
# donations 리스트와 그 원소(list_elem): trace.py와 같은 이름 패턴. 둘 다 있어야 씀
T_DONS = field_off("struct list", r"don")
T_DON_ELEM = field_off("struct list_elem", r"don", exclude=("elem",))
if T_DONS is None or T_DON_ELEM is None:
    T_DONS = T_DON_ELEM = None
T_HEAD = max([o + 4 for o in (T_TID, T_STATUS, T_PRI, T_BASE) if o is not None] + ([T_DONS + 16] if T_DONS is not None else []))

def find_list(pattern, skip=r"^$"):
    """이름이 pattern에 맞는 전역 struct list 변수 -> (리스트 헤드 주소 목록, 이름). 배열(MLFQS 큐)이면 높은 인덱스부터."""
    out = gdb.execute('info variables -q -n -t "struct list"', to_string=True)
    cur_f = None
    for line in out.splitlines():
        m = re.match(r"File (.+):$", line)
        if m:
            cur_f = os.path.basename(m.group(1))
            continue
        m = re.search(r"struct list (\w+)(?:\[(\d+)\])?;$", line)
        if m and cur_f and re.search(pattern, m.group(1), re.I) and not re.search(skip, m.group(1), re.I):
            head = int(gdb.parse_and_eval("(long)&'%s'::%s" % (cur_f, m.group(1))))
            n = int(m.group(2)) if m.group(2) else None
            return ([head + k * 2 * LIST_TAIL for k in range(n - 1, -1, -1)] if n else [head]), m.group(1)
    return None, None

READY_HEADS, READY_NAME = find_list(r"^ready")
if READY_HEADS is None:
    READY_HEADS, READY_NAME = find_list(r"queue|mlfq")
SLEEP_HEADS, SLEEP_NAME = find_list(r"sleep|alarm|wait|block", skip=r"^ready")

def walk(heads, elem_off):
    """리스트 원소 -> 스레드 id 목록 (모르는 원소는 None). 리스트가 망가졌으면 None."""
    out = []
    for head in heads or []:
        e, tail = u64(head + 8), head + LIST_TAIL
        while e != tail:
            if not e or len(out) >= 200:
                return None
            out.append(threads.get(e - elem_off))
            e = u64(e + 8)
    return out

last_lists = {}

# ---- lock / semaphore 대기열 ----
# lock_init/sema_init에서 객체 주소를 모으고 이벤트마다 주인/값과 대기 스레드를 읽음. 바뀐 것만 남김
L_HOLDER = off("((struct lock *)0)->holder")
L_SEMA = off("((struct lock *)0)->semaphore")
S_WAITERS = off("((struct semaphore *)0)->waiters")
objs = {}       # 객체 주소 -> {"id", "kind"}
obj_n = {}
last_sync = {}

def on_obj_init(kind):
    def f():
        if kind == "sema" and (gdb.selected_frame().older().name() or "") in ("lock_init", "cond_wait"):
            return   # lock 안의 세마포어, cond_wait의 임시 세마포어는 따로 안 보임
        addr = arg(0)
        n = obj_n[kind] = obj_n.get(kind, 0) + 1
        label = "%s%s%d" % ("" if test_started else "k", kind[0].upper(), n)
        sym = gdb.execute("info symbol %d" % addr, to_string=True)   # 전역 변수면 이름을 붙임
        if " in section " in sym and "+" not in sym.split(" in section ")[0]:
            label += " (%s)" % sym.split(" in section ")[0].strip()
        objs[addr] = {"id": label, "kind": kind}
    return f

OBJ_SIZE = {"lock": int(gdb.parse_and_eval("sizeof(struct lock)")), "sema": int(gdb.parse_and_eval("sizeof(struct semaphore)"))}

def read_obj(addr, kind, pagecache):
    """{"h": 주인 / "v": 값, "w": 대기 스레드}. 해제됐거나 모르는 스레드가 섞였으면 None.
    객체 전체를 한 번에 읽고 대기열이 비었으면 더 안 읽음 (이벤트마다 모든 객체를 읽어서 읽기 횟수가 곧 속도임)"""
    n, pg = OBJ_SIZE[kind], addr & ~0xfff
    if (addr + n - 1) & ~0xfff != pg:
        raw = bytes(inf.read_memory(addr, n))
    else:   # 객체 여러 개가 같은 페이지(전역 변수, 스레드 스택)에 몰려 있어서 페이지 단위로 한 번만 읽음
        if pg not in pagecache:
            pagecache[pg] = bytes(inf.read_memory(pg, 0x1000))
        raw = pagecache[pg][addr - pg:addr - pg + n]
    so = L_SEMA if kind == "lock" else 0
    head = addr + so + S_WAITERS
    w = [] if struct.unpack_from("<Q", raw, so + S_WAITERS + 8)[0] == head + LIST_TAIL else walk([head], T_ELEM)
    if w is None or None in w:
        return None
    if kind == "lock":
        h = struct.unpack_from("<Q", raw, L_HOLDER)[0]
        if h and h not in threads:
            return None
        return {"h": threads.get(h), "w": w}
    return {"v": struct.unpack_from("<I", raw, so)[0], "w": w}

threads = {}   # 스레드 페이지 주소 -> 고유 id (같은 페이지 재사용 대비)
info = []      # id -> {name, addr, parent, tid}
dead = set()
events = []
sources = set()
test_started = False

def cur_addr():
    return int(gdb.parse_and_eval("$rsp")) & ~0xfff

def cur():
    return threads.get(cur_addr())

def arg(n):
    return int(gdb.parse_and_eval("(long)$" + ("rdi", "rsi", "rdx", "rcx")[n]))

def tick():
    try:
        return int(gdb.parse_and_eval("'timer.c'::ticks"))
    except gdb.error:
        return None

def caller(skip=1, n=3):
    """호출자 프레임 n개의 (함수 이름, "경로:줄") 목록. skip=1이면 훅이 걸린 함수 자신은 뺌."""
    f = gdb.selected_frame()
    for _ in range(skip):
        f = f and f.older()
    names, locs = [], []
    while f and len(names) < n:
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

def read_str(addr, limit=128):
    """유저 문자열. 못 읽으면 None, 길면 잘라서 끝에 …"""
    out = b""
    try:
        while len(out) < limit:
            # 페이지 경계를 넘지 않게 나눠 읽음 (뒤 페이지가 매핑 안 돼 있어도 앞부분은 읽히게)
            n = min(limit - len(out), 0x1000 - ((addr + len(out)) & 0xfff))
            chunk = bytes(inf.read_memory(addr + len(out), n))
            z = chunk.find(b"\0")
            if z >= 0:
                return (out + chunk[:z]).decode(errors="replace")
            out += chunk
    except gdb.MemoryError:
        if not out:
            return None
    return out.decode(errors="replace") + "…"

def read_bytes(addr, n):
    try:
        return bytes(inf.read_memory(addr, n))
    except gdb.MemoryError:
        return None

# ---- 페이지 / 파일 / 상태 집계 ----
pages = {}   # 페이지 주소 -> {n, by, user, stack, locs, ev}
blocks = {}  # 테스트 시작 후 malloc한 블록 주소 -> {size, by, stack, locs, ev}
MALLOC = False   # malloc/free를 둘 다 훅했을 때만 블록 누수를 셈
files = {}   # struct file 주소 -> {name, by, how, stack, locs, ev}
pending_name = {}   # 스레드 -> filesys_open에 넘긴 이름 (file_open 복귀 때 붙임)
pending_dup = {}    # 스레드 -> file_duplicate 원본 파일 주소
pending_sys = {}    # 스레드 -> 진행 중인 시스템 콜 이벤트 번호
exit_ev = {}        # 스레드 -> 자기 exit 이벤트 번호 (누수가 그 프로세스 종료 전/후 어디서 났는지 보임)
closed = set()      # file_close한 struct file 주소 (다시 file_close하면 이중 해제)
dupsrc = {}         # 스레드 -> [원본, 복제본] struct file 주소 쌍 (file_duplicate/file_reopen. fork 자식의 fd 복제 확인용)
last_open = {}      # 스레드 -> 진행 중인 시스템 콜 안에서 마지막으로 file_open한 struct file 주소
smashed = set()     # magic이 깨진 걸 이미 기록한 스레드
last_st = {}
last_pri = {}

def counts():
    """테스트 시작 후 할당돼 아직 안 풀린 페이지 수 (유저 풀, 커널 풀), 열린 파일 수"""
    up = sum(p["n"] for p in pages.values() if p["user"] and p["ev"] is not None)
    kp = sum(p["n"] for p in pages.values() if not p["user"] and p["ev"] is not None)
    return [up, kp, sum(1 for f in files.values() if f["ev"] is not None)]

# 기록 재생 중이면 이벤트마다 QEMU의 실행 명령어 수(icount)를 남김. 디버거가 이 값으로 그 이벤트 시점에 정확히 멈춤
ICOUNT = bool(os.environ.get("TRACE_ICOUNT"))

def icount():
    try:
        m = re.search(r"instruction count = (\d+)", gdb.execute("monitor info replay", to_string=True))
    except gdb.error:
        return None
    return int(m.group(1)) if m else None

def record(kind, stack=True, **kw):
    ev = {"kind": kind, "by": cur(), "tick": tick(), **kw}
    if stack:
        ev["stack"], ev["locs"] = caller()
    st, pri = {}, {}
    for addr, i in threads.items():
        if i in dead:
            continue
        try:   # 스레드마다 앞부분을 한 번에 읽음 (이벤트마다 모든 스레드를 읽어서 읽기 횟수가 곧 속도임)
            raw = bytes(inf.read_memory(addr, T_HEAD))
        except gdb.MemoryError:
            continue
        r32 = lambda o: struct.unpack_from("<i", raw, o)[0]
        s = r32(T_STATUS)
        s = STATUS[s] if 0 <= s < 4 else "?"
        if info[i]["tid"] is None and r32(T_TID) > 0:
            info[i]["tid"] = r32(T_TID)
        if last_st.get(i) != s:
            st[i] = last_st[i] = s
        p = [r32(T_PRI), r32(T_BASE if T_BASE is not None else T_PRI)]
        if T_DONS is not None:   # 세 번째 = donations 리스트 (스레드 id 목록, 못 읽으면 None). 비었으면 더 안 읽음
            head = addr + T_DONS
            if struct.unpack_from("<Q", raw, T_DONS + 8)[0] == head + LIST_TAIL:
                p.append([])
            else:
                try:
                    p.append(walk([head], T_DON_ELEM))
                except gdb.MemoryError:
                    p.append(None)
        if last_pri.get(i) != p:
            pri[i] = last_pri[i] = p
    if st:
        ev["st"] = st
    if pri:
        ev["pri"] = pri   # 스레드 -> [priority, base priority]. 바뀐 것만
    for key, heads, eo in (("rl", READY_HEADS, T_ELEM), ("sl", SLEEP_HEADS, T_SLEEP_ELEM)):
        try:
            v = walk(heads, eo)
        except gdb.MemoryError:
            v = None
        if v is not None and last_lists.get(key) != v:   # 직전과 같거나 망가졌으면 생략
            ev[key] = last_lists[key] = v
    sy, pc = {}, {}
    for addr, o in objs.items():
        try:
            v = read_obj(addr, o["kind"], pc)
        except gdb.MemoryError:
            v = None
        if last_sync.get(o["id"]) != v:
            sy[o["id"]] = last_sync[o["id"]] = v
    live = {o["id"] for o in objs.values()}
    for k in [k for k, v in last_sync.items() if v is not None and k not in live]:   # 해제된 페이지의 객체
        sy[k] = last_sync[k] = None
    if sy:
        ev["sync"] = sy   # 객체 -> 상태 (None이면 못 읽음). 바뀐 것만
    ev["cnt"] = counts()
    if vm_delta:   # 이 이벤트 전까지 바뀐 페이지 상태 (Project 3). 순서가 곧 상태라 시간순 그대로 붙임
        ev["vm"] = [d for _, d in vm_delta]
        by = [i for i, _ in vm_delta]
        if any(i != ev["by"] for i in by):   # 바꾼 스레드가 이벤트 주인과 다르면 (fault 처리 중 디스크 I/O로 다른 스레드가 돎)
            ev["vmby"] = by
        vm_delta.clear()
    if ICOUNT:
        ev["ic"] = icount()
    events.append(ev)
    if len(events) >= MAX_EVENTS:
        truncate()
    return len(events) - 1

def truncate():
    """상한에 닿으면 power_off/panic 훅만 남기고 끔. 누수 검사는 끝까지 못 따라가므로 하지 않음"""
    global truncated
    if truncated:
        return
    truncated = True
    for h in HOOKS:
        if h.fn not in (on_power_off, on_panic):
            h.enabled = False

# ---- 훅 ----
def on_init_thread():
    addr = arg(0)
    i = len(info)
    name = gdb.parse_and_eval("(char *)$rsi").string()
    parent = cur() if (gdb.selected_frame().older().name() or "") == "thread_create" else None
    threads[addr] = i
    if parent is not None and parent in prog:   # fork한 자식은 부모 프로그램을 그대로 이어받음
        prog[i] = prog[parent]
    info.append({"name": name, "addr": hex(addr), "parent": parent, "tid": None})
    if parent is not None:
        record("create", target=i)

def on_thread_exit():
    i = cur()
    if i is None:
        return
    pending_sys.pop(i, None)
    if VM_RET:
        try:
            vm_died_in_fault()
        except (gdb.error, ValueError, IndexError, RuntimeError) as ex:
            gdb.write("trace warning: fault 중 종료를 분석하지 못했어요 (%r)\n" % ex)
    exit_ev[i] = len(events)
    record("exit", target=i)
    dead.add(i)
    last_st.pop(i, None)
    last_pri.pop(i, None)

def on_run_task():
    global test_started
    test_started = True
    record("run_task", cmd=read_str(u64(arg(0) + 8), 512))   # run_task(argv): argv[0]="run", argv[1]=명령줄

prog = {}   # 스레드 -> 지금 실행 중인 프로그램 이름 (exec한 명령줄의 첫 단어. 스레드 이름은 exec해도 안 바뀔 수 있음)

def on_process_exec():
    cmd = read_str(arg(0), 512)
    if cmd:
        prog[cur()] = cmd.split()[0] if cmd.split() else cmd
    record("exec", cmd=cmd)

def prog_of(i):
    return prog.get(i, info[i]["name"] if i is not None else None)

def on_process_wait():
    record("wait", child=gdb.parse_and_eval("(int)$rdi").__int__())

def frame_regs(f):
    r = {k: u64(f + o) for k, o in F.items()}
    r["cs"] &= 0xffff   # uint16 필드 뒤의 패딩은 초기화 안 된 값일 수 있음
    return r

def on_syscall():
    f = arg(0)
    r = frame_regs(f)
    nr = r["rax"]
    name = SYSNAMES[nr] if nr < len(SYSNAMES) else None
    args, strs, buf, bad = [], {}, None, []
    sig = SIG.get(name, "iiiiii" if name is None else "")
    for k, c in enumerate(sig):
        v = r[AREGS[k]]
        if c == "i":
            v = struct.unpack("<i", struct.pack("<I", v & 0xffffffff))[0]
        elif c == "u":
            v &= 0xffffffff   # z(size_t)는 64비트 그대로 (mmap-kernel이 아주 큰 length를 넘김)
        args.append(v)
        if c == "s":
            strs[k] = read_str(v) if v < KERN_BASE else None
            if strs[k] is None:
                bad.append(k)
        elif c == "b":
            n = r[AREGS[k + 1]] & 0xffffffff
            # 버퍼의 처음과 끝 바이트가 유저 영역에 매핑돼 있는지 (gdb는 커널 주소도 읽히므로 범위도 따로 봄)
            if n and (v + n > KERN_BASE or read_bytes(v, 1) is None or read_bytes(v + n - 1, 1) is None):
                bad.append(k)
            if name == "write":   # write는 쓰려는 내용 앞부분을 같이 남김
                b = read_bytes(v, min(n, 96)) if n else b""
                buf = None if b is None else b.decode(errors="replace")
    ev = record("sys", stack=False, nr=nr, name=name or ("#%d" % nr), args=args, strs=strs, bad=bad,
                **({"buf": buf} if buf is not None else {}), rip=r["rip"], rsp=r["rsp"])
    if events[ev]["by"] is not None:
        pending_sys[events[ev]["by"]] = ev
        last_open.pop(events[ev]["by"], None)

def on_sysret():
    """syscall_entry에서 syscall_handler가 돌아온 직후. rsp가 intr_frame을 가리킴"""
    i = cur()
    ev = pending_sys.pop(i, None)
    if ev is None:
        return
    rax = u64(int(gdb.parse_and_eval("$rsp")) + F["rax"])
    ret = struct.unpack("<i", struct.pack("<I", rax & 0xffffffff))[0]
    events[ev]["ret"] = ret
    events[ev]["ret_raw"] = rax
    if events[ev]["name"] == "open" and i in last_open:   # 유저가 받은 fd가 가리키는 struct file
        events[ev]["fp"] = hex(last_open.pop(i))
    record("sysret", stack=False, call=ev, ret=ret)
    # 커널 스택(같은 4KB 페이지의 위쪽)이 넘치면 페이지 아래쪽 struct thread의 magic부터 덮임
    if i not in smashed and u64(cur_addr() + T_MAGIC) & 0xffffffff != THREAD_MAGIC:
        smashed.add(i)
        record("smash", stack=False, sys=events[ev]["name"])

def on_do_iret():
    f = arg(0)
    if u64(f + F["cs"]) & 0xffff != SEL_UCSEG:
        return   # 커널 스레드 전환용 do_iret은 무시
    r = frame_regs(f)
    via = gdb.selected_frame().older().name() or "??"
    rsp = r["rsp"]
    stack = None
    if USER_STACK - 0x10000 <= rsp < USER_STACK:
        raw = read_bytes(rsp, min(USER_STACK - rsp, 4096))
        stack = raw.hex() if raw is not None else None
    i = cur()
    ev = pending_sys.pop(i, None)   # exec이 성공하면 시스템 콜은 돌아오지 않고 여기로 옴
    if ev is not None:
        events[ev]["ret"] = None
    record("uentry", via=via, regs=r, stack_hex=stack, prog=prog_of(i), dupsrc=dupsrc.get(i, []))

def on_page_fault():
    try:
        cr2 = int(gdb.parse_and_eval("(long)$cr2"))
    except gdb.error:
        cr2 = None
    record("fault", **fault_info(arg(0), cr2))

def fault_info(f, cr2):
    r = frame_regs(f)
    user = (r["cs"] & 3) == 3
    ev = {"addr": cr2, "rip": r["rip"], "rsp": r["rsp"], "user": user, "err": r["error_code"]}
    if not user:   # 커널 안에서 난 fault면 어느 줄인지 남김
        sal = gdb.find_pc_line(r["rip"])
        fn = gdb.execute("info symbol %d" % r["rip"], to_string=True).split(" in section")[0].strip()
        ev["ksym"] = fn
        if sal.symtab and sal.line:
            p = os.path.relpath(sal.symtab.fullname(), ROOT)
            if not p.startswith(".."):
                sources.add(p)
                ev["kloc"] = "%s:%d" % (p, sal.line)
    ev["prog"] = prog_of(cur())
    return ev

def on_kill():
    """exception.c의 kill(f): page fault 말고 다른 예외(#GP, #UD, 0으로 나누기 등)로 프로세스를 죽일 때"""
    f = arg(0)
    r = frame_regs(f)
    vec = u64(f + off("((struct intr_frame *)0)->vec_no"))
    if vec == 14:
        return   # page fault는 page_fault 훅에서 이미 기록함
    record("fault", prog=prog_of(cur()), vec=vec, addr=None, rip=r["rip"], rsp=r["rsp"],
           user=(r["cs"] & 3) == 3, err=r["error_code"])

line_buf = {}

def on_putchar():
    i = cur()
    c = int(gdb.parse_and_eval("(int)$rdi")) & 0xff
    b = line_buf.setdefault(i, bytearray())
    if c == 10:
        record("out", stack=False, text=b.decode(errors="replace"))
        line_buf[i] = bytearray()
    else:
        b.append(c)

def on_panic():
    s = lambda n: gdb.parse_and_eval("(char *)$" + ("rdi", "rsi", "rdx", "rcx")[n]).string()
    msg = s(3)
    if msg.startswith("assertion `%s'"):
        try:
            msg = msg.replace("%s", gdb.parse_and_eval("(char *)$r8").string(), 1)
        except gdb.error:
            pass
    globals()["panicked"] = True
    rsp = int(gdb.parse_and_eval("(long)$rsp"))
    record("panic", file=s(0), line=int(gdb.parse_and_eval("(int)$rsi")), func=s(2), msg=msg, rsp=rsp)
    if rsp < KERN_BASE:   # 원본 syscall-entry.S의 popq %rsp~sysretq 틈에 인터럽트가 걸림. run.sh가 보고 다시 돌림
        gdb.write("syscall-entry race: kernel on user stack %#x\n" % rsp)

# 페이지: palloc_get_multiple(flags, cnt) 진입에서 인자를, 복귀 직전에서 결과 주소를 받음
palloc_req = {}
def on_palloc_in():
    palloc_req[cur_addr()] = (arg(0), arg(1))

def on_palloc_out():
    req = palloc_req.pop(cur_addr(), None)
    page = int(gdb.parse_and_eval("$rax"))
    if req is None or not page:
        return
    names, locs = caller(skip=1, n=4)
    # palloc_get_page/thread_create 같은 얇은 포장 함수는 건너뛰고 실제로 부른 쪽을 보여줌
    pages[page] = {"n": req[1], "by": cur(), "user": bool(req[0] & 4), "stack": names, "locs": locs,
                   "ev": len(events) if test_started else None}

def on_malloc_out():
    """malloc 복귀 직전. 파일 시스템이 malloc을 자주 불러서 진입 훅 없이 프레임의 size 인자를 읽음"""
    b = int(gdb.parse_and_eval("$rax"))
    if not b or not test_started:
        return
    try:
        size = int(gdb.parse_and_eval("size"))
    except gdb.error:
        size = None
    names, locs = caller(skip=1, n=4)
    blocks[b] = {"size": size, "by": cur(), "stack": names, "locs": locs, "ev": len(events)}

def drop_objs(lo, hi):
    """해제된 메모리 안의 lock/sema는 그만 읽음"""
    for o in [o for o in objs if lo <= o < hi]:
        del objs[o]

def on_pfree():
    a, n = arg(0), arg(1)
    pages.pop(a, None)
    drop_objs(a, a + n * 0x1000)   # 스레드 스택 등

def on_free():
    """malloc.c의 free(p). 블록 크기는 arena(블록이 든 페이지 맨 앞)의 desc에서 읽음. 큰 블록은 desc가 NULL이고 free_cnt가 페이지 수"""
    p = arg(0)
    blocks.pop(p, None)
    if not p or not any(p <= o < p + 0x100000 for o in objs):
        return
    a = p & ~0xfff
    desc = u64(a + A_DESC)
    drop_objs(p, p + u64(desc + D_SIZE) if desc else a + u64(a + A_CNT) * 0x1000)

def on_filesys_open():
    pending_name[cur_addr()] = read_str(arg(0))

def on_file_dup_in():
    pending_dup[cur_addr()] = arg(0)

def file_ret(how):
    def f():
        fp = int(gdb.parse_and_eval("$rax"))
        k = cur_addr()
        name = pending_name.pop(k, None) if how == "open" else None
        src = pending_dup.pop(k, None) if how != "open" else None
        if not fp:
            return
        closed.discard(fp)   # 해제된 주소를 malloc이 다시 줬을 수 있음
        if how == "open":
            last_open[cur()] = fp
        elif src is not None:
            dupsrc.setdefault(cur(), []).append([hex(src), hex(fp)])
        if src is not None and src in files:
            name = files[src]["name"]
        names, locs = caller(skip=1, n=4)
        files[fp] = {"name": name, "by": cur(), "how": how, "stack": names, "locs": locs,
                     "ev": len(events) if test_started else None}
    return f

def on_file_close():
    fp = arg(0)
    if not fp:
        return
    if files.pop(fp, None) is not None:
        closed.add(fp)
    elif fp in closed:
        names, locs = caller(skip=1, n=4)
        record("dclose", stack=False, fp=hex(fp), stack2=names, locs2=locs)

# ---- Project 3: 페이지 상태 ----
# 학생이 만든 SPT(해시 등)는 안 읽고, 원본 코드 함수에 건 훅으로 페이지마다 상태를 다시 만듦:
# uninit_new(SPT에 들어감) -> anon/file_backed_initializer(lazy 로딩) -> pml4_set_page/clear_page(프레임 매핑)
# -> *_swap_out/_swap_in -> *_destroy. 변화는 다음 이벤트의 "vm"에 [종류, 프로세스, va, ...]로 붙임
VM = False
VM_RET = None        # vm_try_handle_fault의 복귀 지점 (있으면 page_fault 대신 여기서 fault를 처리 결과와 같이 기록)
vm_delta = []        # (바꾼 스레드, 변화)
vm_done = {}         # 스레드 -> 마지막으로 vm_try_handle_fault 복귀에서 기록한 fault 주소
vm_pages = {}        # struct page 주소 -> (프로세스, va)
vm_frames = {}       # kva -> (프로세스, va)
pml4_of = {}         # pml4 -> 프로세스
sym_cache = {}

def vm_add(d):
    vm_delta.append((cur(), d))

def pml4_owner(pml4):
    if pml4 not in pml4_of:
        for addr, i in threads.items():
            if i not in dead:
                try:
                    pml4_of[u64(addr + T_PML4)] = i
                except gdb.MemoryError:
                    pass
    return pml4_of.get(pml4)

def sym_name(a):
    if a not in sym_cache:
        s = gdb.execute("info symbol %d" % a, to_string=True).split(" in section")[0].strip() if a else ""
        sym_cache[a] = None if not a or s.startswith("No symbol") else s
    return sym_cache[a]

def fn_args(fr):
    """프레임의 인자 심볼 (순서대로). pc가 안쪽 블록({ } 안)에 있으면 거기엔 인자가 없어서 함수 블록까지 올라감"""
    b = fr.block()
    while b.function is None and b.superblock is not None:
        b = b.superblock
    return [s for s in b if s.is_argument]

def page_key(pg):
    """struct page -> (프로세스, va). uninit_new에서 못 본 페이지(직접 만든 struct page)는 va와 매핑된 프레임으로 찾음"""
    k = vm_pages.get(pg)
    if k is None:
        va = u64(pg + P_VA)
        fr = u64(pg + P_FRAME)
        try:
            k = vm_frames.get(u64(fr + FR_KVA)) if fr else None
        except gdb.MemoryError:   # 0으로 안 채운 struct page의 frame 필드
            k = None
        k = k if k and k[1] == va else (cur(), va)
    return k

def on_uninit_new():
    pg, va, init, typ = arg(0), arg(1), arg(2), arg(3)
    w = None
    f = gdb.selected_frame().older()
    if f and f.name() == "vm_alloc_page_with_initializer":
        try:   # 세 번째 인자 (이름은 학생이 바꿀 수 있어 순서로 읽음)
            w = bool(int(f.read_var(fn_args(f)[2])))
        except (gdb.error, ValueError, IndexError, RuntimeError):
            pass
    k = vm_pages[pg] = (cur(), va)
    vm_add(["a", k[0], va, typ & 0xffffffff, w, sym_name(init)])

def on_vm_init(t):
    def f():
        k = page_key(arg(0))
        vm_add(["t", k[0], k[1], t])
    return f

def on_set_page():
    o = pml4_owner(arg(0))
    va, kva = arg(1), arg(2)
    vm_frames[kva] = (o, va)
    vm_add(["m", o, va, kva, bool(arg(3) & 1)])

def on_clear_page():
    o, va = pml4_owner(arg(0)), arg(1)
    for kva in [k for k, v in vm_frames.items() if v == (o, va)]:
        del vm_frames[kva]
    vm_add(["u", o, va])

def on_pml4_destroy():
    o = pml4_owner(arg(0))
    pml4_of.pop(arg(0), None)
    for kva in [k for k, v in vm_frames.items() if v[0] == o]:
        del vm_frames[kva]
    vm_add(["x", o])

def on_swap(c):
    def f():
        k = page_key(arg(0))
        vm_add([c, k[0], k[1]])
    return f

def on_vm_destroy():
    pg = arg(0)
    k = page_key(pg)
    vm_pages.pop(pg, None)
    vm_add(["d", k[0], k[1]])

def on_vm_ret():
    """vm_try_handle_fault (f, addr, user, write, not_present)가 돌아오기 직전. 원본 page_fault는 VM 빌드에서 항상
    이 함수를 먼저 부르므로 page_fault에는 훅을 안 걸고 여기서 인자(순서로 읽음, 이름은 학생이 바꿀 수 있음)와 결과를 같이 남김.
    fault마다 gdb가 멈추는 횟수가 곧 속도라서 한 번으로 줄임"""
    f, addr = vm_fault_args(gdb.selected_frame())
    vm_done[cur_addr()] = addr
    record("fault", vmok=bool(int(gdb.parse_and_eval("$rax")) & 0xff), **fault_info(f, addr))

def vm_fault_args(fr):
    """vm_try_handle_fault 프레임 -> (intr_frame, fault 주소). 주소는 인자를 학생이 고쳤을 수 있어(pg_round_down 등)
    부른 쪽 page_fault의 fault_addr(cr2)를 먼저 씀"""
    a = fn_args(fr)
    f, addr = (int(fr.read_var(s).cast(gdb.lookup_type("long"))) for s in a[:2])
    try:
        addr = int(fr.older().read_var("fault_addr").cast(gdb.lookup_type("long")))
    except (gdb.error, ValueError, AttributeError):
        pass
    return f, addr

def vm_died_in_fault():
    """thread_exit 때: vm_try_handle_fault 안에서(또는 page_fault에서 부르기 전에) exit하면 복귀 훅이 안 걸려서 그 fault를 여기서 남김"""
    fr, n = gdb.selected_frame(), 0
    while fr and n < 20:
        name = fr.name()
        if name == "vm_try_handle_fault":
            f, addr = vm_fault_args(fr)
            break
        if name == "page_fault":
            if vm_done.get(cur_addr()) == int(fr.read_var("fault_addr").cast(gdb.lookup_type("long"))):
                return   # vm_try_handle_fault가 false를 반환해 이미 기록함. page_fault가 그 뒤 exit한 것
            f = int(fr.read_var(fn_args(fr)[0]).cast(gdb.lookup_type("long")))
            addr = int(fr.read_var("fault_addr").cast(gdb.lookup_type("long")))
            break
        fr, n = fr.older(), n + 1
    else:
        return
    record("fault", vmok=False, died=True, **fault_info(f, addr))

# ---- 시간 초과 때: 멈춰 있는 스레드가 어디서 무엇을 기다리는지 ----
def scope_off(fn, var):
    """-O0 빌드에서 fn의 인자 var가 놓인 rbp 기준 오프셋. 못 구하면 None"""
    try:
        out = gdb.execute("info scope " + fn, to_string=True)
    except gdb.error:
        return None
    for part in out.split("Symbol ")[1:]:
        if not part.startswith(var + " is "):
            continue
        m = re.search(r"\$rbp offset (-?\d+)\+(-?\d+)", part)
        if m:
            return int(m.group(1)) + int(m.group(2))
        m = re.search(r"DW_OP_fbreg (-?\d+)", part)   # 프레임 기준(CFA) = rbp + 16 (frame pointer를 쓰는 빌드)
        if m:
            return 16 + int(m.group(1))
    return None

def fn_at(pc):
    try:
        b = gdb.block_for_pc(pc)
        while b and not b.function:
            b = b.superblock
        name = b.function.name if b else None
    except RuntimeError:
        name = None
    sal = gdb.find_pc_line(pc)
    loc = None
    if sal.symtab and sal.line:
        path = os.path.relpath(sal.symtab.fullname(), ROOT)
        if not path.startswith(".."):
            sources.add(path)
            loc = "%s:%d" % (path, sal.line)
    return name or "??", loc

def stuck():
    """살아 있는 스레드마다 호출 경로(저장된 tf의 rbp 체인)와, lock_acquire에서 기다리면 그 lock과 주인"""
    lock_off = scope_off("lock_acquire", "lock")
    holder_off = off("((struct lock *)0)->holder")
    out = []
    here = cur_addr()
    for addr, i in threads.items():
        if i in dead or info[i]["name"] == "idle":
            continue
        try:
            if addr == here:
                f = gdb.newest_frame()
                pc, rbp = f.pc(), int(gdb.parse_and_eval("$rbp"))
            else:
                pc, rbp = u64(addr + T_TF + F["rip"]), u64(addr + T_TF + off("((struct intr_frame *)0)->R.rbp"))
            names, locs, lock = [], [], None
            while len(names) < 12:
                n, l = fn_at(pc if not names else pc - 1)   # 복귀 주소는 call 다음 명령어라 한 칸 앞으로
                names.append(n)
                locs.append(l)
                if n == "lock_acquire" and lock is None and lock_off is not None:
                    la = u64(rbp + lock_off)
                    h = u64(la + holder_off)
                    lock = {"addr": hex(la), "holder": threads.get(h)}
                if not (addr < rbp < addr + 0x1000):
                    break
                pc, rbp = u64(rbp + 8), u64(rbp)
            out.append({"id": i, "status": STATUS[i32(addr + T_STATUS)] if 0 <= i32(addr + T_STATUS) < 4 else "?",
                        "stack": names, "locs": locs, **({"lock": lock} if lock else {})})
        except (gdb.error, gdb.MemoryError):
            continue
    return out

def ret_addr(fn):
    """복귀 직전 명령어(leave 또는 pop %rbp) 주소. trace.py와 같은 이유로 ret 자체에는 안 검"""
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

def sysret_addr():
    """syscall_entry 안에서 syscall_handler 호출 바로 다음 명령어 주소"""
    gdb.execute("set trust-readonly-sections on")
    try:
        out = gdb.execute("x/80i syscall_entry", to_string=True)
    finally:
        gdb.execute("set trust-readonly-sections off")
    ls = out.splitlines()
    for k, l in enumerate(ls[:-1]):
        if re.search(r"\scall\s", l):
            return re.search(r"0x[0-9a-f]+", ls[k + 1]).group(0)
    return None

# ---- 유저 프로그램 심볼 (fault/진입 주소 -> 함수, 소스 줄) ----
def user_syms():
    """유저 주소를 프로그램 ELF로 풀이함. 스레드 이름 = 프로그램 이름 (KAIST 규칙: 이름은 명령줄 첫 단어)"""
    bins = {}
    for root, _, fs in os.walk("tests"):
        for f in fs:
            p = os.path.join(root, f)
            if "." not in f and os.access(p, os.X_OK):
                bins.setdefault(f, p)
    want = {}
    for ev in events:
        if ev["kind"] == "fault" and ev.get("user"):
            want.setdefault(ev["prog"], set()).add(ev["rip"])
        elif ev["kind"] == "uentry":
            want.setdefault(ev["prog"], set()).add(ev["regs"]["rip"])
    out = {}
    for name, addrs in want.items():
        b = bins.get(name)
        if not b:
            continue
        addrs = sorted(addrs)
        try:
            res = subprocess.run(["addr2line", "-f", "-e", b] + ["%#x" % a for a in addrs],
                                 capture_output=True, text=True, timeout=20).stdout.splitlines()
        except (OSError, subprocess.SubprocessError):
            continue
        for k, a in enumerate(addrs):
            fn, loc = (res[2 * k:2 * k + 2] + ["??", "??"])[:2]
            m = re.match(r"(.*):(\d+)", loc)
            entry = {"fn": fn}
            if m and m.group(1) != "??":
                p = os.path.relpath(os.path.realpath(os.path.join(os.getcwd(), m.group(1))), ROOT)
                if not p.startswith("..") and os.path.exists(os.path.join(ROOT, p)):
                    sources.add(p)
                    entry["loc"] = "%s:%s" % (p, m.group(2))
            out["%s@%x" % (name, a)] = entry
    return out

# ---- 저장 / 종료 (trace.py와 같은 흐름) ----
saved = False
panicked = False
ended = False
HOOKS = []

def leftovers():
    """테스트 시작 후 할당돼 끝날 때까지 안 풀린 페이지/파일. 죽은 스레드의 struct thread 페이지는
    스케줄러가 다음 전환 때 지우므로(destruction_req) 누수가 아니라 pending으로 표시함"""
    dead_pages = {int(info[i]["addr"], 16) for i in dead}
    # malloc이 받은 arena 페이지는 그 안의 블록이 안 풀려서 남은 것이므로, 블록 쪽(실제로 malloc한 곳)으로만 보임
    via_malloc = lambda p: MALLOC and "malloc" in p["stack"][:2]
    lp = [dict(p, addr=hex(a), pending=a in dead_pages, xev=exit_ev.get(p["by"])) for a, p in pages.items()
          if p["ev"] is not None and not via_malloc(p)]
    lb = [dict(b, addr=hex(a), xev=exit_ev.get(b["by"])) for a, b in blocks.items()]
    lf = [dict(f, addr=hex(a), xev=exit_ev.get(f["by"])) for a, f in files.items() if f["ev"] is not None]
    return {"pages": lp, "files": lf, "blocks": lb if MALLOC else None}

def save(status):
    global saved
    if saved:
        return
    saved = True
    try:
        syms = user_syms()
    except Exception as ex:
        gdb.write("trace warning: 유저 심볼을 풀이하지 못했어요 (%r)\n" % ex)
        syms = {}
    src = {p: open(os.path.join(ROOT, p), errors="replace").read() for p in sorted(sources)}
    text = json.dumps({"kind": "userprog", "threads": info, "events": events, "sources": src, "status": status,
                       "syscalls": SYSNAMES,
                       "lists": {"ready": READY_NAME, "sleep": SLEEP_NAME, "base": T_BASE is not None, "dons": T_DONS is not None}, "sig": SIG, "truncated": truncated,
                       "leaks": leftovers() if status == "ok" and not truncated else None,
                       "usyms": syms, "vm": vm_info() if VM else None})
    with open(OUT + ".tmp", "w") as fp:
        fp.write(text)
    os.replace(OUT + ".tmp", OUT)
    gdb.write("trace: %d events, %s -> %s\n" % (len(events), status, OUT))

def vm_info():
    try:
        upool = int(gdb.parse_and_eval("'palloc.c'::user_pool.used_map->bit_cnt"))
    except gdb.error:
        upool = None
    return {"upool": upool, "ret": VM_RET is not None}

def on_power_off():
    global ended
    try:
        for i, b in line_buf.items():   # 줄바꿈 없이 끝난 출력
            if b and not truncated:
                events.append({"kind": "out", "by": i, "tick": tick(), "text": b.decode(errors="replace"), "cnt": counts()})
        record("end")
    finally:
        ended = True
    return True

def finish():
    if saved:
        return
    for h in HOOKS:
        h.enabled = False
    if ended:
        status = "panic" if panicked else "ok"
    else:
        status = "attach_failed" if not events else ("timeout" if timed_out and not interrupted else "aborted")
        for _ in range(3):
            if status == "attach_failed":
                break
            try:
                if events[-1]["kind"] != status:
                    try:
                        st = stuck()
                    except Exception as ex:
                        gdb.write("trace warning: 멈춘 스레드를 분석하지 못했어요 (%r)\n" % ex)
                        st = []
                    record(status, secs=TIMEOUT, stuck=st)
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
        try:
            gdb.execute("continue")
            return
        except BaseException:
            pass
    try:
        gdb.execute("kill")
    except BaseException:
        pass

timed_out = False
interrupted = False
stopped = False
STOP_FILE = os.environ.get("TRACE_STOP")

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
            if not saved and not stopped:
                os.kill(os.getpid(), signal.SIGINT)
            return
        time.sleep(0.5)

threading.Thread(target=_watch, daemon=True).start()

REGS = ("rip", "rsp", "rbp", "rax", "rbx", "rcx", "rdx", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15", "eflags")
last_stop = [None, set(), 0]   # [직전 정지의 레지스터, 이번 round에 불린 훅, 똑같이 다시 온 round 수]

class Hook(gdb.Breakpoint):
    def __init__(self, spec, fn):
        super().__init__(spec if spec.startswith("*") else "*" + spec, internal=True)
        self.fn = fn
    def stop(self):
        global stopped
        if timed_out or interrupted:
            stopped = True
            return True
        try:
            # QEMU가 가끔 같은 브레이크포인트를 두 번 알림 (넘어가는 사이에 인터럽트가 걸렸다 돌아옴). 레지스터가 전부 같으면 두 번째만 같은 정지로 봄.
            # 세 번째부터는 진짜 반복임 (매핑 없이 true를 반환해 같은 fault가 계속 남 등). 그래서 반복 횟수는 하나 적게 찍힘
            fr = gdb.selected_frame()
            sig = tuple(int(fr.read_register(r)) for r in REGS)
            # 같은 주소에 훅이 여럿이면(효율 측정 등) 한 정지에서 다 불리므로, 같은 훅 객체가 다시 와야 새 정지(round)로 셈
            if sig != last_stop[0]:
                last_stop[:] = [sig, {self}, 0]
            elif self in last_stop[1]:
                last_stop[1] = {self}
                last_stop[2] += 1
            else:
                last_stop[1].add(self)
            if last_stop[2] == 1:
                return False
            if self.fn() is True:
                stopped = True
                return True
        except KeyboardInterrupt:
            stopped = True
            return True
        except Exception as ex:
            gdb.write("trace error at %s: %r\n" % (self.location, ex))
        return False

specs = [("init_thread", on_init_thread), ("thread_exit", on_thread_exit), ("run_task", on_run_task),
         ("process_exec", on_process_exec), ("process_wait", on_process_wait),
         ("syscall_handler", on_syscall), ("do_iret", on_do_iret), ("page_fault", on_page_fault), ("kill", on_kill),
         ("putchar_have_lock", on_putchar), ("debug_panic", on_panic), ("power_off", on_power_off),
         ("palloc_get_multiple", on_palloc_in), ("palloc_free_multiple", on_pfree),
         ("filesys_open", on_filesys_open), ("file_duplicate", on_file_dup_in), ("file_reopen", on_file_dup_in), ("file_close", on_file_close),
         ("lock_init", on_obj_init("lock")), ("sema_init", on_obj_init("sema"))]
try:
    A_DESC, A_CNT = off("((struct arena *)0)->desc"), off("((struct arena *)0)->free_cnt")
    D_SIZE = off("((struct desc *)0)->block_size")
    specs.append(("free", on_free))
    MALLOC = True
except gdb.error:
    gdb.write("trace warning: malloc.c의 arena 구조를 찾지 못해, free한 lock/sema를 계속 읽을 수 있어요\n")
try:
    a = sysret_addr()
    if a:
        specs.append(("*" + a, on_sysret))
    else:
        gdb.write("trace warning: syscall_entry에서 복귀 지점을 찾지 못해 시스템 콜 반환값은 기록하지 않아요\n")
except gdb.error as ex:
    gdb.write("trace warning: syscall_entry를 분석하지 못했어요 (%s)\n" % ex)
for fn, cb in (("palloc_get_multiple", on_palloc_out), ("file_open", file_ret("open")),
               ("file_reopen", file_ret("reopen")), ("file_duplicate", file_ret("dup"))) + ((("malloc", on_malloc_out),) if MALLOC else ()):
    try:
        r = ret_addr(fn)
    except gdb.error:
        r = None
    if r is None:
        gdb.write("trace warning: %s의 복귀 지점을 찾지 못해 누수 검사에서 뺐어요\n" % fn)
        MALLOC = MALLOC and fn != "malloc"
        continue
    specs.append(("*" + r, cb))
# Project 3: VM 빌드(vm_try_handle_fault가 있음)일 때만. 함수 이름은 원본 스켈레톤 것
try:
    gdb.parse_and_eval("vm_try_handle_fault")
    P_VA, P_FRAME = off("((struct page *)0)->va"), off("((struct page *)0)->frame")
    FR_KVA = off("((struct frame *)0)->kva")
    T_PML4 = off("((struct thread *)0)->pml4")
    VM = True
except gdb.error as ex:
    if "vm_try_handle_fault" not in str(ex):   # VM 빌드인데 원본 구조체 필드가 없음
        gdb.write("trace warning: VM 구조(struct page/frame의 va, frame, kva, thread의 pml4)를 찾지 못해 가상 메모리 기록을 껐어요 (%s)\n" % ex)
if VM:
    specs += [("uninit_new", on_uninit_new), ("anon_initializer", on_vm_init(1)), ("file_backed_initializer", on_vm_init(2)),
              ("pml4_set_page", on_set_page), ("pml4_clear_page", on_clear_page), ("pml4_destroy", on_pml4_destroy),
              ("anon_swap_out", on_swap("o")), ("file_backed_swap_out", on_swap("o")),
              ("anon_swap_in", on_swap("i")), ("file_backed_swap_in", on_swap("i")),
              ("uninit_destroy", on_vm_destroy), ("anon_destroy", on_vm_destroy), ("file_backed_destroy", on_vm_destroy)]
    try:
        VM_RET = ret_addr("vm_try_handle_fault")
    except gdb.error:
        VM_RET = None
    if VM_RET:
        specs = [x for x in specs if x[0] != "page_fault"] + [("*" + VM_RET, on_vm_ret)]
    else:
        gdb.write("trace warning: vm_try_handle_fault의 복귀 지점을 찾지 못해 fault 처리 결과는 기록하지 않아요\n")
for spec, fn in specs:
    try:
        HOOKS.append(Hook(spec, fn))
    except gdb.error:
        gdb.write("trace warning: %s 함수가 없어 이 이벤트는 기록하지 않아요\n" % spec)
