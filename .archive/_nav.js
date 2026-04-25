// Zentrale Navigation — ein Punkt ändern → alle Seiten aktualisieren
(function() {
  var NAV_HTML = '<nav class="nav" aria-label="Hauptnavigation">\
  <a href="/">\
    <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>\
    Dashboard\
  </a>\
  <span class="sep" aria-hidden="true">·</span>\
  <a href="/pages/notes">Notizen</a>\
  <a href="/pages/projects">Projekte</a>\
  <a href="/pages/knowledge">Wissen</a>\
  <a href="/pages/system">System</a>\
  <a href="/trading">Trading</a>\
  <a href="/bot">Bot</a>\
  <a href="/depot">Depot</a>\
  <a href="/report">Report</a>\
  <button id="theme-toggle" aria-label="Theme wechseln" title="Theme wechseln" style="background:none;border:none;cursor:pointer;color:var(--c-text-muted);padding:var(--s-2);border-radius:var(--r-sm);display:flex;align-items:center;margin-left:auto;transition:color var(--t)">\
    <svg id="icon-sun" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="display:none"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>\
    <svg id="icon-moon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>\
  </button>\
</nav>';

  function setActiveLink() {
    var path = location.pathname.replace(/\/$/,'') || '/';
    document.querySelectorAll('.nav a').forEach(function(a) {
      var href = a.getAttribute('href');
      var isActive = (href === '/' && path === '/') ||
                     (href !== '/' && path.startsWith(href));
      if (isActive) a.setAttribute('aria-current','page');
    });
  }

  function initThemeToggle() {
    var btn = document.getElementById('theme-toggle');
    var iconSun = document.getElementById('icon-sun');
    var iconMoon = document.getElementById('icon-moon');
    if (!btn) return;

    function applyTheme(t) {
      document.documentElement.className = t;
      if (iconSun) iconSun.style.display = t === 'dark' ? 'none' : 'block';
      if (iconMoon) iconMoon.style.display = t === 'dark' ? 'block' : 'none';
      localStorage.setItem('theme', t);
    }

    var current = localStorage.getItem('theme') || 'dark';
    applyTheme(current);
    btn.addEventListener('click', function() {
      current = current === 'dark' ? 'light' : 'dark';
      applyTheme(current);
    });
  }

  function init() {
    var header = document.querySelector('header');
    if (!header) return;
    header.innerHTML = NAV_HTML;
    setActiveLink();
    initThemeToggle();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
