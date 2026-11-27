// ASHFALL — screen-side game: menus, fight simulation, finishers, rendering.
'use strict';
(() => {
  const cv = document.getElementById('c'), g = cv.getContext('2d');
  const W = 1280, H = 720, GY = 612, XMIN = 70, XMAX = W - 70, GRAV = 0.85, JUMP = 17;
  const FONT = "Impact, 'Arial Black', 'Helvetica Neue', sans-serif";
  const PCOL = ['#ff5340', '#4aa8ff'];
  const rnd = (a, b) => a + Math.random() * (b - a);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  // ------------------------------------------------------------------ state
  const P = [0, 1].map((s) => ({ joined: false, pad: false, kb: false, sel: s ? 2 : 0, locked: false, wins: 0 }));
  const inp = [0, 1].map(() => ({ cur: 0, latch: 0, bits: 0, prev: 0, kb: 0 }));
  const G = { phase: 'lobby', sub: '', t: 0, time: 0, round: 1, timer: 90, f: [], projs: [], traps: [], parts: [], shake: 0, hitstop: 0, slow: 0, stage: 0, banner: null, cine: null, flash: 0, winner: -1 };
  const uiState = [null, null];

  // ------------------------------------------------------------------ network
  let ws = null, room = '', padURL = '', qr = null;
  try { room = sessionStorage.getItem('ashfall-room') || ''; } catch (e) { /* private mode */ }
  function connect() {
    ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws?role=screen&room=' + room);
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.t === 'room') {
        room = m.code;
        try { sessionStorage.setItem('ashfall-room', room); } catch (err) { /* ignore */ }
        const local = /^(localhost|127\.|\[::1\])/.test(location.hostname);
        const host = local && m.ips[0] ? m.ips[0] + ':' + m.port : location.host;
        padURL = location.protocol + '//' + host + '/pad?r=' + room;
        qr = qrMatrix(padURL);
      } else if (m.t === 'join') { P[m.s].pad = true; setJoined(m.s); if (uiState[m.s]) toPad(m.s, uiState[m.s]); SFX.play('ok'); }
      else if (m.t === 'leave') { P[m.s].pad = false; inp[m.s].cur = 0; setJoined(m.s); }
      else if (m.t === 'i') { const b = m.d.b | 0; inp[m.s].latch |= b; inp[m.s].cur = b; }
    };
    ws.onclose = () => { P.forEach((p, s) => { p.pad = false; setJoined(s); }); setTimeout(connect, 1000); };
  }
  function toPad(s, obj) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(Object.assign({ to: s }, obj))); }
  function ui(s, title, sub) {
    const m = { t: 'ui', title, sub: sub || '' };
    uiState[s] = m; toPad(s, m);
  }
  function setJoined(s) {
    P[s].joined = P[s].pad || P[s].kb;
    if (!P[s].joined) P[s].locked = false;
    refreshUI();
  }

  // ------------------------------------------------------------------ keyboard (testing / fallback)
  const KEYS = [
    { KeyA: 1, KeyD: 2, KeyW: 4, KeyS: 8, KeyF: 16, KeyG: 32, KeyH: 64, KeyJ: 128 },
    { ArrowLeft: 1, ArrowRight: 2, ArrowUp: 4, ArrowDown: 8, KeyM: 16, Comma: 32, Period: 64, Slash: 128 },
  ];
  function key(e, on) {
    SFX.unlock();
    for (let s = 0; s < 2; s++) {
      const b = KEYS[s][e.code];
      if (!b) continue;
      e.preventDefault();
      if (!P[s].kb) { P[s].kb = true; setJoined(s); }
      if (on) { inp[s].kb |= b; inp[s].latch |= b; } else inp[s].kb &= ~b;
    }
  }
  addEventListener('keydown', (e) => { if (!e.repeat) key(e, true); });
  addEventListener('keyup', (e) => key(e, false));
  addEventListener('pointerdown', () => SFX.unlock());

  function sampleInput() {
    for (const i of inp) { i.prev = i.bits; i.bits = i.cur | i.kb | i.latch; i.latch = 0; }
  }
  const pressed = (s, b) => P[s].joined && (inp[s].bits & b) && !(inp[s].prev & b);
  const anyPressed = (b) => pressed(0, b) || pressed(1, b);

  // ------------------------------------------------------------------ phone UI text
  const GLYPH = { 4: '↑', 8: '↓', 16: 'PUNCH', 32: 'KICK', 128: 'SPECIAL' };
  const seqText = (ch) => ch.fin.seq.map((b) => GLYPH[b]).join('   ');
  function refreshUI() {
    for (let s = 0; s < 2; s++) {
      const f = G.f[s];
      if (G.phase === 'lobby') ui(s, 'PLAYER ' + (s + 1) + ' READY', 'Press PUNCH to start');
      else if (G.phase === 'select') ui(s, P[s].locked ? ROSTER[P[s].sel].name + ' LOCKED IN' : 'PICK YOUR FIGHTER', P[s].locked ? 'KICK = change' : 'Stick = move · PUNCH = lock in');
      else if (G.phase === 'vs') ui(s, ROSTER[P[s].sel].name, 'Get ready…');
      else if (G.sub === 'finish' && f) ui(s, G.winner === s ? 'END IT!   ' + seqText(f.ch) : '…', G.winner === s ? 'Enter the finisher now' : 'This is going to hurt');
      else if (G.sub === 'over') ui(s, G.winner === s ? 'VICTORY' : 'DEFEATED', 'PUNCH = play again');
      else if (f) ui(s, f.ch.name, 'SPECIAL: ' + f.ch.sp[0].name + ' · ↓+SPECIAL: ' + f.ch.sp[1].name);
    }
  }

  // ------------------------------------------------------------------ particles
  function part(x, y, vx, vy, life, col, size, grav, glow) {
    if (G.parts.length > 500) G.parts.shift();
    G.parts.push({ x, y, vx, vy, life, max: life, col, size, grav: grav == null ? 0.3 : grav, glow });
  }
  function burst(x, y, n, col, spd, life, size, grav, glow) {
    for (let i = 0; i < n; i++) { const a = rnd(0, 6.283), v = rnd(spd * 0.3, spd); part(x, y, Math.cos(a) * v, Math.sin(a) * v, rnd(life * 0.5, life), col, rnd(size * 0.5, size), grav, glow); }
  }
  function stepParts() {
    for (let i = G.parts.length - 1; i >= 0; i--) {
      const p = G.parts[i];
      p.vy += p.grav; p.x += p.vx; p.y += p.vy;
      if (p.y > GY + 6 && p.grav > 0) { p.y = GY + 6; p.vy *= -0.3; p.vx *= 0.6; }
      if (--p.life <= 0) G.parts.splice(i, 1);
    }
  }
  function banner(text, sub, dur, col) { G.banner = { text, sub, t: 0, dur: dur || 90, col: col || '#fff' }; }

  // ------------------------------------------------------------------ fighters
  function newFighter(slot) {
    return { slot, ch: ROSTER[P[slot].sel], x: W / 2 + (slot ? 230 : -230), y: GY, vx: 0, vy: 0, face: slot ? -1 : 1, hp: 100, ghost: 100, state: 'idle', t: 0, dur: 0, mv: null, hitDone: false, cd: 0, combo: 0, comboT: 0, jug: 0, inv: 0, blocking: false, crouching: false, hitLow: false, pose: POSES.idle.slice(), flash: 0, fx: {}, buf: 0, bufT: 0, pb: 0, seq: [], airAct: false, diving: false, armorHit: false, tgt: 'idle', ai: null, hurtAny: false };
  }
  const opp = (f) => G.f[1 - f.slot];
  const grounded = (f) => f.y >= GY && f.vy >= 0;
  const isCrouch = (f) => f.state === 'crouch' || (f.state === 'block' && f.crouching) || (f.state === 'stun' && f.blocking && f.crouching) || (f.state === 'atk' && f.mv.low && (f.mv.low === 2 || f.t <= f.mv.su)) || f.state === 'recover';

  function hurtbox(f) {
    if (f.inv > 0 || f.state === 'down' || f.state === 'getup' || f.state === 'frozen' || f.fx.alpha === 0) return null;
    if (f.state === 'atk' && f.mv.kind === 'tele') return null;
    if (!grounded(f)) return { l: f.x - 28, r: f.x + 28, t: f.y - 170, b: f.y - 20 };
    return { l: f.x - 28, r: f.x + 28, t: f.y - (isCrouch(f) ? 118 : 182 * f.ch.tall), b: f.y };
  }
  function startMove(f, m) {
    f.state = 'atk'; f.mv = m; f.t = 0; f.hitDone = false; f.diving = false; f.armorHit = false;
    if (grounded(f)) f.vx = 0;
    if (m.sp) f.cd = m.cd || 90;
    if (!m.sp) SFX.play('whoosh');
  }
  function setStun(f, dur, blocking) { f.state = 'stun'; f.t = 0; f.dur = dur; f.blocking = blocking; f.mv = null; f.fx.alpha = null; }

  function applyHit(att, def, m, srcX) {
    if (G.sub !== 'play' && G.sub !== 'finish') return false;
    const dir = Math.sign(def.x - srcX) || att.face;
    const cx = (def.x + srcX) / 2 + dir * 20, cy = def.y + (m.ry ? (m.ry[0] + m.ry[1]) / 2 : m.pr ? m.pr.y : -40);
    const dz = def.state === 'dizzy';
    const canBlock = !dz && (def.pb & BIT.BL) && grounded(def) && (def.state === 'idle' || def.state === 'walk' || def.state === 'crouch' || def.state === 'block' || (def.state === 'stun' && def.blocking));
    const cr = !!(def.pb & BIT.D);
    if (canBlock && (m.lvl === 'low' ? cr : m.lvl === 'over' ? !cr : true)) {
      def.crouching = cr;
      setStun(def, Math.round((m.stun || 20) * 0.6), true);
      def.vx = dir * (m.kb || 6) * 0.8;
      if (m.sp) { def.hp = Math.max(1, def.hp - Math.ceil(m.dmg * 0.2)); }
      burst(cx, cy, 8, '#bfe3ff', 6, 14, 4, 0.1, true);
      SFX.play('block');
      G.hitstop = 3;
      return true;
    }
    if (def.state === 'atk' && def.mv.armor && def.t > 4 && !def.armorHit && !m.heavy) {
      def.armorHit = true; def.hp = Math.max(1, def.hp - m.dmg * 0.6); def.flash = 6;
      burst(cx, cy, 8, '#ffd9a0', 6, 14, 4, 0.2, true); SFX.play('block'); G.hitstop = 4;
      return true;
    }
    const comboing = (def.state === 'stun' && !def.blocking) || def.state === 'fall';
    att.combo = comboing ? att.combo + 1 : 1;
    att.comboT = 80;
    const dmg = m.dmg * Math.max(0.4, 1 - 0.12 * (att.combo - 1)) * def.ch.def;
    def.hp -= dmg;
    def.flash = 7; def.fx.alpha = null;
    G.hitstop = Math.min(12, 4 + Math.round(dmg / 2));
    G.shake = Math.max(G.shake, m.heavy || m.launch ? 12 : 6);
    burst(cx, cy, 10, '#fff2c0', 8, 14, 5, 0.1, true);
    burst(cx, cy, m.heavy ? 14 : 7, '#b3121c', 7, 34, 5, 0.45);
    SFX.play(m.heavy || dmg >= 11 ? 'heavy' : 'hit');
    if (dz) { def.hp = 0; def.state = 'fall'; def.t = 0; def.vx = dir * 6; def.vy = -9; return true; }
    if (def.hp <= 0) {
      def.hp = 0;
      if (onKO(att, def)) return true;
    }
    if (!grounded(def) || m.launch || def.hp <= 0) {
      def.state = 'fall'; def.t = 0; def.mv = null;
      def.vx = dir * (m.launch ? m.launch[0] : 5); def.vy = m.launch ? m.launch[1] : -8;
      if (def.hp <= 0) { def.vx = dir * 8; def.vy = Math.min(def.vy, -11); }
      if (def.y >= GY) def.y = GY - 1;
      if (++def.jug > 3) def.inv = 999;
    } else {
      def.hitLow = m.lvl === 'low' || cy > def.y - 100;
      setStun(def, m.stun || 16, false);
      def.vx = dir * (m.kb || 5);
    }
    return true;
  }

  // Returns true if the defender was put into the "finish them" daze instead of a normal knockout.
  function onKO(att, def) {
    if (G.sub !== 'play') return false;
    P[att.slot].wins++;
    G.winner = att.slot;
    G.t = 0;
    G.projs.length = 0; G.traps.length = 0;
    SFX.play('ko');
    if (P[att.slot].wins >= 2) {
      G.sub = 'finish';
      def.state = 'dizzy'; def.t = 0; def.vx = 0; def.vy = 0; def.y = GY; def.mv = null;
      att.seq = [];
      banner('END IT!', '', 110, '#ff3b2f');
      SFX.say('End it!'); SFX.music(false);
      refreshUI();
      return true;
    }
    G.sub = 'ko'; G.slow = 54;
    banner('K.O.', att.ch.name + ' takes round ' + G.round, 130, '#ffcf5a');
    SFX.say('Knockout');
    return false;
  }

  function control(f, o, bits, pr) {
    const act = pr & (BIT.P | BIT.K | BIT.S);
    if (act) { f.buf = act; f.bufT = 8; }
    if (f.bufT > 0) f.bufT--; else f.buf = 0;
    const s = f.state;
    if (s === 'idle' || s === 'walk' || s === 'crouch' || s === 'block') {
      f.face = o.x >= f.x ? 1 : -1;
      const down = bits & BIT.D;
      if ((f.buf & BIT.S) && f.cd <= 0) { startMove(f, f.ch.sp[down ? 1 : 0]); f.buf = 0; }
      else if (f.buf & BIT.P) { startMove(f, down ? MOVES.upper : MOVES.punch); f.buf = 0; }
      else if (f.buf & BIT.K) { startMove(f, down ? MOVES.sweep : MOVES.kick); f.buf = 0; }
      else if (bits & BIT.BL) { f.state = 'block'; f.crouching = !!down; f.vx = 0; }
      else if (bits & BIT.U) {
        f.state = 'jump'; f.t = 0; f.vy = -JUMP; f.airAct = false;
        f.vx = ((bits & BIT.R ? 1 : 0) - (bits & BIT.L ? 1 : 0)) * f.ch.speed * 1.4;
        SFX.play('jump');
      } else if (down) { f.state = 'crouch'; f.vx = 0; }
      else {
        const d = (bits & BIT.R ? 1 : 0) - (bits & BIT.L ? 1 : 0);
        f.state = d ? 'walk' : 'idle';
        f.vx = d * f.ch.speed * (d === f.face ? 1 : 0.8);
      }
    } else if (s === 'jump' && !f.airAct && (f.buf & (BIT.P | BIT.K))) {
      startMove(f, f.buf & BIT.P ? MOVES.airP : MOVES.airK); f.buf = 0; f.airAct = true;
    }
  }

  function tryHit(f, o, m) {
    if (f.hitDone) return;
    const ub = hurtbox(o);
    if (!ub) return;
    const x0 = f.x + f.face * m.rx[0], x1 = f.x + f.face * m.rx[1];
    const l = Math.min(x0, x1), r = Math.max(x0, x1), t = f.y + m.ry[0], b = f.y + m.ry[1];
    if (l < ub.r && r > ub.l && t < ub.b && b > ub.t) { f.hitDone = true; applyHit(f, o, m, f.x); }
  }
  function trail(f, kind) {
    if (kind === 'fire') part(f.x - f.face * 20, f.y - rnd(40, 150), -f.face * rnd(1, 4), rnd(-2, 0), 20, Math.random() < 0.5 ? '#ff7a1a' : '#ffd35e', 9, -0.1, true);
    else if (kind === 'dust') part(f.x - f.face * 20, GY - rnd(0, 20), -f.face * rnd(1, 4), rnd(-3, 0), 24, '#9c8f7e', 9, 0.05);
    else if (kind === 'spark') part(f.x + rnd(-30, 30), f.y - rnd(40, 190), rnd(-3, 3), rnd(-3, 3), 12, '#9fe8ff', 5, 0, true);
    else if (kind === 'wind') part(f.x - f.face * 10, f.y - rnd(20, 120), -f.face * rnd(2, 6), rnd(-1, 1), 14, '#b8fff2', 5, 0, true);
  }
  const endMove = (f) => { f.state = 'idle'; f.mv = null; f.fx.alpha = null; };

  function stepMove(f, o) {
    const m = f.mv, t = f.t;
    if (t === 1 && m.sp && m.snd) SFX.play(m.snd);
    switch (m.kind) {
      case 'proj': case 'quake':
        if (t === m.su) {
          const pr = m.pr;
          G.projs.push({ x: f.x + f.face * 55, y: f.y + pr.y, y0: f.y + pr.y, vx: f.face * pr.vx, w: pr.w, h: pr.h, own: f.slot, m, type: pr.type, wave: pr.wave, t: 0 });
          if (m.kind === 'quake') { G.shake = 10; burst(f.x + f.face * 30, GY, 10, '#9c8f7e', 6, 20, 7, 0.3); }
        }
        if (t >= m.su + m.re) endMove(f);
        break;
      case 'dash':
        if (t <= m.su) f.vx = 0;
        else if (t <= m.su + m.ac) { f.vx = f.face * m.spd; tryHit(f, o, m); trail(f, m.trail); }
        else { f.vx *= 0.7; if (t >= m.su + m.ac + m.re) endMove(f); }
        break;
      case 'tele':
        f.fx.alpha = t < m.su ? 1 - t / m.su : (t - m.su) / m.re;
        if (t === m.su) {
          burst(f.x, f.y - 90, 14, '#9b5cff', 5, 22, 7, 0, true);
          const side = o.x > f.x ? 1 : -1;
          let nx = o.x + side * 95;
          if (nx > XMAX || nx < XMIN) nx = o.x - side * 95;
          f.x = nx; f.face = o.x >= f.x ? 1 : -1;
          burst(f.x, f.y - 90, 14, '#9b5cff', 5, 22, 7, 0, true);
        }
        if (t >= m.su + m.re) endMove(f);
        break;
      case 'rise':
        if (t === m.su) { f.vy = m.vy; f.vx = f.face * 3; }
        if (t > m.su && t <= m.su + m.ac) { tryHit(f, o, m); trail(f, m.trail); }
        break;
      case 'dive':
        if (t === m.su) { f.vy = -13; f.vx = f.face * 4; }
        if (t > m.su && !f.diving && f.vy >= -1) f.diving = true;
        if (f.diving) { f.vx = f.face * 11; f.vy = 13; tryHit(f, o, m); trail(f, m.trail); }
        break;
      case 'ground':
        if (t === m.su) G.traps.push({ x: clamp(o.x + o.vx * 8, XMIN, XMAX), t: 0, own: f.slot, m, hit: false });
        if (t >= m.su + m.re) endMove(f);
        break;
      default: // normals
        if (t > m.su && t <= m.su + m.ac) tryHit(f, o, m);
        if (!m.air && t >= m.su + m.ac + m.re) endMove(f);
    }
  }

  function land(f) {
    f.vy = 0;
    if (f.state === 'jump') { f.state = 'idle'; f.vx = 0; SFX.play('land'); }
    else if (f.state === 'atk') {
      const k = f.mv.kind;
      if (k === 'rise' || k === 'dive') { f.state = 'recover'; f.t = 0; f.dur = f.mv.re; f.vx = 0; f.mv = null; f.diving = false; }
      else if (f.mv.air) { f.state = 'idle'; f.mv = null; f.vx = 0; }
      SFX.play('land');
    } else if (f.state === 'fall') {
      f.state = 'down'; f.t = 0; f.vx *= 0.5;
      G.shake = Math.max(G.shake, 5);
      burst(f.x, GY, 8, '#8a8078', 4, 18, 7, 0.1);
      SFX.play('land');
    }
  }

  function physics(f, o) {
    if (f.inv > 0) f.inv--;
    if (f.cd > 0) f.cd--;
    if (f.flash > 0) f.flash--;
    if (f.comboT > 0 && --f.comboT === 0) f.combo = 0;
    f.ghost += (f.hp - f.ghost) * (f.ghost > f.hp ? 0.04 : 1);
    f.t++;
    const s = f.state;
    if (s === 'atk') stepMove(f, o);
    else if (s === 'stun' || s === 'recover') { f.vx *= 0.85; if (f.t >= f.dur) { f.state = 'idle'; f.blocking = false; } }
    else if (s === 'down') { f.vx *= 0.8; if (f.hp > 0 && f.t >= 38) { f.state = 'getup'; f.t = 0; } }
    else if (s === 'getup') { f.vx = 0; if (f.t >= 16) { f.state = 'idle'; f.inv = 6; f.jug = 0; } }
    else if (s === 'dizzy' || s === 'win') f.vx = 0;
    if (s === 'frozen') return;
    if (f.y < GY || f.vy < 0) {
      f.vy += GRAV; f.y += f.vy;
      if (f.y >= GY) { f.y = GY; land(f); }
    }
    f.x = clamp(f.x + f.vx, XMIN, XMAX);
  }

  function stepProjs() {
    for (let i = G.projs.length - 1; i >= 0; i--) {
      const p = G.projs[i], o = G.f[1 - p.own];
      p.t++; p.x += p.vx;
      if (p.wave) p.y = p.y0 + Math.sin(p.t * 0.15) * 26;
      let dead = p.x < -80 || p.x > W + 80;
      const ub = hurtbox(o);
      if (!dead && ub && p.x - p.w / 2 < ub.r && p.x + p.w / 2 > ub.l && p.y - p.h / 2 < ub.b && p.y + p.h / 2 > ub.t) {
        applyHit(G.f[p.own], o, p.m, p.x - p.vx * 3); dead = true;
      }
      for (let j = 0; j < i && !dead; j++) {
        const q = G.projs[j];
        if (q.own !== p.own && Math.abs(q.x - p.x) < 40 && Math.abs(q.y - p.y) < 60) {
          burst((p.x + q.x) / 2, (p.y + q.y) / 2, 16, '#ffffff', 7, 16, 5, 0, true);
          SFX.play('block'); G.projs.splice(i, 1); G.projs.splice(j, 1); i--; dead = false; p.gone = true; break;
        }
      }
      if (p.gone) continue;
      if (dead) G.projs.splice(i, 1);
    }
    for (let i = G.traps.length - 1; i >= 0; i--) {
      const tr = G.traps[i], o = G.f[1 - tr.own], d = tr.m.delay;
      tr.t++;
      if (tr.t === d) SFX.play('dark');
      if (tr.t >= d && tr.t < d + 7 && !tr.hit) {
        const ub = hurtbox(o);
        if (ub && Math.abs(o.x - tr.x) < 62 && ub.b > GY - 90) { tr.hit = true; applyHit(G.f[tr.own], o, tr.m, o.x - o.face); }
      }
      if (tr.t > d + 26) G.traps.splice(i, 1);
    }
  }

  // ------------------------------------------------------------------ CPU opponent
  function aiBits(f, o) {
    const a = f.ai || (f.ai = { t: 0, hold: 0 });
    const dx = o.x - f.x, d = Math.abs(dx), tow = dx > 0 ? BIT.R : BIT.L, awy = dx > 0 ? BIT.L : BIT.R;
    let extra = 0;
    if (f.state === 'jump' && d < 160 && f.vy > -3 && !f.airAct) extra = BIT.K;
    if (--a.t > 0) return a.hold | extra;
    const r = Math.random();
    let hold = 0, tap = 0, t = 12;
    const inc = G.projs.find((p) => p.own !== f.slot && Math.abs(p.x - f.x) < 190 && Math.sign(p.vx) === Math.sign(f.x - p.x));
    const threat = (o.state === 'atk' && d < 180 && o.t <= o.mv.su + 3) || inc;
    if (G.sub === 'finish') {
      if (G.winner !== f.slot) return 0;
      hold = d > 170 ? tow : 0; t = 8;
      if (d <= 280 && G.t > 80 && grounded(f)) { if (r < 0.7) startCine(f, o); else tap = BIT.K; }
    } else if (threat && r < 0.6) {
      const low = (o.state === 'atk' && o.mv.lvl === 'low') || (inc && inc.m.lvl === 'low');
      hold = BIT.BL | (low && Math.random() < 0.7 ? BIT.D : 0); t = 16;
    } else if (d > 430) {
      if (r < 0.3) tap = BIT.S; else if (r < 0.42) { hold = tow | BIT.U; t = 4; } else { hold = tow; t = 18; }
    } else if (d > 165) {
      if (r < 0.45) hold = tow;
      else if (r < 0.6) { hold = tow | BIT.U; t = 4; }
      else if (r < 0.75) { tap = BIT.S; hold = Math.random() < 0.4 ? BIT.D : 0; t = 10; }
      else if (r < 0.87) { hold = awy; t = 14; }
    } else if (r < 0.25) tap = BIT.P;
    else if (r < 0.47) tap = BIT.K;
    else if (r < 0.6) { hold = BIT.D; tap = BIT.K; }
    else if (r < 0.7) { hold = BIT.D; tap = BIT.P; }
    else if (r < 0.78) { hold = BIT.D; tap = BIT.S; }
    else if (r < 0.9) { hold = BIT.BL; t = 18; }
    else { hold = awy; t = 14; }
    a.hold = hold; a.t = t;
    return hold | tap | extra;
  }

  // ------------------------------------------------------------------ match flow
  function goLobby() { G.phase = 'lobby'; G.sub = ''; G.t = 0; SFX.music(false); refreshUI(); }
  function goSelect() {
    G.phase = 'select'; G.sub = ''; G.t = 0; G.f = []; G.cine = null; G.banner = null;
    P.forEach((p) => { p.locked = false; p.wins = 0; });
    SFX.music(false); SFX.say('Choose your fighter');
    refreshUI();
  }
  function goVS() {
    G.phase = 'vs'; G.t = 0;
    G.stage = Math.floor(Math.random() * 3);
    paintStage(G.stage);
    SFX.play('gong');
    SFX.say(ROSTER[P[0].sel].name + ' versus ' + ROSTER[P[1].sel].name);
    refreshUI();
  }
  function resetRound() {
    G.f = [newFighter(0), newFighter(1)];
    G.projs = []; G.traps = []; G.parts = [];
    G.timer = 90; G.sub = 'intro'; G.t = 0; G.slow = 0; G.hitstop = 0; G.winner = -1;
    banner('ROUND ' + G.round, '', 60);
    SFX.say('Round ' + G.round);
  }
  function goFight() {
    G.phase = 'fight'; G.round = 1; G.cine = null;
    resetRound(); SFX.music(true); refreshUI();
  }
  function goOver(text, sub) {
    G.sub = 'over'; G.t = 0;
    const w = G.f[G.winner];
    if (w) { w.state = 'win'; w.vx = 0; }
    banner(text, sub, 99999, '#ffcf5a');
    SFX.music(false);
    refreshUI();
  }

  function stepSelect() {
    let humans = 0, ready = 0;
    for (let s = 0; s < 2; s++) {
      const p = P[s];
      if (!p.joined) continue;
      humans++;
      if (!p.locked) {
        const col = p.sel % 3, row = (p.sel / 3) | 0;
        let nc = col, nr = row;
        if (pressed(s, BIT.L)) nc = (col + 2) % 3;
        if (pressed(s, BIT.R)) nc = (col + 1) % 3;
        if (pressed(s, BIT.U) || pressed(s, BIT.D)) nr = 1 - row;
        if (nc !== col || nr !== row) { p.sel = nr * 3 + nc; SFX.play('blip'); }
        if (pressed(s, BIT.P)) { p.locked = true; SFX.play('ok'); SFX.say(ROSTER[p.sel].name); refreshUI(); }
      } else if (pressed(s, BIT.K)) { p.locked = false; SFX.play('back'); refreshUI(); }
      if (p.locked) ready++;
    }
    if (humans && ready === humans) {
      if (++G.t > 40) {
        P.forEach((p) => { if (!p.joined) p.sel = Math.floor(Math.random() * ROSTER.length); });
        goVS();
      }
    } else G.t = 0;
    if (!humans) goLobby();
  }

  function stepFight() {
    G.t++;
    const [a, b] = G.f;
    if (G.sub === 'cine') { stepCine(); stepPoses(); return; }
    if (G.hitstop > 0) { G.hitstop--; return; }
    if (G.slow > 0 && --G.slow % 3) return;

    const live = G.sub === 'play' || G.sub === 'finish';
    for (const f of G.f) {
      const o = opp(f);
      let bits = 0;
      if (live) bits = P[f.slot].joined ? inp[f.slot].bits : aiBits(f, o);
      if (G.sub === 'cine') return; // CPU just started a finisher
      const pr = bits & ~f.pb;
      f.pb = bits;
      if (G.sub === 'finish' && G.winner === f.slot && pr) {
        for (const k of [BIT.U, BIT.D, BIT.P, BIT.K, BIT.S]) if (pr & k) f.seq.push({ b: k, t: G.t });
        f.seq = f.seq.slice(-3);
        const q = f.ch.fin.seq;
        if (f.seq.length === 3 && f.seq.every((e, i) => e.b === q[i]) && G.t - f.seq[0].t < 150 && f.state !== 'stun') { startCine(f, o); return; }
      }
      if (live && f.state !== 'dizzy') control(f, o, bits, pr);
    }
    physics(a, b); physics(b, a);
    // push apart
    const pushable = (f) => f.state !== 'down' && f.state !== 'getup' && !(f.state === 'atk' && f.mv.kind === 'tele');
    if (pushable(a) && pushable(b) && Math.abs(a.y - b.y) < 110) {
      const d = b.x - a.x, min = 58;
      if (Math.abs(d) < min) {
        const push = (min - Math.abs(d)) / 2, s = d >= 0 ? 1 : -1;
        a.x = clamp(a.x - s * push, XMIN, XMAX); b.x = clamp(b.x + s * push, XMIN, XMAX);
        if (Math.abs(b.x - a.x) < min) { if (a.x <= XMIN + 1 || a.x >= XMAX - 1) b.x = a.x + s * min; else a.x = b.x - s * min; }
      }
    }
    stepProjs();
    stepPoses();

    if (G.sub === 'intro') {
      if (G.t === 62) { banner('FIGHT!', '', 45, '#ff5340'); SFX.say('Fight!'); SFX.play('gong'); }
      if (G.t >= 100) { G.sub = 'play'; G.t = 0; }
    } else if (G.sub === 'play') {
      if (G.t % 60 === 0 && --G.timer <= 0) timeUp();
    } else if (G.sub === 'ko') {
      const w = G.f[G.winner];
      if (w && G.t > 70 && (w.state === 'idle' || w.state === 'walk' || w.state === 'crouch')) { w.state = 'win'; w.vx = 0; }
      if (G.t >= 190) {
        if (G.winner >= 0 && P[G.winner].wins >= 2) goOver(G.f[G.winner].ch.name + ' WINS', '');
        else { G.round++; resetRound(); }
      }
    } else if (G.sub === 'finish') {
      const l = G.f[1 - G.winner], w = G.f[G.winner];
      if (l.state !== 'dizzy') { if (l.state === 'down' && l.t > 50) { goOver(w.ch.name + ' WINS', ''); SFX.say(w.ch.name + ' wins'); } }
      else if (G.t > 420) { l.state = 'fall'; l.vy = -4; l.vx = 0; l.y = GY - 1; }
    } else if (G.sub === 'over') {
      if ((G.t > 100 && anyPressed(BIT.P)) || G.t > 1500) goSelect();
    }
  }

  function timeUp() {
    const [a, b] = G.f;
    G.sub = 'ko'; G.t = 0; G.projs.length = 0; G.traps.length = 0;
    if (Math.abs(a.hp - b.hp) < 0.5) { G.winner = -1; banner('DRAW', 'Replay the round', 130); G.round--; return; }
    G.winner = a.hp > b.hp ? 0 : 1;
    P[G.winner].wins++;
    banner('TIME', G.f[G.winner].ch.name + ' takes round ' + G.round, 130, '#ffcf5a');
    SFX.say('Time');
  }

  // ------------------------------------------------------------------ poses
  const mixPose = (a, b, k) => a.map((v, i) => v + (b[i] - v) * k);
  function targetPose(f) {
    switch (f.state) {
      case 'idle': return mixPose(POSES.idle, POSES.idleB, (Math.sin(G.time * 0.09 + f.slot * 2) + 1) / 2);
      case 'walk': return mixPose(POSES.walkA, POSES.walkB, (Math.sin(f.t * 0.24) + 1) / 2);
      case 'crouch': case 'getup': case 'recover': return POSES.crouch;
      case 'block': return f.crouching ? POSES.cblock : POSES.block;
      case 'jump': return POSES.jump;
      case 'atk': {
        const m = f.mv;
        if (m.kind === 'rise' || m.kind === 'dive' || m.air) return f.t <= m.su ? POSES[m.pw] : POSES[m.p];
        if (f.t <= m.su) return POSES[m.pw || m.p];
        if (f.t <= m.su + (m.ac || 8) + (m.sp ? 4 : 1)) return POSES[m.p];
        return m.low ? POSES.crouch : POSES.idle;
      }
      case 'stun': return f.blocking ? (f.crouching ? POSES.cblock : POSES.block) : f.hitLow ? POSES.hitL : POSES.hitH;
      case 'fall': return POSES.fall;
      case 'down': return POSES.down;
      case 'dizzy': { const p = POSES.dizzy.slice(); p[0] += Math.sin(G.time * 0.07) * 9; p[1] += Math.cos(G.time * 0.05) * 8; p[2] += Math.sin(G.time * 0.07) * 10; return p; }
      case 'win': return POSES.win;
      case 'frozen': return typeof f.tgt === 'string' ? POSES[f.tgt] : f.tgt;
    }
    return POSES.idle;
  }
  function stepPoses() {
    for (const f of G.f) {
      const tp = targetPose(f), k = f.state === 'atk' ? 0.55 : f.state === 'stun' ? 0.6 : 0.3;
      for (let i = 0; i < 11; i++) f.pose[i] += (tp[i] - f.pose[i]) * k;
    }
  }

  // ------------------------------------------------------------------ finishers
  const CINE_END = { ash: 235, crush: 205, slice: 235, bolt: 225, grave: 235, cyclone: 255 };
  function startCine(a, v) {
    G.sub = 'cine'; G.projs.length = 0; G.traps.length = 0; G.banner = null; G.hitstop = 0;
    a.y = GY; a.vx = a.vy = 0; a.state = 'frozen'; a.tgt = 'cast'; a.fx = {}; a.mv = null;
    a.face = v.x >= a.x ? 1 : -1;
    v.y = GY; v.vx = v.vy = 0; v.state = 'frozen'; v.tgt = POSES.dizzy; v.fx = {};
    G.cine = { type: a.ch.fin.type, t: 0, a, v, slashes: [], bolt: null, vx0: v.x };
    SFX.play('gong');
    SFX.say(a.ch.fin.name.toLowerCase());
    for (let s = 0; s < 2; s++) ui(s, a.ch.fin.name, s === a.slot ? 'Finisher!' : 'Ouch.');
  }
  function stepCine() {
    const c = G.cine, a = c.a, v = c.v, t = ++c.t, vx = v.x;
    for (const f of G.f) { if (f.flash > 0) f.flash--; f.ghost += (f.hp - f.ghost) * 0.04; }
    switch (c.type) {
      case 'ash':
        if (t >= 30 && t < 130) {
          if (t % 30 === 0) SFX.play('fire');
          v.fx.dark = (t - 30) / 95; v.tgt = POSES.hitH; G.shake = 3;
          for (let i = 0; i < 4; i++) part(vx + rnd(-45, 45), GY - rnd(0, 30), rnd(-1, 1), rnd(-9, -4), rnd(18, 34), Math.random() < 0.4 ? '#ffd35e' : '#ff5a14', rnd(6, 13), -0.05, true);
        }
        if (t === 130) {
          v.fx.hide = true; c.pile = true; SFX.play('boom'); G.shake = 14;
          for (let i = 0; i < 110; i++) part(vx + rnd(-28, 28), GY - rnd(0, 190), rnd(-2.5, 2.5), rnd(-2, 1), rnd(50, 110), Math.random() < 0.8 ? '#2b2625' : '#ff7a1a', rnd(3, 8), 0.06);
        }
        if (t === 150) a.tgt = 'win';
        break;
      case 'crush': {
        if (t === 30) { a.tgt = 'summon'; SFX.play('quake'); }
        c.by = -320 + Math.max(0, t - 40) ** 2 * 0.36;
        if (c.by >= GY - 92 && !c.hit) {
          c.hit = t; v.fx.hide = true; G.shake = 30; SFX.play('boom'); G.flash = 0.6;
          burst(vx, GY - 10, 46, '#b3121c', 15, 55, 8, 0.5);
          burst(vx, GY - 10, 30, '#8d8478', 13, 45, 10, 0.5);
        }
        if (c.hit) c.by = GY - 92;
        else if (t > 50) v.fx.sy = 1 - Math.max(0, (c.by - (GY - 330)) / 240) * 0.5;
        if (t === 125) a.tgt = 'win';
        break;
      }
      case 'slice':
        if (t >= 30 && t <= 40) a.fx.alpha = 1 - (t - 30) / 10;
        if (t === 30) SFX.play('dark');
        if (t >= 45 && t <= 93 && (t - 45) % 12 === 0) {
          c.slashes.push({ ang: rnd(-0.9, 0.9) + ((t - 45) / 12 % 2 ? 2.4 : 0), t });
          SFX.play('slash'); v.flash = 5; G.shake = 7; v.tgt = (t / 12 | 0) % 2 ? POSES.hitH : POSES.hitL;
          burst(vx, GY - 110, 10, '#b3121c', 9, 30, 5, 0.4);
        }
        if (t === 104) { a.x = clamp(vx + a.face * 150, XMIN, XMAX); a.tgt = 'punch'; a.pose = POSES.punch.slice(); }
        if (t >= 104 && t <= 112) a.fx.alpha = (t - 104) / 8;
        if (t === 136) { SFX.play('heavy'); burst(vx, GY - 100, 40, '#b3121c', 10, 50, 6, 0.45); v.tgt = POSES.hitH; }
        if (t >= 136) v.fx.split = t - 136;
        if (t === 165) a.tgt = 'win';
        break;
      case 'bolt':
        if (t === 30) a.tgt = 'summon';
        if (t >= 40 && t <= 100 && (t - 40) % 15 === 0) {
          const pts = [[vx + rnd(-140, 140), -10]];
          for (let i = 1; i <= 7; i++) pts.push([pts[0][0] + (vx - pts[0][0]) * i / 7 + (i < 7 ? rnd(-40, 40) : 0), (GY - 110) * i / 7]);
          c.bolt = { pts, t };
          SFX.play(t === 40 ? 'thunder' : 'zap'); G.flash = 0.7; G.shake = 12;
          v.tgt = (t / 15 | 0) % 2 ? POSES.hitH : POSES.summon;
          burst(vx, GY - 110, 12, '#9fe8ff', 10, 18, 5, 0, true);
        }
        v.fx.xray = !!c.bolt && t - c.bolt.t < 9 && t < 112;
        if (t === 112) {
          v.fx.hide = true; c.pile = true; SFX.play('boom'); G.flash = 1; G.shake = 24;
          burst(vx, GY - 100, 70, '#9fe8ff', 16, 40, 7, 0.2, true);
          burst(vx, GY - 100, 50, '#b3121c', 13, 60, 7, 0.45);
          burst(vx, GY - 100, 30, '#1b1b22', 11, 70, 9, 0.4);
        }
        if (t === 140) a.tgt = 'win';
        break;
      case 'grave':
        if (t === 30) { a.tgt = 'summon'; SFX.play('dark'); }
        c.portal = t < 30 ? 0 : t < 60 ? (t - 30) / 30 : t < 185 ? 1 : Math.max(0, 1 - (t - 185) / 25);
        c.hands = clamp((t - 50) / 35, 0, 1);
        if (t === 90) { v.tgt = POSES.summon; SFX.play('dark'); }
        if (t > 90) { v.fx.sink = (t - 90) * 2.7; if (t % 6 === 0) part(vx + rnd(-60, 60), GY, rnd(-1, 1), rnd(-4, -1), 30, '#7dffb0', 6, 0, true); G.shake = 2; }
        if (t === 175) { v.fx.hide = true; SFX.play('quake'); }
        if (t === 190) a.tgt = 'win';
        break;
      case 'cyclone':
        if (t === 30 || t === 70 || t === 110) SFX.play('wind');
        c.twist = t < 30 ? 0 : t < 125 ? Math.min(1, (t - 30) / 20) : Math.max(0, 1 - (t - 125) / 25);
        if (t > 40 && t < 150) { v.y -= (t - 40) * 0.26; v.fx.rot = (v.fx.rot || 0) + 23; v.tgt = POSES.fall; }
        if (t >= 150 && !c.hit) {
          v.fx.rot = 0; v.tgt = POSES.down; v.pose = POSES.down.slice();
          c.fy = c.fy == null ? -260 : c.fy + 30; v.y = Math.min(GY, c.fy);
          if (v.y >= GY) { c.hit = t; G.shake = 28; SFX.play('boom'); G.flash = 0.5; burst(vx, GY - 8, 40, '#b3121c', 13, 55, 7, 0.5); burst(vx, GY, 26, '#8a8078', 10, 40, 9, 0.3); }
        }
        if (t > 30 && t < 150 && t % 2 === 0) part(vx + rnd(-70, 70), GY - rnd(0, 300), rnd(-6, 6), rnd(-4, 0), 16, '#b8fff2', 5, 0, true);
        if (t === 195) a.tgt = 'win';
        break;
    }
    if (t >= CINE_END[c.type]) {
      goOver(a.ch.fin.name, a.ch.name + ' WINS');
      a.state = 'frozen'; a.tgt = 'win';
      SFX.say(a.ch.name + ' wins.');
    }
  }

  // ------------------------------------------------------------------ stages
  const bg = document.createElement('canvas');
  bg.width = W; bg.height = H;
  const STAGES = ['MOON SHRINE', 'THE CRUCIBLE', 'STORMSPIRE'];
  function seeded(seed) { let s = seed; return () => (s = (s * 16807) % 2147483647) / 2147483647; }
  function paintStage(n) {
    const b = bg.getContext('2d'), R = seeded(7 + n * 13);
    const grad = (y0, y1, stops) => { const gr = b.createLinearGradient(0, y0, 0, y1); stops.forEach((c, i) => gr.addColorStop(i / (stops.length - 1), c)); return gr; };
    const HZ = GY - 46;
    const floor = (c1, c2, line) => {
      b.fillStyle = grad(HZ, H, [c1, c2]); b.fillRect(0, HZ, W, H - HZ);
      b.strokeStyle = line; b.lineWidth = 2;
      for (let i = -12; i <= 12; i++) { b.beginPath(); b.moveTo(W / 2 + i * 70, HZ); b.lineTo(W / 2 + i * 190, H); b.stroke(); }
      for (let i = 0; i < 5; i++) { const y = HZ + (H - HZ) * ((i / 5) ** 1.6); b.beginPath(); b.moveTo(0, y); b.lineTo(W, y); b.stroke(); }
    };
    if (n === 0) {
      b.fillStyle = grad(0, HZ, ['#070a22', '#1d1642', '#4a2a58']); b.fillRect(0, 0, W, HZ);
      for (let i = 0; i < 90; i++) { b.fillStyle = 'rgba(255,255,255,' + (0.2 + R() * 0.6) + ')'; b.fillRect(R() * W, R() * 330, 2, 2); }
      const mg = b.createRadialGradient(960, 180, 60, 960, 180, 260); mg.addColorStop(0, 'rgba(255,240,210,.5)'); mg.addColorStop(1, 'rgba(255,240,210,0)');
      b.fillStyle = mg; b.fillRect(600, 0, 680, 480);
      b.fillStyle = '#f6ead0'; b.beginPath(); b.arc(960, 180, 105, 0, 7); b.fill();
      b.fillStyle = 'rgba(190,170,150,.35)'; [[930, 150, 22], [1000, 210, 30], [985, 130, 12]].forEach(([x, y, r]) => { b.beginPath(); b.arc(x, y, r, 0, 7); b.fill(); });
      [['#1a1436', 150, 330], ['#110d26', 90, 400]].forEach(([c, amp, base]) => {
        b.fillStyle = c; b.beginPath(); b.moveTo(0, HZ);
        for (let x = 0; x <= W; x += 80) b.lineTo(x, base - R() * amp);
        b.lineTo(W, HZ); b.fill();
      });
      // shrine roof + pillars
      b.fillStyle = '#0b0818';
      b.beginPath(); b.moveTo(60, 232); b.quadraticCurveTo(640, 150, 1220, 232); b.lineTo(1260, 200); b.lineTo(1180, 262); b.lineTo(100, 262); b.lineTo(20, 200); b.fill();
      [150, 430, 850, 1130].forEach((x) => { b.fillRect(x - 24, 250, 48, HZ - 250); b.fillRect(x - 36, HZ - 22, 72, 22); });
      floor('#2c2740', '#0f0c18', 'rgba(140,120,190,.16)');
    } else if (n === 1) {
      b.fillStyle = grad(0, HZ, ['#0c0303', '#3a0c06', '#b5380b']); b.fillRect(0, 0, W, HZ);
      b.fillStyle = '#140605';
      [[210, 250, 150], [1050, 200, 190], [640, 120, 90]].forEach(([x, y, r]) => {
        b.beginPath(); b.arc(x, y, r, 0, 7); b.fill();
        for (let i = 0; i < 12; i++) { const a = i * Math.PI / 6; b.fillRect(x + Math.cos(a) * r - 16, y + Math.sin(a) * r - 16, 32, 32); }
        b.fillStyle = '#3a0c06'; b.beginPath(); b.arc(x, y, r * 0.3, 0, 7); b.fill(); b.fillStyle = '#140605';
      });
      b.strokeStyle = '#0a0302'; b.lineWidth = 9; b.setLineDash([16, 8]);
      [330, 520, 790, 930].forEach((x, i) => { b.beginPath(); b.moveTo(x, 0); b.lineTo(x, 180 + i * 37 % 150); b.stroke(); });
      b.setLineDash([]);
      b.fillStyle = '#0a0302'; b.fillRect(0, HZ - 70, W, 70);
      for (let x = 0; x < W; x += 160) b.fillRect(x + 20, HZ - 120 - R() * 60, 90, 130);
      b.fillStyle = grad(HZ - 14, HZ + 6, ['rgba(255,150,40,0)', 'rgba(255,170,60,.9)']); b.fillRect(0, HZ - 14, W, 20);
      floor('#3b1a12', '#0c0504', 'rgba(255,130,50,.2)');
    } else {
      b.fillStyle = grad(0, HZ, ['#080e12', '#1d2b33', '#46565c']); b.fillRect(0, 0, W, HZ);
      for (let layer = 0; layer < 2; layer++) {
        for (let x = -20; x < W;) {
          const w = 50 + R() * 90, h = 120 + R() * (layer ? 200 : 300);
          b.fillStyle = layer ? '#0a1116' : '#16222a'; b.fillRect(x, HZ - h, w, h);
          b.fillStyle = 'rgba(255,220,140,.5)';
          for (let i = 0; i < 6; i++) if (R() < 0.5) b.fillRect(x + 8 + R() * (w - 20), HZ - h + 12 + R() * (h - 30), 5, 8);
          x += w + R() * 14;
        }
      }
      b.fillStyle = '#080d11'; b.fillRect(0, HZ - 26, W, 26);
      for (let x = 10; x < W; x += 46) b.fillRect(x, HZ - 52, 6, 30);
      b.fillRect(0, HZ - 56, W, 6);
      floor('#27333a', '#0b1013', 'rgba(170,210,230,.14)');
    }
  }
  function drawStageFx() {
    const t = G.time, n = G.stage;
    if (n === 0) {
      [150, 430, 850, 1130].forEach((x, i) => {
        const fl = 1 + Math.sin(t * 0.4 + i * 2) * 0.15 + Math.sin(t * 0.9 + i) * 0.1;
        const gr = g.createRadialGradient(x, 330, 2, x, 330, 60 * fl); gr.addColorStop(0, 'rgba(255,200,90,.9)'); gr.addColorStop(0.3, 'rgba(255,120,30,.45)'); gr.addColorStop(1, 'rgba(255,120,30,0)');
        g.fillStyle = gr; g.fillRect(x - 70, 250, 140, 160);
      });
    } else if (n === 1) {
      for (let i = 0; i < 34; i++) {
        const life = (t * (0.6 + (i % 5) * 0.2) + i * 53) % 420;
        g.fillStyle = 'rgba(255,' + (140 + i * 3) + ',40,' + (1 - life / 420) + ')';
        g.fillRect((i * 97 + Math.sin(t * 0.02 + i) * 40) % W, GY - 40 - life, 3, 3);
      }
    } else {
      g.strokeStyle = 'rgba(190,220,240,.28)'; g.lineWidth = 1.5; g.beginPath();
      for (let i = 0; i < 70; i++) { const x = (i * 137 + t * 9) % (W + 200) - 100, y = (i * 211 + t * 26) % H; g.moveTo(x, y); g.lineTo(x - 8, y + 26); }
      g.stroke();
      const ph = t % 430;
      if (ph < 8 || (ph > 14 && ph < 18)) { g.fillStyle = 'rgba(220,235,255,.22)'; g.fillRect(0, 0, W, H); }
    }
  }

  // ------------------------------------------------------------------ rendering
  function text(s, x, y, size, col, align, stroke) {
    g.font = '900 ' + size + 'px ' + FONT; g.textAlign = align || 'center'; g.textBaseline = 'middle';
    if (stroke !== 0) { g.lineJoin = 'round'; g.lineWidth = stroke || Math.max(4, size / 8); g.strokeStyle = '#0a0606'; g.strokeText(s, x, y); }
    g.fillStyle = col || '#fff'; g.fillText(s, x, y);
  }
  function drawEntity(f) {
    if (f.fx.hide) return;
    const o = { flash: f.flash > 0 ? Math.min(1, f.flash / 6) : 0, dark: f.fx.dark, alpha: f.fx.alpha == null ? undefined : f.fx.alpha, xray: f.fx.xray, sy: f.fx.sy, time: G.time + f.slot * 40 };
    let p = f.pose;
    if (f.fx.rot) { p = p.slice(); p[10] += f.fx.rot; }
    if (o.alpha !== 0 && !f.fx.sink) {
      const sh = clamp(1 - (GY - f.y) / 400, 0.3, 1);
      g.fillStyle = 'rgba(0,0,0,' + 0.4 * sh * (o.alpha == null ? 1 : o.alpha) + ')';
      g.beginPath(); g.ellipse(f.x, GY + 4, 52 * sh * f.ch.bulk ** 0.5, 9 * sh, 0, 0, 7); g.fill();
    }
    if (f.fx.sink) {
      g.save(); g.beginPath(); g.rect(0, 0, W, GY + 3); g.clip();
      drawFighter(g, f.ch, p, f.x + Math.sin(G.time * 0.6) * 3, f.y + f.fx.sink, f.face, o);
      g.restore();
    } else if (f.fx.split != null) {
      const s = f.fx.split, yc = GY - 108;
      const yl = (x) => yc + (x - f.x) * 0.3;
      const half = (upper) => {
        g.save();
        if (upper) { const k = Math.min(s, 60); g.translate(k * 1.3, Math.min(k * 0.39 + Math.max(0, s - 22) ** 2 * 0.09, 112)); }
        g.beginPath();
        g.moveTo(-400, yl(-400)); g.lineTo(W + 400, yl(W + 400)); g.lineTo(W + 400, upper ? -600 : H + 200); g.lineTo(-400, upper ? -600 : H + 200);
        g.closePath(); g.clip();
        drawFighter(g, f.ch, p, f.x, f.y, f.face, o);
        g.restore();
      };
      half(false); half(true);
    } else drawFighter(g, f.ch, p, f.x, f.y, f.face, o);
  }

  function drawProj(p) {
    const t = G.time, d = Math.sign(p.vx);
    g.save(); g.translate(p.x, p.y);
    if (p.type === 'fire') {
      const gr = g.createRadialGradient(0, 0, 3, 0, 0, 30); gr.addColorStop(0, '#fff6c8'); gr.addColorStop(0.4, '#ff9a1f'); gr.addColorStop(1, 'rgba(255,60,0,0)');
      g.fillStyle = gr; g.beginPath(); g.ellipse(-d * 8, 0, 40, 24, 0, 0, 7); g.fill();
      part(p.x - d * 14, p.y + rnd(-10, 10), -d * rnd(0, 2), rnd(-1.5, 0.5), 14, '#ff7a1a', 7, -0.05, true);
    } else if (p.type === 'dagger') {
      g.shadowColor = '#c9a2ff'; g.shadowBlur = 14; g.strokeStyle = '#e9dcff'; g.lineWidth = 5; g.lineCap = 'round';
      g.beginPath(); g.moveTo(-d * 20, 0); g.lineTo(d * 20, 0); g.stroke();
      g.strokeStyle = '#9b5cff'; g.lineWidth = 3; g.beginPath(); g.moveTo(-d * 20, -6); g.lineTo(-d * 20, 6); g.stroke();
    } else if (p.type === 'orb') {
      const gr = g.createRadialGradient(0, 0, 2, 0, 0, 28); gr.addColorStop(0, '#fff'); gr.addColorStop(0.5, '#6fd6ff'); gr.addColorStop(1, 'rgba(60,140,255,0)');
      g.fillStyle = gr; g.beginPath(); g.arc(0, 0, 28, 0, 7); g.fill();
      g.strokeStyle = '#e8fbff'; g.lineWidth = 2; g.beginPath();
      for (let i = 0; i < 4; i++) { const a = rnd(0, 6.28); g.moveTo(0, 0); g.lineTo(Math.cos(a) * 16 + rnd(-8, 8), Math.sin(a) * 16 + rnd(-8, 8)); g.lineTo(Math.cos(a) * 34, Math.sin(a) * 34); }
      g.stroke();
    } else if (p.type === 'skull') {
      g.shadowColor = '#7dffb0'; g.shadowBlur = 18; g.fillStyle = '#e4e2d0';
      g.beginPath(); g.arc(0, -2, 17, 0, 7); g.fill(); g.fillRect(-9, 8, 18, 10); g.shadowBlur = 0;
      g.fillStyle = '#0c120e'; g.beginPath(); g.arc(d * 7, -3, 5, 0, 7); g.arc(-d * 4, -3, 5, 0, 7); g.fill();
      part(p.x - d * 16, p.y + rnd(-10, 10), -d, rnd(-1, 1), 16, '#7dffb0', 6, 0, true);
    } else if (p.type === 'gust') {
      g.strokeStyle = 'rgba(200,255,245,.8)'; g.lineWidth = 4; g.lineCap = 'round';
      for (let i = 0; i < 4; i++) { const yy = -36 + i * 24, ph = Math.sin(t * 0.5 + i) * 8; g.beginPath(); g.arc(-d * (30 - ph), yy, 26, d > 0 ? -1 : Math.PI - 1, d > 0 ? 1 : Math.PI + 1); g.stroke(); }
    } else if (p.type === 'quake') {
      g.fillStyle = '#7a6f62'; g.strokeStyle = '#0d0909'; g.lineWidth = 2.5;
      for (let i = 0; i < 3; i++) { const h = 30 + Math.sin(t * 0.8 + i * 2) * 14 + i * 8; g.beginPath(); g.moveTo(-28 + i * 16, 24); g.lineTo(-18 + i * 16 + d * 6, 24 - h); g.lineTo(-4 + i * 16, 24); g.closePath(); g.fill(); g.stroke(); }
      part(p.x + rnd(-20, 20), GY, rnd(-2, 2), rnd(-5, -1), 16, '#9c8f7e', 6, 0.3);
    }
    g.restore();
  }
  function drawHands(x, k, col, n, reach) {
    g.strokeStyle = col; g.lineCap = 'round'; g.shadowColor = col; g.shadowBlur = 12;
    for (let i = 0; i < n; i++) {
      const bx = x + (i - (n - 1) / 2) * (110 / n) * 1.4, h = reach * k * (0.7 + 0.3 * Math.sin(i * 1.7)), sway = Math.sin(G.time * 0.2 + i * 2) * 10;
      g.lineWidth = 7; g.beginPath(); g.moveTo(bx, GY + 4); g.quadraticCurveTo(bx + sway, GY - h * 0.5, x + (bx - x) * 0.4 + sway, GY - h); g.stroke();
      g.lineWidth = 3;
      for (let j = -1; j <= 1; j++) { g.beginPath(); g.moveTo(x + (bx - x) * 0.4 + sway, GY - h); g.lineTo(x + (bx - x) * 0.4 + sway + j * 8, GY - h - 14 * k); g.stroke(); }
    }
    g.shadowBlur = 0;
  }
  function drawTrap(tr) {
    const d = tr.m.delay, k = tr.t < d ? tr.t / d : 1;
    g.fillStyle = 'rgba(125,255,176,' + (0.25 + 0.25 * Math.sin(G.time * 0.6)) * k + ')';
    g.beginPath(); g.ellipse(tr.x, GY + 4, 62 * k, 12 * k, 0, 0, 7); g.fill();
    if (tr.t >= d) drawHands(tr.x, clamp(1 - (tr.t - d - 10) / 16, 0, 1) * Math.min(1, (tr.t - d) / 4), '#7dffb0', 4, 110);
  }

  function drawCineBack() {
    const c = G.cine, vx = c.v.x, t = c.t;
    g.fillStyle = 'rgba(4,2,6,' + Math.min(0.62, t / 40) + ')'; g.fillRect(0, 0, W, H);
    if (c.type === 'grave' && c.portal > 0) {
      const gr = g.createRadialGradient(vx, GY + 4, 4, vx, GY + 4, 130 * c.portal + 1); gr.addColorStop(0, '#031208'); gr.addColorStop(0.7, '#0c3a22'); gr.addColorStop(1, 'rgba(125,255,176,.0)');
      g.save(); g.translate(0, (GY + 4) * (1 - 0.16)); g.scale(1, 0.16); g.fillStyle = gr; g.beginPath(); g.arc(vx, GY + 4, 130 * c.portal, 0, 7); g.fill(); g.restore();
      g.strokeStyle = 'rgba(125,255,176,.8)'; g.lineWidth = 3; g.beginPath(); g.ellipse(vx, GY + 4, 118 * c.portal, 19 * c.portal, 0, 0, 7); g.stroke();
    }
    if (c.type === 'crush' && !c.hit && t > 40) {
      g.fillStyle = 'rgba(0,0,0,.5)'; g.beginPath(); g.ellipse(vx, GY + 4, 30 + (c.by + 320) / 9, 6 + (c.by + 320) / 60, 0, 0, 7); g.fill();
    }
    if (c.pile) {
      g.fillStyle = c.type === 'ash' ? '#262120' : 'rgba(8,8,12,.8)';
      g.beginPath(); g.ellipse(c.vx0, GY + 2, c.type === 'ash' ? 46 : 90, c.type === 'ash' ? 13 : 14, 0, c.type === 'ash' ? Math.PI : 0, 7); g.fill();
    }
  }
  function drawCineFront() {
    const c = G.cine, vx = c.v.x, t = c.t;
    if (c.type === 'ash' && t >= 30 && t < 140) {
      const k = Math.min(1, (t - 30) / 12) * (t > 125 ? (140 - t) / 15 : 1);
      const gr = g.createLinearGradient(vx - 70, 0, vx + 70, 0); gr.addColorStop(0, 'rgba(255,80,0,0)'); gr.addColorStop(0.5, 'rgba(255,190,70,' + 0.6 * k + ')'); gr.addColorStop(1, 'rgba(255,80,0,0)');
      g.fillStyle = gr; g.fillRect(vx - 70 - Math.sin(t) * 5, 0, 140, GY + 6);
    }
    if (c.type === 'crush' && t > 40) {
      g.save(); g.translate(vx, c.by);
      g.fillStyle = '#6f665b'; g.strokeStyle = '#0d0909'; g.lineWidth = 5; g.beginPath();
      [[-92, 30], [-70, -60], [-10, -96], [62, -74], [98, -8], [80, 70], [10, 96], [-66, 82]].forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
      g.closePath(); g.fill(); g.stroke();
      g.strokeStyle = '#3d3832'; g.lineWidth = 4; g.beginPath(); g.moveTo(-50, -30); g.lineTo(-5, -5); g.lineTo(-20, 40); g.moveTo(-5, -5); g.lineTo(50, -25); g.stroke();
      g.restore();
    }
    if (c.type === 'slice') {
      for (const s of c.slashes) {
        const k = 1 - (t - s.t) / 14; if (k <= 0) continue;
        g.save(); g.translate(vx, GY - 105); g.rotate(s.ang);
        g.strokeStyle = 'rgba(255,255,255,' + k + ')'; g.shadowColor = '#c9a2ff'; g.shadowBlur = 20; g.lineWidth = 9 * k; g.lineCap = 'round';
        g.beginPath(); g.moveTo(-260, 0); g.lineTo(260, 0); g.stroke(); g.restore();
      }
    }
    if (c.type === 'bolt' && c.bolt && t - c.bolt.t < 10) {
      const k = 1 - (t - c.bolt.t) / 10;
      g.shadowColor = '#6fd6ff'; g.shadowBlur = 30; g.lineJoin = 'bevel';
      g.strokeStyle = 'rgba(160,230,255,' + k + ')'; g.lineWidth = 16 * k; g.beginPath(); c.bolt.pts.forEach((p, i) => (i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1]))); g.stroke();
      g.strokeStyle = 'rgba(255,255,255,' + k + ')'; g.lineWidth = 5; g.stroke(); g.shadowBlur = 0;
    }
    if (c.type === 'grave' && c.hands > 0 && c.portal > 0) drawHands(vx, c.hands * c.portal * (t > 90 ? Math.max(0.25, 1 - (t - 90) / 90) : 1), '#7dffb0', 5, 210);
    if (c.type === 'cyclone' && c.twist > 0) {
      g.strokeStyle = 'rgba(200,255,245,' + 0.55 * c.twist + ')'; g.lineWidth = 5;
      for (let i = 0; i < 16; i++) {
        const y = GY - i * 42, r = (26 + i * 12) * c.twist, off = Math.sin(t * 0.25 + i * 0.6) * (8 + i * 2);
        g.beginPath(); g.ellipse(vx + off, y, r, r * 0.2, 0, (t * 0.5 + i) % 6.28, ((t * 0.5 + i) % 6.28) + 4.6); g.stroke();
      }
    }
  }

  function drawHUD() {
    const bw = 500, bh = 30, y = 40;
    for (let s = 0; s < 2; s++) {
      const f = G.f[s], x = s ? W - 60 - bw : 60;
      g.fillStyle = '#0a0606'; g.fillRect(x - 5, y - 5, bw + 10, bh + 10);
      g.fillStyle = '#3a0d0d'; g.fillRect(x, y, bw, bh);
      const gw = bw * clamp(f.ghost, 0, 100) / 100, hw = bw * clamp(f.hp, 0, 100) / 100;
      g.fillStyle = '#f5f0e0'; g.fillRect(s ? x : x + bw - gw, y, gw, bh);
      const gr = g.createLinearGradient(0, y, 0, y + bh); gr.addColorStop(0, f.hp > 25 ? '#ffe066' : '#ff6a4a'); gr.addColorStop(1, f.hp > 25 ? '#e08a12' : '#b31a12');
      g.fillStyle = gr; g.fillRect(s ? x : x + bw - hw, y, hw, bh);
      g.strokeStyle = PCOL[s]; g.lineWidth = 3; g.strokeRect(x - 5, y - 5, bw + 10, bh + 10);
      text(f.ch.name + (P[s].joined ? '' : '  (CPU)'), s ? x + bw : x, y + bh + 26, 28, '#fff', s ? 'right' : 'left');
      for (let i = 0; i < 2; i++) {
        const px = s ? x + 14 + i * 30 : x + bw - 14 - i * 30;
        g.beginPath(); g.arc(px, y + bh + 26, 10, 0, 7); g.fillStyle = i < P[s].wins ? '#ffcf5a' : '#1a1212'; g.fill(); g.lineWidth = 3; g.strokeStyle = '#0a0606'; g.stroke();
      }
      // special cooldown
      const cdw = 150, cx = s ? x + bw - cdw : x, cdm = 110;
      g.fillStyle = '#0a0606'; g.fillRect(cx - 2, y + bh + 46, cdw + 4, 10);
      g.fillStyle = f.cd > 0 ? '#555' : tone(f.ch.c.glow, {}); g.fillRect(cx, y + bh + 48, cdw * (1 - clamp(f.cd / cdm, 0, 1)), 6);
      if (f.combo >= 2 && f.comboT > 0) text(f.combo + ' HITS', s ? W - 160 : 160, 230, 46, '#ffcf5a');
    }
    text(String(Math.max(0, G.timer)), W / 2, y + 18, 56, G.timer <= 10 ? '#ff5340' : '#fff');
    text('ROUND ' + G.round + ' · ' + STAGES[G.stage], W / 2, y + 62, 16, 'rgba(255,255,255,.7)', 'center', 3);
  }
  function drawBanner() {
    const b = G.banner; if (!b) return;
    b.t++;
    if (b.t > b.dur) { G.banner = null; return; }
    const k = Math.min(1, b.t / 8), sc = 2.2 - 1.2 * k, a = b.t > b.dur - 10 ? (b.dur - b.t) / 10 : k;
    g.save(); g.globalAlpha = a; g.translate(W / 2, 300); g.scale(sc, sc);
    const size = b.text.length > 12 ? 92 : 130;
    text(b.text, 0, 0, size, b.col, 'center', 14);
    g.restore();
    if (b.sub) { g.save(); g.globalAlpha = a; text(b.sub, W / 2, 392, 40, '#fff'); g.restore(); }
  }

  function renderFight() {
    g.save();
    if (G.shake > 0.5) { g.translate(rnd(-G.shake, G.shake), rnd(-G.shake, G.shake) * 0.6); G.shake *= 0.86; } else G.shake = 0;
    g.drawImage(bg, 0, 0);
    drawStageFx();
    if (G.cine) drawCineBack();
    G.traps.forEach(drawTrap);
    const order = G.cine ? [G.cine.v, G.cine.a] : G.f[0].state === 'atk' ? [G.f[1], G.f[0]] : [G.f[0], G.f[1]];
    order.forEach(drawEntity);
    G.projs.forEach(drawProj);
    for (const p of G.parts) {
      const k = p.life / p.max;
      g.globalAlpha = Math.min(1, k * 1.6);
      g.fillStyle = p.col;
      if (p.glow) { g.beginPath(); g.arc(p.x, p.y, p.size * (0.4 + k * 0.6), 0, 7); g.fill(); }
      else g.fillRect(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size);
    }
    g.globalAlpha = 1;
    if (G.cine) drawCineFront();
    g.restore();
    if (G.flash > 0.02) { g.fillStyle = 'rgba(255,255,255,' + G.flash + ')'; g.fillRect(0, 0, W, H); G.flash *= 0.8; }
    if (!G.cine) drawHUD();
    else { g.fillStyle = '#000'; g.fillRect(0, 0, W, 54); g.fillRect(0, H - 54, W, 54); }
    drawBanner();
    if (G.sub === 'finish') {
      const k = clamp(1 - G.t / 420, 0, 1);
      g.fillStyle = '#0a0606'; g.fillRect(W / 2 - 202, 150, 404, 16); g.fillStyle = '#ff3b2f'; g.fillRect(W / 2 - 200, 152, 400 * k, 12);
      if (G.t > 60) text(P[G.winner].joined ? 'FINISHER:  ' + seqText(G.f[G.winner].ch) : '', W / 2, 196, 30, '#ffcf5a');
    }
    if (G.sub === 'over' && G.t > 100 && (G.time >> 5) % 2) text('PRESS PUNCH TO PLAY AGAIN', W / 2, H - 90, 30, '#fff');
  }

  function titleBG() {
    if (G.stage !== 0 || !titleBG.done) { G.stage = 0; paintStage(0); titleBG.done = true; }
    g.drawImage(bg, 0, 0); drawStageFx();
    g.fillStyle = 'rgba(6,4,12,.62)'; g.fillRect(0, 0, W, H);
  }
  function renderLobby() {
    titleBG();
    const gr = g.createLinearGradient(0, 70, 0, 210); gr.addColorStop(0, '#fff3c4'); gr.addColorStop(0.5, '#ff9a1f'); gr.addColorStop(1, '#c2200c');
    text('ASHFALL', 400, 140, 170, gr, 'center', 18);
    text('TOURNAMENT OF CINDERS', 400, 240, 34, '#e8d9c0', 'center', 6);
    const steps = ['1.  Connect both phones to the same Wi-Fi', '2.  Scan the code with the phone camera', '3.  Turn the phone sideways', '4.  Press PUNCH to begin'];
    steps.forEach((s, i) => text(s, 110, 330 + i * 46, 28, '#fff', 'left', 5));
    for (let s = 0; s < 2; s++) {
      const x = 110 + s * 310, y = 540;
      g.fillStyle = P[s].joined ? PCOL[s] : 'rgba(255,255,255,.08)'; g.fillRect(x, y, 280, 96);
      g.strokeStyle = PCOL[s]; g.lineWidth = 4; g.strokeRect(x, y, 280, 96);
      text('PLAYER ' + (s + 1), x + 140, y + 32, 34, '#fff');
      text(P[s].joined ? (P[s].pad ? 'PHONE CONNECTED' : 'KEYBOARD') : (s === 1 && P[0].joined ? 'waiting… (or fight the CPU)' : 'waiting for phone…'), x + 140, y + 70, 20, '#fff', 'center', 4);
    }
    // QR
    const qx = 810, qy = 150, qs = 380;
    g.fillStyle = '#fff'; g.fillRect(qx, qy, qs, qs);
    if (qr) {
      const n = qr.length, cell = qs / (n + 8);
      g.fillStyle = '#000';
      for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (qr[y][x]) g.fillRect(qx + (x + 4) * cell, qy + (y + 4) * cell, cell + 0.5, cell + 0.5);
    }
    text(padURL ? padURL.replace(/^https?:\/\//, '') : 'connecting…', qx + qs / 2, qy + qs + 40, 30, '#ffcf5a', 'center', 6);
    text('or type this address into Safari', qx + qs / 2, qy + qs + 78, 20, '#fff', 'center', 4);
    if (P[0].joined || P[1].joined) { if ((G.time >> 5) % 2) text('PRESS PUNCH TO START', 400, 672, 34, '#ffcf5a'); }
    if (SFX.locked()) text('🔇 click or press a key on this screen to turn sound on', W / 2, 20, 18, 'rgba(255,255,255,.75)', 'center', 3);
  }

  function renderSelect() {
    titleBG();
    text('CHOOSE YOUR FIGHTER', W / 2, 62, 64, '#ffcf5a', 'center', 10);
    const cw = 150, chh = 170, gx = W / 2 - cw * 1.5, gy = 150;
    ROSTER.forEach((ch, i) => {
      const x = gx + (i % 3) * cw, y = gy + ((i / 3) | 0) * chh;
      g.fillStyle = '#17121f'; g.fillRect(x + 5, y + 5, cw - 10, chh - 10);
      g.save(); g.beginPath(); g.rect(x + 5, y + 5, cw - 10, chh - 10); g.clip();
      const gr = g.createLinearGradient(0, y, 0, y + chh); gr.addColorStop(0, tone(ch.c.main, { dark: 0.5 })); gr.addColorStop(1, '#0b0810');
      g.fillStyle = gr; g.fillRect(x, y, cw, chh);
      drawFighter(g, ch, POSES.idle, x + cw / 2 - 12, y + chh + 62, 1, { scale: 1.05, time: G.time });
      g.restore();
      text(ch.name, x + cw / 2, y + chh - 22, 22, '#fff', 'center', 5);
      g.strokeStyle = '#3a3048'; g.lineWidth = 3; g.strokeRect(x + 5, y + 5, cw - 10, chh - 10);
    });
    for (let s = 0; s < 2; s++) {
      const p = P[s], ch = ROSTER[p.sel], cx = s ? W - 215 : 215;
      if (!p.joined) {
        text(s ? 'CPU' : 'PLAYER 1', cx, 300, 60, 'rgba(255,255,255,.35)');
        text(s ? 'opponent picked at random' : 'not connected', cx, 350, 20, 'rgba(255,255,255,.5)', 'center', 3);
        continue;
      }
      const x = gx + (p.sel % 3) * cw, y = gy + ((p.sel / 3) | 0) * chh, pulse = p.locked ? 0 : Math.sin(G.time * 0.2) * 2;
      g.strokeStyle = PCOL[s]; g.lineWidth = p.locked ? 9 : 6;
      g.strokeRect(x + 5 - pulse + (s ? 4 : -4) * 0, y + 5 - pulse, cw - 10 + pulse * 2, chh - 10 + pulse * 2);
      text('P' + (s + 1), x + (s ? cw - 26 : 26), y + 24, 24, PCOL[s], 'center', 5);
      const pose = p.locked ? POSES.win : mixPose(POSES.idle, POSES.idleB, (Math.sin(G.time * 0.09) + 1) / 2);
      g.fillStyle = 'rgba(0,0,0,.45)'; g.beginPath(); g.ellipse(cx, 566, 110, 16, 0, 0, 7); g.fill();
      drawFighter(g, ch, pose, cx, 560, s ? -1 : 1, { scale: 1.75, time: G.time });
      text(ch.name, cx, 110, 58, PCOL[s], 'center', 9);
      text(ch.title, cx, 152, 22, '#fff', 'center', 4);
      text('SPECIAL · ' + ch.sp[0].name, cx, 606, 20, '#fff', 'center', 4);
      text('↓ + SPECIAL · ' + ch.sp[1].name, cx, 632, 20, '#fff', 'center', 4);
      text(p.locked ? 'LOCKED IN' : 'PUNCH to lock in', cx, 676, 28, p.locked ? '#ffcf5a' : '#fff', 'center', 5);
    }
    text('PUNCH  lock in      KICK  change      one phone = fight the CPU', W / 2, H - 24, 18, 'rgba(255,255,255,.7)', 'center', 3);
  }

  function renderVS() {
    g.drawImage(bg, 0, 0); drawStageFx();
    g.fillStyle = 'rgba(6,4,12,.55)'; g.fillRect(0, 0, W, H);
    const k = Math.min(1, G.t / 18), e = 1 - (1 - k) ** 3;
    for (let s = 0; s < 2; s++) {
      const ch = ROSTER[P[s].sel], cx = s ? W + 300 - 620 * e : -300 + 620 * e;
      drawFighter(g, ch, POSES.idle, cx, 600, s ? -1 : 1, { scale: 2.1, time: G.time });
      text(ch.name, cx, 660, 64, PCOL[s], 'center', 10);
    }
    g.save(); g.translate(W / 2, 330); g.scale(2 - e, 2 - e); text('VS', 0, 0, 190, '#ffcf5a', 'center', 20); g.restore();
    text(STAGES[G.stage], W / 2, 80, 40, '#fff', 'center', 7);
  }

  // ------------------------------------------------------------------ main loop
  function step() {
    G.time++;
    sampleInput();
    stepParts();
    if (G.phase === 'lobby') { if (anyPressed(BIT.P)) { SFX.play('ok'); goSelect(); } }
    else if (G.phase === 'select') stepSelect();
    else if (G.phase === 'vs') { if (++G.t > 150) goFight(); }
    else if (G.phase === 'fight') stepFight();
  }
  function render() {
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalAlpha = 1; g.shadowBlur = 0;
    if (G.phase === 'lobby') renderLobby();
    else if (G.phase === 'select') renderSelect();
    else if (G.phase === 'vs') renderVS();
    else renderFight();
  }
  let last = 0, acc = 0;
  function frame(now) {
    requestAnimationFrame(frame);
    acc += Math.min(100, now - last); last = now;
    let n = 0;
    while (acc >= 1000 / 60 && n++ < 4) { step(); acc -= 1000 / 60; }
    if (n) render();
  }
  function fit() {
    const s = Math.min(innerWidth / W, innerHeight / H);
    cv.style.width = Math.floor(W * s) + 'px'; cv.style.height = Math.floor(H * s) + 'px';
  }
  addEventListener('resize', fit); fit();
  window.__ashfall = { G, P, inp, step, startCine, ROSTER }; // debugging hook
  connect();
  refreshUI();
  requestAnimationFrame((t) => { last = t; frame(t); });
})();
