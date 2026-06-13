"""Embedded single-page web console (served by main.py).

Kept as a Python constant so it is always bundled into serverless
deployments where non-.py data files are not import-traced.
Source of truth; encounter/static/index.html mirrors it for reference.
"""

from html import escape as _esc


def render_brand_page(
    brand_id: int,
    brand_name: str,
    website: str | None,
    products,
    undo_ids: list[int] | None = None,
) -> str:
    """A standalone, server-rendered page listing one brand's products.

    Plain HTML + native forms — no JavaScript required to view, navigate,
    select, delete, or undo — so it works in every browser. Tick products and
    press "Delete selected"; an Undo banner appears right after so a deletion
    is reversible (deletes are soft — hidden, not destroyed).
    """
    undo_ids = undo_ids or []
    cards = []
    for p in products:
        img = p.images[0].image_url if getattr(p, "images", None) else ""
        price = f"{p.currency or '$'}{p.price:,.0f}" if p.price is not None else "—"
        cat = f" · {_esc(p.category)}" if p.category else ""
        review = '<span class="rev">needs review</span>' if p.needs_review else ""
        src = (
            f'<a class="src" href="{_esc(p.product_url)}" target="_blank" '
            f'rel="noopener">View on site ↗</a>'
            if p.product_url
            else ""
        )
        cards.append(
            '<div class="card">'
            f'<input class="sel" type="checkbox" name="ids" value="{p.id}" '
            f'form="delform" aria-label="Select product"/>'
            f'<img src="{_esc(img)}" loading="lazy" '
            'onerror="this.style.opacity=.12"/>'
            f'<div class="nm">{_esc(p.name or "Untitled")}</div>'
            f'<div class="meta">{_esc(price)}{cat}</div>'
            f'{review}{src}</div>'
        )
    grid = "\n".join(cards) or '<p class="muted">No products yet for this brand.</p>'
    site = (
        f'<a class="muted" href="{_esc(website)}" target="_blank" '
        f'rel="noopener">{_esc(website)} ↗</a>'
        if website
        else ""
    )
    purge = (
        f'<form method="post" action="/b/{brand_id}/purge-junk" style="margin:0" '
        f"onsubmit=\"return confirm('Remove obvious non-product pages "
        f"(no price + page-like name or icon image)? You can undo afterwards.')\">"
        f'<button class="purge" type="submit">Remove non-products</button></form>'
    )
    undo = ""
    countdown_js = ""
    if undo_ids:
        ids_val = ",".join(str(i) for i in undo_ids)
        n = len(undo_ids)
        undo = (
            f'<div id="undobar" class="undobar" data-ids="{ids_val}" '
            f'data-commit="/b/{brand_id}/commit-delete">'
            f'Removed {n} product{"" if n == 1 else "s"}.'
            f'<form method="post" action="/b/{brand_id}/restore" '
            f'style="display:inline;margin:0 0 0 10px">'
            f'<input type="hidden" name="ids" value="{ids_val}"/>'
            f'<button class="undo" type="submit">Undo</button></form>'
            f'<span class="muted" style="margin-left:10px">removing in '
            f'<span id="undosec">10</span>s…</span></div>'
        )
        # Best-effort: after 10s with no Undo, permanently delete (Undo is a
        # plain form submit that navigates away, cancelling this timer). If JS
        # is unavailable the items simply stay hidden (still "deleted") — safe.
        countdown_js = (
            "<script>(function(){var b=document.getElementById('undobar');"
            "if(!b)return;var ids=b.getAttribute('data-ids'),"
            "url=b.getAttribute('data-commit'),n=10,"
            "el=document.getElementById('undosec');"
            "var t=setInterval(function(){n--;if(el)el.textContent=n>0?n:0;"
            "if(n<=0){clearInterval(t);try{fetch(url,{method:'POST',headers:"
            "{'Content-Type':'application/x-www-form-urlencoded'},"
            "body:'ids='+encodeURIComponent(ids),keepalive:true});}catch(e){}"
            "b.style.display='none';}},1000);})();</script>"
        )
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{_esc(brand_name)} — Encounter</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font:14px/1.5 system-ui,sans-serif; background:#0f1115; color:#e8eaed; }}
  header {{ padding:14px 24px; border-bottom:1px solid #272b35; display:flex; flex-wrap:wrap; align-items:center; gap:12px; position:sticky; top:0; background:#0f1115; z-index:2; }}
  header h1 {{ font-size:20px; margin:0; }}
  a {{ color:#6ea8fe; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  .muted {{ color:#9aa0aa; font-size:13px; }}
  .back {{ font-size:14px; }}
  .spacer {{ flex:1; }}
  main {{ padding:24px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:14px; }}
  .card {{ position:relative; border:1px solid #272b35; border-radius:10px; padding:10px; background:#181b22; display:flex; flex-direction:column; }}
  .card img {{ width:100%; height:170px; object-fit:cover; border-radius:7px; background:#000; }}
  .sel {{ position:absolute; top:14px; left:14px; width:22px; height:22px; cursor:pointer; z-index:1; accent-color:#6ea8fe; }}
  .nm {{ margin-top:8px; font-weight:600; }}
  .meta {{ color:#9aa0aa; font-size:13px; margin-top:2px; }}
  .rev {{ display:inline-block; margin-top:6px; font-size:10px; padding:1px 6px; border-radius:99px; background:#3a2d12; color:#fbbf24; }}
  .src {{ margin-top:8px; font-size:13px; }}
  .btn {{ border-radius:7px; padding:7px 12px; font-size:13px; cursor:pointer; border:1px solid #272b35; }}
  .del-sel {{ background:#dc2626; color:#fff; border:none; }}
  .del-sel:hover {{ background:#ef4444; }}
  .purge {{ background:#3a2d12; color:#fbbf24; border:1px solid #5b4a1d; border-radius:7px; padding:7px 12px; font-size:13px; cursor:pointer; }}
  .purge:hover {{ background:#4a3917; }}
  .undobar {{ padding:10px 24px; background:#10261a; color:#86efac; border-bottom:1px solid #1d5b39; }}
  .undo {{ background:none; border:1px solid #1d5b39; color:#86efac; border-radius:6px; padding:3px 10px; font-size:13px; cursor:pointer; margin-left:8px; }}
  .undo:hover {{ background:#15351f; }}
</style></head>
<body>
<header>
  <a class="back" href="/">← All brands</a>
  <h1>{_esc(brand_name)}</h1>
  <span class="muted">{len(products)} products</span>
  {site}
  <span class="spacer"></span>
  <label class="muted" style="display:flex;align-items:center;gap:5px">
    <input type="checkbox" onclick="document.querySelectorAll('.sel').forEach(c=>c.checked=this.checked)"/> Select all
  </label>
  <button class="btn del-sel" type="submit" form="delform"
    onclick="if(!document.querySelector('.sel:checked')){{alert('Tick some products first.');return false;}}">
    Delete selected</button>
  {purge}
</header>
{undo}
<form id="delform" method="post" action="/b/{brand_id}/delete-selected">
<main class="grid">
{grid}
</main>
</form>
{countdown_js}
</body></html>"""


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Encounter — Console</title>
<style>
  :root {
    --bg: #0f1115; --panel: #181b22; --line: #272b35; --txt: #e8eaed;
    --muted: #9aa0aa; --accent: #6ea8fe; --good: #4ade80; --warn: #fbbf24;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font: 14px/1.5 system-ui, sans-serif; background: var(--bg); color: var(--txt); }
  header { padding: 18px 24px; border-bottom: 1px solid var(--line); display: flex; align-items: baseline; gap: 12px; }
  header h1 { font-size: 18px; margin: 0; }
  header span { color: var(--muted); font-size: 13px; }
  nav { display: flex; gap: 4px; padding: 0 24px; border-bottom: 1px solid var(--line); }
  nav button { background: none; border: none; color: var(--muted); padding: 12px 16px; cursor: pointer; border-bottom: 2px solid transparent; font-size: 14px; }
  nav button.active { color: var(--txt); border-bottom-color: var(--accent); }
  main { padding: 24px; max-width: 1100px; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 20px; margin-bottom: 20px; }
  h2 { margin: 0 0 14px; font-size: 15px; }
  label { display: block; color: var(--muted); font-size: 12px; margin: 10px 0 4px; }
  input, textarea, select { width: 100%; background: #11141a; border: 1px solid var(--line); color: var(--txt); border-radius: 7px; padding: 9px 11px; font-size: 14px; }
  button.go { background: var(--accent); color: #06101f; border: none; border-radius: 7px; padding: 10px 18px; font-weight: 600; cursor: pointer; margin-top: 14px; }
  button.go:disabled { opacity: .5; cursor: default; }
  .row { display: flex; gap: 16px; flex-wrap: wrap; }
  .row > div { flex: 1; min-width: 160px; }
  .summary { display: flex; gap: 28px; flex-wrap: wrap; margin-top: 8px; }
  .summary b { display: block; font-size: 26px; color: var(--accent); }
  .summary small { color: var(--muted); }
  .card { display: flex; gap: 16px; border: 1px solid var(--line); border-radius: 9px; padding: 14px; margin-bottom: 12px; background: #11141a; }
  .card img { width: 120px; height: 120px; object-fit: cover; border-radius: 7px; background: #000; }
  .conf { font-weight: 700; }
  .conf.high { color: var(--good); } .conf.mid { color: var(--warn); } .conf.low { color: #f87171; }
  .pill { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 99px; background: #222733; color: var(--muted); margin-right: 6px; }
  .muted { color: var(--muted); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
  .grid .thumb { border: 1px solid var(--line); border-radius: 8px; padding: 8px; background: #11141a; position: relative; }
  .grid .thumb img { width: 100%; height: 110px; object-fit: cover; border-radius: 6px; }
  .err { color: #f87171; margin-top: 10px; }
  .ok { color: var(--good); margin-top: 10px; }
  /* live import progress */
  .progress { margin-top: 16px; }
  .bar { height: 10px; background: #11141a; border: 1px solid var(--line); border-radius: 99px; overflow: hidden; }
  .bar > i { display: block; height: 100%; width: 32%; background: var(--accent); border-radius: 99px; animation: slide 1.1s ease-in-out infinite; }
  @keyframes slide { 0% { margin-left: -32%; } 100% { margin-left: 100%; } }
  .tick { margin-top: 9px; color: var(--muted); font-variant-numeric: tabular-nums; }
  .tick b { color: var(--accent); font-size: 18px; }
  /* catalogue QA */
  .badge-rev { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 99px; background: #3a2d12; color: var(--warn); margin-top: 4px; }
  .del { background: none; border: 1px solid var(--line); color: var(--muted); border-radius: 6px; padding: 3px 7px; cursor: pointer; font-size: 11px; margin-top: 8px; width: 100%; }
  .del:hover { color: #f87171; border-color: #f87171; }
</style>
</head>
<body>
<header>
  <h1>Encounter</h1><span id="health">Product Recognition Console</span>
</header>
<div id="errbar" style="display:none;background:#3a1212;color:#f9a8a8;padding:8px 24px;font-size:13px;border-bottom:1px solid #5b1d1d;"></div>
<nav>
  <button data-tab="import" class="active">Brand Import</button>
  <button data-tab="catalogue">Catalogue</button>
  <button data-tab="search">Visual Search</button>
  <button data-tab="review">Review Queue</button>
</nav>
<main>
  <!-- IMPORT -->
  <section id="tab-import">
    <div class="panel">
      <h2>Import a brand</h2>
      <label>Brand website URL</label>
      <input id="import-url" placeholder="https://www.tomdixon.net" />
      <div class="row">
        <div>
          <label>Max pages to crawl (optional)</label>
          <input id="import-max" type="number" placeholder="200" />
        </div>
      </div>
      <button class="go" id="import-go">Import</button>
      <div id="import-out"></div>
    </div>
  </section>

  <!-- CATALOGUE -->
  <section id="tab-catalogue" hidden>
    <div class="panel">
      <h2>Catalogue by brand</h2>
      <p class="muted">Pick a brand to check what was extracted. Use “Not a product” to drop swatches, banners, or anything that isn't a real product.</p>
      <div class="row">
        <div><label>Jump to brand</label>
          <select id="cat-brand"><option value="">— choose a brand —</option></select></div>
        <div><label>&nbsp;</label><button class="go" id="cat-refresh" style="margin-top:0">Refresh brands</button></div>
      </div>
      <div id="brand-count" class="muted" style="margin-top:8px"></div>
      <div id="brand-cards" class="grid" style="margin-top:14px"></div>
      <div id="cat-detail" hidden style="margin-top:14px">
        <a href="#" id="cat-back" class="muted">← all brands</a>
        <h2 id="cat-title" style="margin:10px 0 4px"></h2>
        <div id="cat-count" class="muted"></div>
        <div id="cat-out" class="grid" style="margin-top:10px"></div>
      </div>
    </div>
  </section>

  <!-- SEARCH -->
  <section id="tab-search" hidden>
    <div class="panel">
      <h2>Identify a photo</h2>
      <label>Upload a photo of a design object</label>
      <input id="search-file" type="file" accept="image/*" />
      <button class="go" id="search-go">Search</button>
      <div id="search-out"></div>
    </div>
  </section>

  <!-- REVIEW -->
  <section id="tab-review" hidden>
    <div class="panel">
      <h2>Products needing review</h2>
      <p class="muted">Importer-flagged products with incomplete data or suspicious prices. Fix fields and resolve, or drop non-products.</p>
      <button class="go" id="review-refresh">Refresh</button>
      <div id="review-out"></div>
    </div>
  </section>
</main>

<script>
const $ = (s) => document.querySelector(s);
// Surface any runtime error on-screen (so issues are visible without a console).
function showErr(msg) {
  const b = document.getElementById('errbar');
  if (b) { b.style.display = 'block'; b.textContent = String(msg); }
}
window.addEventListener('error', (e) => showErr('Error: ' + (e.message || e.error)));
window.addEventListener('unhandledrejection', (e) =>
  showErr('Error: ' + ((e.reason && e.reason.message) || e.reason)));
const api = (p, opt) => fetch(p, opt).then(async r => {
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = body.detail;
    throw new Error(typeof d === 'string' ? d : (d ? JSON.stringify(d) : r.statusText));
  }
  return body;
});

// tabs
document.querySelectorAll('nav button').forEach(b => b.onclick = () => {
  document.querySelectorAll('nav button').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  ['import','catalogue','search','review'].forEach(t => $('#tab-'+t).hidden = (t !== b.dataset.tab));
  if (b.dataset.tab === 'review') loadReview();
  if (b.dataset.tab === 'catalogue') loadCatalogue();
});

// health
api('/health').then(h => {
  $('#health').textContent =
    `embedder=${h.embedder} · vectors=${h.indexed_vectors} · storage=${h.storage_backend}`;
}).catch(()=>{});

const confClass = (c) => c >= 0.9 ? 'high' : c >= 0.6 ? 'mid' : 'low';
const money = (p, c) => p == null ? '' : `${c||'$'}${Number(p).toLocaleString()}`;

// IMPORT — fire the import and watch the catalogue fill up live.
$('#import-go').onclick = async () => {
  const url = $('#import-url').value.trim();
  if (!url) return;
  const btn = $('#import-go'); btn.disabled = true;
  const max = $('#import-max').value;
  const t0 = Date.now();
  $('#import-out').innerHTML = `
    <div class="progress">
      <div class="bar"><i></i></div>
      <div class="tick" id="import-tick"><b>0</b> products imported</div>
      <p class="muted" id="import-note">Crawling ${url} … large catalogues take a minute or two. You can keep using other tabs.</p>
    </div>`;
  let polling = true;
  const tick = $('#import-tick');
  const poll = async () => {
    while (polling) {
      try {
        const p = await api('/brands/import-progress?url=' + encodeURIComponent(url));
        const secs = Math.round((Date.now() - t0) / 1000);
        tick.innerHTML = `<b>${p.products}</b> products · ${p.images} images`
          + (p.needs_review ? ` · ${p.needs_review} to review` : '')
          + ` · ${secs}s`;
      } catch (e) {}
      await new Promise(r => setTimeout(r, 1500));
    }
  };
  poll();
  try {
    const q = '/brands/import?url=' + encodeURIComponent(url)
      + (max ? '&max_pages=' + Number(max) : '');
    const s = await api(q);
    polling = false;
    $('#import-out').innerHTML = `
      <div class="summary">
        <div><b>${s.products_imported}</b><small>products imported</small></div>
        <div><b>${s.images_imported}</b><small>images imported</small></div>
        <div><b>${s.products_need_review}</b><small>need review</small></div>
        <div><b>${s.pages_crawled}</b><small>pages crawled</small></div>
      </div>
      <p class="ok">${s.brand}: ${s.message}</p>
      <p class="muted">Open the <a href="#" id="go-cat">Catalogue</a> to eyeball what was extracted.</p>`;
    const gc = $('#go-cat');
    if (gc) gc.onclick = (e) => { e.preventDefault();
      document.querySelector('nav button[data-tab=catalogue]').click(); };
  } catch (e) {
    polling = false;
    $('#import-out').innerHTML = `<p class="err">${e.message}</p>
      <p class="muted">The import may still be running server-side — check the Catalogue in a minute.</p>`;
  } finally { btn.disabled = false; }
};

// SEARCH
$('#search-go').onclick = async () => {
  const f = $('#search-file').files[0];
  if (!f) return;
  const btn = $('#search-go'); btn.disabled = true;
  $('#search-out').innerHTML = '<p class="muted">Identifying…</p>';
  try {
    const fd = new FormData(); fd.append('file', f);
    const r = await api('/search', { method: 'POST', body: fd });
    if (!r.top_candidate) {
      $('#search-out').innerHTML = renderCorrectionForm(r.query_image_id);
      bindCorrection(r.query_image_id);
      return;
    }
    const c = r.top_candidate;
    let html = candidateCard(c, true);
    if (r.candidates.length > 1) {
      html += '<h2 style="margin-top:18px">Other candidates</h2>';
      r.candidates.slice(1).forEach(x => html += candidateCard(x, false));
    }
    if (r.similar_products.length) {
      html += '<h2 style="margin-top:18px">Similar products</h2><div class="grid">';
      r.similar_products.forEach(s => html += `
        <div class="thumb"><img src="${s.images[0]||''}" /><div>${s.product_name}</div>
        <small class="muted">${money(s.price,s.currency)}</small></div>`);
      html += '</div>';
    }
    html += `<p class="muted" style="margin-top:14px">Not right?
      <a href="#" id="wrong">Correct this</a></p>`;
    $('#search-out').innerHTML = html;
    $('#wrong').onclick = (e) => { e.preventDefault();
      $('#search-out').insertAdjacentHTML('beforeend', renderCorrectionForm(r.query_image_id));
      bindCorrection(r.query_image_id); };
  } catch (e) {
    $('#search-out').innerHTML = `<p class="err">${e.message}</p>`;
  } finally { btn.disabled = false; }
};

function candidateCard(c, primary) {
  const cls = confClass(c.confidence);
  return `<div class="card">
    <img src="${c.matched_image_url || c.images[0] || ''}" />
    <div>
      <div><span class="pill">${c.brand}</span>
        <span class="conf ${cls}">${(c.confidence*100).toFixed(0)}% confident</span></div>
      <h2 style="margin:6px 0">${c.product_name}</h2>
      <div>${money(c.price, c.currency)} ${c.category ? '· '+c.category : ''}</div>
      <p class="muted">${(c.description||'').slice(0,200)}</p>
    </div></div>`;
}

function renderCorrectionForm(imageId) {
  return `<div class="panel" style="margin-top:14px">
    <h2>Label this photo (field capture)</h2>
    <p class="muted">Your label enters the verification pipeline — it never trains the model directly.</p>
    <div class="row">
      <div><label>Brand</label><input id="cor-brand" placeholder="Tom Dixon"/></div>
      <div><label>Product</label><input id="cor-prod" placeholder="Melt Pendant"/></div>
    </div>
    <label>Location (optional)</label><input id="cor-loc" placeholder="Hotel lobby"/>
    <label>Notes (optional)</label><input id="cor-notes"/>
    <button class="go" id="cor-go" data-img="${imageId}">Submit correction</button>
    <div id="cor-out"></div></div>`;
}

function bindCorrection(imageId) {
  $('#cor-go').onclick = async () => {
    try {
      await api(`/images/${imageId}/correction`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          brand: $('#cor-brand').value, product_name: $('#cor-prod').value,
          capture_location: $('#cor-loc').value || null, notes: $('#cor-notes').value || null
        })
      });
      $('#cor-out').innerHTML = '<p class="ok">Submitted for verification. Thank you!</p>';
    } catch (e) { $('#cor-out').innerHTML = `<p class="err">${e.message}</p>`; }
  };
}

// CATALOGUE — a by-brand overview that drills into one brand's products.
let catOverviewLoaded = false;
const brandName = {};
$('#cat-refresh').onclick = () => { catOverviewLoaded = false; loadCatalogue(); };
$('#cat-brand').onchange = () => { if ($('#cat-brand').value) location.href = '/b/' + $('#cat-brand').value; };
$('#cat-back').onclick = (e) => { e.preventDefault(); showOverview(); };

// Event delegation: one listener on the always-present containers, so clicks
// work no matter when/how the cards are (re)rendered.
$('#brand-cards').addEventListener('click', (e) => {
  const card = e.target.closest('[data-bid]');
  if (card && card.dataset.bid) showBrand(card.dataset.bid);
});
$('#cat-out').addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-del]');
  if (!btn) return;
  if (!confirm('Remove this from the catalogue? This deletes it from visual search too.')) return;
  try {
    await api('/products/' + btn.dataset.del, { method: 'DELETE' });
    const card = btn.closest('[data-pid]'); if (card) card.remove();
  } catch (e) { alert(e.message); }
});

function showOverview() {
  $('#cat-detail').hidden = true;
  $('#brand-cards').hidden = false;
  $('#brand-count').hidden = false;
  $('#cat-brand').value = '';
}

async function loadCatalogue() {
  showOverview();
  if (catOverviewLoaded) return;
  $('#brand-cards').innerHTML = '<p class="muted">Loading brands…</p>';
  try {
    const rows = await api('/brands/overview');
    const sel = $('#cat-brand');
    sel.length = 1;
    const totalP = rows.reduce((a, b) => a + b.products, 0);
    $('#brand-count').textContent =
      `${rows.length} brands · ${totalP.toLocaleString()} products`;
    rows.forEach(b => {
      brandName[b.id] = b.name;
      const o = document.createElement('option');
      o.value = b.id; o.textContent = `${b.name} (${b.products})`; sel.appendChild(o);
    });
    $('#brand-cards').innerHTML = rows.length ? rows.map(b => `
      <a class="thumb" href="/b/${b.id}" style="cursor:pointer;display:block;color:inherit;text-decoration:none">
        <img src="${b.sample||''}" loading="lazy" onerror="this.style.opacity=0.15"/>
        <div style="margin-top:6px;font-weight:600">${b.name}</div>
        <small class="muted">${b.products} product${b.products===1?'':'s'}${b.needs_review?` · <span style="color:var(--warn)">${b.needs_review} to review</span>`:''}</small>
      </a>`).join('') : '<p class="muted">No products yet — import a brand first.</p>';
    catOverviewLoaded = true;  // clicks handled by delegation on #brand-cards
  } catch (e) { $('#brand-cards').innerHTML = `<p class="err">${e.message}</p>`; }
}

async function showBrand(bid) {
  $('#brand-cards').hidden = true;
  $('#brand-count').hidden = true;
  $('#cat-detail').hidden = false;
  $('#cat-title').textContent = brandName[bid] || 'Brand';
  $('#cat-out').innerHTML = '<p class="muted">Loading…</p>';
  $('#cat-brand').value = bid;
  try {
    const items = await api(`/products?limit=2000&brand_id=${bid}`);
    $('#cat-count').textContent = `${items.length} product${items.length===1?'':'s'}`;
    $('#cat-out').innerHTML = items.length ? items.map(p => productTile(p)).join('')
      : '<p class="muted">No products.</p>';
    // delete clicks handled by delegation on #cat-out
  } catch (e) { $('#cat-out').innerHTML = `<p class="err">${e.message}</p>`; }
}

function productTile(p) {
  const img = (p.images[0]||{}).image_url || '';
  return `<div class="thumb" data-pid="${p.id}">
    <img src="${img}" loading="lazy" onerror="this.style.opacity=0.2"/>
    <div style="margin-top:6px">${p.name||''}</div>
    <small class="muted">${money(p.price, p.currency)}${p.category? ' · '+p.category:''}</small>
    ${p.needs_review ? '<div class="badge-rev">review</div>' : ''}
    ${p.product_url ? `<div><a class="muted" href="${p.product_url}" target="_blank" rel="noopener"><small>source ↗</small></a></div>` : ''}
    <button class="del" data-del="${p.id}">✕ Not a product</button>
  </div>`;
}

// REVIEW
$('#review-refresh').onclick = loadReview;
async function loadReview() {
  $('#review-out').innerHTML = '<p class="muted">Loading…</p>';
  try {
    const items = await api('/review/products?limit=50');
    if (!items.length) { $('#review-out').innerHTML = '<p class="ok">Queue is clear 🎉</p>'; return; }
    $('#review-out').innerHTML = items.map(p => `
      <div class="card" data-pid="${p.id}">
        <img src="${(p.images[0]||{}).image_url||''}" />
        <div style="flex:1">
          <span class="pill">${(p.brand||{}).name||''}</span>
          <label>Name</label><input value="${p.name||''}" data-f="name"/>
          <div class="row">
            <div><label>Category</label><input value="${p.category||''}" data-f="category"/></div>
            <div><label>Price</label><input value="${p.price||''}" data-f="price"/></div>
          </div>
          <label>Materials</label><input value="${p.materials||''}" data-f="materials"/>
          <button class="go" data-save="${p.id}">Save & resolve</button>
          <button class="del" data-del="${p.id}" style="margin-top:8px">✕ Not a product</button>
        </div></div>`).join('');
    document.querySelectorAll('[data-save]').forEach(btn => btn.onclick = async () => {
      const card = btn.closest('[data-pid]');
      const body = { resolve_review: true };
      card.querySelectorAll('[data-f]').forEach(i => {
        let v = i.value.trim(); if (v === '') return;
        body[i.dataset.f] = i.dataset.f === 'price' ? Number(v) : v;
      });
      try {
        await api(`/products/${btn.dataset.save}`, {
          method: 'PATCH', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
        });
        card.remove();
      } catch (e) { alert(e.message); }
    });
    document.querySelectorAll('#review-out [data-del]').forEach(btn => btn.onclick = async () => {
      try {
        await api('/products/' + btn.dataset.del, { method: 'DELETE' });
        const card = btn.closest('[data-pid]'); if (card) card.remove();
      } catch (e) { alert(e.message); }
    });
  } catch (e) { $('#review-out').innerHTML = `<p class="err">${e.message}</p>`; }
}
</script>
</body>
</html>
"""
