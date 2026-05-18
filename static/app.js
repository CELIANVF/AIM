/**
 * AIM — shared UX behaviors.
 *
 * Provides:
 *   - Theme management (light / dark / auto) persisted in localStorage.
 *   - Sidebar collapse persistence on desktop.
 *   - Dismissible flash messages with auto-dismiss for success.
 *   - "/" keyboard shortcut to focus the global search.
 *   - Loading state on form submission (disables button + shows spinner).
 *
 * Designed to be safe to load on every page (no-ops if elements are missing).
 */
(function () {
  'use strict';

  /* ---------- Theme ---------- */
  var THEME_KEY = 'aim:theme';
  function applyTheme(theme) {
    var root = document.documentElement;
    root.setAttribute('data-theme', theme);
  }
  function nextTheme(current) {
    if (current === 'light') return 'dark';
    if (current === 'dark') return 'auto';
    return 'light';
  }
  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch (e) {}
    applyTheme(saved || 'auto');

    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-theme-toggle]');
      if (!btn) return;
      var current = document.documentElement.getAttribute('data-theme') || 'auto';
      var next = nextTheme(current);
      applyTheme(next);
      try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
      btn.setAttribute('title', themeLabel(next));
      btn.setAttribute('aria-label', themeLabel(next));
    });

    var btn = document.querySelector('[data-theme-toggle]');
    if (btn) {
      var current = document.documentElement.getAttribute('data-theme') || 'auto';
      btn.setAttribute('title', themeLabel(current));
      btn.setAttribute('aria-label', themeLabel(current));
    }
  }
  function themeLabel(theme) {
    if (theme === 'light') return 'Thème clair (clic pour passer au sombre)';
    if (theme === 'dark') return 'Thème sombre (clic pour passer à automatique)';
    return 'Thème automatique (clic pour passer au clair)';
  }

  /* ---------- Sidebar collapse (desktop) ---------- */
  var SIDEBAR_KEY = 'aim:sidebar-collapsed';
  function initSidebarCollapse() {
    var btn = document.querySelector('[data-sidebar-collapse]');
    if (!btn) return;
    var saved = null;
    try { saved = localStorage.getItem(SIDEBAR_KEY); } catch (e) {}
    if (saved === '1' && window.innerWidth > 1024) {
      document.body.classList.add('sidebar-collapsed');
    }
    btn.addEventListener('click', function () {
      var isOn = document.body.classList.toggle('sidebar-collapsed');
      try { localStorage.setItem(SIDEBAR_KEY, isOn ? '1' : '0'); } catch (e) {}
    });
  }

  /* ---------- Dismissible flashes ---------- */
  function dismissFlash(el) {
    if (!el || el.classList.contains('is-dismissing')) return;
    el.classList.add('is-dismissing');
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 260);
  }
  function initFlashes() {
    var flashes = document.querySelectorAll('.flash');
    for (var i = 0; i < flashes.length; i++) {
      var el = flashes[i];
      if (el.querySelector('.flash-close')) continue;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'flash-close';
      btn.setAttribute('aria-label', 'Fermer ce message');
      btn.textContent = '×';
      el.appendChild(btn);

      (function (flashEl) {
        btn.addEventListener('click', function () { dismissFlash(flashEl); });
        if (flashEl.classList.contains('success') || flashEl.classList.contains('info')) {
          setTimeout(function () { dismissFlash(flashEl); }, 6000);
        }
      })(el);
    }
  }

  /* ---------- "/" focuses global search ---------- */
  function initSearchShortcut() {
    var input = document.querySelector('.search input[type="text"], .search input[name="q"]');
    if (!input) return;
    document.addEventListener('keydown', function (e) {
      if (e.key !== '/') return;
      var t = e.target;
      var tag = (t && t.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || (t && t.isContentEditable)) return;
      e.preventDefault();
      input.focus();
      try { input.select(); } catch (err) {}
    });
  }

  /* ---------- Form submit loading state ---------- */
  function initFormSubmit() {
    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (!form || form.tagName !== 'FORM') return;
      if (form.hasAttribute('data-no-loading')) return;
      var btns = form.querySelectorAll('button[type="submit"], input[type="submit"], button:not([type])');
      for (var i = 0; i < btns.length; i++) {
        var b = btns[i];
        if (b.disabled) continue;
        b.classList.add('is-loading');
        // Re-enable after timeout safety net to avoid stuck UI on validation errors that prevent submit
        setTimeout((function (bb) {
          return function () { bb.classList.remove('is-loading'); };
        })(b), 15000);
      }
    }, true);
  }

  /* ---------- Init on DOM ready ---------- */
  function run() {
    initTheme();
    initSidebarCollapse();
    initFlashes();
    initSearchShortcut();
    initFormSubmit();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();
