"use strict";

const $ = (s) => document.querySelector(s);
const api = () => window.pywebview.api;

const M_PLAY = '<svg viewBox="0 0 24 24"><path d="M8 5.2v13.6a.7.7 0 0 0 1.06.6l11-6.8a.7.7 0 0 0 0-1.2l-11-6.8A.7.7 0 0 0 8 5.2z" fill="currentColor"/></svg>';
const M_PAUSE = '<svg viewBox="0 0 24 24"><rect x="7" y="5.2" width="3.4" height="13.6" rx="1.2" fill="currentColor"/><rect x="13.6" y="5.2" width="3.4" height="13.6" rx="1.2" fill="currentColor"/></svg>';

const voice = $("#voice");
const musicEl = $("#music");
const chat = $("#chat");
const input = $("#input");

const state = {
  radio: [], ri: -1,        // 推荐歌单(radio) + 当前位置
  oneShot: false,           // 当前在放"点名的单曲"（放完切回 radio）
  cur: null,                // 当前曲目对象（null=没在放任何歌）
  pendingSong: null,        // 等开场白/回应念完再插播的单曲
  vol: 0.85, pendingPlay: false,
  words: [], spans: [], hostBody: null, lastActive: -1,
};
let statusTimer = null;

/* ============ DJ 名称：设置里可改，所有可见处随之改 ============ */
let HOST = "Dsdio";
function applyHostName(name) {
  HOST = (name || "Dsdio").trim() || "Dsdio";
  const brand = $("#brand"); if (brand) brand.textContent = HOST.toUpperCase();
  if (input) input.placeholder = `Talk to ${HOST}…`;
  const partist = $("#partist"), ptitle = $("#ptitle");
  if (partist && ptitle && ptitle.classList.contains("idle")) partist.textContent = `Ask ${HOST} to spin something`;
  const vl = $("#voice-label"); if (vl) vl.textContent = `${HOST}'s voice`;
  const ul = $("#username-label"); if (ul) ul.textContent = `你的名字 · ${HOST} 开机这样称呼你`;
  const ml = $("#mini-letter"); if (ml) ml.textContent = (HOST.charAt(0) || "D").toUpperCase();  // 迷你头像首字母
  document.querySelectorAll(".msg.host .who").forEach((w) => { w.textContent = HOST.toUpperCase(); });  // 刷新已有气泡上的名字
}

/* ================= Particle network (cursor-stretch) ================= */
function initFX() {
  const canvas = $("#fx"), shell = $("#shell");
  if (!canvas || !shell) return;
  const ctx = canvas.getContext("2d");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  let w = 0, h = 0, pts = [];
  const m = { x: 0, y: 0, on: false };
  const LINK = 112, GR = 190;

  function resize() {
    const r = shell.getBoundingClientRect();
    w = r.width; h = r.height;
    canvas.width = w * dpr; canvas.height = h * dpr;
    canvas.style.width = w + "px"; canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.max(30, Math.round((w * h) / 5200));
    pts = [];
    for (let i = 0; i < n; i++) {
      const x = Math.random() * w, y = Math.random() * h;
      pts.push({ x, y, tx: x, ty: y, vx: (Math.random() - 0.5) * 0.18, vy: (Math.random() - 0.5) * 0.18 });
    }
  }
  function step() {
    ctx.clearRect(0, 0, w, h);
    const sp = window.__voicing || state.cur ? 1.5 : 1;
    for (const p of pts) {
      p.x += p.vx * sp; p.y += p.vy * sp;
      if (p.x <= 0 || p.x >= w) p.vx *= -1;
      if (p.y <= 0 || p.y >= h) p.vy *= -1;
      p.x = Math.max(0, Math.min(w, p.x)); p.y = Math.max(0, Math.min(h, p.y));
      let ox = 0, oy = 0;
      if (m.on) {
        const dx = m.x - p.x, dy = m.y - p.y, d = Math.hypot(dx, dy);
        if (d < GR) { const f = Math.pow(1 - d / GR, 2) * 0.42; ox = dx * f; oy = dy * f; }
      }
      p.tx += ((p.x + ox) - p.tx) * 0.22; p.ty += ((p.y + oy) - p.ty) * 0.22;
    }
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i];
      for (let j = i + 1; j < pts.length; j++) {
        const b = pts[j], dx = a.x - b.x, dy = a.y - b.y, d = Math.hypot(dx, dy);
        if (d < LINK) {
          ctx.strokeStyle = `rgba(67,231,255,${(1 - d / LINK) * 0.26})`;
          ctx.lineWidth = 0.7; ctx.beginPath(); ctx.moveTo(a.tx, a.ty); ctx.lineTo(b.tx, b.ty); ctx.stroke();
        }
      }
    }
    for (const p of pts) {
      const dm = m.on ? Math.hypot(p.x - m.x, p.y - m.y) : 1e9;
      if (dm < GR) {
        ctx.strokeStyle = `rgba(155,242,255,${(1 - dm / GR) * 0.6})`;
        ctx.lineWidth = 0.8; ctx.beginPath(); ctx.moveTo(p.tx, p.ty); ctx.lineTo(m.x, m.y); ctx.stroke();
      }
      const near = dm < GR;
      ctx.beginPath(); ctx.arc(p.tx, p.ty, near ? 2 : 1.5, 0, 6.283);
      ctx.fillStyle = near ? "rgba(155,242,255,0.95)" : "rgba(67,231,255,0.5)";
      ctx.shadowColor = "#43e7ff"; ctx.shadowBlur = near ? 8 : 2; ctx.fill();
    }
    ctx.shadowBlur = 0;
    if (m.on) { ctx.beginPath(); ctx.arc(m.x, m.y, 2.5, 0, 6.283); ctx.fillStyle = "rgba(155,242,255,.9)"; ctx.shadowColor = "#43e7ff"; ctx.shadowBlur = 12; ctx.fill(); ctx.shadowBlur = 0; }
    requestAnimationFrame(step);
  }
  shell.addEventListener("mousemove", (e) => { const r = shell.getBoundingClientRect(); m.x = e.clientX - r.left; m.y = e.clientY - r.top; m.on = true; });
  shell.addEventListener("mouseleave", () => { m.on = false; });
  window.addEventListener("resize", resize);
  resize(); step();
}

/* ================= Galaxy (设置面板 · 深空星辰，可交互) ================= */
const galaxy = (() => {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  let canvas, ctx, raf = 0, running = false, w = 0, h = 0;
  let stars = [], shooting = [], sparks = [];
  const m = { x: -1e9, y: -1e9, on: false };
  const REACH = 132;

  function tint(hue, a) {
    if (hue > 0.87) return `rgba(206,172,255,${a})`;   // 紫
    if (hue > 0.74) return `rgba(255,214,168,${a})`;   // 暖金
    if (hue > 0.42) return `rgba(168,238,255,${a})`;   // 青白
    return `rgba(230,240,255,${a})`;                    // 星白
  }
  function build() {
    const n = Math.max(110, Math.round((w * h) / 950));
    stars = [];
    for (let i = 0; i < n; i++) {
      const layer = Math.random();                      // 0 远 → 1 近
      stars.push({
        x: Math.random() * w, y: Math.random() * h,
        r: 0.45 + layer * 1.7, depth: 0.3 + layer * 1.5,
        tw: Math.random() * 6.28, tws: 0.5 + Math.random() * 1.9,
        hue: Math.random(),
      });
    }
  }
  function resize() {
    const r = $("#settings").getBoundingClientRect();
    w = r.width; h = r.height;
    if (!w || !h) return;
    canvas.width = w * dpr; canvas.height = h * dpr;
    canvas.style.width = w + "px"; canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    build();
  }
  function shoot(x, y) {
    const ang = Math.PI * (0.12 + Math.random() * 0.22);
    const sp = 6 + Math.random() * 4.5;
    shooting.push({ x: x == null ? Math.random() * w * 0.8 : x, y: y == null ? Math.random() * h * 0.45 : y,
      vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp, life: 1, hue: Math.random() });
  }
  function burst(x, y) {
    for (let i = 0; i < 16; i++) {
      const a = Math.random() * 6.283, s = 1 + Math.random() * 2.8;
      sparks.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: 1, hue: Math.random() });
    }
    if (Math.random() < 0.55) shoot(x, y);
  }
  function step(t) {
    if (!running) return;
    if (!w || !h) resize();
    const time = t / 1000;
    ctx.clearRect(0, 0, w, h);
    const px0 = m.on ? (m.x - w / 2) : 0, py0 = m.on ? (m.y - h / 2) : 0;

    for (const s of stars) {
      const px = s.x - px0 * s.depth * 0.013;
      const py = s.y - py0 * s.depth * 0.013;
      const tw = 0.5 + 0.5 * Math.sin(time * s.tws + s.tw);
      let a = 0.22 + 0.6 * tw * (s.depth / 1.8), r = s.r;
      let dm = 1e9;
      if (m.on) dm = Math.hypot(m.x - px, m.y - py);
      if (dm < REACH) {
        const f = 1 - dm / REACH;
        a = Math.min(1, a + f * 0.75); r = s.r + f * 2.0;
        ctx.strokeStyle = `rgba(176,210,255,${f * 0.30})`;
        ctx.lineWidth = 0.6; ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(m.x, m.y); ctx.stroke();
      }
      ctx.beginPath(); ctx.arc(px, py, r, 0, 6.283);
      ctx.fillStyle = tint(s.hue, a);
      ctx.shadowColor = tint(s.hue, 0.9); ctx.shadowBlur = (dm < REACH ? 9 : 2.5) * (s.depth / 1.4);
      ctx.fill();
    }
    ctx.shadowBlur = 0;
    if (m.on) { ctx.beginPath(); ctx.arc(m.x, m.y, 2.4, 0, 6.283); ctx.fillStyle = "rgba(196,176,255,.9)"; ctx.shadowColor = "#b9a0ff"; ctx.shadowBlur = 15; ctx.fill(); ctx.shadowBlur = 0; }

    for (const sh of shooting) {
      sh.x += sh.vx; sh.y += sh.vy; sh.life -= 0.012;
      const tx = sh.x - sh.vx * 7, ty = sh.y - sh.vy * 7;
      const g = ctx.createLinearGradient(sh.x, sh.y, tx, ty);
      g.addColorStop(0, tint(sh.hue, sh.life)); g.addColorStop(1, "rgba(255,255,255,0)");
      ctx.strokeStyle = g; ctx.lineWidth = 1.7; ctx.beginPath(); ctx.moveTo(sh.x, sh.y); ctx.lineTo(tx, ty); ctx.stroke();
    }
    shooting = shooting.filter((s) => s.life > 0 && s.x < w + 80 && s.y < h + 80);

    for (const sp of sparks) {
      sp.x += sp.vx; sp.y += sp.vy; sp.vx *= 0.92; sp.vy *= 0.92; sp.life -= 0.028;
      ctx.beginPath(); ctx.arc(sp.x, sp.y, 1.6 * sp.life + 0.4, 0, 6.283);
      ctx.fillStyle = tint(sp.hue, sp.life); ctx.shadowColor = tint(sp.hue, 0.9); ctx.shadowBlur = 6; ctx.fill();
    }
    ctx.shadowBlur = 0;
    sparks = sparks.filter((s) => s.life > 0);

    if (Math.random() < 0.004) shoot();
    raf = requestAnimationFrame(step);
  }
  function start() {
    if (!canvas) {
      canvas = $("#galaxy"); if (!canvas) return; ctx = canvas.getContext("2d");
      const panel = $("#settings");
      panel.addEventListener("mousemove", (e) => { const r = panel.getBoundingClientRect(); m.x = e.clientX - r.left; m.y = e.clientY - r.top; m.on = true; });
      panel.addEventListener("mouseleave", () => { m.on = false; });
      panel.addEventListener("mousedown", (e) => { const r = panel.getBoundingClientRect(); burst(e.clientX - r.left, e.clientY - r.top); });
      window.addEventListener("resize", () => { if (running) resize(); });
    }
    running = true; resize();
    cancelAnimationFrame(raf); raf = requestAnimationFrame(step);
  }
  function stop() { running = false; cancelAnimationFrame(raf); }
  return { start, stop };
})();

/* ================= Music visualizer (音律跳动) ================= */
function initViz(sel = "#viz", N = 36) {
  const canvas = $(sel); if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const bars = new Array(N).fill(0);
  let w = 0, h = 0;
  function resize() {
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = Math.max(1, w * dpr); canvas.height = Math.max(1, h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function frame(t) {
    if (!w || !h) resize();
    ctx.clearRect(0, 0, w, h);
    const playing = !musicEl.paused && !!state.cur;
    const gap = 3, bw = (w - gap * (N - 1)) / N, tt = t / 1000;
    for (let i = 0; i < N; i++) {
      let target = 0;
      if (playing) {
        const s = (Math.sin(tt * 6.0 + i * 0.55) + Math.sin(tt * 3.3 + i * 0.9) + Math.sin(tt * 11.0 + i * 0.27)) / 3;
        const center = 1 - Math.abs(i - (N - 1) / 2) / ((N - 1) / 2);
        target = (0.18 + 0.82 * Math.abs(s)) * (0.55 + 0.45 * center) * (0.7 + 0.3 * Math.random());
      }
      // 上升快、回落慢，做出打击感
      bars[i] += (target - bars[i]) * (target > bars[i] ? 0.55 : 0.12);
      const bh = Math.max(2, bars[i] * h);
      const x = i * (bw + gap), y = h - bh;
      ctx.fillStyle = `rgba(67,231,255,${0.3 + 0.6 * bars[i]})`;
      ctx.shadowColor = "#43e7ff"; ctx.shadowBlur = 7 * bars[i];
      ctx.fillRect(x, y, Math.max(1, bw), bh);
    }
    ctx.shadowBlur = 0;
    requestAnimationFrame(frame);
  }
  window.addEventListener("resize", resize);
  resize(); requestAnimationFrame(frame);
}

/* ================= Helpers ================= */
function setStatus(text, loading = false, isErr = false) {
  const el = $("#status");
  el.innerHTML = (loading ? '<span class="spinner"></span>' : "") + text;
  el.classList.toggle("err", isErr); el.classList.remove("hidden");
  clearTimeout(statusTimer);
}
function hideStatus() { $("#status").classList.add("hidden"); }
function toast(text, isErr = false) { setStatus(text, false, isErr); clearTimeout(statusTimer); statusTimer = setTimeout(hideStatus, 3000); }
function fmt(sec) { if (!isFinite(sec) || sec < 0) sec = 0; const m = Math.floor(sec / 60), s = Math.floor(sec % 60); return `${m}:${String(s).padStart(2, "0")}`; }

/* ================= Chat ================= */
function addUserMsg(text) {
  const el = document.createElement("div");
  el.className = "msg user"; el.textContent = text;
  chat.appendChild(el); chat.scrollTop = chat.scrollHeight;
}
function addHostMsg(text, typing = false) {
  const el = document.createElement("div");
  el.className = "msg host" + (typing ? " typing" : "");
  const who = document.createElement("span"); who.className = "who"; who.textContent = HOST.toUpperCase();
  const body = document.createElement("span"); body.className = "body"; body.textContent = text;
  el.append(who, body);
  chat.appendChild(el); chat.scrollTop = chat.scrollHeight;
  return { el, body };
}
let voiceGen = 0, respCtx = null;

// 直接播放控制命令（下一首/上一首/暂停/继续）：发起对话前先问后端，命中就就地操作播放器，
// 不发给 DeepSeek（零延迟、不耗 API、离线可用）。命中返回 true。
async function tryPlaybackCommand(text) {
  let cmd;
  try { cmd = await api().playback_command(text); }
  catch (_) { return false; }
  if (!cmd || !cmd.action) return false;
  const actions = {
    next: musicNext, prev: musicPrev,
    pause: () => musicEl.pause(), resume: () => musicEl.play(),
  };
  const fn = actions[cmd.action];
  if (!fn) return false;
  addUserMsg(text);                          // 像一次轻量对话显示，但不写进 DeepSeek 历史
  fn();                                       // 即时切歌/暂停（_play 同步设好 state.cur）
  if (cmd.say) { addHostMsg(cmd.say); await speakOnce(cmd.say); }   // 念固定短语，等念完
  // 固定短语之后：让 Dsdio 用 DJ 口吻自然补一句（不重复固定短语；带上刚切到的歌名）
  const t = state.cur;
  const nowPlaying = t ? (t.artist ? `${t.name} — ${t.artist}` : (t.name || "")) : "";
  let fu;
  try { fu = await api().command_followup(cmd.action, cmd.say || "", nowPlaying); }
  catch (_) { fu = null; }
  if (fu && fu.ok && fu.text) { addHostMsg(fu.text); speakOnce(fu.text); }
  return true;
}

async function doSend() {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  if (await tryPlaybackCommand(text)) return;   // 直接命令：就地切歌/暂停，不再发给 DeepSeek
  addUserMsg(text);
  const ph = addHostMsg("", true);
  const gen = ++voiceGen;
  const ctx = (respCtx = { gen, el: ph.el, body: ph.body, queue: [], playing: false, ended: false, started: false });
  let res;
  try { res = await api().chat(text, gen); }   // 传 gen：前后端共用同一代号，逐句/续解推送不会错位
  catch (e) { res = { ok: false, error: String(e) }; }
  ph.el.classList.remove("typing");
  if (!res.ok) {
    if (!ctx.started) ph.body.textContent = res.error || "…something glitched.";
    if (/key/i.test(res.error || "")) openSettings();
    return;
  }
  if (res.note) toast(res.note);
  if (res.tracks && res.tracks.length) {
    if (res.one_shot) {                              // 点名单曲：放完切回推荐歌单，不动 radio
      state.pendingSong = res.tracks[0]; state.pendingPlay = true;
    } else {                                         // 氛围/歌单：换掉推荐歌单
      state.radio = res.tracks.slice(); state.ri = -1; state.pendingSong = null; state.pendingPlay = true;
    }
  }
  ctx.ended = true;          // 生成结束；队列放完后接上音乐
  kick(ctx);
}

// 后端逐句推来：渲染该句的词、入播放队列（边生成边说）
window.dsdioSentence = function (p) {
  const ctx = respCtx;
  if (!ctx || p.gen !== ctx.gen) return;
  ctx.el.classList.remove("typing");
  const span = document.createElement("span");
  span.className = "sent";
  const tokens = p.text.match(/\S+|\s+/g) || [p.text];
  const kws = [];
  let wi = 0;
  tokens.forEach((tok) => {
    if (/^\s+$/.test(tok)) { span.appendChild(document.createTextNode(tok)); return; }
    const w = document.createElement("span");
    w.className = "kw"; w.textContent = tok;
    w.dataset.start = (p.words && p.words[wi]) ? p.words[wi].start : 0;
    span.appendChild(w); kws.push(w); wi++;
  });
  span.appendChild(document.createTextNode(" "));
  ctx.body.appendChild(span);
  chat.scrollTop = chat.scrollHeight;
  ctx.queue.push({ voice: p.voice, kws });
  kick(ctx);
};

// 后端把后台解锁好的歌逐首推来，追加到推荐歌单尾（氛围歌单近乎秒起，其余原版陆续补进来）
window.dsdioQueueAppend = function (gen, tracks) {
  if (gen !== voiceGen) return;                          // 过期请求的歌，丢弃
  if (!Array.isArray(tracks) || !tracks.length) return;
  const have = new Set(state.radio.map((t) => t.id));
  const add = tracks.filter((t) => t && !have.has(t.id));
  if (!add.length) return;
  const wasEmpty = state.radio.length === 0;
  state.radio = state.radio.concat(add);
  if (wasEmpty && !state.cur && musicEl.paused && !state.oneShot) {  // 极端：首曲当时没就绪 → 补起播
    if (window.__voicing) state.pendingPlay = true;
    else { state.pendingPlay = false; playRadio(0); }
  }
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const SENT_PAUSE = 240;   // 句间微微停顿，更像聊天的换气

function kick(ctx) { if (!ctx.playing) { ctx.playing = true; pump(ctx); } }

async function pump(ctx) {
  if (ctx.gen !== voiceGen) { ctx.playing = false; return; }
  const item = ctx.queue.shift();
  if (!item) { ctx.playing = false; if (ctx.ended) finishResp(ctx); return; }
  if (!ctx.started) { ctx.started = true; setVoicing(true); musicEl.volume = state.vol * 0.2; }
  else { await sleep(SENT_PAUSE); if (ctx.gen !== voiceGen) { ctx.playing = false; return; } }  // 句间换气
  await playChunk(ctx, item);
  pump(ctx);
}

// 迷你停靠条的台词区：只镜像"正在念的这一句"，词序与气泡完全一致，可同步逐词高亮
function setMiniCaption(kws) {
  const cap = $("#mini-caption");
  if (!cap) return [];
  cap.innerHTML = "";
  const mirror = [];
  (kws || []).forEach((k) => {
    const w = document.createElement("span");
    w.className = "mw"; w.textContent = k.textContent;
    cap.appendChild(w); cap.appendChild(document.createTextNode(" "));
    mirror.push(w);
  });
  return mirror;
}
// 头像律动光环：说话或放歌时点亮
function refreshMiniLive() {
  const av = $("#mini-avatar"); if (!av) return;
  av.classList.toggle("live", !!window.__voicing || (!musicEl.paused && !!state.cur));
}

function playChunk(ctx, item) {
  return new Promise((resolve) => {
    const mini = setMiniCaption(item.kws);   // 迷你条：换成当前这一句
    refreshMiniLive();
    if (!item.voice) {
      item.kws.forEach((k) => k.classList.add("said"));
      mini.forEach((k) => k.classList.add("msaid"));
      resolve(); return;
    }
    let raf = 0;
    const done = () => {
      cancelAnimationFrame(raf);
      item.kws.forEach((k) => { k.classList.remove("saying"); k.classList.add("said"); });
      mini.forEach((k) => { k.classList.remove("msaying"); k.classList.add("msaid"); });
      resolve();
    };
    const tick = () => {
      if (ctx.gen !== voiceGen) { done(); return; }
      const t = voice.currentTime * 1000;
      let active = -1;
      for (let i = 0; i < item.kws.length; i++) { if (t >= Number(item.kws[i].dataset.start)) active = i; else break; }
      item.kws.forEach((k, i) => { k.classList.toggle("said", i < active); k.classList.toggle("saying", i === active); });
      mini.forEach((k, i) => { k.classList.toggle("msaid", i < active); k.classList.toggle("msaying", i === active); });
      if (active >= 0 && item.kws[active]) item.kws[active].scrollIntoView({ block: "nearest" });
      raf = requestAnimationFrame(tick);
    };
    voice.onended = done; voice.onerror = done;
    voice.src = item.voice;
    voice.play().then(tick).catch(done);
  });
}

function finishResp(ctx) {
  setVoicing(false);
  refreshMiniLive();
  if (ctx.gen === voiceGen) afterVoice();
}

function afterVoice() {
  musicEl.volume = state.vol;
  if (!state.pendingPlay) return;
  if (state.pendingSong) {                       // 点名的单曲：插播，放完切回推荐歌单
    const s = state.pendingSong; state.pendingSong = null; state.pendingPlay = false; playSong(s);
  } else if (state.radio.length) {               // 氛围歌单：从头开播
    state.pendingPlay = false; playRadio(0);
  }
}

/* ================= Voice (Dsdio TTS) ================= */
// 语音以「逐句队列」播放，见 playSentences() / playVoiceChunk()，无需全局监听器。

/* ================= Music ================= */
function showPlayer() { $("#player").classList.remove("hidden"); }
function _play(t) {
  if (!t) return;
  state.cur = t;
  const title = $("#ptitle");
  title.textContent = t.name || "—";
  title.classList.remove("idle");
  $("#partist").textContent = t.artist || "";
  musicEl.src = t.url;
  musicEl.volume = window.__voicing ? state.vol * 0.2 : state.vol;
  musicEl.play().catch(() => {});
}
function playRadio(i) {                 // 放推荐歌单第 i 首
  state.oneShot = false;
  if (!state.radio.length || i < 0 || i >= state.radio.length) { state.ri = -1; return; }
  state.ri = i; _play(state.radio[i]);
}
function playSong(t) {                   // 插播点名的单曲；放完切回推荐歌单
  state.oneShot = true; _play(t);
}
function musicNext() {
  if (state.oneShot) { state.oneShot = false; playRadio(state.ri + 1); }  // 单曲(放完/跳过) → 续推荐歌单
  else playRadio(state.ri + 1);
}
function musicPrev() {
  if (state.oneShot) { state.oneShot = false; playRadio(Math.max(0, state.ri)); }
  else playRadio(Math.max(0, state.ri - 1));
}
function toggleMusic() {
  if (state.cur) { if (musicEl.paused) musicEl.play(); else musicEl.pause(); return; }
  if (state.radio.length) { playRadio(0); return; }
  toast(`Ask ${HOST} to put something on 🎵`);
}
function updateMusicBtn() {
  $("#m-play").innerHTML = (!musicEl.paused && state.cur) ? M_PAUSE : M_PLAY;
  refreshMiniLive();
}
musicEl.addEventListener("play", updateMusicBtn);
musicEl.addEventListener("pause", updateMusicBtn);
musicEl.addEventListener("ended", musicNext);
musicEl.addEventListener("timeupdate", () => {
  const d = musicEl.duration || 0;
  const pct = d ? `${(musicEl.currentTime / d) * 100}%` : "0";
  $("#pfill").style.width = pct;
  const mf = $("#mini-fill"); if (mf) mf.style.width = pct;     // 迷你条进度同步
  $("#ptime").textContent = `${fmt(musicEl.currentTime)} / ${fmt(d)}`;
});
$("#prail").addEventListener("click", (e) => {
  const r = $("#prail").getBoundingClientRect();
  if (musicEl.duration) musicEl.currentTime = ((e.clientX - r.left) / r.width) * musicEl.duration;
});

/* ================= Mic (Web Speech) ================= */
let micRecs = [], recording = false, micEnabled = true;
let REC_LANG = "zh";                       // zh / en（仅 online 引擎用；SenseVoice 自动多语言、Vosk 恒中文）
let REC_ENGINE = "sensevoice";             // sensevoice(本地中/英,免VPN) / online(Google,需VPN) / vosk(旧)
let voiceReady = false;                    // 离线引擎模型是否已就绪
const SR_CTOR = () => window.SpeechRecognition || window.webkitSpeechRecognition;
// 在线引擎按所选语言走：中文 zh-CN（也能认嵌入的英文词）、English en-US。
function recogLangs() { return REC_LANG === "en" ? ["en-US"] : ["zh-CN"]; }
// 识别语言选择只对 online(Google) 引擎有意义；SenseVoice 自动多语言、Vosk 恒中文 → 非 online 时整块隐藏
function syncRecLangUI() {
  const show = REC_ENGINE === "online";
  ["#reclang-field", "#reclang-hint"].forEach((sel) => { const el = $(sel); if (el) el.classList.toggle("hidden", !show); });
}
function applyMicState(on) { micEnabled = on; $("#mic").classList.toggle("off", !on); }
// 出声状态：除了本地 __voicing 标记，离线引擎下还要告诉后端（唤醒监听据此丢弃自己的声音）
function setVoicing(on) {
  window.__voicing = on;
  if (REC_ENGINE !== "online") { try { api().voice_speaking(on); } catch (_) {} }
}
// 预加载离线引擎模型（首次会下载，可能几十秒）；返回是否就绪
async function prepareVoice() {
  if (REC_ENGINE === "online") { voiceReady = true; return true; }
  try { const r = await api().voice_prepare(); voiceReady = !!(r && r.ready); return voiceReady; }
  catch (_) { voiceReady = false; return false; }
}
const MIC_ERR = {
  "not-allowed": "麦克风没授权 —— 弹出权限请求时点「允许」再试",
  "service-not-allowed": "麦克风被系统/内核拦了 —— 去允许麦克风权限",
  "no-speech": "没听到声音，再说一次？",
  "audio-capture": "找不到麦克风设备，检查一下麦克风",
  "aborted": "语音输入被中断了",
  "network": "语音识别要联网识别(走 Google)，这个内核常连不上 —— 先打字吧",
};
const confOf = (alt) => (typeof alt.confidence === "number" && alt.confidence > 0 ? alt.confidence : 0.5);
function stopMic() { recording = false; $("#mic").classList.remove("rec"); micRecs.forEach((r) => { try { r.abort(); } catch (_) {} }); micRecs = []; }
function toggleMic() {
  if (!micEnabled) { toast("语音输入已在设置里关闭", true); return; }
  if (recording) { stopMic(); return; }
  if (REC_ENGINE === "online") micOnline(); else micOffline();
}
// 在线：浏览器内核语音识别（走 Google，需 VPN），双语并行取置信度高的
function micOnline() {
  const SR = SR_CTOR();
  if (!SR) { toast("Voice input isn't available in this build yet — type for now", true); return; }
  const langs = recogLangs();
  let best = { txt: "", conf: -1 }, pending = langs.length, lastErr = "", done = false;
  const finish = () => {
    if (done) return; done = true; stopMic();
    if (best.txt) { input.value = best.txt; doSend(); }
    else if (lastErr) toast(MIC_ERR[lastErr] || ("语音出错：" + lastErr), true);
  };
  micRecs = langs.map((lang) => {
    const r = new SR(); r.lang = lang; r.interimResults = false; r.maxAlternatives = 1;
    r.onresult = (e) => {
      const alt = e.results[0][0], conf = confOf(alt);
      if (alt.transcript && conf > best.conf) best = { txt: alt.transcript.trim(), conf };
    };
    r.onerror = (e) => { lastErr = (e && e.error) || lastErr; };
    r.onend = () => { if (--pending <= 0) finish(); };
    return r;
  });
  micRecs.forEach((r) => { try { r.start(); } catch (_) {} });
  recording = true; $("#mic").classList.add("rec");
  setTimeout(() => { if (recording && !done) finish(); }, 12000);   // 兜底：12s 还没收尾就强行结束
}
// 离线：后端本地识别（Vosk·中文），点一下说话，停顿即结束
async function micOffline() {
  recording = true; $("#mic").classList.add("rec");
  if (!voiceReady) { toast("正在加载本地识别模型…"); await prepareVoice(); }
  if (!recording) return;                          // 期间又点了一下取消
  let r;
  try { r = await api().voice_listen(8000, 1500); } catch (_) { r = {}; }
  recording = false; $("#mic").classList.remove("rec");
  const t = (r && r.text || "").trim();
  if (t) { input.value = t; doSend(); } else toast("没听清，再说一次？", true);
}

// 单句出声（唤醒问候用）：合成 → 在 voice 元素上播完再 resolve，期间标记 __voicing 抑制唤醒自激
async function speakOnce(text) {
  let r;
  try { r = await api().speak(text); } catch (_) { return; }
  if (!r || !r.ok || !r.voice) return;
  setVoicing(true); musicEl.volume = state.vol * 0.2; refreshMiniLive();
  try {
    await new Promise((resolve) => {
      voice.onended = resolve; voice.onerror = resolve;
      voice.src = r.voice; voice.play().catch(resolve);
    });
  } finally {
    setVoicing(false); musicEl.volume = state.vol; refreshMiniLive();
  }
}

/* ================= 迷你态语音唤醒 ================= */
// 迷你态常驻监听唤醒词；听到后回一句 "I'm here / Yes?"，待机 5s 等你开口，
// 你说话停顿满 2s 视为说完 → 走正常对话(出声回应)，然后回到唤醒待命。
const wake = (() => {
  const STANDBY_MS = 5000;   // 唤醒后等用户开口的时间
  const GAP_MS = 2000;       // 说话停顿多久算说完
  const SETTLE_MS = 350;     // 念完问候到开始收音的缓冲，躲开自己尾音
  const GREETS = ["I'm here", "Yes?"];

  let words = [];            // 归一化后的唤醒词列表
  let busy = false;          // 正处理一次唤醒（问候+收音+回应），防重入

  // —— 在线（Web Speech，走 Google）——
  let recs = [], onlineOn = false, phase = "off", standbyT = 0, gapT = 0, cand = {};
  // —— 离线（后端 Vosk·中文）——
  let offlineOn = false;

  const norm = (s) => (s || "").toLowerCase().replace(/[\s，。！？、,.!?~·]+/g, "");
  const greet = () => GREETS[Math.floor(Math.random() * GREETS.length)];
  function setWords(raw) { words = (raw || "").split(/[,，]/).map(norm).filter(Boolean); refresh(); }
  function clearTimers() { clearTimeout(standbyT); clearTimeout(gapT); standbyT = gapT = 0; }
  function setListenUI(a) { const av = $("#mini-avatar"); if (av) av.classList.toggle("listening", a); }
  function miniSay(t) { const cap = $("#mini-caption"); if (cap) cap.textContent = t || ""; }

  function shouldRun() { return _mini && micEnabled && words.length > 0; }
  function refresh() {
    if (!shouldRun()) { stopAll(); return; }
    if (REC_ENGINE === "online") { stopOffline(); startOnline(); }
    else { stopOnline(); startOffline(); }
  }
  function stopAll() { stopOnline(); stopOffline(); busy = false; setListenUI(false); }

  /* ---- 在线：浏览器内核语音识别（需 VPN），双语并行取置信度高的 ---- */
  function bestCand() { let b = { txt: "", conf: -1 }; for (const k in cand) if (cand[k].conf > b.conf) b = cand[k]; return b.txt; }
  function ensureRecs() {
    if (recs.length) return;
    recs = recogLangs().map((lang) => {
      const r = new (SR_CTOR())();
      r.lang = lang; r.continuous = true; r.interimResults = true; r.maxAlternatives = 1;
      r.onresult = (e) => onResult(e, lang);
      r.onerror = (e) => { const err = e && e.error; if (err === "not-allowed" || err === "service-not-allowed") { onlineOn = false; phase = "off"; setListenUI(false); } };
      r.onend = () => { if (onlineOn) setTimeout(() => { if (onlineOn) { try { r.start(); } catch (_) {} } }, 250); };
      return r;
    });
  }
  function startOnline() {
    if (onlineOn || !SR_CTOR()) return;
    onlineOn = true; phase = "wake"; ensureRecs();
    recs.forEach((r) => { try { r.start(); } catch (_) {} });
  }
  function stopOnline() {
    onlineOn = false; phase = "off"; clearTimers();
    recs.forEach((r) => { try { r.abort(); } catch (_) {} });
    recs = [];   // 清掉，下次按当前识别语言重建
  }
  function onResult(e, lang) {
    if (!onlineOn || window.__voicing) return;   // Dsdio 正在说话时不收音
    let interim = "", finalTxt = "", conf = 0;
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) { finalTxt += r[0].transcript; conf += confOf(r[0]); }
      else interim += r[0].transcript;
    }
    if (phase === "wake") {
      const n = norm(finalTxt || interim);
      if (n && words.some((w) => n.includes(w))) triggerOnline();
    } else if (phase === "await" || phase === "listen") {
      const t = (finalTxt || interim).trim();
      if (!t) return;
      if (phase === "await") { phase = "listen"; clearTimeout(standbyT); standbyT = 0; }
      if (finalTxt) { const c = cand[lang] || { txt: "", conf: 0 }; cand[lang] = { txt: (c.txt + finalTxt).trim(), conf: c.conf + conf }; }
      clearTimeout(gapT); gapT = setTimeout(finishOnline, GAP_MS);
      miniSay((bestCand() + " " + interim).trim());
    }
  }
  async function triggerOnline() {
    phase = "greet"; clearTimers(); cand = {}; setListenUI(true);
    const g = greet(); miniSay(g);
    await speakOnce(g);
    if (!onlineOn) { setListenUI(false); return; }
    await sleep(SETTLE_MS);
    if (!onlineOn) { setListenUI(false); return; }
    phase = "await"; miniSay("听着呢…");
    standbyT = setTimeout(() => { if (phase === "await") { phase = "wake"; setListenUI(false); miniSay(""); } }, STANDBY_MS);
  }
  function finishOnline() {
    const text = bestCand().trim();
    phase = "wake"; clearTimers(); setListenUI(false); cand = {};
    if (text) { input.value = text; doSend(); } else miniSay("");
  }

  /* ---- 离线：后端本地识别（免 VPN）。唤醒检测 + 收音都在 Python，前端只管念问候/起对话 ---- */
  async function startOffline() {
    if (offlineOn) return;
    offlineOn = true;
    if (!voiceReady) {
      miniSay("加载识别模型…");
      const ok = await prepareVoice();
      if (!offlineOn) return;            // 期间退出了迷你
      miniSay("");
      if (!ok) { toast("本地识别模型没装好，先用在线或打字", true); offlineOn = false; return; }
    }
    try { await api().voice_wake_start(); } catch (_) {}
  }
  function stopOffline() {
    if (!offlineOn) return;
    offlineOn = false;
    try { api().voice_wake_stop(); } catch (_) {}
  }
  // Python 命中唤醒词时回调（监听已自动暂停，等我们念问候 + 收指令 + 回应后再 resume）
  async function onWake() {
    if (busy || !offlineOn) { try { api().voice_wake_resume(); } catch (_) {} return; }
    busy = true;
    setListenUI(true);
    const g = greet(); miniSay(g); await speakOnce(g);
    if (offlineOn) {
      await sleep(SETTLE_MS);
      miniSay("听着呢…");
      let r;
      try { r = await api().voice_listen(STANDBY_MS, GAP_MS); } catch (_) { r = {}; }
      miniSay("");
      const text = (r && r.text || "").trim();
      if (text && offlineOn) { input.value = text; doSend(); }   // 回应播放时 speaking 标记让监听丢弃自己的声音
    }
    setListenUI(false);
    busy = false;
    try { await api().voice_wake_resume(); } catch (_) {}   // 重新开始监听唤醒
  }

  return { refresh, stop: stopAll, setWords, onWake };
})();
window.dsdioOnWake = function () { wake.onWake(); };

/* ================= Settings ================= */
function openSettings() { $("#settings").classList.remove("hidden"); galaxy.start(); loadSettings(); }
function closeSettings() { $("#settings").classList.add("hidden"); galaxy.stop(); }
async function loadSettings() {
  const st = await api().get_state();
  const s = st.settings;
  applyHostName(st.host);
  $("#host-name").value = s.host_name || "";
  const list = $("#persona-list"); list.innerHTML = "";
  st.personas.forEach((p) => {
    const row = document.createElement("label");
    row.className = "persona" + (p.id === s.persona ? " sel" : "");
    row.innerHTML = `<input type="radio" name="persona" value="${p.id}" ${p.id === s.persona ? "checked" : ""}/><span class="pname">${p.name}</span><button class="try" data-id="${p.id}">▶</button>`;
    list.appendChild(row);
  });
  list.querySelectorAll('input[name="persona"]').forEach((r) => r.addEventListener("change", () => {
    list.querySelectorAll(".persona").forEach((el) => el.classList.remove("sel"));
    r.closest(".persona").classList.add("sel");
  }));
  list.querySelectorAll(".try").forEach((b) => b.addEventListener("click", async (e) => {
    e.preventDefault(); b.textContent = "…";
    const r = await api().preview_voice(b.dataset.id); b.textContent = "▶";
    if (r.ok) { const a = new Audio(r.audio); a.play().catch(() => {}); } else toast(r.error || "Preview failed", true);
  }));
  $("#user-name").value = s.user_name || "";
  $("#rate").value = s.rate; $("#rate-val").textContent = s.rate + "%";
  $("#vol").value = Math.round(s.volume * 100); $("#vol-val").textContent = Math.round(s.volume * 100) + "%";
  $("#mic-toggle").checked = s.mic_enabled !== false; applyMicState(s.mic_enabled !== false);
  $("#wake-word").value = s.wake_word || ""; wake.setWords(s.wake_word || "");
  REC_LANG = s.recog_lang === "en" ? "en" : "zh";   // both/whisper 时代的旧值统一归到中文
  document.querySelectorAll("#reclang-seg button").forEach((b) => b.classList.toggle("on", b.dataset.lang === REC_LANG));
  REC_ENGINE = s.recog_engine === "online" ? "online" : "sensevoice";  // 非 online 一律按默认离线引擎
  document.querySelectorAll("#recengine-seg button").forEach((b) => b.classList.toggle("on", b.dataset.engine === REC_ENGINE));
  syncRecLangUI();
  document.querySelectorAll("#engine-seg button").forEach((b) => b.classList.toggle("on", b.dataset.engine === (s.tts_engine || "edge")));
  const hint = $("#key-hint");
  hint.textContent = st.has_key ? "Configured ✓" : "Not set — paste your key and save";
  hint.className = "hint " + (st.has_key ? "ok" : "warn");
  $("#api-key").value = "";
  $("#weather-city").value = s.weather_city || "";
  $("#weather-country").value = s.weather_country || "";
  $("#weather-key").value = "";
  const wh = $("#weather-hint");
  wh.textContent = st.has_weather_key ? "天气已配置 ✓" : "未配置（填 OpenWeather key）";
  wh.className = "hint " + (st.has_weather_key ? "ok" : "warn");
  $("#autostart-toggle").checked = !!st.autostart;
}
async function saveSettings() {
  const persona = (document.querySelector('input[name="persona"]:checked') || {}).value;
  state.vol = Number($("#vol").value) / 100;
  musicEl.volume = state.vol;
  const patch = { persona, rate: Number($("#rate").value), volume: state.vol, host_name: $("#host-name").value.trim(), user_name: $("#user-name").value.trim(), wake_word: $("#wake-word").value.trim(), weather_city: $("#weather-city").value.trim(), weather_country: $("#weather-country").value.trim().toUpperCase() };
  const wkey = $("#weather-key").value.trim();
  if (wkey) patch.weather_key = wkey;
  const st = await api().save_settings(patch);
  applyHostName(st.host);
  wake.setWords(patch.wake_word);   // 改了唤醒词立刻生效（若正处迷你态会按需重起监听）
  const key = $("#api-key").value.trim();
  if (key) await api().set_api_key(key);
  toast("Settings saved");
  closeSettings();
  loadWeather();
}

/* ================= 迷你停靠态 ================= */
// 迷你态背景全透明 = 整条窗鼠标穿透，点不回来；还原靠全局热键 Ctrl+Alt+D（后端 toggle_mini）。
let _mini = false;
function _applyMini(on) {
  _mini = on;
  document.body.classList.toggle("mini", on);
  if (on) {
    refreshMiniLive();
    if (recording) stopMic();   // 别和唤醒抢麦克风
    wake.refresh();   // 迷你态：满足条件就起唤醒监听
  } else {
    wake.stop();      // 回完整态：停唤醒，改用打字/点麦克风
  }
}
// 供后端热键回调：同步前端布局（true=切迷你，false=切完整）
window.dsdioSetMini = function (on) { if (!!on !== _mini) _applyMini(!!on); };
async function enterMini() {
  if (_mini) return;
  _applyMini(true);                                // 先切布局，再让窗口缩小（几乎同帧）
  let r; try { r = await api().enter_mini(); } catch (_) { r = {}; }
  // 全局热键没注册上时后端不会开鼠标穿透 → 提示用户改用点头像还原（否则会以为卡死）
  if (r && r.clickthrough === false) toast("热键被占用，点头像即可还原");
}
async function exitMini() {
  if (!_mini) return;
  try { await api().exit_mini(); } catch (_) {}     // 先把窗口还原回完整尺寸
  _applyMini(false);                                // 再切回完整布局，避免一闪
}

/* ================= Bind ================= */
function bind() {
  $("#send").addEventListener("click", doSend);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") doSend(); });
  $("#mic").addEventListener("click", toggleMic);
  $("#m-play").addEventListener("click", toggleMusic);
  $("#settings-btn").addEventListener("click", openSettings);
  $("#settings-close").addEventListener("click", closeSettings);
  $("#save-settings").addEventListener("click", saveSettings);
  $("#host-name").addEventListener("input", (e) => { e.target.value = e.target.value.replace(/[^A-Za-z0-9 .'_-]/g, ""); });
  $("#autostart-toggle").addEventListener("change", async (e) => {
    const on = e.target.checked;
    let r; try { r = await api().set_autostart(on); } catch (_) { r = { ok: false }; }
    if (!r.ok) { e.target.checked = !on; toast("设置开机自启失败", true); return; }
    toast(on ? "已设为开机自启" : "已取消开机自启");
  });
  $("#rate").addEventListener("input", (e) => ($("#rate-val").textContent = e.target.value + "%"));
  $("#vol").addEventListener("input", (e) => { $("#vol-val").textContent = e.target.value + "%"; state.vol = Number(e.target.value) / 100; musicEl.volume = state.vol; });
  $("#mic-toggle").addEventListener("change", (e) => { const on = e.target.checked; applyMicState(on); wake.refresh(); api().save_settings({ mic_enabled: on }); toast(on ? "麦克风已开启" : "麦克风已关闭"); });
  document.querySelectorAll("#engine-seg button").forEach((b) => b.addEventListener("click", () => {
    const eng = b.dataset.engine;
    document.querySelectorAll("#engine-seg button").forEach((x) => x.classList.toggle("on", x === b));
    api().save_settings({ tts_engine: eng });
    toast(eng === "kokoro" ? "已切到 Kokoro（首次约 3 秒加载模型）" : "已切到 edge-tts");
  }));
  document.querySelectorAll("#reclang-seg button").forEach((b) => b.addEventListener("click", () => {
    REC_LANG = b.dataset.lang;
    document.querySelectorAll("#reclang-seg button").forEach((x) => x.classList.toggle("on", x === b));
    api().save_settings({ recog_lang: REC_LANG });
    wake.refresh();
    toast(REC_LANG === "en" ? "识别：English（仅在线引擎）" : "识别：中文");
  }));
  document.querySelectorAll("#recengine-seg button").forEach((b) => b.addEventListener("click", () => {
    REC_ENGINE = b.dataset.engine;
    document.querySelectorAll("#recengine-seg button").forEach((x) => x.classList.toggle("on", x === b));
    api().save_settings({ recog_engine: REC_ENGINE });
    voiceReady = false;
    if (REC_ENGINE === "online") { toast("已切到在线识别（需 VPN，最准）"); }
    else { toast("正在准备本地识别模型…"); prepareVoice().then((ok) => toast(ok ? "本地识别已就绪 ✓" : "模型未就绪，检查网络或重试", !ok)); }
    syncRecLangUI();
    wake.refresh();
  }));
  $("#btn-min").addEventListener("click", enterMini);
  $("#mini-avatar").addEventListener("click", exitMini);
  $("#btn-close").addEventListener("click", () => api().close());
  $("#btn-top").addEventListener("click", async () => { const r = await api().toggle_top(); $("#btn-top").classList.toggle("active", r.on_top); });
}

// 开机定制：按时间+天气生成歌单并自动播放（开场白逐句念，念完起歌单）
async function startupMix() {
  const ph = addHostMsg("", true);
  const gen = ++voiceGen;
  const ctx = (respCtx = { gen, el: ph.el, body: ph.body, queue: [], playing: false, ended: false, started: false });
  let res;
  try { res = await api().startup_mix(gen); }   // 同上：传 gen 统一前后端代号
  catch (_) { res = { ok: false }; }
  ph.el.classList.remove("typing");
  if (res && res.ok && res.tracks && res.tracks.length) {
    state.radio = res.tracks.slice(); state.ri = -1; state.pendingSong = null; state.pendingPlay = true;
  }
  if (!ctx.started) ph.el.remove();   // 没生成开场白就别留空气泡
  ctx.ended = true;
  kick(ctx);                          // 有开场白先念，随后 afterVoice 起歌单
}

let _booted = false;
async function apiReady() {
  if (_booted || !(window.pywebview && window.pywebview.api)) return;
  _booted = true;
  try {
    const st = await api().get_state();
    applyHostName(st.host);
    state.vol = st.settings.volume; musicEl.volume = state.vol;
    applyMicState(st.settings.mic_enabled !== false);
    REC_LANG = st.settings.recog_lang === "en" ? "en" : "zh";
    REC_ENGINE = st.settings.recog_engine === "online" ? "online" : "sensevoice";
    syncRecLangUI();
    if (REC_ENGINE !== "online") prepareVoice();   // 后台预载离线模型，进迷你即可秒用
    wake.setWords(st.settings.wake_word || "");
    $("#onair").textContent = st.music_up ? "ON AIR" : "LATE NIGHT";
    if (!st.has_key) toast("First run — add your DeepSeek API key in Settings", true);
    loadWeather();
    setInterval(loadWeather, 15 * 60 * 1000);
    startupMix();   // 开机自动出歌单 + 播放
  } catch (_) { /* ignore */ }
}

// UI works immediately — does NOT wait on the Python bridge / pywebviewready
function renderClock() {
  const d = new Date(), p = (n) => String(n).padStart(2, "0");
  const wk = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"][d.getDay()];
  $("#dt").textContent = `${wk} ${p(d.getMonth() + 1)}.${p(d.getDate())} · ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
async function loadWeather() {
  try {
    const w = await api().weather();
    $("#wx").textContent = (w && w.ok) ? `${w.emoji} ${w.temp}° ${w.desc}${w.city ? " · " + w.city : ""}` : "";
  } catch (_) { $("#wx").textContent = ""; }
}

updateMusicBtn();
bind();
initFX();
initViz("#viz", 36);
initViz("#mini-viz", 22);   // 迷你停靠条里的律动
renderClock();
setInterval(renderClock, 1000);
// 开机问候由 startupMix() 现场生成并念出（按时间 + 天气 + 你的名字），不再放固定自我介绍。

// API-dependent bits: listen for the event AND poll, whichever wins first
window.addEventListener("pywebviewready", apiReady);
(function waitApi(n) { if (_booted) return; if (window.pywebview && window.pywebview.api) apiReady(); else if (n < 40) setTimeout(() => waitApi(n + 1), 150); })(0);
