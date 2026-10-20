// =========================================================
// APP.JS — interactions for dashboard / scan / verdict /
// ingredient-detail. Wired to the real backend (main.py)
// instead of app-data.js mocks. Loads AFTER the shared
// script.js (cursor, sprite engine, split-title, etc.)
// Every block guards on the element existing, so this one
// file can be included on every app page without errors.
// =========================================================

// Change this if your backend runs somewhere other than localhost:8000.
const API_BASE = window.location.hostname.endsWith('.app.github.dev')
  ? window.location.origin.replace(/-\d+\.app\.github\.dev$/, '-8000.app.github.dev')
  : 'http://localhost:8000';

// ---------------------------------------------------------
// DASHBOARD — recent scans strip (from /api/scans) + nudge dismiss
// ---------------------------------------------------------
(function(){
  const strip = document.getElementById('recent-scans-strip');
  if (!strip) return;

  strip.innerHTML = '<p style="font-size:0.8rem;opacity:0.6;">Loading recent scans…</p>';

  fetch(`${API_BASE}/api/scans`)
    .then(r => r.json())
    .then(scans => {
      if (!scans.length){
        strip.innerHTML = '<p style="font-size:0.8rem;opacity:0.6;">No scans yet — go scan something.</p>';
        return;
      }
      strip.innerHTML = scans.map(scan => `
        <a class="scan-thumb" href="verdict.html?scanId=${scan.scanId}">
          <span class="verdict-tag verdict-tag--${scan.verdict}">${scan.verdict.toUpperCase()}</span>
          <span class="scan-thumb-name">${scan.productName}</span>
          <span class="scan-thumb-date">${scan.date}</span>
        </a>
      `).join('');
    })
    .catch(err => {
      console.error('Failed to load scans:', err);
      strip.innerHTML = '<p style="font-size:0.8rem;opacity:0.6;">Couldn\'t reach the backend — is it running on ' + API_BASE + '?</p>';
    });

  const dismissBtn = document.getElementById('nudge-dismiss');
  const nudgeCard = document.getElementById('nudge-card');
  if (dismissBtn && nudgeCard){
    dismissBtn.addEventListener('click', () => nudgeCard.classList.add('dismissed'));
  }

  const cravingForm = document.getElementById('dash-craving-form');
  if (cravingForm){
    cravingForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const val = encodeURIComponent(document.getElementById('dash-craving-input').value || '');
      window.location.href = `craving-search.html?q=${val}`;
    });
  }
})();

// ---------------------------------------------------------
// SCAN PAGE — real capture -> upload to /api/scan -> verdict
// redirect, plus a demo trigger for the low-confidence/error
// state (backend doesn't detect "low confidence" yet, so this
// stays a client-side demo until that logic exists server-side).
// ---------------------------------------------------------
(function(){
  const scanBtn = document.getElementById('scan-capture-btn');
  const fileInput = document.getElementById('scan-file-input');
  const processingOverlay = document.getElementById('processing-overlay');
  const processingText = document.getElementById('processing-text');
  const errorOverlay = document.getElementById('error-overlay');
  const errorTriggerBtn = document.getElementById('scan-error-demo-btn');
  const retakeBtn = document.getElementById('error-retake-btn');
  const continueAnywayBtn = document.getElementById('error-continue-btn');

  if (!scanBtn || !processingOverlay) return;

  const STAGES = ['Finding the label…', 'Reading ingredients…', 'Checking your profile…'];

  function runProcessing(requestPromise, onDone, onError){
    processingOverlay.classList.add('active');
    let i = 0;
    processingText.textContent = STAGES[i];
    const iv = setInterval(() => {
      i = Math.min(i + 1, STAGES.length - 1);
      processingText.textContent = STAGES[i];
    }, 850);

    requestPromise
      .then(result => {
        clearInterval(iv);
        processingOverlay.classList.remove('active');
        onDone(result);
      })
      .catch(err => {
        clearInterval(iv);
        processingOverlay.classList.remove('active');
        console.error('Scan failed:', err);
        if (onError) onError(err);
        else if (errorOverlay) errorOverlay.classList.add('active');
      });
  }

  function uploadScan(file){
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${API_BASE}/api/scan`, { method: 'POST', body: formData })
      .then(r => {
        if (!r.ok) throw new Error(`Scan request failed: ${r.status}`);
        return r.json();
      });
  }

  // Real camera/upload capture needs a hidden file input in scan.html:
  // <input type="file" id="scan-file-input" accept="image/*" capture="environment" style="display:none">
  if (fileInput){
    scanBtn.addEventListener('click', (e) => {
      e.preventDefault();
      fileInput.click();
    });

    fileInput.addEventListener('change', () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      runProcessing(
        uploadScan(file),
        (scan) => { window.location.href = `verdict.html?scanId=${scan.scanId}`; }
      );
    });
  } else {
    scanBtn.addEventListener('click', () => {
      console.warn('No #scan-file-input found — add one to scan.html to enable real capture.');
    });
  }

  // "or upload a photo instead" — same pipeline, but no capture= attribute,
  // so desktop/tablet users without a camera get a normal file picker
  // instead of a dead link.
  const uploadInput = document.getElementById('scan-upload-input');
  const uploadAltLink = document.getElementById('scan-upload-alt-link');
  if (uploadInput && uploadAltLink){
    uploadAltLink.addEventListener('click', (e) => {
      e.preventDefault();
      uploadInput.click();
    });
    uploadInput.addEventListener('change', () => {
      const file = uploadInput.files && uploadInput.files[0];
      if (!file) return;
      runProcessing(
        uploadScan(file),
        (scan) => { window.location.href = `verdict.html?scanId=${scan.scanId}`; }
      );
    });
  }

  if (errorTriggerBtn && errorOverlay){
    errorTriggerBtn.addEventListener('click', (e) => {
      e.preventDefault();
      processingOverlay.classList.add('active');
      processingText.textContent = STAGES[0];
      setTimeout(() => {
        processingOverlay.classList.remove('active');
        errorOverlay.classList.add('active');
      }, 1400);
    });
  }

  if (retakeBtn && errorOverlay){
    retakeBtn.addEventListener('click', () => errorOverlay.classList.remove('active'));
  }
  if (continueAnywayBtn){
    continueAnywayBtn.addEventListener('click', () => {
      window.location.href = 'dashboard.html';
    });
  }
})();

// ---------------------------------------------------------
// VERDICT PAGE — render the scan matching ?scanId= from URL
// (fetched from the real backend)
// ---------------------------------------------------------
(function(){
  const root = document.getElementById('verdict-result');
  if (!root) return;

  const params = new URLSearchParams(window.location.search);
  const scanId = params.get('scanId');

  if (!scanId){
    root.innerHTML = '<p style="padding:2rem;">No scan selected. <a href="dashboard.html">Back to dashboard</a>.</p>';
    return;
  }

  fetch(`${API_BASE}/api/scans/${scanId}`)
    .then(r => {
      if (!r.ok) throw new Error(`Scan not found: ${r.status}`);
      return r.json();
    })
    .then(renderVerdict)
    .catch(err => {
      console.error('Failed to load scan:', err);
      root.innerHTML = `<p style="padding:2rem;">Couldn't load that scan — is the backend running on ${API_BASE}?</p>`;
    });

  function renderVerdict(scan){
    const spriteByVerdict = {
      safe: 'assets/appy/static/eat.png',
      flagged: 'assets/appy/static/dirty.png',
      unclear: 'assets/appy/static/meditate.png'
    };
    const labelByVerdict = { safe: 'SAFE', flagged: 'FLAGGED', unclear: 'UNCLEAR' };
    const copyByVerdict = {
      safe: "Nothing on your list showed up — looks good to eat.",
      flagged: "Found something that matches your profile. Check the flagged ingredients below.",
      unclear: "Couldn't fully confirm this one — some ingredients need a closer look."
    };

    const verdictSprite = document.getElementById('verdict-result-sprite');
    verdictSprite.style.backgroundImage = `url('${spriteByVerdict[scan.verdict]}')`;
    if (window.AppySprites) AppySprites.scan(verdictSprite);   // start the sprite animation
    document.getElementById('verdict-badge').textContent = labelByVerdict[scan.verdict];
    document.getElementById('verdict-badge').className = `verdict-badge-lg verdict-badge-lg--${scan.verdict}`;
    document.getElementById('verdict-product-name').textContent = scan.productName;
    document.getElementById('verdict-copy').textContent = copyByVerdict[scan.verdict];

    const flaggedSection = document.getElementById('flagged-list-section');
    const flaggedList = document.getElementById('flagged-list');
    const swapCta = document.getElementById('verdict-swap-cta');

    if (scan.flaggedIngredients.length){
      flaggedSection.style.display = 'block';
      flaggedList.innerHTML = scan.flaggedIngredients.map(ing => `
        <a class="flagged-chip" href="ingredient-detail.html?id=${ing.id}&scanId=${scan.scanId}">
          ${ing.name} <span class="flagged-chip-arrow">→</span>
        </a>
      `).join('');
      if (swapCta){ swapCta.style.display = 'inline-block'; swapCta.href = `swaps.html?scanId=${scan.scanId}`; }
    } else {
      flaggedSection.style.display = 'none';
      if (swapCta) swapCta.style.display = 'none';
    }
  }
})();

// ---------------------------------------------------------
// INGREDIENT DETAIL PAGE — render ingredient matching ?id=
// (fetched from the real backend)
// ---------------------------------------------------------
(function(){
  const root = document.getElementById('ingredient-root');
  if (!root) return;

  const params = new URLSearchParams(window.location.search);
  const id = params.get('id');
  const scanId = params.get('scanId') || '';

  const backLink = document.getElementById('ingredient-back-link');
  if (backLink && scanId) backLink.href = `verdict.html?scanId=${scanId}`;

  if (!id){
    root.innerHTML = `
      <div class="ingredient-card ingredient-not-found">
        <h2 class="app-heading">No ingredient specified</h2>
      </div>`;
    return;
  }

  fetch(`${API_BASE}/api/ingredient/${id}`)
    .then(r => {
      if (!r.ok) throw new Error(`Ingredient not found: ${r.status}`);
      return r.json();
    })
    .then(ingredient => {
      root.innerHTML = `
        <div class="ingredient-card">
          <h1 class="app-heading ingredient-name">${ingredient.name}</h1>
          <div class="ingredient-block">
            <div class="ingredient-block-label">WHAT IT IS</div>
            <div class="ingredient-block-body">${ingredient.plainLanguage}</div>
          </div>
          <div class="ingredient-block">
            <div class="ingredient-block-label">ALSO HIDES UNDER</div>
            <div class="alias-list">
              ${ingredient.aliases.map(a => `<span class="alias-chip">${a}</span>`).join('')}
            </div>
          </div>
          <div class="ingredient-block">
            <div class="ingredient-block-label">WHY IT'S FLAGGED FOR YOU</div>
            <div class="ingredient-block-body">${ingredient.whyForYou}</div>
          </div>
        </div>
      `;
    })
    .catch(err => {
      console.error('Failed to load ingredient:', err);
      root.innerHTML = `
        <div class="ingredient-card ingredient-not-found">
          <h2 class="app-heading">Ingredient not found</h2>
          <p class="app-subheading">Couldn't load detail for this one — is the backend running on ${API_BASE}?</p>
        </div>`;
    });
})();
// ---------------------------------------------------------
// SWAPS PAGE — ?scanId= (flagged scan) or ?q= (typed craving)
// ---------------------------------------------------------
(function(){
  const root = document.getElementById('swaps-root');
  if (!root) return;

  const params = new URLSearchParams(window.location.search);
  const scanId = params.get('scanId');
  const q = (params.get('q') || '').trim();
  const backLink = document.getElementById('swaps-back-link');
  const contextEl = document.getElementById('swaps-context');

  if (!scanId && !q){
    if (contextEl) contextEl.textContent = 'Nothing selected.';
    root.innerHTML = '<p class="swap-empty">Scan something flagged, or <a href="craving-search.html">describe a craving</a>.</p>';
    return;
  }

  let request;
  if (scanId){
    if (backLink) backLink.href = `verdict.html?scanId=${encodeURIComponent(scanId)}`;
    request = fetch(`${API_BASE}/api/scans/${encodeURIComponent(scanId)}`)
      .then(r => { if (!r.ok) throw new Error(`Scan not found: ${r.status}`); return r.json(); })
      .then(scan => {
        if (contextEl) contextEl.textContent = `Because "${scan.productName}" was flagged`;
        return fetch(`${API_BASE}/api/swaps/${encodeURIComponent(scanId)}`);
      });
  } else {
    if (backLink) backLink.href = 'craving-search.html';
    if (contextEl) contextEl.textContent = `Because you're craving "${q}"`;
    request = fetch(`${API_BASE}/api/swaps?q=${encodeURIComponent(q)}`);
  }

  request
    .then(r => { if (!r.ok) throw new Error(`Swaps request failed: ${r.status}`); return r.json(); })
    .then(data => {
      const results = data.results || [];
      if (!results.length){
        root.innerHTML = '<p class="swap-empty">No ranked swaps found for this one yet.</p>';
        return;
      }
      root.innerHTML = `<div class="swap-grid">${results.map(s => `
        <div class="swap-result-card">
          <span class="swap-macro-delta">${s.macroDelta || ''}</span>
          <h3>${s.name}</h3>
          <div class="swap-tags">${(s.tags || []).map(t => `<span class="swap-tag">${t}</span>`).join('')}</div>
          <p class="swap-why">${s.why || ''}</p>
        </div>
      `).join('')}</div>`;
    })
    .catch(err => {
      console.error('Failed to load swaps:', err);
      root.innerHTML = `<p class="swap-empty">Couldn't load swaps (${err.message}). Is the backend running on ${API_BASE}?</p>`;
    });
})();
