/* ==============================================================================
   SMART CAMPUS 360 - Dashboard interactions (Phase 5 glass redesign)
   Progressive enhancement only: every feature degrades gracefully if JS is off,
   so the dashboard content remains fully usable without scripting.
   ============================================================================== */
(function () {
  'use strict';

  var THEME_KEY = 'sc360-theme';

  /* ---------- Light / Dark theme toggle ---------- */
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    var icon = document.getElementById('themeIcon');
    if (icon) icon.className = theme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
  }

  function initThemeToggle() {
    var btn = document.getElementById('themeToggle');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      var next = current === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
      applyTheme(next);
    });
  }

  /* ---------- Sidebar drawer (mobile) ---------- */
  function initSidebar() {
    var hamb = document.getElementById('scHamb');
    var scrim = document.getElementById('scScrim');
    function open() { document.body.classList.add('sc-nav-open'); if (scrim) scrim.classList.add('show'); }
    function close() { document.body.classList.remove('sc-nav-open'); if (scrim) scrim.classList.remove('show'); }
    if (hamb) hamb.addEventListener('click', function () {
      document.body.classList.contains('sc-nav-open') ? close() : open();
    });
    if (scrim) scrim.addEventListener('click', close);
    window.addEventListener('resize', function () {
      if (window.innerWidth > 991) close();
    });
  }

  /* ---------- Dropdowns (notification bell + profile) ---------- */
  function initDropdowns() {
    document.querySelectorAll('.sc-dd').forEach(function (dd) {
      var toggle = dd.querySelector('[data-dd-toggle]');
      if (!toggle) return;
      toggle.addEventListener('click', function (ev) {
        ev.stopPropagation();
        var wasOpen = dd.classList.contains('open');
        document.querySelectorAll('.sc-dd.open').forEach(function (o) { o.classList.remove('open'); });
        if (!wasOpen) dd.classList.add('open');
      });
    });
    document.addEventListener('click', function () {
      document.querySelectorAll('.sc-dd.open').forEach(function (o) { o.classList.remove('open'); });
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') document.querySelectorAll('.sc-dd.open').forEach(function (o) { o.classList.remove('open'); });
    });
  }

  /* ---------- Quick Location Finder (client-side filter of real campus nodes) ---------- */
  function initQuickFinder() {
    var input = document.getElementById('qfindInput');
    if (!input) return;
    var chips = Array.prototype.slice.call(document.querySelectorAll('#qfindList .sc-qchip'));
    var dl = document.getElementById('locDatalist');
    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase();
      chips.forEach(function (c) {
        c.style.display = (!q || c.getAttribute('data-label').toLowerCase().indexOf(q) !== -1) ? '' : 'none';
      });
    });
    // Enter -> jump to the navigator so routing/search continues there
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') {
        var target = chips.filter(function (c) { return c.style.display !== 'none'; })[0];
        if (target) window.location.href = target.getAttribute('href');
      }
    });
    if (dl) { /* datalist options are server-rendered */ }
  }

  /* ---------- Header global search -> Lost & Found search (supports ?q=) ---------- */
  function initGlobalSearch() {
    var form = document.getElementById('scSearchForm');
    if (!form) return;
    form.addEventListener('submit', function (ev) {
      var input = document.getElementById('scSearchInput');
      var q = input && input.value.trim();
      if (!q) { ev.preventDefault(); return; }
      // Navigate to the Lost & Found module with the query; it filters server-side.
      ev.preventDefault();
      window.location.href = '/lost-found/?q=' + encodeURIComponent(q);
    });
  }

  /* ---------- Reveal-on-scroll animations ---------- */
  function initReveal() {
    var els = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window) || !els.length) {
      els.forEach(function (e) { e.classList.add('visible'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('visible'); io.unobserve(en.target); }
      });
    }, { threshold: 0.08 });
    els.forEach(function (e) { io.observe(e); });
  }

  /* ---------- Live clock in the topbar ---------- */
  function initClock() {
    var el = document.getElementById('scClock');
    if (!el) return;
    function tick() {
      var d = new Date();
      el.textContent = d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) +
        ' • ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    }
    tick();
    setInterval(tick, 30000);
  }

  function init() {
    initThemeToggle();
    initSidebar();
    initDropdowns();
    initQuickFinder();
    initGlobalSearch();
    initReveal();
    initClock();
  }

  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);
})();
