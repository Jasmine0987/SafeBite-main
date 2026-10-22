// appy-sprites.js — runs Appy's sprite sheets everywhere on the site.
// Load AFTER script.js (it uses createSprite from there).
(function () {
  if (typeof createSprite !== 'function') return;

  var REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var FPS = { walk: 10, drinkwalk: 9, eat: 8, think: 7, read: 7, sit: 6, meditate: 6, dirty: 6 };
  // transparent square image: gives <img> a square box, like one 256px sheet frame
  var BLANK = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256'/>";
  var RE = /assets\/appy\/(?:static\/([a-z]+)\.png|sprite-([a-z]+)\.png)/;

  var io = 'IntersectionObserver' in window ? new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      var s = e.target.__sprite;
      if (!s || !e.target.__appyManaged) return;
      if (e.isIntersecting && !REDUCED) s.play(); else s.stop();
    });
  }, { rootMargin: '120px' }) : null;

  function useSheet(el, name) {
    el.style.backgroundImage = "url('assets/appy/sprite-" + name + ".png')";
    el.style.backgroundSize = '500% 500%';
    el.style.backgroundRepeat = 'no-repeat';
    el.dataset.appySheet = name;
  }

  function animate(el, name) {
    if (el.__sprite) return;                        // already driven (script.js or earlier)
    var fps = parseInt(el.dataset.fps, 10) || FPS[name] || 7;
    var s = createSprite(el, { fps: fps, autoplay: false });
    el.__appyManaged = true;
    s.setFrame(Math.floor(Math.random() * 25));     // so repeated Appys don't move in lockstep
    if (io) io.observe(el); else if (!REDUCED) s.play();
  }

  function handleImg(img) {
    var src = img.getAttribute('src') || '';
    var m = src.match(/assets\/appy\/static\/([a-z]+)\.png/);
    if (!m || !FPS[m[1]] || REDUCED) return;
    if (img.hasAttribute('data-no-sprite')) return;
    useSheet(img, m[1]);
    if (src !== BLANK) img.setAttribute('src', BLANK);
    animate(img, m[1]);
  }

  function handleBg(el) {
    var bg = getComputedStyle(el).backgroundImage;
    if (!bg || bg === 'none') return;
    var m = bg.match(RE);
    if (!m) return;
    var staticName = m[1], sheetName = m[2];
    if (staticName) {
      if (!FPS[staticName] || REDUCED) return;
      useSheet(el, staticName);
      animate(el, staticName);
    } else if (sheetName) {
      el.style.backgroundSize = '500% 500%';        // fixes 'contain' showing all 25 frames at once
      el.style.backgroundRepeat = 'no-repeat';
      animate(el, sheetName);
    }
  }

  var SKIP = { SCRIPT: 1, STYLE: 1, LINK: 1, META: 1, HEAD: 1, TITLE: 1, BR: 1, CANVAS: 1 };

  function scan(root) {
    root = root || document.body;
    if (!root || root.nodeType !== 1) { if (root && root.nodeType === 9) root = root.body; else return; }
    var list = [root].concat(Array.prototype.slice.call(root.querySelectorAll('*')));
    list.forEach(function (el) {
      if (SKIP[el.tagName] || el.closest('svg') && el.tagName !== 'svg') return;
      if (el.tagName === 'IMG') handleImg(el);
      else handleBg(el);
    });
  }

  window.AppySprites = { scan: scan };

  function start() {
    scan(document.body);
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        if (m.type === 'attributes') {
          if (m.target.tagName === 'IMG' && !/^data:/.test(m.target.getAttribute('src') || '')) handleImg(m.target);
        } else {
          m.addedNodes.forEach(function (n) { if (n.nodeType === 1) scan(n); });
        }
      });
    }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();