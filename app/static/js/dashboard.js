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

  /* ---------- Sidebar expandable nav groups ---------- */
  function initNavGroups() {
    document.querySelectorAll('[data-group-toggle]').forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        var group = btn.closest('.sc-nav-group');
        if (!group) return;
        var isOpen = group.classList.contains('open');
        document.querySelectorAll('.sc-nav-group.open').forEach(function (g) { g.classList.remove('open'); });
        if (!isOpen) group.classList.add('open');
      });
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

  /* ---------- Banner date + live clock ---------- */
  function initClock() {
    var dateEl = document.getElementById('scDate');
    var timeEl = document.getElementById('scTime');
    if (!dateEl && !timeEl) return;
    function tick() {
      var d = new Date();
      if (dateEl) dateEl.textContent = d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
      if (timeEl) timeEl.textContent = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    }
    tick();
    setInterval(tick, 30000);
  }

  /* ---------- Falling star-sparkle shimmer (cosmetic; bubble balls removed) ---------- */
  function initSnow() {
    var layer = document.getElementById('scSnow');
    if (!layer) return;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var count = 42;
    var frag = document.createDocumentFragment();
    for (var i = 0; i < count; i++) {
      var f = document.createElement('span');
      f.className = 'sc-flake star';
      var size = 8 + Math.random() * 10;
      f.style.left = (Math.random() * 100) + 'vw';
      f.style.setProperty('--sz', size.toFixed(1) + 'px');
      f.style.setProperty('--dur', (10 + Math.random() * 12).toFixed(1) + 's');
      f.style.setProperty('--delay', (-Math.random() * 15).toFixed(1) + 's');
      f.style.setProperty('--drift', ((Math.random() * 2 - 1) * 90).toFixed(0) + 'px');
      f.style.setProperty('--tw', (2 + Math.random() * 3).toFixed(1) + 's');
      f.textContent = '\u2726';
      frag.appendChild(f);
    }
    layer.appendChild(frag);
  }

  /* ---------- Count-up for stat numbers ---------- */
  function initCountUp() {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var nums = document.querySelectorAll('.sc-snum');
    nums.forEach(function (el) {
      var raw = (el.textContent || '').trim();
      var target = parseInt(raw.replace(/[^0-9]/g, ''), 10);
      if (isNaN(target) || target === 0) return;
      var dur = 1100, start = null;
      function step(ts) {
        if (!start) start = ts;
        var p = Math.min((ts - start) / dur, 1);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.floor(eased * target).toLocaleString();
        if (p < 1) requestAnimationFrame(step); else el.textContent = target.toLocaleString();
      }
      el.textContent = '0';
      requestAnimationFrame(step);
    });
  }

  /* ---------- 3D tilt on feature cards ---------- */
  function initTilt() {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (window.matchMedia && window.matchMedia('(hover: none)').matches) return;
    document.querySelectorAll('.sc-fcard').forEach(function (card) {
      card.addEventListener('mousemove', function (e) {
        var r = card.getBoundingClientRect();
        var px = (e.clientX - r.left) / r.width - 0.5;
        var py = (e.clientY - r.top) / r.height - 0.5;
        card.style.transform = 'perspective(900px) rotateX(' + (-py * 7).toFixed(2) + 'deg) rotateY(' + (px * 9).toFixed(2) + 'deg) translateY(-4px)';
      });
      card.addEventListener('mouseleave', function () { card.style.transform = ''; });
    });
  }

  function init() {
    initThemeToggle();
    initSidebar();
    initDropdowns();
    initNavGroups();
    initQuickFinder();
    initGlobalSearch();
    initReveal();
    initClock();
    initSnow();
    initCountUp();
    initTilt();
  }

  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);
})();
