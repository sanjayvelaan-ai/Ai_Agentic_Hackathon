/**
 * REMIXORA AI — Theme Manager
 * Supports 'dark' (Obsidian), 'light' (Pearl Lavender), and 'system'.
 * Persists in localStorage and respects prefers-color-scheme.
 */
(function() {
  'use strict';

  const STORAGE_KEY = 'remixora-theme';
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

  function getSavedTheme() {
    return localStorage.getItem(STORAGE_KEY) || 'system';
  }

  function resolveTheme(preference) {
    if (preference === 'system') {
      return mediaQuery.matches ? 'dark' : 'light';
    }
    return preference === 'light' ? 'light' : 'dark';
  }

  function applyTheme(preference) {
    const active = resolveTheme(preference);
    document.documentElement.setAttribute('data-theme', active);
    document.documentElement.setAttribute('data-color-scheme', active);
    
    // Update theme toggle buttons if present in DOM
    const buttons = document.querySelectorAll('[data-theme-btn]');
    buttons.forEach(btn => {
      const mode = btn.dataset.themeBtn;
      if (mode === preference) {
        btn.classList.add('active');
        btn.setAttribute('aria-pressed', 'true');
      } else {
        btn.classList.remove('active');
        btn.setAttribute('aria-pressed', 'false');
      }
    });

    // Dispatch custom event for canvas / WebGL or dynamic components
    window.dispatchEvent(new CustomEvent('remixora-theme-change', { detail: { preference, active } }));
  }

  function setTheme(preference) {
    if (!['dark', 'light', 'system'].includes(preference)) preference = 'system';
    localStorage.setItem(STORAGE_KEY, preference);
    applyTheme(preference);
  }

  // System listener
  mediaQuery.addEventListener('change', () => {
    if (getSavedTheme() === 'system') {
      applyTheme('system');
    }
  });

  // Init early to prevent flash of wrong theme
  applyTheme(getSavedTheme());

  // Expose to window
  window.RemixoraTheme = {
    get: getSavedTheme,
    set: setTheme,
    resolve: () => resolveTheme(getSavedTheme()),
    initButtons: function() {
      applyTheme(getSavedTheme());
      document.addEventListener('click', e => {
        const btn = e.target.closest('[data-theme-btn]');
        if (btn) {
          e.preventDefault();
          setTheme(btn.dataset.themeBtn);
        }
      });
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.RemixoraTheme.initButtons());
  } else {
    window.RemixoraTheme.initButtons();
  }
})();
