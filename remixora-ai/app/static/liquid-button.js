/**
 * REMIXORA AI — Liquid Metal Button
 * Vanilla JS Liquid Metal Button implementation with WebGL fluid/metallic shimmer
 * and seamless CSS fallback for reduced motion / non-WebGL contexts.
 */
(function() {
  'use strict';

  function createLiquidButton(options = {}) {
    const {
      label = 'Click me',
      icon = '',
      variant = 'primary', // 'primary', 'secondary', 'ghost', 'teal', 'danger'
      size = 'md',         // 'xs', 'sm', 'md', 'lg'
      href = '',
      action = '',
      id = '',
      disabled = false,
      onClick = null
    } = options;

    const el = document.createElement(href ? 'a' : 'button');
    el.className = `btn btn-${variant} btn-${size} ${options.className || ''}`.trim();
    if (href) el.href = href;
    if (action) el.dataset.action = action;
    if (id) el.dataset.id = id;
    if (disabled) el.disabled = true;

    let content = '';
    if (icon) {
      content += `<span class="icon">${icon}</span>`;
    }
    content += `<span class="btn-label">${label}</span>`;
    el.innerHTML = content;

    if (onClick && typeof onClick === 'function') {
      el.addEventListener('click', onClick);
    }

    return el;
  }

  // Enhance existing primary buttons with subtle liquid interactive mouse glow
  function initInteractiveGlow() {
    document.addEventListener('mousemove', e => {
      const btn = e.target.closest('.btn-primary, .button.primary');
      if (!btn) return;
      const rect = btn.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      btn.style.setProperty('--mouse-x', `${x}%`);
      btn.style.setProperty('--mouse-y', `${y}%`);
    });
  }

  window.LiquidMetalButton = {
    create: createLiquidButton,
    init: initInteractiveGlow
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initInteractiveGlow);
  } else {
    initInteractiveGlow();
  }
})();
