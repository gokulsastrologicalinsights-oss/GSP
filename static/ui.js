/**
 * Gokul Publisher (GSP) — Shared UI Design System & Reusable Components
 * Provides: Theme management, Lucide-style SVG icons, Toast notifications,
 * Confirmation dialogs, Status badges, Empty/Loading/Error states.
 */
(function (window) {
  'use strict';

  const THEME_STORAGE_KEY = 'gsp_theme';

  const ICONS = {
    home: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
    sparkles: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>',
    calendar: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="4" rx="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>',
    message: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    chart: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" x2="18" y1="20" y2="10"/><line x1="12" x2="12" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="14"/></svg>',
    users: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    link: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
    settings: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>',
    sun: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>',
    moon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>',
    plus: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>',
    check: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    x: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
    alert: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>',
    refresh: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>',
    menu: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/></svg>',
    send: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>',
    clock: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    edit: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>',
    trash: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>',
    eye: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>'
  };

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function icon(name) {
    return ICONS[name] || '';
  }

  function getTheme() {
    const attr = document.documentElement.getAttribute('data-theme');
    if (attr === 'light' || attr === 'dark') return attr;
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY);
      if (saved === 'light' || saved === 'dark') return saved;
    } catch (_) {}
    return 'dark';
  }

  function applyTheme(theme, persistBackend = false) {
    const normalized = theme === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', normalized);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, normalized);
    } catch (_) {}

    // Update topbar toggle button if present
    const btn = document.getElementById('theme-toggle-btn');
    if (btn) {
      const isDark = normalized === 'dark';
      btn.setAttribute('aria-label', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
      btn.setAttribute('title', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
      btn.innerHTML = (isDark ? ICONS.sun : ICONS.moon) +
        `<span class="theme-toggle-label">${isDark ? 'Light' : 'Dark'}</span>`;
    }

    // Update settings select/buttons if present
    const select = document.getElementById('settings-theme-select');
    if (select && select.value !== normalized) {
      select.value = normalized;
    }
    document.querySelectorAll('[data-theme-choice]').forEach((el) => {
      el.classList.toggle('active', el.dataset.themeChoice === normalized);
    });

    if (persistBackend && typeof fetch === 'function') {
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'ui_theme', value: normalized })
      }).catch(() => {});
    }
  }

  function toggleTheme() {
    const next = getTheme() === 'dark' ? 'light' : 'dark';
    applyTheme(next, true);
    toast(`Switched to ${next === 'dark' ? 'Dark' : 'Light'} Mode`, 'info', 2200);
  }

  function initTheme(backendTheme) {
    let initial = null;
    try {
      initial = localStorage.getItem(THEME_STORAGE_KEY);
    } catch (_) {}
    if (initial !== 'light' && initial !== 'dark') {
      initial = backendTheme === 'light' ? 'light' : 'dark';
    }
    applyTheme(initial, false);
  }

  function ensureToastContainer() {
    let container = document.getElementById('gsp-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'gsp-toast-container';
      container.className = 'gsp-toast-container';
      container.setAttribute('aria-live', 'polite');
      document.body.appendChild(container);
    }
    return container;
  }

  function toast(message, type = 'info', duration = 3500) {
    const container = ensureToastContainer();
    const el = document.createElement('div');
    const safeType = ['success', 'error', 'warning', 'info'].includes(type) ? type : 'info';
    el.className = `gsp-toast gsp-toast-${safeType}`;
    const iconHtml = safeType === 'success' ? ICONS.check : safeType === 'error' || safeType === 'warning' ? ICONS.alert : ICONS.sparkles;
    el.innerHTML = `<span class="gsp-toast-icon">${iconHtml}</span><span class="gsp-toast-msg">${escapeHtml(message)}</span><button type="button" class="gsp-toast-close" aria-label="Dismiss">${ICONS.x}</button>`;
    const remove = () => {
      el.classList.add('gsp-toast-leave');
      setTimeout(() => el.remove(), 180);
    };
    el.querySelector('.gsp-toast-close').addEventListener('click', remove);
    container.appendChild(el);
    if (duration > 0) {
      setTimeout(remove, duration);
    }
    return el;
  }

  function confirmDialog({
    title = 'Confirm Action',
    message = 'Are you sure you want to continue?',
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    variant = 'primary'
  } = {}) {
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'modal-overlay gsp-confirm-overlay';
      const btnClass = variant === 'danger' ? 'btn-danger' : 'btn-primary';
      overlay.innerHTML = `
        <div class="modal-card gsp-confirm-card" role="dialog" aria-modal="true">
          <div class="modal-header">
            <h3>${escapeHtml(title)}</h3>
            <button type="button" class="close-btn gsp-confirm-x" aria-label="Close">${ICONS.x}</button>
          </div>
          <div class="modal-body">
            <p class="gsp-confirm-message">${escapeHtml(message)}</p>
            <div class="gsp-confirm-actions">
              <button type="button" class="btn btn-secondary gsp-confirm-cancel">${escapeHtml(cancelText)}</button>
              <button type="button" class="btn ${btnClass} gsp-confirm-ok">${escapeHtml(confirmText)}</button>
            </div>
          </div>
        </div>
      `;
      const cleanup = (result) => {
        overlay.remove();
        resolve(result);
      };
      overlay.querySelector('.gsp-confirm-x').addEventListener('click', () => cleanup(false));
      overlay.querySelector('.gsp-confirm-cancel').addEventListener('click', () => cleanup(false));
      overlay.querySelector('.gsp-confirm-ok').addEventListener('click', () => cleanup(true));
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) cleanup(false);
      });
      document.body.appendChild(overlay);
      overlay.querySelector('.gsp-confirm-ok').focus();
    });
  }

  function statusBadge(status, label) {
    const s = String(status || 'unknown').toLowerCase();
    const map = {
      published: 'success',
      published_safe_mode: 'success',
      replied: 'success',
      approved: 'success',
      connected: 'success',
      scheduled: 'info',
      processing: 'info',
      draft: 'neutral',
      pending: 'warning',
      pending_approval: 'warning',
      review_required: 'warning',
      retry_waiting: 'warning',
      failed: 'danger',
      auth_required: 'danger',
      rejected: 'danger',
      disconnected: 'neutral',
      skipped: 'neutral',
      ignored: 'neutral'
    };
    const tone = map[s] || 'neutral';
    const text = label || s.replace(/_/g, ' ');
    return `<span class="gsp-status-badge gsp-status-${tone}">${escapeHtml(text)}</span>`;
  }

  function emptyState({ icon: iconHtml = '📭', title = 'Nothing here yet', description = '', actionHtml = '' } = {}) {
    return `
      <div class="gsp-empty-state">
        <div class="gsp-empty-icon">${iconHtml}</div>
        <h4 class="gsp-empty-title">${escapeHtml(title)}</h4>
        ${description ? `<p class="gsp-empty-desc">${escapeHtml(description)}</p>` : ''}
        ${actionHtml ? `<div class="gsp-empty-action">${actionHtml}</div>` : ''}
      </div>
    `;
  }

  function loadingState(message = 'Loading...') {
    return `
      <div class="gsp-loading-state" role="status">
        <span class="gsp-spinner"></span>
        <span>${escapeHtml(message)}</span>
      </div>
    `;
  }

  function errorState(message = 'Something went wrong.', retryId = '') {
    return `
      <div class="gsp-error-state" role="alert">
        <span class="gsp-error-icon">${ICONS.alert}</span>
        <span class="gsp-error-msg">${escapeHtml(message)}</span>
        ${retryId ? `<button type="button" class="btn btn-secondary btn-sm" id="${escapeHtml(retryId)}">Retry</button>` : ''}
      </div>
    `;
  }

  window.GSPUI = {
    icon,
    escapeHtml,
    getTheme,
    applyTheme,
    toggleTheme,
    initTheme,
    toast,
    confirm: confirmDialog,
    statusBadge,
    emptyState,
    loadingState,
    errorState
  };

  // Apply theme immediately on script parse
  applyTheme(getTheme(), false);
})(window);
