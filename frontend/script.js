// =========================================================
// SPRITE ENGINE — steps through a 5x5 (25-frame) sprite sheet
// via background-position percentages. Works for any element
// sized independently of the native 256px frame.
// =========================================================
function createSprite(el, { cols = 5, rows = 5, fps = 12, autoplay = true } = {}){
  if (el.__sprite) return el.__sprite;
  const frameCount = cols * rows;
  let frame = 0;
  let raf = null;
  let last = 0;
  const interval = 1000 / fps;

  function paint(){
    const col = frame % cols;
    const row = Math.floor(frame / cols) % rows;
    const x = cols === 1 ? 0 : (col / (cols - 1)) * 100;
    const y = rows === 1 ? 0 : (row / (rows - 1)) * 100;
    el.style.backgroundPosition = `${x}% ${y}%`;
  }

  function tick(ts){
    if (!last) last = ts;
    if (ts - last >= interval){
      frame = (frame + 1) % frameCount;
      paint();
      last = ts;
    }
    raf = requestAnimationFrame(tick);
  }

  function play(){ if (!raf) raf = requestAnimationFrame(tick); }
  function stop(){ if (raf) cancelAnimationFrame(raf); raf = null; last = 0; }
  function setFrame(i){ frame = ((i % frameCount) + frameCount) % frameCount; paint(); }
  function step(){ frame = (frame + 1) % frameCount; paint(); }

  paint();
  if (autoplay) play();

  const api = { play, stop, setFrame, step, el };
  el.__sprite = api;
  return api;
}

// =========================================================
// CUSTOM BEE CURSOR + DRIPPING HONEY TRAIL
// Two-frame PNG (fly / idle) — fly is the default everywhere,
// idle only shows while hovering a button or link. No rotation:
// the bee always stays upright regardless of movement direction.
// Instead of a stitched line, the bee leaves small honey drops
// behind as it moves — they fall and fade under light gravity,
// no dark lines involved. Suppressed entirely while the pointer
// is inside the footer, where the paw cursor takes over instead.
// =========================================================
(function(){
  const cursor = document.getElementById('appy-cursor');
  const canvas = document.getElementById('trail-canvas');
  const isTouch = window.matchMedia('(hover: none) and (pointer: coarse)').matches;
  if (isTouch || !cursor || !canvas) return;
  const ctx = canvas.getContext('2d');

  const BEE_IDLE = 'assets/cursor/bee-idle.png';
  const BEE_FLY  = 'assets/cursor/bee-fly.png';
  cursor.style.backgroundImage = `url('${BEE_FLY}')`;

  function setBeeFrame(hovering){
    cursor.style.backgroundImage = `url('${hovering ? BEE_IDLE : BEE_FLY}')`;
  }
  document.querySelectorAll('a, button, .brutal-btn, .gooey-btn, .knock-btn').forEach(el => {
    el.addEventListener('mouseenter', () => setBeeFrame(true));
    el.addEventListener('mouseleave', () => setBeeFrame(false));
  });

  // ---- dashed flight trail settings ----
  const SPACING = 18;     // distance between dash centres (bigger = more gap)
  const DASH_LEN = 9;     // length of each dash
  const DASH_W = 2.5;     // thickness
  const FADE = 0.02;     // life lost per frame (smaller = longer trail)
  const COLOR = '#111';

  let mouseX = window.innerWidth / 2;
  let mouseY = window.innerHeight / 2;
  let lastDashX = mouseX;
  let lastDashY = mouseY;
  let dashes = [];

  function resizeCanvas(){
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);

  window.addEventListener('mousemove', (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
    cursor.style.left = mouseX + 'px';
    cursor.style.top = mouseY + 'px';

    // no trail in the footer (paw cursor owns it); reset anchor so
    // there's no long dash line when the bee comes back
    if (document.body.classList.contains('over-footer')){
      lastDashX = mouseX;
      lastDashY = mouseY;
      return;
    }

    const dx = mouseX - lastDashX;
    const dy = mouseY - lastDashY;
    const dist = Math.hypot(dx, dy);

    if (dist >= SPACING){
      const ux = dx / dist;
      const uy = dy / dist;
      const angle = Math.atan2(dy, dx);
      const n = Math.floor(dist / SPACING);   // fast moves still get evenly spaced dashes
      for (let i = 1; i <= n; i++){
        dashes.push({
          x: lastDashX + ux * SPACING * i,
          y: lastDashY + uy * SPACING * i,
          angle,
          life: 1
        });
      }
      lastDashX += ux * SPACING * n;
      lastDashY += uy * SPACING * n;
      if (dashes.length > 120) dashes.splice(0, dashes.length - 120);
    }
  });

  function drawDash(d){
    ctx.save();
    ctx.globalAlpha = Math.max(d.life, 0);
    ctx.translate(d.x, d.y);
    ctx.rotate(d.angle);
    ctx.strokeStyle = COLOR;
    ctx.lineWidth = DASH_W;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(-DASH_LEN / 2, 0);
    ctx.lineTo(DASH_LEN / 2, 0);
    ctx.stroke();
    ctx.restore();
  }

  function drawTrail(){
    const overFooter = document.body.classList.contains('over-footer');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    cursor.style.opacity = overFooter ? '0' : '1';

    if (!overFooter){
      dashes.forEach(d => {
        d.life -= FADE;
        drawDash(d);
      });
    }
    dashes = dashes.filter(d => d.life > 0);
    requestAnimationFrame(drawTrail);
  }
  drawTrail();
})();

// =========================================================
// SECTION COLOR WASH — body background crossfades between
// each section's data-color as it enters view (flying-paper
// technique: transparent sections, single animated body bg).
// =========================================================
(function(){
  const sections = document.querySelectorAll('[data-color]');
  if (!sections.length) return;

  const io = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting){
        document.body.style.backgroundColor = entry.target.getAttribute('data-color');
      }
    });
  }, { threshold: 0.45 });

  sections.forEach(s => io.observe(s));
})();

// =========================================================
// SCROLL-LINKED PARALLAX LAYERS
// =========================================================
(function(){
  const layers = document.querySelectorAll('[data-parallax-speed]');
  if (!layers.length) return;

  let ticking = false;

  function update(){
    const scrolled = window.scrollY;
    layers.forEach(el => {
      const speed = parseFloat(el.getAttribute('data-parallax-speed')) || 0;
      const yPos = -(scrolled * speed);
      el.style.transform = el.style.transform && el.style.transform.includes('rotate')
        ? el.style.transform
        : `translate3d(0, ${yPos}px, 0)`;
    });
    ticking = false;
  }

  window.addEventListener('scroll', () => {
    if (!ticking){
      requestAnimationFrame(update);
      ticking = true;
    }
  }, { passive: true });

  update();
})();

// =========================================================
// HERO WALKER — sprite walk-cycle + walk-across-floor motion
// =========================================================
(function(){
  const el = document.getElementById('hero-walker');
  if (!el) return;
  createSprite(el, { fps: 10 });
})();

// =========================================================
// SPRITE MASCOTS — idle-cycling sprites across the page
// =========================================================
(function(){
  const idleSprites = [
    ['hero-sit-sprite', 6],
    ['verdict-maybe-sprite', 6],
    ['verdict-no-sprite', 5],
    ['verdict-title-no-sprite', 9],
    ['swap-success-sprite', 8],
    ['swap-track-sprite', 6],
    ['hiw-sprite-1', 7],
    ['hiw-sprite-2', 6],
    ['hiw-sprite-3', 8],
  ];
  idleSprites.forEach(([id, fps]) => {
    const el = document.getElementById(id);
    if (el) createSprite(el, { fps });
  });

  // knock-knock dialog sprite
  const knockSprite = document.getElementById('knock-sprite');
  if (knockSprite) createSprite(knockSprite, { fps: 9 });

  // swap walker marches back and forth between the two cards
  const swapWalker = document.getElementById('swap-walker');
  if (swapWalker){
    createSprite(swapWalker, { fps: 9 });
    let t = 0;
    function march(){
      t += 0.03;
      const offset = Math.sin(t) * 14;
      swapWalker.style.transform = `translateX(calc(-50% + ${offset}px)) scaleX(${Math.cos(t) >= 0 ? 1 : -1})`;
      requestAnimationFrame(march);
    }
    requestAnimationFrame(march);
  }
})();

// =========================================================
// VERDICT — 3-state gooey menu
// =========================================================
(function(){
  const buttons = document.querySelectorAll('.gooey-btn');
  const panels = document.querySelectorAll('.verdict-panel');
  if (!buttons.length) return;

  function setState(state){
    buttons.forEach(b => b.classList.toggle('active', b.dataset.state === state));
    panels.forEach(p => p.classList.toggle('visible', p.dataset.panel === state));
  }

  buttons.forEach(btn => btn.addEventListener('click', () => setState(btn.dataset.state)));
  setState('maybe');
})();

// =========================================================
// HOW IT WORKS — Swiper card-stack carousel
// =========================================================
(function(){
  if (!window.Swiper) return;
  new Swiper('.hiw-swiper', {
    effect: 'cards',
    grabCursor: true,
    loop: true,
  });
})();



// =========================================================
// SPLIT-WORD / SPLIT-LETTER TITLE REVEAL (scroll-triggered)
// Default behavior (.split-title alone) animates whole words
// falling in — unchanged, still what index.html uses. Adding
// the modifier class "split-letters" alongside "split-title"
// animates individual characters falling in instead, with each
// word's letters grouped in a non-breaking wrapper so the line
// only ever wraps at real word boundaries (not mid-word).
// =========================================================
(function(){
  if (!window.gsap) return;
  const hasScrollTrigger = !!window.ScrollTrigger;

  function splitBy(root, unit){
    // unit: 'word' wraps each non-whitespace run in a span;
    // 'letter' wraps each word in a nowrap group, with each
    // character inside it as its own animatable span.
    const pieces = [];
    const className = unit === 'letter' ? 'split-letter' : 'split-word';

    function walk(node){
      Array.from(node.childNodes).forEach(child => {
        if (child.nodeType === Node.TEXT_NODE){
          const parts = child.textContent.split(/(\s+)/); // words + whitespace
          const frag = document.createDocumentFragment();
          parts.forEach(part => {
            if (part === '') return;
            if (/^\s+$/.test(part)){
              frag.appendChild(document.createTextNode(part));
            } else if (unit === 'letter'){
              const wordWrap = document.createElement('span');
              wordWrap.className = 'split-word-wrap';
              part.split('').forEach(ch => {
                const span = document.createElement('span');
                span.className = className;
                span.textContent = ch;
                wordWrap.appendChild(span);
                pieces.push(span);
              });
              frag.appendChild(wordWrap);
            } else {
              const span = document.createElement('span');
              span.className = className;
              span.textContent = part;
              frag.appendChild(span);
              pieces.push(span);
            }
          });
          node.replaceChild(frag, child);
        } else if (child.nodeType === Node.ELEMENT_NODE){
          if (child.tagName === 'BR') return;
          walk(child);
        }
      });
    }

    walk(root);
    return pieces;
  }

  // ---- AUTO-DROP: every page-level heading (h1/h2) falls in, with no
  // per-page markup. A heading opts out with data-no-fall, or by living
  // in the nav/footer/dialogs. Already-tagged headings are left alone,
  // so about.html (which tags its own) behaves exactly as before.
  document.querySelectorAll('h1, h2').forEach(h => {
    if (h.classList.contains('split-title')) return;
    if (h.hasAttribute('data-no-fall')) return;
    if (h.closest('nav, footer, dialog, [role="dialog"], .modal')) return;
    if (!h.textContent.trim()) return;
    h.classList.add('split-title', 'split-letters');
  });

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const titles = reduceMotion ? [] : document.querySelectorAll('.split-title');
  titles.forEach(title => {
    const isLetters = title.classList.contains('split-letters');
    const pieces = splitBy(title, isLetters ? 'letter' : 'word');
    if (!pieces.length) return;

    const tween = {
      y: -100,
      opacity: 0,
      rotation: () => gsap.utils.random(-80, 80),
      duration: isLetters ? 0.5 : 0.7,
      ease: 'back',
      stagger: isLetters ? 0.025 : 0.15
    };

    if (hasScrollTrigger){
      gsap.registerPlugin(ScrollTrigger);
      gsap.from(pieces, {
        ...tween,
        scrollTrigger: {
          trigger: title,
          start: 'top 82%',
          toggleActions: 'play none none none'
        }
      });
    } else {
      gsap.from(pieces, tween);
    }

    // FAILSAFE: if a heading has been on screen for 2.5s and its
    // letters are still not visible (ScrollTrigger mis-measured,
    // hidden parent, etc.), force them visible. Text never vanishes.
    const guard = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        guard.disconnect();
        setTimeout(() => {
          const stuck = pieces.some(el => parseFloat(getComputedStyle(el).opacity) < 0.05);
          if (stuck){
            gsap.killTweensOf(pieces);
            gsap.set(pieces, { clearProps: 'all' });
          }
        }, 2500);
      });
    }, { threshold: 0.1 });
    guard.observe(title);
  });

  // Fonts/images shift layout; re-measure trigger positions once loaded.
  if (hasScrollTrigger){
    window.addEventListener('load', () => ScrollTrigger.refresh());
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => ScrollTrigger.refresh());
  }
})();

// =========================================================
// SCROLL REVEAL — fade-up for non-card content
// =========================================================
(function(){
  const targets = document.querySelectorAll('.reveal');
  if (!targets.length) return;

  const io = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting){
        entry.target.classList.add('in-view');
        io.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15 });

  targets.forEach(el => io.observe(el));
})();

// =========================================================
// KNOCK-KNOCK DIALOG — runaway skip button + embarrassment
// =========================================================
(function(){
  const skipBtn = document.getElementById('knock-skip-btn');
  const enterBtn = document.getElementById('knock-enter-btn');
  const flashMsg = document.getElementById('knock-embarrass');
  if (!skipBtn || !flashMsg) return;

  let hoverCount = 0;
  const FLASH_THRESHOLD = 7;
  let flashShown = false;

  function positionSkipButtonInitial(){
    const dialog = skipBtn.closest('.knock-dialog');
    const dialogRect = dialog.getBoundingClientRect();
    skipBtn.style.position = 'absolute';
    skipBtn.style.top = '';
    skipBtn.style.left = '';
    skipBtn.style.bottom = '18%';
    skipBtn.style.left = '50%';
    skipBtn.style.transform = 'translateX(-50%)';
  }

  function getRandomPos(){
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const bw = skipBtn.offsetWidth;
    const bh = skipBtn.offsetHeight;
    const x = Math.floor(Math.random() * (vw - bw));
    const y = Math.floor(Math.random() * (vh - bh));
    return { x, y };
  }

  function runAway(){
    hoverCount++;
    const pos = getRandomPos();

    skipBtn.style.position = 'fixed';
    skipBtn.style.bottom = '';
    skipBtn.style.left = '';
    skipBtn.style.transform = '';
    skipBtn.style.zIndex = '20';

    anime({
      targets: skipBtn,
      left: `${pos.x}px`,
      top: `${pos.y}px`,
      easing: 'easeOutCirc',
      duration: 450
    });

    if (hoverCount >= FLASH_THRESHOLD && !flashShown){
      flashShown = true;
      flashMsg.classList.add('flash');
      setTimeout(() => {
        flashMsg.classList.remove('flash');
      }, 2800);
    }
  }

  skipBtn.addEventListener('mouseover', runAway);
  skipBtn.addEventListener('click', function(e){
    e.preventDefault();
    runAway();
  });
})();

// =========================================================
// JOURNEY TRACKER — clickable 5-step stepper (architecture.html)
// Auto-advances every 4.5s; a manual click jumps straight to
// that step and resets the timer; hovering the tracker pauses
// auto-advance so it never fights a reader mid-read.
// =========================================================
(function(){
  const tracker = document.getElementById('journey-tracker');
  if (!tracker) return;

  const dots = tracker.querySelectorAll('.journey-dot');
  const panels = tracker.querySelectorAll('.journey-panel');
  if (!dots.length || !panels.length) return;

  let current = 1;
  let timer = null;

  function setStep(n){
    current = n;
    dots.forEach(d => d.classList.toggle('active', d.dataset.step === String(n)));
    panels.forEach(p => p.classList.toggle('active', p.dataset.panel === String(n)));
  }

  function next(){
    const n = current >= dots.length ? 1 : current + 1;
    setStep(n);
  }

  function startAuto(){
    stopAuto();
    timer = setInterval(next, 4500);
  }
  function stopAuto(){
    if (timer) clearInterval(timer);
    timer = null;
  }

  dots.forEach(dot => {
    dot.addEventListener('click', () => {
      setStep(Number(dot.dataset.step));
      startAuto();
    });
  });

  tracker.addEventListener('mouseenter', stopAuto);
  tracker.addEventListener('mouseleave', startAuto);

  setStep(1);
  startAuto();
})();

// =========================================================
// FLIP CARDS — tap-to-flip fallback for touch devices
// (architecture.html "one system, many little decisions")
// Hover already flips via CSS; this just makes tap/click do
// the same thing so it works without a mouse.
// =========================================================
(function(){
  const cards = document.querySelectorAll('.flip-card');
  if (!cards.length) return;

  cards.forEach(card => {
    card.addEventListener('click', () => {
      card.classList.toggle('is-flipped');
    });
  });
})();

// =========================================================
// CONNECTION CHAIN — scroll-triggered line draw
// (architecture.html "the magic is in the connections")
// =========================================================
(function(){
  const line = document.getElementById('chain-line');
  if (!line) return;

  const io = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting){
        line.classList.add('in-view');
        io.unobserve(line);
      }
    });
  }, { threshold: 0.3 });

  io.observe(line);
})();

// =========================================================
// Q&A TOGGLE — "Can I eat this?" / "What can I have instead?"
// (architecture.html closing section)
// =========================================================
(function(){
  const buttons = document.querySelectorAll('.qa-toggle');
  const answerText = document.getElementById('qa-answer-text');
  if (!buttons.length || !answerText) return;

  const answers = {
    eat: "That's the SCAN flow — point your camera, and SafeBite reads the label against your profile in seconds.",
    instead: "That's the CRAVE flow — tell SafeBite what you're craving, and it finds something that still hits the spot."
  };

  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      buttons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      answerText.textContent = answers[btn.dataset.answer] || '';
    });
  });
})();

// =========================================================
// FOOTER PAW CURSOR + FOOTPRINT TRAIL + PROP DEFLECTION
// Active only while the pointer is inside <footer class="footer">.
// - Cursor image swaps/rotates to face the direction of travel.
// - Every ~28px traveled, stamps a fading paw print, alternating
//   left/right of the movement line like a walking gait.
// - Any .fl-item prop within range gets nudged away from the paw
//   and springs back (CSS transition) once the paw moves off.
// =========================================================
(function(){
  const footer = document.getElementById('footer');
  const flatlay = document.getElementById('footer-flatlay');
  const pawCursor = document.getElementById('footer-paw-cursor');
  const pawCursorImg = document.getElementById('footer-paw-cursor-img');
  const isTouch = window.matchMedia('(hover: none) and (pointer: coarse)').matches;
  if (!footer || !flatlay || !pawCursor || isTouch) return;

  const PAW_A = 'assets/footer/paw-a.png';
  const PAW_B = 'assets/footer/paw-b.png';

  const items = Array.from(document.querySelectorAll('.fl-item')).map(el => {
    const baseRotate = parseFloat(el.getAttribute('data-rotate')) || 0;
    return { el, baseRotate, dx: 0, dy: 0, deflected: false };
  });

  let inFooter = false;
  let px = 0, py = 0;      // current "reach tip" position (screen coords)
  let lastPx = 0, lastPy = 0;
  let lastStampDist = 0;
  let stampSide = 1;       // alternates -1 / 1 for left/right gait

  function setBaseTransform(item){
    item.el.style.transform = `translate(0px, 0px) rotate(${item.baseRotate}deg)`;
  }
  items.forEach(setBaseTransform);

  function spawnPrint(x, y){
    const print = document.createElement('div');
    print.className = 'paw-print';
    print.style.left = x + 'px';
    print.style.top = y + 'px';
    print.style.transform = `translate(-50%,-50%) rotate(0deg)`;
    const img = document.createElement('img');
    img.src = stampSide > 0 ? PAW_A : PAW_B;
    img.alt = '';
    print.appendChild(img);
    document.body.appendChild(print);

    requestAnimationFrame(() => {
      print.style.transition = 'opacity 900ms ease, transform 900ms ease';
      print.style.opacity = '0';
      print.style.transform += ' scale(0.85)';
    });
    setTimeout(() => print.remove(), 950);
  }

  function updateDeflection(){
    const RANGE = 110;      // px radius of influence (bumped up for larger props)
    const MAX_PUSH = 26;    // px max nudge distance

    items.forEach(item => {
      if (!inFooter){
        if (item.dx !== 0 || item.dy !== 0){
          item.dx = 0; item.dy = 0;
          item.el.style.transition = 'transform .5s cubic-bezier(.34,1.56,.64,1)';
          setBaseTransform(item);
        }
        return;
      }

      const r = item.el.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const vx = cx - px;
      const vy = cy - py;
      const dist = Math.hypot(vx, vy);

      if (dist < RANGE){
        const strength = (1 - dist / RANGE) * MAX_PUSH;
        const nx = vx / (dist || 1);
        const ny = vy / (dist || 1);
        item.dx = nx * strength;
        item.dy = ny * strength;
        item.el.style.transition = 'transform .08s linear';
        item.el.style.transform = `translate(${item.dx}px, ${item.dy}px) rotate(${item.baseRotate}deg)`;
        item.deflected = true;
      } else if (item.deflected){
        item.deflected = false;
        item.dx = 0; item.dy = 0;
        item.el.style.transition = 'transform .5s cubic-bezier(.34,1.56,.64,1)';
        setBaseTransform(item);
      }
    });

    requestAnimationFrame(updateDeflection);
  }
  requestAnimationFrame(updateDeflection);

  // The leg SVG is a fixed 2000px-tall shape (see style.css) — we just
  // translate the whole container to the mouse's position inside the
  // footer. The footer's overflow:hidden clips off everything past the
  // bottom edge, which is what makes the leg look rooted to the floor
  // no matter where the paw currently sits.
  window.addEventListener('mousemove', (e) => {
    const overFooter = e.target.closest('#footer');
    inFooter = !!overFooter;
    document.body.classList.toggle('over-footer', inFooter);
    pawCursor.classList.toggle('active', inFooter);

    if (!inFooter) return;

    const footerRect = footer.getBoundingClientRect();
    const relX = e.clientX - footerRect.left;
    const relY = e.clientY - footerRect.top;

    pawCursor.style.transform = `translate(${relX}px, ${relY}px) translateX(-50%)`;

    px = e.clientX;
    py = e.clientY;

    const dx = px - lastPx;
    const dy = py - lastPy;
    const dist = Math.hypot(dx, dy);

    if (dist > 1 && pawCursorImg){
      const tilt = Math.max(-16, Math.min(16, dx * 0.7));
      pawCursorImg.style.transform = `translate(-50%, -55%) rotate(${tilt}deg)`;
    }

    lastStampDist += dist;
    if (lastStampDist > 30){
      lastStampDist = 0;
      stampSide *= -1;
      spawnPrint(px + (stampSide * 10), py + 20);
    }

    lastPx = px;
    lastPy = py;
  });

  footer.addEventListener('mouseleave', () => {
    inFooter = false;
    document.body.classList.remove('over-footer');
    pawCursor.classList.remove('active');
  });
})();


// =========================================================
// FOOTER PROP DEFLECTION — items nudge away from the bee
// cursor while inside the footer, then spring back.
// =========================================================
(function(){
  const footer = document.getElementById('footer');
  const isTouch = window.matchMedia('(hover: none) and (pointer: coarse)').matches;
  if (!footer || isTouch) return;

  const items = Array.from(document.querySelectorAll('.fl-item')).map(el => {
    const baseRotate = parseFloat(el.getAttribute('data-rotate')) || 0;
    return { el, baseRotate, dx: 0, dy: 0, deflected: false };
  });

  let inFooter = false;
  let px = 0, py = 0;

  function setBaseTransform(item){
    item.el.style.transform = `translate(0px, 0px) rotate(${item.baseRotate}deg)`;
  }
  items.forEach(setBaseTransform);

  function updateDeflection(){
    const RANGE = 110;
    const MAX_PUSH = 26;

    items.forEach(item => {
      if (!inFooter){
        if (item.dx !== 0 || item.dy !== 0){
          item.dx = 0; item.dy = 0;
          item.el.style.transition = 'transform .5s cubic-bezier(.34,1.56,.64,1)';
          setBaseTransform(item);
        }
        return;
      }

      const r = item.el.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const vx = cx - px;
      const vy = cy - py;
      const dist = Math.hypot(vx, vy);

      if (dist < RANGE){
        const strength = (1 - dist / RANGE) * MAX_PUSH;
        const nx = vx / (dist || 1);
        const ny = vy / (dist || 1);
        item.dx = nx * strength;
        item.dy = ny * strength;
        item.el.style.transition = 'transform .08s linear';
        item.el.style.transform = `translate(${item.dx}px, ${item.dy}px) rotate(${item.baseRotate}deg)`;
        item.deflected = true;
      } else if (item.deflected){
        item.deflected = false;
        item.dx = 0; item.dy = 0;
        item.el.style.transition = 'transform .5s cubic-bezier(.34,1.56,.64,1)';
        setBaseTransform(item);
      }
    });

    requestAnimationFrame(updateDeflection);
  }
  requestAnimationFrame(updateDeflection);

  window.addEventListener('mousemove', (e) => {
    inFooter = !!e.target.closest('#footer');
    px = e.clientX;
    py = e.clientY;
  });
})();