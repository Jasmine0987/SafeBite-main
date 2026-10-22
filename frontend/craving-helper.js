/* SafeBite: craving-search helper. Drop-in for craving-search.html.
   Adds grouped craving ideas, smart diet toggles, a live "we understood" preview,
   recent searches, a "surprise me" button and rotating placeholder examples. */
(function () {
  const input = document.getElementById('craving-input');
  if (!input) return;

  const BASE = (typeof API_BASE !== 'undefined') ? API_BASE
    : (location.hostname.endsWith('.app.github.dev')
        ? location.origin.replace('-5500.', '-8000.') : 'http://localhost:8000');

  const GROUPS = [
    ['Crunchy & salty', [
      ['Crunchy + salty', 'something crunchy and salty'],
      ['Like popcorn', 'something like popcorn'],
      ['Cheesy + crispy', 'something cheesy and crispy'],
      ['Samosa / pakora', 'something like samosa or pakora']]],
    ['Sweet tooth', [
      ['Sweet + chocolatey', 'something sweet and chocolatey'],
      ['Like ice cream', 'something like ice cream'],
      ['Like cookies', 'something like cookies'],
      ['Candy fix', 'something sweet and fruity like candy'],
      ['Gulab jamun mood', 'something like gulab jamun']]],
    ['Cold & fizzy', [
      ['Fizzy + refreshing', 'something fizzy and refreshing'],
      ['Fizzy, not too sweet', 'something fizzy but not too sweet'],
      ['Creamy milkshake', 'something creamy and cold like a milkshake'],
      ['Icy + fruity', 'something icy and fruity']]],
    ['Warm & comforting', [
      ['Warm + comforting', 'something warm and comforting'],
      ['Hot chocolate', 'hot chocolate'],
      ['Soupy + savoury', 'something warm and savoury like soup'],
      ['Mac & cheese', 'something like mac and cheese']]],
    ['Spicy & bold', [
      ['Crispy + spicy', 'something crispy and spicy'],
      ['Tangy chaat', 'something tangy and spicy like chaat'],
      ['Biryani mood', 'something like biryani'],
      ['Sweet + spicy', 'something sweet and spicy']]],
  ];
  const FILTERS = ['dairy-free', 'vegan', 'gluten-free', 'nut-free', 'low sugar', 'high protein'];
  const PLACEHOLDERS = [
    'something crunchy, salty and cheesy',
    'fizzy but not too sweet',
    'warm, creamy comfort food',
    'sweet and chocolatey, dairy-free',
    'something like samosa but baked',
    'icy and fruity, low sugar',
  ];
  const RECENT_KEY = 'safebite_recent_cravings';

  const css = document.createElement('style');
  css.textContent = `
  #cs-helper{margin-top:22px;display:grid;gap:16px}
  #cs-helper .cs-label{font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px;color:#141414}
  #cs-helper .cs-row{display:flex;flex-wrap:wrap;gap:10px}
  #cs-helper .cs-toggle.on{background:var(--green,#2E9B5F);color:#fff}
  #cs-helper .cs-note{font-size:13px;color:#141414;opacity:.8;margin:0}
  #cs-heard{margin-top:14px;min-height:30px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:13px;color:#141414}
  #cs-heard b{font-size:11px;letter-spacing:.08em;text-transform:uppercase}
  #cs-heard .cs-chip{padding:5px 11px;background:var(--yellow,#FFD84D);color:#141414;border:2px solid #141414;
    font-size:11px;font-weight:800;text-transform:uppercase}`;
  document.head.appendChild(css);

  // ---- UI scaffolding -------------------------------------------------------
  const host = document.querySelector('.quick-cravings') || input.parentElement;
  const oldChips = document.querySelector('.craving-chips');
  if (oldChips) oldChips.style.display = 'none';
  const oldLabel = document.querySelector('.quick-cravings-label');
  if (oldLabel) oldLabel.textContent = 'PICK A MOOD OR DESCRIBE YOUR OWN';

  const wrap = document.createElement('div');
  wrap.id = 'cs-helper';
  host.appendChild(wrap);

  const heard = document.createElement('div');
  heard.id = 'cs-heard';
  const note = document.querySelector('.craving-form-note');
  (note || input.parentElement).insertAdjacentElement('afterend', heard);

  const esc = s => String(s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const chip = (label, value, extra) =>
    `<button type="button" class="craving-chip ${extra || ''}" data-craving="${esc(value)}">${esc(label)}</button>`;

  function recent() {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch (e) { return []; }
  }
  function saveRecent(v) {
    v = (v || '').trim();
    if (v.length < 3) return;
    try {
      const list = [v].concat(recent().filter(x => x.toLowerCase() !== v.toLowerCase())).slice(0, 6);
      localStorage.setItem(RECENT_KEY, JSON.stringify(list));
    } catch (e) { /* storage unavailable */ }
  }

  function build() {
    const r = recent();
    let html = '';
    if (r.length) {
      html += `<div><div class="cs-label">Your recent cravings</div><div class="cs-row">${
        r.map(v => chip(v, v)).join('')}<button type="button" class="craving-chip" data-clear="1">Clear</button></div></div>`;
    }
    GROUPS.forEach(([title, items]) => {
      html += `<div><div class="cs-label">${esc(title)}</div><div class="cs-row">${
        items.map(([l, v]) => chip(l, v)).join('')}</div></div>`;
    });
    html += `<div><div class="cs-label">Smart filters <span style="opacity:.6">(added to your search)</span></div>
      <div class="cs-row">${FILTERS.map(f =>
        `<button type="button" class="craving-chip cs-toggle" data-filter="${f}">${f}</button>`).join('')}
        <button type="button" class="craving-chip" data-surprise="1">🎲 Surprise me</button></div>
      <p class="cs-note" style="margin-top:10px">Your saved allergens are always filtered out automatically.</p></div>`;
    wrap.innerHTML = html;
    syncToggles();
  }

  function syncToggles() {
    const v = input.value.toLowerCase();
    wrap.querySelectorAll('.cs-toggle').forEach(b =>
      b.classList.toggle('on', v.includes(b.dataset.filter)));
  }

  function setValue(v) {
    input.value = v;
    input.focus();
    syncToggles();
    preview();
  }

  wrap.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.clear) { try { localStorage.removeItem(RECENT_KEY); } catch (x) {} build(); return; }
    if (b.dataset.surprise) {
      const all = [].concat.apply([], GROUPS.map(g => g[1]));
      setValue(all[Math.floor(Math.random() * all.length)][1]);
      return;
    }
    if (b.dataset.filter) {
      const f = b.dataset.filter;
      const re = new RegExp('(,?\\s*)\\b' + f.replace(/[-\s]/g, '[-\\s]') + '\\b', 'i');
      if (re.test(input.value)) input.value = input.value.replace(re, '').replace(/\s{2,}/g, ' ').trim();
      else input.value = (input.value.trim() ? input.value.trim() + ', ' : '') + f;
      input.focus(); syncToggles(); preview();
      return;
    }
    if (b.dataset.craving) setValue(b.dataset.craving);
  });

  // ---- live "we understood" preview ----------------------------------------
  let timer = null, seq = 0;
  function preview() {
    clearTimeout(timer);
    const text = input.value.trim();
    if (text.length < 3) { heard.innerHTML = ''; return; }
    timer = setTimeout(() => {
      const my = ++seq;
      fetch(`${BASE}/api/craving/understand?q=${encodeURIComponent(text)}`)
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (!d || my !== seq) return;
          heard.innerHTML = d.understood.length
            ? `<b>We understood</b>${d.understood.map(u => `<span class="cs-chip">${esc(u)}</span>`).join('')}`
            : `<span>Hmm, not sure yet. Try a taste (sweet, salty, spicy), a texture (crunchy, creamy) or a food (chips, ice cream).</span>`;
        })
        .catch(() => { /* preview is optional */ });
    }, 300);
  }
  input.addEventListener('input', () => { syncToggles(); preview(); });

  // ---- remember searches on submit ----------------------------------------
  const form = input.closest('form');
  if (form) form.addEventListener('submit', () => saveRecent(input.value), true);
  const submitBtn = document.querySelector('.craving-submit');
  if (submitBtn) submitBtn.addEventListener('click', () => saveRecent(input.value), true);

  // ---- rotating placeholder -------------------------------------------------
  let pi = 0;
  setInterval(() => {
    if (document.activeElement === input || input.value) return;
    pi = (pi + 1) % PLACEHOLDERS.length;
    input.placeholder = PLACEHOLDERS[pi];
  }, 3500);

  build();
})();