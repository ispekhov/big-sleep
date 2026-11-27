// Synthesised sound effects, announcer and a small music loop (WebAudio, no assets).
'use strict';
const SFX = (() => {
  let ac = null, master = null, noiseBuf = null, musicTimer = null, step = 0;
  function init() {
    if (ac) return ac;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ac = new AC();
    master = ac.createGain();
    master.gain.value = 0.6;
    master.connect(ac.destination);
    noiseBuf = ac.createBuffer(1, ac.sampleRate, ac.sampleRate);
    const d = noiseBuf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    return ac;
  }
  function unlock() { if (init() && ac.state === 'suspended') ac.resume(); }
  function locked() { return !ac || ac.state !== 'running'; }

  function tone(f0, f1, dur, type, vol, delay) {
    if (locked()) return;
    const t = ac.currentTime + (delay || 0), o = ac.createOscillator(), g = ac.createGain();
    o.type = type || 'sine';
    o.frequency.setValueAtTime(f0, t);
    o.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t + dur);
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    o.connect(g); g.connect(master);
    o.start(t); o.stop(t + dur + 0.02);
  }
  function noise(dur, vol, freq, type, delay, f1) {
    if (locked()) return;
    const t = ac.currentTime + (delay || 0), s = ac.createBufferSource(), fl = ac.createBiquadFilter(), g = ac.createGain();
    s.buffer = noiseBuf; s.loop = true;
    fl.type = type || 'lowpass';
    fl.frequency.setValueAtTime(freq, t);
    if (f1) fl.frequency.exponentialRampToValueAtTime(f1, t + dur);
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    s.connect(fl); fl.connect(g); g.connect(master);
    s.start(t, Math.random()); s.stop(t + dur + 0.02);
  }

  const S = {
    hit() { noise(0.12, 0.8, 1800, 'lowpass'); tone(160, 50, 0.12, 'sine', 0.8); },
    heavy() { noise(0.25, 1, 1200, 'lowpass'); tone(120, 30, 0.3, 'sine', 1); tone(300, 60, 0.1, 'square', 0.25); },
    block() { noise(0.06, 0.5, 3000, 'highpass'); tone(700, 400, 0.06, 'square', 0.15); },
    whoosh() { noise(0.14, 0.25, 500, 'bandpass', 0, 2400); },
    jump() { noise(0.12, 0.15, 300, 'bandpass', 0, 900); },
    land() { noise(0.1, 0.4, 300, 'lowpass'); tone(80, 40, 0.1, 'sine', 0.5); },
    fire() { noise(0.4, 0.45, 400, 'bandpass', 0, 2500); tone(200, 500, 0.3, 'sawtooth', 0.1); },
    zap() { tone(1400, 120, 0.25, 'sawtooth', 0.25); noise(0.2, 0.3, 5000, 'highpass'); },
    dark() { tone(90, 260, 0.4, 'sawtooth', 0.2); noise(0.4, 0.2, 700, 'bandpass', 0, 200); },
    wind() { noise(0.5, 0.4, 600, 'bandpass', 0, 1800); },
    quake() { noise(0.6, 0.9, 200, 'lowpass'); tone(60, 25, 0.6, 'sine', 1); },
    slash() { noise(0.1, 0.5, 6000, 'highpass', 0, 2000); tone(2400, 600, 0.1, 'sawtooth', 0.12); },
    thunder() { noise(1.2, 1, 3000, 'lowpass', 0, 100); tone(70, 25, 1, 'sine', 0.9); },
    boom() { noise(0.9, 1, 900, 'lowpass', 0, 60); tone(100, 20, 0.9, 'sine', 1); },
    ko() { tone(220, 40, 0.8, 'sawtooth', 0.4); noise(0.5, 0.8, 1000, 'lowpass'); },
    blip() { tone(660, 660, 0.05, 'square', 0.12); },
    ok() { tone(520, 520, 0.08, 'square', 0.15); tone(780, 780, 0.12, 'square', 0.15, 0.08); },
    back() { tone(400, 200, 0.12, 'square', 0.12); },
    gong() { tone(110, 105, 2.2, 'sine', 0.7); tone(277, 270, 1.6, 'sine', 0.25); tone(415, 400, 1.1, 'triangle', 0.15); noise(0.3, 0.3, 900, 'bandpass'); },
  };
  function play(name) { if (S[name]) try { S[name](); } catch (e) { /* audio is optional */ } }

  function say(text) {
    try {
      if (!window.speechSynthesis) return;
      const u = new SpeechSynthesisUtterance(text);
      u.pitch = 0.2; u.rate = 0.85; u.volume = 1;
      speechSynthesis.cancel();
      speechSynthesis.speak(u);
    } catch (e) { /* optional */ }
  }

  // 16-step dark loop: kick, hat, bass.
  const BASS = [55, 0, 55, 0, 0, 55, 0, 65.4, 55, 0, 55, 0, 0, 49, 0, 51.9];
  function tick() {
    if (locked()) return;
    const s = step++ % 16;
    if (s % 4 === 0) tone(130, 38, 0.18, 'sine', 0.55);
    if (s % 4 === 2) noise(0.04, 0.08, 7000, 'highpass');
    if (s === 4 || s === 12) noise(0.12, 0.2, 1500, 'bandpass');
    if (BASS[s]) tone(BASS[s], BASS[s], 0.16, 'sawtooth', 0.13);
  }
  function music(on) {
    clearInterval(musicTimer); musicTimer = null;
    if (on) { step = 0; musicTimer = setInterval(tick, 140); }
  }
  return { play, say, music, unlock, locked };
})();
