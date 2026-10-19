// auth.js — load in <head> on every logged-in page (and on login.html)
(function () {
  const API = location.hostname.endsWith('.app.github.dev')
    ? location.origin.replace(/-\d+\.app\.github\.dev$/, '-8000.app.github.dev')
    : 'http://localhost:8000';
  window.SB_API = API;

  const TOKEN_KEY = 'safebite_token';
  const USER_KEY = 'safebite_user';

  window.SBAuth = {
    token() { return localStorage.getItem(TOKEN_KEY); },
    user() { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch (e) { return null; } },
    save(data) {
      localStorage.setItem(TOKEN_KEY, data.token);
      localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    },
    clear() {
      [TOKEN_KEY, USER_KEY, 'safebite_allergens', 'safebite-profile'].forEach(k => localStorage.removeItem(k));
    },
    logout() {
      const done = () => { SBAuth.clear(); location.href = 'login.html'; };
      if (!SBAuth.token()) return done();
      fetch(API + '/api/auth/logout', { method: 'POST' }).then(done, done);
    }
  };

  // Attach the login token to every call to our backend; bounce to login on 401.
  const realFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (!url.startsWith(API)) return realFetch(input, init);

    init = Object.assign({}, init);
    const headers = new Headers(init.headers || {});
    const t = SBAuth.token();
    if (t) headers.set('Authorization', 'Bearer ' + t);
    init.headers = headers;

    return realFetch(input, init).then(res => {
      const isAuthCall = url.includes('/api/auth/login') || url.includes('/api/auth/signup');
      if (res.status === 401 && !isAuthCall) {
        SBAuth.clear();
        location.href = 'login.html';
      }
      return res;
    });
  };

  // Pages that need an account
  const PROTECTED = ['dashboard', 'scan', 'verdict', 'history', 'swaps', 'craving-search',
    'ingredient-detail', 'swap-detail', 'onboarding-allergens', 'settings', 'profile'];
  const page = location.pathname.split('/').pop().replace('.html', '');
  if (PROTECTED.includes(page) && !SBAuth.token()) location.replace('login.html');
})();