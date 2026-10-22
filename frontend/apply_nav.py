import glob, os, re

NAV = '''<!-- ============ NAVBAR (shared site-wide nav) ============ -->
<nav class="navbar" id="navbar">
  <div class="nav-inner">
    <a href="index.html" class="nav-logo">SAFEBITE<span class="nav-logo-dot">.</span></a>
    <ul class="nav-links">
      <li class="nav-item"><a href="index.html"><span class="nav-frame"><img src="assets/appy/static/eat.png" alt=""></span>Home</a></li>
      <li class="nav-item"><a href="how-it-works.html"><span class="nav-frame"><img src="assets/appy/static/read.png" alt=""></span>How It Works</a></li>
      <li class="nav-item"><a href="architecture.html"><span class="nav-frame"><img src="assets/appy/static/think.png" alt=""></span>How It Thinks</a></li>
      <li class="nav-item"><a href="results.html"><span class="nav-frame"><img src="assets/appy/static/sit.png" alt=""></span>Results</a></li>
      <li class="nav-item"><a href="about.html"><span class="nav-frame"><img src="assets/appy/static/meditate.png" alt=""></span>About</a></li>
    </ul>
  </div>
</nav>'''

NAV_RE = re.compile(r'(?:<!--[^>]*?NAVBAR[^>]*?-->\s*)?<nav\b[^>]*>.*?</nav>', re.S)

for path in sorted(glob.glob('*.html')):
    with open(path, encoding='utf-8', newline='') as f:
        html = f.read()
    if not NAV_RE.search(html):
        print(f'SKIPPED (no <nav> found): {path}')
        continue
    name = os.path.basename(path)
    block = NAV.replace(f'<li class="nav-item"><a href="{name}">',
                        f'<li class="nav-item"><a href="{name}" class="is-active">', 1)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(NAV_RE.sub(lambda m: block, html, count=1))
    print(f'updated: {path}')