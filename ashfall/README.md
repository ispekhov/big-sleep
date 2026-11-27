# ASHFALL — Tournament of Cinders

An original 1v1 fighting game for the living room. The projector (or TV) is the
arena, and two phones on the same Wi-Fi are the controllers. No app install, no
accounts, no dependencies — just Node.js.

Six fighters, two special moves each, best-of-three rounds, three stages, a CPU
opponent when only one phone is connected, and a finisher for every fighter.

## Run it

You need one computer on your home Wi-Fi to host the game (Mac, Windows, Linux,
Raspberry Pi — anything with [Node.js](https://nodejs.org) 18+).

```
cd ashfall
node server.js
```

The terminal prints two addresses:

1. **Screen** — open it on whatever drives the projector:
   - laptop plugged into / mirrored to the projector: open `http://localhost:3000`
   - smart projector with its own browser: open `http://<computer-ip>:3000`
   - press `F11` (or the browser's full-screen button) and click once to turn sound on
2. **Phones** — scan the QR code on the screen with the iPhone camera, open the
   link in Safari and turn the phone sideways. First phone is Player 1, second is Player 2.

Tip: in Safari use Share → *Add to Home Screen* and launch it from there to get a
full-screen controller without the address bar.

If the phones can't connect, check that they are on the same Wi-Fi as the
computer (not a guest network) and that the computer's firewall allows incoming
connections for Node on port 3000. Use `PORT=8080 node server.js` for another port.

## Controls (phone)

| Input | Action |
| --- | --- |
| Stick ◀ ▶ | walk |
| Stick ▲ (also diagonals) | jump |
| Stick ▼ | crouch |
| PUNCH / KICK | high punch / mid kick |
| ▼ + PUNCH | uppercut (launches) |
| ▼ + KICK | sweep (must be blocked crouching) |
| PUNCH / KICK in the air | jump attacks (must be blocked standing) |
| BLOCK (hold) | block; hold ▼ too for a low block |
| SPECIAL | special move 1 |
| ▼ + SPECIAL | special move 2 |

The bar under your name shows when your special is ready again.

### Finishers

Win the deciding round and your opponent is left dazed: **END IT!** Enter your
fighter's sequence (it is shown on the winner's phone) before the timer runs out.

| Fighter | Specials | Finisher |
| --- | --- | --- |
| Kaida | Cinder Shot · Flame Rush | ↓ ↓ PUNCH — *Ash to Ash* |
| Brakk | Rampage · Faultline | ↓ ↑ KICK — *Gravestone* |
| Nyx | Fang · Shade Step | ↑ ↓ SPECIAL — *Thousand Cuts* |
| Iona | Ball Lightning · Arc Rise | ↑ ↑ PUNCH — *Skyfall* |
| Morrow | Wailing Skull · Grave Grasp | ↓ ↓ SPECIAL — *Six Feet Under* |
| Sable | Gale · Talon Dive | ↑ ↓ KICK — *Eye of the Storm* |

## Keyboard (for testing without phones)

Player 1: `W A S D` move, `F` punch, `G` kick, `H` block, `J` special.
Player 2: arrow keys, `M` punch, `,` kick, `.` block, `/` special.

## How it works

- `server.js` — static file server plus a tiny hand-rolled WebSocket relay (no npm packages).
- `public/index.html` + `game.js` — the game itself; runs entirely in the screen's browser.
- `public/pad.html` — the touch controller; sends button state to the screen through the server.
- `public/fighters.js` — roster, move data and the procedural fighter renderer (no image assets).
- `public/sfx.js` — synthesised sound effects and music. `public/qr.js` — QR code generator.
