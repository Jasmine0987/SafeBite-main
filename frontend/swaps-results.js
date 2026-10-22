/* SafeBite: swaps page results (replaces the old swaps IIFE in app.js).
   Reads ?q=<craving> or ?scanId=<id>, calls the backend, renders ranked safe
   swaps into #swaps-root and wires the four filter buttons. */
(function () {
  const root = document.getElementById('swaps-root');
  if (!root) return;

  const BASE = (typeof API_BASE !== 'undefined') ? API_BASE
    : (location.hostname.endsWith('.app.github.dev')
        ? location.origin.replace('-5500.', '-8000.') : 'http://localhost:8000');

  const params = new URLSearchParams(location.search);
  const q = params.get('q');
  const scanId = params.get('scanId');
  const contextEl = document.getElementById('swaps-context');
  const countEl = document.querySelector('.result-count');
  const backLink = document.getElementById('swaps-back-link');

  let data = null, mode = 'all';

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const css = document.createElement('style');
  css.textContent = `
  #swaps-root .sr-heard{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 18px}
  #swaps-root .sr-heard b{font-size:11px;letter-spacing:.08em;text-transform:uppercase;margin-right:4px;color:#141414}
  #swaps-root .sr-chip{padding:6px 12px;background:var(--yellow,#FFD84D);color:#141414;border:2px solid #141414;
    font-size:11px;font-weight:800;text-transform:uppercase}
  #swaps-root .sr-notice{margin:0 0 16px;padding:14px 18px;background:#fff;color:#141414;border:3px solid #141414;
    box-shadow:6px 6px 0 #141414;font-size:14px;line-height:1.5}
  #swaps-root .sr-notice.warn{background:var(--yellow,#FFD84D)}
  #swaps-root .sr-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:26px;margin:26px 0 40px}
  #swaps-root .sr-card{display:flex;flex-direction:column;gap:10px;padding:24px;background:#fff;color:#141414;
    border:3px solid #141414;box-shadow:9px 9px 0 #141414;transition:transform .2s}
  #swaps-root .sr-card:hover{transform:translate(-3px,-3px)}
  #swaps-root .sr-top{display:flex;justify-content:space-between;align-items:center;font-size:11px;font-weight:800;text-transform:uppercase}
  #swaps-root .sr-cat{padding:4px 9px;border:2px solid #141414;background:var(--cream,#FCF6E8)}
  #swaps-root .sr-match{color:#141414}
  #swaps-root .sr-card h3{margin:2px 0 0;font-size:22px;line-height:1.15;color:#141414}
  #swaps-root .sr-bar{height:10px;border:2px solid #141414;background:#fff}
  #swaps-root .sr-bar i{display:block;height:100%;background:var(--green,#2E9B5F)}
  #swaps-root .sr-card p{margin:0;font-size:14px;line-height:1.5;color:#141414}
  #swaps-root .sr-delta{font-weight:800}
  #swaps-root .sr-on{font-size:12px;color:#141414;opacity:.8}
  #swaps-root .sr-badges{display:flex;flex-wrap:wrap;gap:6px}
  #swaps-root .sr-badge{padding:3px 8px;border:2px solid #141414;font-size:10px;font-weight:800;text-transform:uppercase;
    background:var(--cream,#FCF6E8);color:#141414}
  #swaps-root .sr-safe{font-size:12px;font-weight:800;color:#141414}
  #swaps-root details{border-top:2px dashed #141414;padding-top:10px;color:#141414}
  #swaps-root summary{cursor:pointer;font-size:12px;font-weight:800;text-transform:uppercase}
  #swaps-root details p{margin-top:8px}
  #swaps-root .swap-empty{padding:25px;background:#fff;color:#141414;border:3px solid #141414;box-shadow:8px 8px 0 #141414}
  #swaps-root .swap-empty a{color:#141414;font-weight:800}
  #swaps-root .sr-foot{font-size:12px;color:#141414;opacity:.75;margin-bottom:30px}`;
  document.head.appendChild(css);

  function visible(list) {
    if (mode === 'closest') return list.slice().sort((a, b) => b.match - a.match).slice(0, 3);
    if (mode === 'simple') return list.filter(s => s.simple);
    if (mode === 'macro') return list.filter(s => s.macroFriendly);
    return list;
  }

  function card(s) {
    const m = s.macros || {};
    const matched = (s.matchedOn && s.matchedOn.length)
      ? `<p class="sr-on">Matched on: ${s.matchedOn.map(esc).join(' · ')}</p>` : '';
    const badges = (s.badges || []).slice(0, 5)
      .map(b => `<span class="sr-badge">${esc(b)}</span>`).join('');
    return `
    <article class="sr-card">
      <div class="sr-top"><span class="sr-cat">${esc(s.category)}</span><span class="sr-match">${esc(s.match)}% match</span></div>
      <h3>${esc(s.name)}</h3>
      <div class="sr-bar"><i style="width:${Math.max(4, Math.min(100, +s.match || 0))}%"></i></div>
      <p>${esc(s.why)}</p>
      <p class="sr-delta">${esc(s.macroDelta)}</p>
      ${matched}
      <div class="sr-badges">${badges}</div>
      <p class="sr-safe">✓ Passed your allergen check</p>
      <details>
        <summary>Ingredients &amp; nutrition</summary>
        <p><b>Ingredients:</b> ${(s.ingredients || []).map(esc).join(', ')}</p>
        <p><b>Per serving:</b> ${esc(m.kcal)} kcal · ${esc(m.protein)}g protein · ${esc(m.sugar)}g sugar · ${esc(m.fiber)}g fibre</p>
      </details>
    </article>`;
  }

  function render() {
    if (!data) return;
    const all = data.results || [];
    const list = visible(all);
    if (countEl) countEl.textContent = `${list.length} option${list.length === 1 ? '' : 's'}`;

    let head = '';
    if (data.understood && data.understood.length) {
      head += `<div class="sr-heard"><b>We understood</b>${data.understood
        .map(u => `<span class="sr-chip">${esc(u)}</span>`).join('')}</div>`;
    }
    if (data.didYouMean) {
      const fixes = Object.entries(data.didYouMean).map(([a, b]) => `“${esc(a)}” → “${esc(b)}”`).join(', ');
      head += `<div class="sr-notice">Auto-corrected: ${fixes}</div>`;
    }
    if (data.fallback) head += `<div class="sr-notice warn">${esc(data.fallback)}</div>`;
    if (data.excluded && data.excluded.count > 0) {
      head += `<div class="sr-notice">🛡 ${data.excluded.count} option${data.excluded.count === 1 ? ' was' : 's were'} hidden because they contain ${data.excluded.by.map(esc).join(', ')}.</div>`;
    }

    const body = list.length
      ? `<div class="sr-grid">${list.map(card).join('')}</div>`
      : `<p class="swap-empty">${all.length
          ? 'Nothing matches this filter. Try <b>All Options</b>.'
          : 'No safe swaps found for this craving. Try describing a taste or texture, or <a href="craving-search.html">search again</a>.'}</p>`;

    root.innerHTML = head + body + (data.note ? `<p class="sr-foot">${esc(data.note)}</p>` : '');
  }

  document.querySelectorAll('.swap-filter').forEach(btn => {
    btn.addEventListener('click', () => { mode = btn.dataset.filter || 'all'; render(); });
  });

  let url = null;
  if (q) {
    url = `${BASE}/api/swaps?q=${encodeURIComponent(q)}`;
    if (contextEl) contextEl.textContent = `Because you're craving "${q}"`;
  } else if (scanId) {
    url = `${BASE}/api/swaps/${encodeURIComponent(scanId)}`;
    if (backLink) backLink.href = `verdict.html?scanId=${encodeURIComponent(scanId)}`;
    if (contextEl) contextEl.textContent = 'Because this product was flagged';
  }
  if (!url) {
    root.innerHTML = '<p class="swap-empty">Pick a craving or scan something first. <a href="craving-search.html">Craving Search</a></p>';
    return;
  }

  root.innerHTML = '<p class="swap-empty">Appy is matching your craving…</p>';
  fetch(url)
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(d => { data = Array.isArray(d) ? { results: d } : d; render(); })
    .catch(err => {
      console.error('Swaps failed:', err);
      root.innerHTML = `<p class="swap-empty">Couldn't load swaps (${esc(err.message)}). Is the backend running and port 8000 public?</p>`;
    });
})();