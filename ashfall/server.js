#!/usr/bin/env node
// ASHFALL — zero-dependency game server.
// Serves the projector screen (/) and phone controller (/pad) and relays
// controller input to the screen over WebSockets. Run: node server.js
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');

const PORT = +process.env.PORT || 3000;
const PUB = path.join(__dirname, 'public');
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css', '.png': 'image/png', '.ico': 'image/x-icon' };

function lanIPs() {
  const out = [];
  for (const list of Object.values(os.networkInterfaces())) {
    for (const i of list || []) if (i.family === 'IPv4' && !i.internal) out.push(i.address);
  }
  // Prefer typical home-network ranges.
  return out.sort((a, b) => (/^192\.168\./.test(b) - /^192\.168\./.test(a)) || (/^10\./.test(b) - /^10\./.test(a)));
}

const server = http.createServer((req, res) => {
  let p = decodeURIComponent((req.url || '/').split('?')[0]);
  if (p === '/') p = '/index.html';
  if (p === '/pad') p = '/pad.html';
  const file = path.normalize(path.join(PUB, p));
  if (!file.startsWith(PUB + path.sep)) { res.writeHead(403); return res.end(); }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404, { 'Content-Type': 'text/plain' }); return res.end('Not found'); }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(data);
  });
});

// ---------- minimal WebSocket (RFC 6455, text frames only) ----------
function wsAccept(req, socket) {
  const key = req.headers['sec-websocket-key'];
  if (!key) { socket.destroy(); return null; }
  const acc = crypto.createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
  socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + acc + '\r\n\r\n');
  socket.setNoDelay(true);
  const ws = { open: true, last: Date.now(), onmessage: null, onclose: null };
  const frame = (op, payload) => {
    if (!ws.open || socket.destroyed) return;
    const n = payload.length;
    const head = n < 126 ? Buffer.from([0x80 | op, n]) : Buffer.from([0x80 | op, 126, n >> 8, n & 255]);
    socket.write(Buffer.concat([head, payload]));
  };
  ws.send = (s) => frame(1, Buffer.from(s, 'utf8'));
  ws.ping = () => frame(9, Buffer.alloc(0));
  ws.close = () => {
    if (!ws.open) return;
    ws.open = false;
    socket.destroy();
    if (ws.onclose) ws.onclose();
  };
  let buf = Buffer.alloc(0), frags = [];
  socket.on('data', (d) => {
    ws.last = Date.now();
    buf = Buffer.concat([buf, d]);
    if (buf.length > 65536) return ws.close();
    for (;;) {
      if (buf.length < 2) return;
      const fin = buf[0] & 0x80, op = buf[0] & 0x0f;
      let len = buf[1] & 0x7f, off = 2;
      if (!(buf[1] & 0x80) || len === 127) return ws.close();
      if (len === 126) { if (buf.length < 4) return; len = buf.readUInt16BE(2); off = 4; }
      if (buf.length < off + 4 + len) return;
      const mask = buf.subarray(off, off + 4);
      const payload = Buffer.from(buf.subarray(off + 4, off + 4 + len));
      for (let i = 0; i < len; i++) payload[i] ^= mask[i & 3];
      buf = buf.subarray(off + 4 + len);
      if (op === 8) return ws.close();
      if (op === 9) { frame(10, payload); continue; }
      if (op === 10) continue;
      frags.push(payload);
      if (fin) {
        const msg = Buffer.concat(frags).toString('utf8');
        frags = [];
        if (ws.onmessage) ws.onmessage(msg);
      }
    }
  });
  socket.on('close', ws.close);
  socket.on('error', ws.close);
  return ws;
}

// ---------- rooms: one screen + up to two pads ----------
const rooms = new Map(); // code -> { screen, pads:[ws,ws], ids:[id,id], timer }
const all = new Set();

function newCode() {
  const A = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  for (;;) {
    let c = '';
    for (let i = 0; i < 4; i++) c += A[crypto.randomInt(A.length)];
    if (!rooms.has(c)) return c;
  }
}

server.on('upgrade', (req, socket) => {
  const q = new URL(req.url, 'http://x').searchParams;
  const ws = wsAccept(req, socket);
  if (!ws) return;
  all.add(ws);
  const role = q.get('role');
  const send = (to, obj) => { if (to && to.open) to.send(JSON.stringify(obj)); };

  if (role === 'screen') {
    let code = (q.get('room') || '').toUpperCase();
    let room = /^[A-Z]{4}$/.test(code) ? rooms.get(code) : null;
    if (room && room.screen && room.screen.open) room = null; // code in use by a live screen
    if (!room) {
      if (!/^[A-Z]{4}$/.test(code) || rooms.has(code)) code = newCode();
      room = { screen: null, pads: [null, null], ids: [null, null], timer: null };
      rooms.set(code, room);
    }
    clearTimeout(room.timer);
    room.screen = ws;
    send(ws, { t: 'room', code, ips: lanIPs(), port: PORT });
    room.pads.forEach((p, s) => { if (p && p.open) send(ws, { t: 'join', s }); });
    ws.onmessage = (msg) => {
      let m; try { m = JSON.parse(msg); } catch (e) { return; }
      room.pads.forEach((p, s) => { if (m.to === s || m.to === -1) send(p, m); });
    };
    ws.onclose = () => {
      all.delete(ws);
      if (room.screen !== ws) return;
      room.screen = null;
      room.pads.forEach((p) => send(p, { t: 'err', m: 'noscreen' }));
      room.timer = setTimeout(() => {
        if (room.screen) return;
        room.pads.forEach((p) => p && p.close());
        rooms.delete(code);
      }, 120000);
    };
    return;
  }

  if (role === 'pad') {
    const code = (q.get('room') || '').toUpperCase();
    const id = (q.get('id') || '').slice(0, 40);
    const room = rooms.get(code) || (rooms.size === 1 ? rooms.values().next().value : null);
    if (!room) { send(ws, { t: 'err', m: 'noroom' }); return ws.close(); }
    let s = id ? room.ids.indexOf(id) : -1;
    if (s < 0) s = room.pads.findIndex((p) => !p || !p.open);
    if (s < 0) { send(ws, { t: 'err', m: 'full' }); return ws.close(); }
    const old = room.pads[s];
    room.pads[s] = ws;
    room.ids[s] = id || null;
    if (old && old.open) old.close();
    send(ws, { t: 'slot', s });
    if (!room.screen) send(ws, { t: 'err', m: 'noscreen' });
    send(room.screen, { t: 'join', s });
    ws.onmessage = (msg) => {
      if (msg.length > 200) return;
      let d; try { d = JSON.parse(msg); } catch (e) { return; }
      send(room.screen, { t: 'i', s, d });
    };
    ws.onclose = () => {
      all.delete(ws);
      if (room.pads[s] !== ws) return;
      room.pads[s] = null;
      send(room.screen, { t: 'leave', s });
    };
    return;
  }
  ws.close();
});

// Drop connections that went silent (phone locked, Wi-Fi dropped).
setInterval(() => {
  const now = Date.now();
  for (const ws of all) {
    if (now - ws.last > 20000) ws.close(); else ws.ping();
  }
}, 5000);

server.listen(PORT, '0.0.0.0', () => {
  const ips = lanIPs();
  console.log('\n  ASHFALL is running.\n');
  console.log('  Projector / TV screen:');
  console.log('    http://localhost:' + PORT + '   (on this computer)');
  ips.forEach((ip) => console.log('    http://' + ip + ':' + PORT + '   (from any device on your Wi-Fi)'));
  console.log('\n  Phones: scan the QR code shown on the screen.\n');
});
