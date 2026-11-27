// Tiny QR encoder: byte mode, error-correction level L, versions 1-5.
// qrMatrix(text) -> array of rows of 0/1, or null if the text is too long.
'use strict';
function qrMatrix(text) {
  const bytes = Array.from(new TextEncoder().encode(text));
  const VER = [null, [26, 7], [44, 10], [70, 15], [100, 20], [134, 26]]; // [total codewords, ec codewords]
  let v = 1;
  while (v <= 5 && bytes.length > VER[v][0] - VER[v][1] - 2) v++;
  if (v > 5) return null;
  const ecN = VER[v][1], dataN = VER[v][0] - ecN, size = 17 + 4 * v;

  // --- data codewords ---
  const bits = [];
  const put = (val, n) => { for (let i = n - 1; i >= 0; i--) bits.push((val >> i) & 1); };
  put(4, 4); put(bytes.length, 8);
  bytes.forEach((b) => put(b, 8));
  put(0, Math.min(4, dataN * 8 - bits.length));
  while (bits.length % 8) bits.push(0);
  const data = [];
  for (let i = 0; i < bits.length; i += 8) data.push(parseInt(bits.slice(i, i + 8).join(''), 2));
  for (let pad = 0xec; data.length < dataN; pad ^= 0xec ^ 0x11) data.push(pad);

  // --- Reed-Solomon ---
  const exp = new Uint8Array(512), log = new Uint8Array(256);
  for (let i = 0, x = 1; i < 255; i++) { exp[i] = x; log[x] = i; x <<= 1; if (x & 256) x ^= 0x11d; }
  for (let i = 255; i < 512; i++) exp[i] = exp[i - 255];
  const mul = (a, b) => (a && b ? exp[log[a] + log[b]] : 0);
  let gen = [1];
  for (let i = 0; i < ecN; i++) {
    const ng = new Array(gen.length + 1).fill(0);
    for (let j = 0; j < gen.length; j++) { ng[j] ^= gen[j]; ng[j + 1] ^= mul(gen[j], exp[i]); }
    gen = ng;
  }
  const rem = new Array(ecN).fill(0);
  for (const d of data) {
    const f = d ^ rem.shift();
    rem.push(0);
    for (let j = 0; j < ecN; j++) rem[j] ^= mul(gen[j + 1], f);
  }
  const code = data.concat(rem);

  // --- function patterns ---
  const m = [], fn = [];
  for (let i = 0; i < size; i++) { m.push(new Array(size).fill(0)); fn.push(new Array(size).fill(false)); }
  const set = (x, y, val) => { if (x >= 0 && y >= 0 && x < size && y < size) { m[y][x] = val ? 1 : 0; fn[y][x] = true; } };
  const finder = (cx, cy) => {
    for (let dy = -1; dy <= 7; dy++) for (let dx = -1; dx <= 7; dx++) {
      const inside = dx >= 0 && dx <= 6 && dy >= 0 && dy <= 6;
      set(cx + dx, cy + dy, inside && (dx === 0 || dx === 6 || dy === 0 || dy === 6 || (dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4)));
    }
  };
  finder(0, 0); finder(size - 7, 0); finder(0, size - 7);
  for (let i = 8; i < size - 8; i++) { set(i, 6, i % 2 === 0); set(6, i, i % 2 === 0); }
  if (v >= 2) {
    const c = size - 7;
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) set(c + dx, c + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
  }
  // format info (level L, mask 0)
  let fd = 1 << 3, fr = fd;
  for (let i = 0; i < 10; i++) fr = (fr << 1) ^ ((fr >>> 9) * 0x537);
  const fmt = ((fd << 10) | fr) ^ 0x5412;
  const fb = (i) => (fmt >>> i) & 1;
  for (let i = 0; i <= 5; i++) set(8, i, fb(i));
  set(8, 7, fb(6)); set(8, 8, fb(7)); set(7, 8, fb(8));
  for (let i = 9; i < 15; i++) set(14 - i, 8, fb(i));
  for (let i = 0; i < 8; i++) set(size - 1 - i, 8, fb(i));
  for (let i = 8; i < 15; i++) set(8, size - 15 + i, fb(i));
  set(8, size - 8, 1);

  // --- data placement + mask 0 ---
  let k = 0;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let vert = 0; vert < size; vert++) {
      for (let j = 0; j < 2; j++) {
        const x = right - j, up = ((right + 1) & 2) === 0, y = up ? size - 1 - vert : vert;
        if (fn[y][x]) continue;
        let bit = 0;
        if (k < code.length * 8) { bit = (code[k >>> 3] >>> (7 - (k & 7))) & 1; k++; }
        m[y][x] = bit ^ ((x + y) % 2 === 0 ? 1 : 0);
      }
    }
  }
  return m;
}
if (typeof module !== 'undefined') module.exports = qrMatrix;
