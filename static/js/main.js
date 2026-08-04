// ImageNinja - main.js
// Theme toggle + year stamp

(function () {
  'use strict';

  // ----- Theme management -----
  const STORAGE_KEY = 'imageninja.theme';
  const root = document.documentElement;

  function getStoredTheme() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
  }
  function setStoredTheme(value) {
    try { localStorage.setItem(STORAGE_KEY, value); } catch (e) { /* noop */ }
  }
  function applyTheme(theme) {
    if (theme === 'dark' || theme === 'light') {
      root.setAttribute('data-theme', theme);
    } else {
      root.removeAttribute('data-theme');
    }
  }

  // Initial: stored > prefers-color-scheme > light
  const stored = getStoredTheme();
  if (stored) {
    applyTheme(stored);
  } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    applyTheme('dark');
  }

  // Bind toggle button if present
  document.addEventListener('DOMContentLoaded', function () {
    const btn = document.querySelector('.theme-toggle');
    if (btn) {
      btn.addEventListener('click', function () {
        const current = root.getAttribute('data-theme') ||
          (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        const next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        setStoredTheme(next);
      });
    }

    // Inject year in footer if needed
    const yearEl = document.querySelector('[data-year]');
    if (yearEl) yearEl.textContent = new Date().getFullYear();
  });
})();
