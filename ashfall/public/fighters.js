// Roster, moves, poses and the procedural fighter renderer.
'use strict';
const BIT = { L: 1, R: 2, U: 4, D: 8, P: 16, K: 32, BL: 64, S: 128 };

// Pose = [torso, head, armF upper, armF lower, armB upper, armB lower,
//         legF upper, legF lower, legB upper, legB lower, whole-body rotation]
// Angles in degrees. Limbs: 0 = straight down, + = toward the opponent. Torso: 0 = upright.
const POSES = {
  idle:   [6, 0, 40, 140, 10, 120, 28, -8, -20, -25, 0],
  idleB:  [9, 3, 44, 134, 14, 114, 31, -11, -23, -28, 0],
  walkA:  [8, 0, 40, 140, 10, 120, 36, 6, -26, -40, 0],
  walkB:  [8, 0, 40, 140, 10, 120, -12, -30, 22, -4, 0],
  crouch: [20, -8, 50, 140, 25, 125, 80, -20, 35, -80, 0],
  jump:   [10, 0, 30, 120, -20, 60, 60, -30, 20, -70, 0],
  punchW: [0, 0, 10, 130, 30, 130, 28, -8, -20, -25, 0],
  punch:  [16, 0, 88, 90, -10, 100, 32, -5, -24, -30, 0],
  kickW:  [-5, 0, 40, 140, 10, 120, 70, -40, -8, -15, 0],
  kick:   [-22, 0, 30, 130, -30, 30, 92, 90, -6, -12, 0],
  upperW: [26, -5, 20, 60, 25, 125, 80, -20, 35, -80, 0],
  upper:  [-10, -12, 150, 172, 0, 90, 12, 2, -12, -16, 0],
  sweep:  [38, -20, 60, 100, -40, -10, 84, 88, 50, -85, 0],
  airP:   [28, 5, 100, 110, 20, 110, 40, -50, -5, -75, 0],
  airK:   [-8, 0, 30, 120, -20, 60, 75, 70, 30, -80, 0],
  block:  [-4, 6, 75, 165, 60, 170, 26, -8, -20, -25, 0],
  cblock: [14, 0, 75, 165, 60, 170, 80, -20, 35, -80, 0],
  hitH:   [-22, -18, -15, 40, -35, 20, 20, -2, -22, -32, 0],
  hitL:   [32, 22, 50, 80, 35, 70, 30, -12, -15, -30, 0],
  fall:   [-10, -10, 60, 90, 80, 120, 60, 30, 40, 10, -70],
  down:   [0, 0, 20, 10, -20, -10, 10, 5, -5, -10, -90],
  dizzy:  [12, 18, 8, 15, -5, 10, 14, -4, -14, -22, 0],
  win:    [-4, -8, 160, 178, 150, 172, 10, 0, -10, -12, 0],
  cast:   [12, 0, 85, 92, 70, 95, 34, -6, -24, -32, 0],
  dash:   [38, -15, -20, 40, 60, 110, 55, -25, -30, -55, 0],
  stomp:  [15, 0, 30, 60, -10, 30, 35, -10, -20, -25, 0],
  rise:   [-6, -10, 155, 175, -20, 40, 50, -40, 5, -20, 0],
  dive:   [-30, 0, 20, 120, -30, 50, 45, 45, 60, -70, 0],
  summon: [-5, -5, 120, 160, 110, 150, 20, -5, -18, -24, 0],
};

// su = startup frames, ac = active, re = recovery. rx/ry = hitbox reach relative to the fighter.
// lvl: high (whiffs on crouch), mid, low (must crouch-block), over (must stand-block).
const MOVES = {
  punch: { su: 4, ac: 3, re: 9, dmg: 5, rx: [15, 98], ry: [-172, -128], lvl: 'high', stun: 15, kb: 5, pw: 'punchW', p: 'punch' },
  kick:  { su: 7, ac: 4, re: 13, dmg: 8, rx: [15, 122], ry: [-130, -70], lvl: 'mid', stun: 18, kb: 8, pw: 'kickW', p: 'kick' },
  upper: { su: 6, ac: 4, re: 20, dmg: 13, rx: [5, 85], ry: [-215, -60], lvl: 'mid', launch: [4, -15], pw: 'upperW', p: 'upper', low: 1, heavy: 1 },
  sweep: { su: 8, ac: 4, re: 20, dmg: 8, rx: [15, 132], ry: [-45, 0], lvl: 'low', launch: [2, -6], pw: 'crouch', p: 'sweep', low: 2 },
  airP:  { su: 4, ac: 99, re: 0, dmg: 6, rx: [5, 92], ry: [-135, -30], lvl: 'over', stun: 17, kb: 5, pw: 'jump', p: 'airP', air: 1 },
  airK:  { su: 5, ac: 99, re: 0, dmg: 8, rx: [5, 112], ry: [-95, 0], lvl: 'over', stun: 19, kb: 6, pw: 'jump', p: 'airK', air: 1 },
};

const ROSTER = [
  {
    id: 'kaida', name: 'KAIDA', title: 'Ember Monk', head: 'topknot', bulk: 1, tall: 1, speed: 4.6, def: 1,
    c: { main: '#c93a1c', alt: '#ffb648', skin: '#e3ac82', pants: '#3a1a14', boot: '#1d0f0c', hair: '#1a1210', glow: '#ffd35e' },
    sp: [
      { name: 'Cinder Shot', kind: 'proj', su: 13, re: 20, dmg: 10, stun: 20, kb: 7, cd: 80, snd: 'fire', p: 'cast', pr: { type: 'fire', vx: 10, w: 44, h: 30, y: -122 } },
      { name: 'Flame Rush', kind: 'dash', su: 9, ac: 13, re: 18, spd: 14, dmg: 12, launch: [7, -9], cd: 110, rx: [0, 62], ry: [-150, -30], lvl: 'mid', snd: 'fire', p: 'dash', trail: 'fire', heavy: 1 },
    ],
    fin: { name: 'ASH TO ASH', type: 'ash', seq: [BIT.D, BIT.D, BIT.P] },
  },
  {
    id: 'brakk', name: 'BRAKK', title: 'The Living Quarry', head: 'horns', bulk: 1.45, tall: 1.08, speed: 3.6, def: 0.85,
    c: { main: '#6b6257', alt: '#d98a2b', skin: '#8d8478', pants: '#3b352f', boot: '#221e1a', hair: '#2a2622', glow: '#ffa23e' },
    sp: [
      { name: 'Rampage', kind: 'dash', su: 12, ac: 15, re: 20, spd: 12, dmg: 14, launch: [9, -10], armor: 1, cd: 120, rx: [0, 70], ry: [-160, -30], lvl: 'mid', snd: 'quake', p: 'dash', trail: 'dust', heavy: 1 },
      { name: 'Faultline', kind: 'quake', su: 18, re: 22, dmg: 9, launch: [2, -8], cd: 110, snd: 'quake', pw: 'kickW', p: 'stomp', pr: { type: 'quake', vx: 9, w: 60, h: 44, y: -22, lvl: 'low' } },
    ],
    fin: { name: 'GRAVESTONE', type: 'crush', seq: [BIT.D, BIT.U, BIT.K] },
  },
  {
    id: 'nyx', name: 'NYX', title: 'Blade of the New Moon', head: 'hood', bulk: 0.85, tall: 0.96, speed: 5.4, def: 1.1,
    c: { main: '#2a2140', alt: '#9b5cff', skin: '#bfa7c9', pants: '#191428', boot: '#0d0a16', hair: '#120e1e', glow: '#c9a2ff' },
    sp: [
      { name: 'Fang', kind: 'proj', su: 8, re: 18, dmg: 7, stun: 16, kb: 4, cd: 60, snd: 'slash', p: 'punch', pr: { type: 'dagger', vx: 16, w: 38, h: 12, y: -128 } },
      { name: 'Shade Step', kind: 'tele', su: 9, re: 9, cd: 90, snd: 'dark', p: 'crouch' },
    ],
    fin: { name: 'THOUSAND CUTS', type: 'slice', seq: [BIT.U, BIT.D, BIT.S] },
  },
  {
    id: 'iona', name: 'IONA', title: 'Stormcaller', head: 'visor', bulk: 0.95, tall: 1, speed: 4.6, def: 1,
    c: { main: '#1d4e89', alt: '#f4e04d', skin: '#d9b08c', pants: '#12263f', boot: '#0b1626', hair: '#f4e04d', glow: '#9fe8ff' },
    sp: [
      { name: 'Ball Lightning', kind: 'proj', su: 14, re: 22, dmg: 9, stun: 30, kb: 3, cd: 90, snd: 'zap', p: 'cast', pr: { type: 'orb', vx: 7.5, w: 46, h: 46, y: -118 } },
      { name: 'Arc Rise', kind: 'rise', su: 5, ac: 14, re: 16, dmg: 13, launch: [4, -14], vy: -15, cd: 100, rx: [0, 72], ry: [-215, -50], lvl: 'mid', snd: 'zap', pw: 'upperW', p: 'rise', trail: 'spark', heavy: 1 },
    ],
    fin: { name: 'SKYFALL', type: 'bolt', seq: [BIT.U, BIT.U, BIT.P] },
  },
  {
    id: 'morrow', name: 'MORROW', title: 'The Last Mourner', head: 'skull', bulk: 0.95, tall: 1.04, speed: 4.0, def: 1,
    c: { main: '#2c3a2e', alt: '#7dffb0', skin: '#d8d6c4', pants: '#1a231c', boot: '#0e130f', hair: '#141a15', glow: '#7dffb0' },
    sp: [
      { name: 'Wailing Skull', kind: 'proj', su: 14, re: 22, dmg: 9, stun: 22, kb: 6, cd: 85, snd: 'dark', p: 'cast', pr: { type: 'skull', vx: 6.5, w: 40, h: 40, y: -122, wave: 1 } },
      { name: 'Grave Grasp', kind: 'ground', su: 16, re: 20, dmg: 10, stun: 34, kb: 1, lvl: 'low', delay: 26, cd: 120, snd: 'dark', p: 'summon' },
    ],
    fin: { name: 'SIX FEET UNDER', type: 'grave', seq: [BIT.D, BIT.D, BIT.S] },
  },
  {
    id: 'sable', name: 'SABLE', title: 'Wind Dancer', head: 'crest', bulk: 0.85, tall: 0.98, speed: 5.0, def: 1.05,
    c: { main: '#e8e4d8', alt: '#22b8a0', skin: '#8a5a3c', pants: '#1f5a52', boot: '#123631', hair: '#0f1414', glow: '#b8fff2' },
    sp: [
      { name: 'Gale', kind: 'proj', su: 11, re: 19, dmg: 6, stun: 18, kb: 17, cd: 75, snd: 'wind', p: 'cast', pr: { type: 'gust', vx: 13, w: 60, h: 90, y: -105 } },
      { name: 'Talon Dive', kind: 'dive', su: 6, re: 14, dmg: 12, stun: 22, kb: 8, cd: 100, rx: [0, 78], ry: [-85, 12], lvl: 'over', snd: 'wind', pw: 'jump', p: 'dive', trail: 'wind', heavy: 1 },
    ],
    fin: { name: 'EYE OF THE STORM', type: 'cyclone', seq: [BIT.U, BIT.D, BIT.K] },
  },
];
ROSTER.forEach((ch) => ch.sp.forEach((m) => { m.sp = 1; if (!m.lvl) m.lvl = (m.pr && m.pr.lvl) || 'mid'; }));

// ---------- rendering ----------
const D2R = Math.PI / 180;
const _hex = {};
function tone(c, o) {
  let a = _hex[c];
  if (!a) { const n = parseInt(c.slice(1), 16); a = _hex[c] = [n >> 16, (n >> 8) & 255, n & 255]; }
  let r = a[0], g = a[1], b = a[2];
  const d = o.dark || 0, f = o.flash || 0;
  if (d) { r += (16 - r) * d; g += (13 - g) * d; b += (12 - b) * d; }
  if (f) { r += (255 - r) * f; g += (255 - g) * f; b += (255 - b) * f; }
  return 'rgb(' + (r | 0) + ',' + (g | 0) + ',' + (b | 0) + ')';
}

function rig(ch, p) {
  const S = ch.tall * 1.15, T = 64 * S, UA = 31 * S, FA = 30 * S, TH = 42 * S, SH = 44 * S;
  const pt = (o, a, l) => [o[0] + Math.sin(a * D2R) * l, o[1] + Math.cos(a * D2R) * l];
  const J = {};
  J.hip = [0, 0];
  J.neck = [Math.sin(p[0] * D2R) * T, -Math.cos(p[0] * D2R) * T];
  const ha = p[0] + p[1];
  J.head = [J.neck[0] + Math.sin(ha * D2R) * 21 * S, J.neck[1] - Math.cos(ha * D2R) * 21 * S];
  J.sh = [J.neck[0] * 0.9, J.neck[1] * 0.9];
  J.eF = pt(J.sh, p[2], UA); J.hF = pt(J.eF, p[3], FA);
  J.eB = pt(J.sh, p[4], UA); J.hB = pt(J.eB, p[5], FA);
  J.kF = pt(J.hip, p[6], TH); J.fF = pt(J.kF, p[7], SH);
  J.kB = pt(J.hip, p[8], TH); J.fB = pt(J.kB, p[9], SH);
  const r = p[10] * D2R;
  let low = -1e9;
  for (const k in J) {
    const q = J[k];
    if (r) { const x = q[0], y = q[1]; q[0] = x * Math.cos(r) - y * Math.sin(r); q[1] = x * Math.sin(r) + y * Math.cos(r); }
    low = Math.max(low, q[1] + (k === 'head' ? 17 * S : 9));
  }
  for (const k in J) J[k][1] -= low;
  J.ha = (ha + p[10]) * D2R; J.S = S;
  return J;
}

// o: { scale, flash, dark, alpha, xray, sy, time }
function drawFighter(g, ch, pose, x, y, face, o) {
  o = o || {};
  const J = rig(ch, pose), S = J.S, bw = ch.bulk, t = o.time || 0;
  const sc = o.scale || 1;
  g.save();
  g.translate(x, y);
  g.scale(face * sc, sc * (o.sy == null ? 1 : o.sy));
  if (o.alpha != null) g.globalAlpha *= o.alpha;
  g.lineCap = 'round'; g.lineJoin = 'round';
  const back = { dark: Math.max(o.dark || 0, 0.4), flash: o.flash };
  const OUT = o.xray ? '#dff3ff' : '#0d0909';
  const C = (k, oo) => (o.xray ? '#0a0c14' : tone(ch.c[k], oo || o));
  const path = (pts) => { g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]); };
  const limb = (a, b, c, w, c1, c2) => {
    g.strokeStyle = OUT; g.lineWidth = w + 5; path([a, b, c]); g.stroke();
    g.strokeStyle = c1; g.lineWidth = w; path([a, b]); g.stroke();
    g.strokeStyle = c2; path([b, c]); g.stroke();
    if (o.xray) { g.strokeStyle = OUT; g.lineWidth = 3; path([a, b, c]); g.stroke(); }
  };
  const dot = (p, r, col) => { g.beginPath(); g.arc(p[0], p[1], r, 0, 7); g.fillStyle = col; g.fill(); g.lineWidth = 2.5; g.strokeStyle = OUT; g.stroke(); };
  const foot = (p, oo) => {
    g.strokeStyle = OUT; g.lineWidth = 17 * S; path([p, [p[0] + 13 * S, p[1] + 1]]); g.stroke();
    g.strokeStyle = C('boot', oo); g.lineWidth = 12 * S; g.stroke();
  };
  const aw = 15 * S * Math.sqrt(bw), lw = 18 * S * Math.sqrt(bw);

  // back arm + back leg
  limb(J.sh, J.eB, J.hB, aw, C('main', back), C('skin', back));
  dot(J.hB, 8.5 * S * Math.sqrt(bw), C('alt', back));
  limb(J.hip, J.kB, J.fB, lw, C('pants', back), C('pants', back));
  foot(J.fB, back);
  // front leg
  limb(J.hip, J.kF, J.fF, lw, C('pants'), C('pants'));
  foot(J.fF);
  // robe / sash
  if (!o.xray && (ch.head === 'skull' || ch.head === 'topknot')) {
    g.beginPath();
    g.moveTo(J.hip[0] - 12 * bw, J.hip[1] - 6); g.lineTo(J.hip[0] + 14 * bw, J.hip[1] - 6);
    g.lineTo((J.kF[0] + J.hip[0]) / 2 + 12, J.kF[1] + (ch.head === 'skull' ? 14 : 0));
    g.lineTo((J.kB[0] + J.hip[0]) / 2 - 12, J.kB[1] + (ch.head === 'skull' ? 22 : 4));
    g.closePath();
    g.fillStyle = C(ch.head === 'skull' ? 'main' : 'alt', back); g.fill(); g.lineWidth = 2.5; g.strokeStyle = OUT; g.stroke();
  }
  // torso
  const tw = 34 * S * bw;
  g.strokeStyle = OUT; g.lineWidth = tw + 5; path([J.hip, J.sh]); g.stroke();
  g.strokeStyle = C('main'); g.lineWidth = tw; g.stroke();
  if (o.xray) {
    g.strokeStyle = OUT; g.lineWidth = 3; path([J.hip, J.neck]); g.stroke();
    for (let i = 3; i < 7; i++) { const q = [J.hip[0] + (J.sh[0] - J.hip[0]) * i / 7, J.hip[1] + (J.sh[1] - J.hip[1]) * i / 7]; path([[q[0] - 11, q[1] + 3], [q[0] + 11, q[1] - 3]]); g.stroke(); }
  } else {
    const dx = J.sh[0] - J.hip[0], dy = J.sh[1] - J.hip[1], l = Math.hypot(dx, dy) || 1, nx = -dy / l, ny = dx / l;
    const bx = J.hip[0] + dx * 0.12, by = J.hip[1] + dy * 0.12, h = tw / 2 - 1;
    g.strokeStyle = C('alt'); g.lineWidth = 7; g.lineCap = 'butt';
    path([[bx - nx * h, by - ny * h], [bx + nx * h, by + ny * h]]); g.stroke();
    g.lineCap = 'round';
  }
  // scarf (Nyx)
  if (ch.head === 'hood' && !o.xray) {
    g.strokeStyle = C('alt'); g.lineWidth = 6;
    g.beginPath(); g.moveTo(J.neck[0], J.neck[1] + 4);
    g.quadraticCurveTo(J.neck[0] - 25, J.neck[1] + 6 + Math.sin(t * 0.15) * 8, J.neck[0] - 50, J.neck[1] + 14 + Math.cos(t * 0.12) * 10);
    g.stroke();
  }
  drawHead(g, ch, J, o, C, OUT, t);
  // front arm
  limb(J.sh, J.eF, J.hF, aw, C('main'), C('skin'));
  dot(J.hF, 8.5 * S * Math.sqrt(bw), C('alt'));
  g.restore();
}

function drawHead(g, ch, J, o, C, OUT, t) {
  const R = 17 * J.S * (ch.head === 'horns' ? 1.08 : 1);
  g.save();
  g.translate(J.head[0], J.head[1]);
  g.rotate(J.ha);
  const circ = (x, y, r, fill) => { g.beginPath(); g.arc(x, y, r, 0, 7); g.fillStyle = fill; g.fill(); g.lineWidth = 2.5; g.strokeStyle = OUT; g.stroke(); };
  const glow = o.xray ? '#dff3ff' : tone(ch.c.glow, { flash: o.flash, dark: o.dark });
  if (o.xray) {
    circ(0, 0, R, '#0a0c14');
    g.fillStyle = OUT; g.beginPath(); g.arc(R * 0.4, -R * 0.1, R * 0.28, 0, 7); g.fill();
    g.fillRect(R * 0.1, R * 0.45, R * 0.7, 3);
    g.restore(); return;
  }
  const w = Math.sin(t * 0.13) * 5;
  switch (ch.head) {
    case 'topknot':
      g.strokeStyle = C('alt'); g.lineWidth = 5;
      g.beginPath(); g.moveTo(-R, -R * 0.35); g.quadraticCurveTo(-R - 16, -R * 0.2 + w, -R - 30, -R * 0.1 - w); g.stroke();
      circ(-R * 0.25, -R * 1.15, R * 0.42, C('hair'));
      circ(0, 0, R, C('skin'));
      g.beginPath(); g.arc(0, 0, R, Math.PI * 1.05, Math.PI * 1.85); g.closePath(); g.fillStyle = C('hair'); g.fill();
      g.strokeStyle = C('alt'); g.lineWidth = 5; g.beginPath(); g.moveTo(-R * 0.95, -R * 0.35); g.lineTo(R * 0.93, -R * 0.38); g.stroke();
      break;
    case 'horns':
      g.fillStyle = C('alt'); g.strokeStyle = OUT; g.lineWidth = 2.5;
      [[R * 0.35, 1], [-R * 0.55, -1]].forEach(([hx, d]) => { g.beginPath(); g.moveTo(hx - 6, -R * 0.75); g.lineTo(hx + d * 5, -R * 1.65); g.lineTo(hx + 7, -R * 0.75); g.closePath(); g.fill(); g.stroke(); });
      circ(0, 0, R, C('skin'));
      g.strokeStyle = C('hair'); g.lineWidth = 5; g.beginPath(); g.moveTo(R * 0.05, -R * 0.3); g.lineTo(R * 0.95, -R * 0.12); g.stroke();
      g.lineWidth = 3; g.beginPath(); g.moveTo(R * 0.3, R * 0.5); g.lineTo(R * 0.85, R * 0.42); g.stroke();
      break;
    case 'hood':
      circ(-R * 0.15, -R * 0.1, R * 1.18, C('main'));
      g.beginPath(); g.ellipse(R * 0.4, R * 0.05, R * 0.55, R * 0.75, 0, 0, 7); g.fillStyle = C('hair'); g.fill();
      break;
    case 'visor':
      g.fillStyle = C('hair'); g.strokeStyle = OUT; g.lineWidth = 2.5;
      g.beginPath(); g.moveTo(R * 0.7, -R * 0.75); g.lineTo(-R * 0.2, -R * 1.6); g.lineTo(-R * 0.3, -R * 1.05); g.lineTo(-R * 1.1, -R * 1.35); g.lineTo(-R * 0.95, -R * 0.5); g.lineTo(-R * 1.5, -R * 0.4 + w * 0.4); g.lineTo(-R * 0.9, 0.2 * R); g.closePath(); g.fill(); g.stroke();
      circ(0, 0, R, C('skin'));
      g.beginPath(); g.arc(0, 0, R, Math.PI * 1.0, Math.PI * 1.8); g.closePath(); g.fillStyle = C('hair'); g.fill();
      break;
    case 'skull':
      circ(-R * 0.25, -R * 0.05, R * 1.2, C('main'));
      circ(R * 0.1, 0, R * 0.92, C('skin'));
      g.fillStyle = '#0a0d0b'; g.beginPath(); g.arc(R * 0.45, -R * 0.12, R * 0.3, 0, 7); g.fill();
      g.strokeStyle = '#0a0d0b'; g.lineWidth = 2;
      for (let i = 0; i < 4; i++) { g.beginPath(); g.moveTo(R * (0.25 + i * 0.2), R * 0.45); g.lineTo(R * (0.25 + i * 0.2), R * 0.75); g.stroke(); }
      break;
    case 'crest':
      g.strokeStyle = OUT; g.lineWidth = 12;
      g.beginPath(); g.moveTo(-R * 0.7, -R * 0.5); g.quadraticCurveTo(-R * 2.2, -R * 0.4 + w, -R * 2.6, R * 1.2 - w); g.stroke();
      g.strokeStyle = C('hair'); g.lineWidth = 8; g.stroke();
      g.strokeStyle = C('alt'); g.lineWidth = 4;
      [[-0.2, -1.9], [-0.7, -1.75], [-1.15, -1.45]].forEach(([fx, fy]) => { g.beginPath(); g.moveTo(-R * 0.3, -R * 0.8); g.lineTo(R * fx, R * fy); g.stroke(); });
      circ(0, 0, R, C('skin'));
      g.beginPath(); g.arc(0, 0, R, Math.PI * 0.95, Math.PI * 1.8); g.closePath(); g.fillStyle = C('hair'); g.fill();
      break;
  }
  // eye / visor
  if (ch.head === 'visor') {
    g.strokeStyle = glow; g.lineWidth = 5; g.beginPath(); g.moveTo(R * 0.05, -R * 0.12); g.lineTo(R * 0.98, -R * 0.12); g.stroke();
  } else if (ch.head === 'hood' || ch.head === 'skull') {
    g.fillStyle = glow; g.shadowColor = glow; g.shadowBlur = 10;
    g.beginPath(); g.arc(R * 0.5, -R * 0.12, R * 0.14, 0, 7); g.fill(); g.shadowBlur = 0;
  } else {
    g.strokeStyle = '#140d0b'; g.lineWidth = 3; g.beginPath(); g.moveTo(R * 0.4, -R * 0.1); g.lineTo(R * 0.72, -R * 0.14); g.stroke();
  }
  g.restore();
}
