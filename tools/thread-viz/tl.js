// 이벤트 타임라인 공통 엔진 (viewer.html, uprog.html). 가로축 = 이벤트 순서, 세로 = 스레드 줄.
// 캔버스는 보이는 폭만큼만 만들고, 스크롤·확대·크기 변경 때 보이는 구간만 다시 그림. 이름 칸은 HTML이라 가로로 안 밀림.
// 쓰는 법: const tl = Timeline($("tl"), { store: "localStorage 키", ctl: 확대 버튼 넣을 요소, alpha, pick(i), tip(i, r, code), marks(g, v) })
//   tl.data({ n, rows: [이름 html], codes: Uint8Array(n * rows) (0 = 안 그림), colors: ["--run", ...] (코드 1부터),
//             bad: [이상 이벤트 index], band: { h, label } (줄 아래 추가 영역, marks가 그림) })
//   tl.cursor(idx)  현재 위치 선. idx가 바뀌었을 때만, 화면 밖이면 따라 스크롤함 (사용자 스크롤은 안 건드림)
//   tl.key(e)       + = - 0 키 처리. 처리했으면 true
// 끌기: 현재 위치 선(위쪽 손잡이 포함) 근처를 끌면 이벤트를 넘겨 보고, 그 밖을 끌면 옆으로 이동함

function Timeline(host, o) {
  const ROW = 22, MAX = 32;
  // lane: 줄 위쪽 6px를 표시(눈금) 자리로 비우고 막대를 아래로 내림
  const BY = o.lane ? 9 : 5, BH = o.lane ? 9 : ROW - 9;
  host.classList.add("tl");
  host.innerHTML = '<div class="tl-lab"></div><div class="tl-sc"><div class="tl-sp"><canvas></canvas><div class="tl-cur"><i class="tl-knob" title="끌어서 이벤트를 넘겨 봐요"></i></div></div></div><div class="tl-tip" hidden></div>';
  const [lab, sc, tip] = host.children, sp = sc.firstChild, cv = sp.firstChild, cur = sp.lastChild;
  let d = { n: 0, rows: [], codes: new Uint8Array(0), colors: [], bad: [] }, R = 0, H = 0;
  let step = 1, fit = true, at = -1, raf = 0;
  try { const z = +localStorage.getItem(o.store); if (z > 0) { fit = false; step = z; } } catch (e) {}
  let zo, zt, zi;
  if (o.ctl) {
    o.ctl.innerHTML = '<button class="icon" aria-label="축소" title="축소 (-)"><i class="ic i-minus"></i></button>' +
      '<span class="tl-zoom mono" title="Ctrl(⌘) + 휠로도 확대·축소해요"></span>' +
      '<button class="icon" aria-label="확대" title="확대 (+)"><i class="ic i-plus"></i></button><button title="전체 보기 (0)">맞춤</button>';
    let fb;
    [zo, zt, zi, fb] = o.ctl.children;
    zo.onclick = () => zoom(step / 2); zi.onclick = () => zoom(step * 2); fb.onclick = () => zoom(0);
  }

  const fitStep = () => (sc.clientWidth || 1) / Math.max(1, d.n);
  function layout() {
    const f = fitStep();
    step = fit ? f : Math.min(Math.max(step, f), Math.max(MAX, f));
    if (step <= f * 1.001) fit = true;
    sp.style.width = d.n * step + "px";
    cur.style.left = (at < 0 ? 0 : at * step + step / 2) + "px";
    if (zt) {
      const r = step / f;
      zt.textContent = "×" + (r < 10 ? +r.toFixed(1) : Math.round(r));
      zo.disabled = fit; zi.disabled = step >= Math.max(MAX, f) - 1e-9;
    }
    req();
  }
  // s = 0이면 맞춤. ax = 고정할 화면 x (기본: 현재 위치 선이 보이면 거기, 아니면 가운데)
  function zoom(s, ax) {
    const W = sc.clientWidth;
    if (ax == null) { ax = at * step + step / 2 - sc.scrollLeft; if (!(ax >= 0 && ax <= W)) ax = W / 2; }
    const e = (sc.scrollLeft + ax) / step;
    fit = !s; if (s) step = s;
    layout();
    sc.scrollLeft = e * step - ax;
    try { localStorage.setItem(o.store, fit ? "0" : String(step)); } catch (err) {}
  }
  const req = () => raf || (raf = requestAnimationFrame(paint));

  // step >= 1: 이벤트마다 한 칸, step < 1: 화면 1px 열마다 그 열의 이벤트 구간 [a, b). cb(a, b, 왼쪽 x, 오른쪽 x)
  function cols(cb, sl, W) {
    if (step >= 1) {
      const i0 = Math.max(0, Math.floor(sl / step)), i1 = Math.min(d.n, Math.ceil((sl + W) / step) + 1);
      for (let i = i0; i < i1; i++) cb(i, i + 1, i * step - sl, (i + 1) * step - sl);
    } else for (let px = 0; px < W; px++) {
      const a = Math.floor((sl + px) / step);
      if (a >= d.n) break;
      cb(a, Math.max(a + 1, Math.min(d.n, Math.floor((sl + px + 1) / step))), px, px + 1);
    }
  }

  function paint() {
    raf = 0;
    const W = sc.clientWidth, dpr = window.devicePixelRatio || 1, sl = sc.scrollLeft;
    if (!W) return;
    // 색은 그릴 때마다 CSS 변수에서 다시 읽음 (테마가 바뀌면 matchMedia가 다시 그리게 함)
    const cs = getComputedStyle(document.documentElement), cc = {};
    const col = n => cc[n] ?? (cc[n] = cs.getPropertyValue(n).trim());
    cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px";
    const g = cv.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.fillStyle = col("--line");
    for (let r = 1; r <= R; r++) if (r < R || d.band) g.fillRect(0, r * ROW, W, 1);
    // 같은 상태가 이어지는 칸은 둥근 막대 하나로 합침. 색마다 Path2D 하나로 모아 한 번에 칠함
    const paths = [];
    for (let r = 0; r < R; r++) {
      let c0 = 0, x0 = 0, xe = 0;
      const flush = () => { if (c0) (paths[c0] || (paths[c0] = new Path2D())).roundRect(x0, r * ROW + BY, Math.max(1, xe - x0 - (xe - x0 > 4 ? 1 : 0)), BH, 3); };
      cols((a, b, xl, xr) => { const c = d.codes[a * R + r]; if (c !== c0) { flush(); c0 = c; x0 = xl; } xe = xr; }, sl, W);
      flush();
    }
    g.globalAlpha = o.alpha || 1;
    paths.forEach((p, c) => { g.fillStyle = col(d.colors[c - 1]); g.fill(p); });
    g.globalAlpha = 1;
    const i0 = Math.max(0, Math.floor(sl / step)), i1 = Math.min(d.n, Math.ceil((sl + W) / step) + 1);
    if (o.marks) o.marks(g, { i0, i1, step, W, ROW, top: R * ROW, col, x: i => i * step - sl + step / 2, y: r => r * ROW + ROW / 2, bar: r => [r * ROW + BY, BH],
      cols: cb => cols(cb, sl, W) });
    // 이상 표시는 확대 정도와 관계없이 항상 그림: 세로로 옅은 빨간 띠 + 위쪽 작은 삼각형
    const bw = Math.max(step, 2);
    for (const i of d.bad) if (i >= i0 && i < i1) {
      const x = i * step - sl;
      g.fillStyle = col("--dying"); g.globalAlpha = .1; g.fillRect(x, 0, bw, R * ROW); g.globalAlpha = 1;
      g.beginPath(); g.moveTo(x + bw / 2 - 4, 0); g.lineTo(x + bw / 2 + 4, 0); g.lineTo(x + bw / 2, 5); g.closePath(); g.fill();
    }
  }

  const evAt = e => {
    const b = sc.getBoundingClientRect(), y = e.clientY - sp.getBoundingClientRect().top;
    if (y < 0 || y >= H || !d.n) return null;
    return [Math.min(d.n - 1, Math.max(0, Math.floor((sc.scrollLeft + e.clientX - b.left) / step))), y < R * ROW ? Math.floor(y / ROW) : -1];
  };
  // 마우스·펜: 현재 위치 선 근처면 넘겨 보기(scrub), 아니면 옆으로 이동(pan). 안 끌고 떼면 그 이벤트로.
  // 터치는 손잡이만 넘겨 보기를 받고, 나머지는 브라우저 스크롤에 맡김
  let drag = null;
  const nearCur = e => at >= 0 && Math.abs(e.clientX - cur.getBoundingClientRect().left - 1) <= 6;
  sp.onpointerdown = e => {
    if (e.button) return;
    const scrub = e.target.classList.contains("tl-knob") || (e.pointerType !== "touch" && nearCur(e));
    if (!scrub && e.pointerType === "touch") return;
    drag = { x: e.clientX, sl: sc.scrollLeft, moved: false, scrub };
    sp.setPointerCapture(e.pointerId); sp.classList.add(scrub ? "scrub" : "pan"); tip.hidden = true;
    e.preventDefault();
  };
  sp.onpointermove = e => {
    if (drag) {
      if (Math.abs(e.clientX - drag.x) > 3) drag.moved = true;
      if (drag.scrub) {
        const b = sc.getBoundingClientRect(), x = e.clientX - b.left;
        // 가장자리 밖으로 끌면 그쪽으로 조금씩 밀어 줌
        if (x < 0) sc.scrollLeft += x; else if (x > b.width) sc.scrollLeft += x - b.width;
        const i = Math.min(d.n - 1, Math.max(0, Math.floor((sc.scrollLeft + Math.min(Math.max(x, 0), b.width)) / step)));
        if (i !== at) o.pick(i);
      } else if (drag.moved) sc.scrollLeft = drag.sl - (e.clientX - drag.x);
      return;
    }
    sp.classList.toggle("near", nearCur(e));
    const h = evAt(e), html = h && o.tip ? o.tip(h[0], h[1], h[1] >= 0 ? d.codes[h[0] * R + h[1]] : 0) : "";
    if (!html) { tip.hidden = true; return; }
    tip.innerHTML = html; tip.hidden = false;
    tip.style.left = Math.max(8, Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8)) + "px";
    tip.style.top = (e.clientY + 18 + tip.offsetHeight > innerHeight ? e.clientY - tip.offsetHeight - 10 : e.clientY + 18) + "px";
  };
  sp.onpointerup = e => {
    const dr = drag; drag = null; sp.classList.remove("scrub", "pan");
    if (dr && !dr.moved && !dr.scrub) { const h = evAt(e); if (h) o.pick(h[0]); }
  };
  sp.onpointercancel = () => { drag = null; sp.classList.remove("scrub", "pan"); };
  sp.onpointerleave = () => { tip.hidden = true; };
  sc.onscroll = () => { tip.hidden = true; req(); };
  sc.addEventListener("wheel", e => {
    if (!e.ctrlKey && !e.metaKey) return;   // 그냥 휠은 브라우저 스크롤 그대로
    e.preventDefault();
    zoom(step * Math.exp(-e.deltaY * 0.002), e.clientX - sc.getBoundingClientRect().left);
  }, { passive: false });
  new ResizeObserver(layout).observe(sc);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", req);

  return {
    data(nd) {
      d = Object.assign({ bad: [] }, nd); R = d.rows.length; H = R * ROW + (d.band ? d.band.h : 0);
      lab.innerHTML = d.rows.map(h => `<div>${h}</div>`).join("") + (d.band ? `<div class="tl-band" style="height:${d.band.h}px">${d.band.label}</div>` : "");
      cv.style.height = cur.style.height = H + "px";
      at = -1; layout();
    },
    cursor(i) {
      const moved = i !== at;
      at = i; cur.style.left = i * step + step / 2 + "px";
      if (!moved) return;
      const x = i * step, W = sc.clientWidth;
      if (x < sc.scrollLeft || x + step > sc.scrollLeft + W) sc.scrollLeft = x + step / 2 - W / 2;
    },
    key(e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return false;
      if (e.key === "+" || e.key === "=") zoom(step * 2);
      else if (e.key === "-") zoom(step / 2);
      else if (e.key === "0") zoom(0);
      else return false;
      return true;
    },
  };
}
