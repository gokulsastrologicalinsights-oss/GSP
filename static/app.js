// Gokul Social Publisher - Simple UI Logic

const state = {
  activeTab: 'dashboard',
  autoReplyEnabled: false,
  igAutoReplyEnabled: false,
  ytAutoReplyEnabled: false,
  safeTestMode: true,
  stats: {
    connected_accounts: 0,
    comments_processed: 0,
    auto_replies_sent: 0,
    pending_review: 0
  }
};

// Tab Switching
function switchTab(tabId) {
  state.activeTab = tabId;
  
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });
  
  document.querySelectorAll('.tab-view').forEach(view => {
    view.classList.toggle('active', view.id === `view-${tabId}`);
  });

  const autopostEl = document.getElementById('tab-autopost');
  if (autopostEl) {
    autopostEl.style.display = tabId === 'autopost' ? 'block' : 'none';
  }

  const titles = {
    dashboard: 'Home',
    accounts: 'Connected Accounts',
    autoreply: 'Community & Auto Reply',
    activity: 'Insights & Activity',
    leads: 'Lead Management',
    autopost: 'Create & Schedule',
    publish: 'Publishing'
  };
  document.getElementById('page-title').textContent = titles[tabId] || 'Publishing';
  if (tabId === 'leads' && typeof loadLeads === 'function') {
    loadLeads();
  }
  if (tabId === 'autoreply' && aqState.subtab === 'inbox' && typeof window.initCommunityInbox === 'function') {
    window.initCommunityInbox();
  }
}

// Fetch System Status
async function loadStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();
    
    state.autoReplyEnabled = data.auto_reply_enabled;
    state.igAutoReplyEnabled = !!data.ig_auto_reply_enabled;
    state.ytAutoReplyEnabled = !!data.yt_auto_reply_enabled;
    state.safeTestMode = data.safe_test_mode;
    state.stats = data.stats;
    if (window.GSPUI && typeof window.GSPUI.initTheme === 'function') {
      window.GSPUI.initTheme(data.ui_theme);
    }
    
    updateUI();
  } catch (err) {
    console.error('Failed to load status:', err);
  }
}

// Update UI Elements
function updateUI() {
  // Master Toggles
  const masterToggle = document.getElementById('master-toggle');
  const settingsMasterToggle = document.getElementById('settings-master-toggle');
  const igAutoReplyToggle = document.getElementById('settings-ig-auto-reply-toggle');
  const ytAutoReplyToggle = document.getElementById('settings-yt-auto-reply-toggle');
  const safeModeToggle = document.getElementById('settings-safe-mode-toggle');
  const badge = document.getElementById('master-status-badge');
  const heroTitle = document.getElementById('hero-status-title');
  const heroDesc = document.getElementById('hero-status-desc');
  const quickBtn = document.getElementById('quick-toggle-btn');

  if (masterToggle) masterToggle.checked = state.autoReplyEnabled;
  if (settingsMasterToggle) settingsMasterToggle.checked = state.autoReplyEnabled;
  if (igAutoReplyToggle) igAutoReplyToggle.checked = state.igAutoReplyEnabled;
  if (ytAutoReplyToggle) ytAutoReplyToggle.checked = state.ytAutoReplyEnabled;
  if (safeModeToggle) safeModeToggle.checked = state.safeTestMode;

  const safeModeBanner = document.getElementById('scheduler-safe-mode-banner');
  const safeModeBannerText = document.getElementById('scheduler-safe-mode-banner-text');
  if (safeModeBanner && safeModeBannerText) {
    if (state.safeTestMode) {
      safeModeBanner.classList.add('safe-mode-enabled');
      safeModeBanner.classList.remove('safe-mode-disabled');
      safeModeBanner.style.borderColor = 'var(--status-warning-border)';
      safeModeBanner.style.background = 'var(--status-warning-bg)';
      safeModeBanner.style.color = 'var(--status-warning)';
      safeModeBannerText.textContent = 'SAFE TESTING MODE – LIVE PUBLISHING DISABLED';
    } else {
      safeModeBanner.classList.remove('safe-mode-enabled');
      safeModeBanner.classList.add('safe-mode-disabled');
      safeModeBanner.style.borderColor = 'var(--status-danger-border)';
      safeModeBanner.style.background = 'var(--status-danger-bg)';
      safeModeBanner.style.color = 'var(--status-danger)';
      safeModeBannerText.textContent = 'LIVE PUBLISHING ENABLED – POSTS WILL BE SENT TO CONNECTED PLATFORMS';
    }
  }

  if (badge) {
    badge.textContent = state.autoReplyEnabled ? 'ACTIVE' : 'OFF';
    badge.className = `badge ${state.autoReplyEnabled ? 'on' : 'off'}`;
  }

  if (heroTitle && heroDesc && quickBtn) {
    if (state.autoReplyEnabled) {
      heroTitle.textContent = 'Automatic Comment Reply is ACTIVE';
      heroDesc.textContent = 'The system is monitoring connected accounts and replying to new comments.';
      quickBtn.textContent = 'Pause Auto Reply';
      quickBtn.style.backgroundColor = '#dc2626';
    } else {
      heroTitle.textContent = 'Automatic Comment Reply is Paused';
      heroDesc.textContent = 'Turn on the switch in the top bar to begin automatically responding to comments.';
      quickBtn.textContent = 'Turn ON Auto Reply';
      quickBtn.style.backgroundColor = '';
    }
  }

  // Stats
  document.getElementById('stat-accounts').textContent = state.stats.connected_accounts;
  document.getElementById('stat-processed').textContent = state.stats.comments_processed;
  document.getElementById('stat-replied').textContent = state.stats.auto_replies_sent;
  document.getElementById('stat-pending').textContent = state.stats.pending_review;
}

// Toggle Auto Reply
async function toggleAutoReply(enable) {
  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'auto_reply_enabled', value: enable ? 'true' : 'false' })
    });
    if (res.ok) {
      state.autoReplyEnabled = enable;
      updateUI();
    }
  } catch (err) {
    console.error('Failed to toggle auto reply:', err);
  }
}

// Toggle Safe Mode
async function toggleSafeMode(enable) {
  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'safe_test_mode', value: enable ? 'true' : 'false' })
    });
    if (res.ok) {
      state.safeTestMode = enable;
      updateUI();
    }
  } catch (err) {
    console.error('Failed to toggle safe mode:', err);
  }
}

// Toggle Instagram Auto Reply
async function toggleIgAutoReply(enable) {
  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'ig_auto_reply_enabled', value: enable ? 'true' : 'false' })
    });
    if (res.ok) {
      state.igAutoReplyEnabled = enable;
      updateUI();
    }
  } catch (err) {
    console.error('Failed to toggle Instagram auto reply:', err);
  }
}

// Toggle YouTube Auto Reply
async function toggleYtAutoReply(enable) {
  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'yt_auto_reply_enabled', value: enable ? 'true' : 'false' })
    });
    if (res.ok) {
      state.ytAutoReplyEnabled = enable;
      updateUI();
    }
  } catch (err) {
    console.error('Failed to toggle YouTube auto reply:', err);
  }
}

// Fetch Activities
async function loadActivities() {
  try {
    const res = await fetch('/api/activities');
    if (!res.ok) return;
    const data = await res.json();
    renderActivities(data.activities || []);
  } catch (err) {
    console.error('Failed to load activities:', err);
  }
}

function renderActivities(activities) {
  const tbody = document.getElementById('activity-table-body');
  if (!tbody) return;

  if (activities.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No activity logged yet.</td></tr>';
    return;
  }

  const esc = window.GSPUI ? window.GSPUI.escapeHtml : (s) => String(s ?? '');
  const badge = (st) => window.GSPUI ? window.GSPUI.statusBadge(st) : `<span class="badge ${st === 'replied' ? 'on' : 'off'}">${esc(st)}</span>`;

  tbody.innerHTML = activities.map(item => `
    <tr>
      <td><strong>${esc(item.platform)}</strong></td>
      <td>${esc(item.author_name || 'Anonymous')}</td>
      <td>${esc(item.comment_text)}</td>
      <td>${esc(item.detected_language)} / ${esc(item.detected_intent)}</td>
      <td>${esc(item.reply_text || '—')}</td>
      <td>${badge(item.status)}</td>
      <td>${new Date(item.created_at).toLocaleTimeString()}</td>
    </tr>
  `).join('');
}

// Facebook Page Connection & Status
async function loadFacebookStatus() {
  try {
    const res = await fetch('/api/facebook/status');
    if (!res.ok) return;
    const data = await res.json();
    
    const pill = document.getElementById('fb-status-pill');
    const title = document.getElementById('fb-page-title');
    const desc = document.getElementById('fb-page-desc');
    const actionArea = document.getElementById('fb-action-area');

    if (data.connected && data.page) {
      if (pill) {
        pill.textContent = 'Connected';
        pill.className = 'status-pill connected';
      }
      if (title) title.textContent = data.page.account_name;
      if (desc) desc.textContent = `Page ID: ${data.page.account_id} • Auto-reply active.`;
      if (actionArea) {
        actionArea.innerHTML = `
          <button class="secondary-btn sm" id="btn-disconnect-fb" style="color: #dc2626; border-color: #fca5a5;">Disconnect</button>
        `;
        document.getElementById('btn-disconnect-fb').addEventListener('click', disconnectFacebook);
      }
    } else if (data.pending_selection && data.pages && data.pages.length > 0) {
      // User authorized via OAuth, prompt page selection right on card
      if (pill) {
        pill.textContent = 'Choose Page';
        pill.className = 'status-pill';
        pill.style.backgroundColor = '#fef3c7';
        pill.style.color = '#92400e';
      }
      if (title) title.textContent = 'Select Page to Connect';
      if (desc) desc.textContent = `Authorized successfully! Choose which of your ${data.pages.length} Pages to connect:`;
      if (actionArea) {
        const optionsHtml = data.pages.map(p => `
          <option value="${p.id}">${p.name} (ID: ${p.id}${p.category ? ' - ' + p.category : ''})</option>
        `).join('');

        actionArea.innerHTML = `
          <div style="display: flex; flex-direction: column; gap: 8px; width: 100%;">
            <select id="card-page-select" style="padding: 8px; border-radius: 6px; border: 1px solid var(--border-color); font-size: 13px; width: 100%;">
              ${optionsHtml}
            </select>
            <div style="display: flex; gap: 8px;">
              <button class="primary-btn sm" id="btn-card-confirm-page" style="flex-grow: 1;">Connect Page</button>
              <button class="secondary-btn sm" id="btn-card-reauth" style="font-size: 11px;">Switch Account</button>
            </div>
          </div>
        `;

        document.getElementById('btn-card-confirm-page').addEventListener('click', async () => {
          const selectedId = document.getElementById('card-page-select').value;
          if (selectedId) {
            await finalizePageConnection(data.session_id, selectedId);
          }
        });

        document.getElementById('btn-card-reauth').addEventListener('click', openFbModal);
      }
    } else {
      if (pill) {
        pill.textContent = 'Not Connected';
        pill.className = 'status-pill disconnected';
        pill.style.backgroundColor = '';
        pill.style.color = '';
      }
      if (title) title.textContent = 'Facebook Pages';
      if (desc) desc.textContent = 'Detect and reply to comments on your official Facebook page posts.';
      if (actionArea) {
        actionArea.innerHTML = `
          <button class="primary-btn sm" id="btn-connect-facebook">Connect Facebook</button>
        `;
        document.getElementById('btn-connect-facebook').addEventListener('click', openFbModal);
      }
    }
  } catch (err) {
    console.error('Failed to load Facebook status:', err);
  }
}

async function finalizePageConnection(sessionId, pageId) {
  try {
    const res = await fetch('/api/facebook/select-page', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, page_id: pageId })
    });
    const result = await res.json();
    if (res.ok) {
      closeSelectPageModal();
      window.history.replaceState({}, document.title, window.location.pathname);
      loadFacebookStatus();
      loadStatus();
      
      const banner = document.getElementById('accounts-notification-banner');
      if (banner) {
        banner.textContent = `Successfully connected Facebook Page: ${result.connected_page.name}!`;
        banner.className = 'form-msg success';
        banner.classList.remove('hidden');
        setTimeout(() => banner.classList.add('hidden'), 5000);
      }
    } else {
      alert(result.detail || 'Failed to connect selected page.');
    }
  } catch (err) {
    alert('Network error connecting page.');
  }
}

let currentOAuthSessionId = null;

async function checkMetaAppConfig() {
  try {
    const res = await fetch('/api/facebook/config');
    if (!res.ok) return;
    const data = await res.json();
    
    const readyBox = document.getElementById('fb-oauth-ready');
    const formBox = document.getElementById('fb-oauth-config-form');
    const appIdInput = document.getElementById('fb-app-id');
    const redirectInput = document.getElementById('fb-redirect-uri');

    if (redirectInput && data.redirect_uri) {
      redirectInput.value = data.redirect_uri;
    }

    if (data.configured) {
      if (readyBox) readyBox.classList.remove('hidden');
      if (formBox) formBox.classList.add('hidden');
    } else {
      if (readyBox) readyBox.classList.add('hidden');
      if (formBox) formBox.classList.remove('hidden');
      if (appIdInput && data.app_id_preview) {
        appIdInput.value = data.app_id_preview;
      }
    }
  } catch (err) {
    console.error('Error checking Meta config:', err);
  }
}

function openFbModal() {
  const modal = document.getElementById('fb-modal');
  if (modal) modal.classList.remove('hidden');
  checkMetaAppConfig();
}

function closeFbModal() {
  const modal = document.getElementById('fb-modal');
  if (modal) modal.classList.add('hidden');
}

async function saveMetaCredentials() {
  const appId = document.getElementById('fb-app-id').value.trim();
  const appSecret = document.getElementById('fb-app-secret').value.trim();
  const redirectUri = document.getElementById('fb-redirect-uri').value.trim();
  const msg = document.getElementById('fb-connect-msg');

  if (!appId || !appSecret) {
    if (msg) {
      msg.textContent = 'Please enter both Meta App ID and App Secret.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
    return;
  }

  try {
    const res = await fetch('/api/facebook/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_id: appId, app_secret: appSecret, redirect_uri: redirectUri })
    });
    const result = await res.json();
    if (res.ok) {
      if (msg) {
        msg.textContent = 'Credentials saved! Redirecting to Facebook login...';
        msg.className = 'form-msg success';
        msg.classList.remove('hidden');
      }
      setTimeout(() => {
        window.location.href = '/api/facebook/login';
      }, 700);
    } else {
      if (msg) {
        msg.textContent = result.detail || 'Failed to save credentials.';
        msg.className = 'form-msg error';
        msg.classList.remove('hidden');
      }
    }
  } catch (err) {
    if (msg) {
      msg.textContent = 'Network or server error.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
  }
}

async function openPageSelectionModal(sessionId) {
  currentOAuthSessionId = sessionId;
  const modal = document.getElementById('fb-select-page-modal');
  const dropdown = document.getElementById('fb-pages-dropdown');
  const msg = document.getElementById('fb-select-page-msg');

  if (modal) modal.classList.remove('hidden');
  if (dropdown) dropdown.innerHTML = '<option value="">Loading your authorized pages...</option>';
  if (msg) msg.classList.add('hidden');

  try {
    const res = await fetch(`/api/facebook/session-pages?session_id=${encodeURIComponent(sessionId)}`);
    if (!res.ok) {
      const err = await res.json();
      if (dropdown) dropdown.innerHTML = '<option value="">Failed to load pages</option>';
      if (msg) {
        msg.textContent = err.detail || 'Could not load pages from session.';
        msg.className = 'form-msg error';
        msg.classList.remove('hidden');
      }
      return;
    }

    const data = await res.json();
    const pages = data.pages || [];

    if (pages.length === 0) {
      if (dropdown) dropdown.innerHTML = '<option value="">No Pages Available</option>';
      if (msg) {
        msg.textContent = 'No Facebook Pages found. Make sure you are an admin of at least one page.';
        msg.className = 'form-msg error';
        msg.classList.remove('hidden');
      }
      return;
    }

    if (dropdown) {
      dropdown.innerHTML = pages.map(p => `
        <option value="${p.id}">${p.name} (ID: ${p.id}${p.category ? ' - ' + p.category : ''})</option>
      `).join('');
    }
  } catch (err) {
    console.error('Error loading session pages:', err);
  }
}

function closeSelectPageModal() {
  const modal = document.getElementById('fb-select-page-modal');
  if (modal) modal.classList.add('hidden');
  currentOAuthSessionId = null;
}

async function connectSelectedPage() {
  if (!currentOAuthSessionId) return;
  const dropdown = document.getElementById('fb-pages-dropdown');
  const pageId = dropdown ? dropdown.value : null;
  const msg = document.getElementById('fb-select-page-msg');

  if (!pageId) {
    if (msg) {
      msg.textContent = 'Please choose a Facebook Page from the dropdown.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
    return;
  }

  try {
    const res = await fetch('/api/facebook/select-page', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentOAuthSessionId, page_id: pageId })
    });
    const result = await res.json();
    if (res.ok) {
      closeSelectPageModal();
      // Remove query parameters from URL without reloading
      window.history.replaceState({}, document.title, window.location.pathname);
      loadFacebookStatus();
      loadStatus();
      
      const banner = document.getElementById('accounts-notification-banner');
      if (banner) {
        banner.textContent = `Successfully connected Facebook Page: ${result.connected_page.name}!`;
        banner.className = 'form-msg success';
        banner.classList.remove('hidden');
        setTimeout(() => banner.classList.add('hidden'), 5000);
      }
    } else {
      if (msg) {
        msg.textContent = result.detail || 'Failed to connect selected page.';
        msg.className = 'form-msg error';
        msg.classList.remove('hidden');
      }
    }
  } catch (err) {
    if (msg) {
      msg.textContent = 'Network or server error.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
  }
}

function handleURLParams() {
  const params = new URLSearchParams(window.location.search);
  const fbError = params.get('fb_error');
  const fbSession = params.get('fb_session');
  const igError = params.get('ig_error');
  const igSession = params.get('ig_session');
  const ytError = params.get('yt_error');
  const ytSession = params.get('yt_session');
  const view = params.get('view');

  if (view) {
    switchTab(view);
  }

  const banner = document.getElementById('accounts-notification-banner');
  if (fbError && banner) {
    switchTab('accounts');
    banner.textContent = `Facebook Login Note: ${decodeURIComponent(fbError)}`;
    banner.className = 'form-msg error';
    banner.classList.remove('hidden');
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  if (igError && banner) {
    switchTab('accounts');
    banner.textContent = `Instagram Login Note: ${decodeURIComponent(igError)}`;
    banner.className = 'form-msg error';
    banner.classList.remove('hidden');
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  if (ytError && banner) {
    switchTab('accounts');
    banner.textContent = `YouTube Login Note: ${decodeURIComponent(ytError)}`;
    banner.className = 'form-msg error';
    banner.classList.remove('hidden');
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  if (fbSession) {
    switchTab('accounts');
    openPageSelectionModal(fbSession);
  }

  if (igSession) {
    switchTab('accounts');
    openIgSelectionModal(igSession);
  }

  if (ytSession) {
    switchTab('accounts');
    openYtSelectionModal(ytSession);
  }
}

async function disconnectFacebook() {
  if (!confirm('Are you sure you want to disconnect this Facebook Page?')) return;
  try {
    await fetch('/api/facebook/disconnect', { method: 'POST' });
    loadFacebookStatus();
    loadStatus();
  } catch (err) {
    console.error('Failed to disconnect Facebook:', err);
  }
}

async function connectFacebookManual() {
  const name = document.getElementById('fb-input-page-name').value.trim();
  const id = document.getElementById('fb-input-page-id').value.trim();
  const token = document.getElementById('fb-input-token').value.trim();
  const msg = document.getElementById('fb-connect-msg');

  if (!id || !token) {
    if (msg) {
      msg.textContent = 'Please enter both Page ID and Page Access Token.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
    return;
  }

  try {
    const res = await fetch('/api/facebook/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_id: id, page_name: name || `Page ${id}`, access_token: token })
    });
    const result = await res.json();
    if (res.ok) {
      closeFbModal();
      loadFacebookStatus();
      loadStatus();
    } else if (msg) {
      msg.textContent = result.detail || 'Connection failed.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
  } catch (err) {
    if (msg) {
      msg.textContent = 'Network or server error.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
  }
}

// Facebook Sync
async function syncFacebook() {
  const btn = document.getElementById('btn-sync-facebook');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Syncing...';
  }
  try {
    const res = await fetch('/api/facebook/sync', { method: 'POST' });
    const data = await res.json();
    if (!data.success && data.error) {
      alert(`Sync Note: ${data.error}`);
    } else {
      loadActivities();
      loadStatus();
    }
  } catch (err) {
    alert('Error during Facebook sync.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Sync Facebook Now';
    }
  }
}

// Comment Simulator Test
async function runSimulatorTest() {
  const input = document.getElementById('sim-comment-text');
  const text = input ? input.value.trim() : '';
  if (!text) return;

  const resultBox = document.getElementById('sim-result-box');
  const simLang = document.getElementById('sim-lang');
  const simIntent = document.getElementById('sim-intent');
  const simStatus = document.getElementById('sim-status');
  const simReply = document.getElementById('sim-reply-text');

  try {
    const res = await fetch('/api/facebook/simulate-comment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        comment_id: `sim_${Date.now()}`,
        author_name: 'Simulator Tester',
        author_id: 'tester_user_1',
        message: text
      })
    });
    const data = await res.json();
    if (data.success && data.result) {
      const r = data.result;
      if (simLang) simLang.textContent = r.language.toUpperCase();
      if (simIntent) simIntent.textContent = r.intent;
      if (simStatus) simStatus.textContent = r.status;
      if (simReply) simReply.textContent = r.reply_text || '— (No auto reply; routed for review)';
      if (resultBox) resultBox.classList.remove('hidden');
      loadActivities();
      loadStatus();
    }
  } catch (err) {
    console.error('Simulator test error:', err);
  }
}

// Initialize Application
function initApp() {
  // Navigation
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      switchTab(btn.dataset.tab);
      const sidebar = document.querySelector('.sidebar');
      if (sidebar) sidebar.classList.remove('mobile-open');
    });
  });

  const mobileToggle = document.getElementById('sidebar-mobile-toggle');
  if (mobileToggle) {
    mobileToggle.addEventListener('click', () => {
      const sidebar = document.querySelector('.sidebar');
      if (sidebar) sidebar.classList.toggle('mobile-open');
    });
  }

  // Toggles
  const masterToggle = document.getElementById('master-toggle');
  if (masterToggle) {
    masterToggle.addEventListener('change', (e) => toggleAutoReply(e.target.checked));
  }

  const settingsMasterToggle = document.getElementById('settings-master-toggle');
  if (settingsMasterToggle) {
    settingsMasterToggle.addEventListener('change', (e) => toggleAutoReply(e.target.checked));
  }

  const quickToggleBtn = document.getElementById('quick-toggle-btn');
  if (quickToggleBtn) {
    quickToggleBtn.addEventListener('click', () => toggleAutoReply(!state.autoReplyEnabled));
  }

  const safeModeToggle = document.getElementById('settings-safe-mode-toggle');
  if (safeModeToggle) {
    safeModeToggle.addEventListener('change', (e) => toggleSafeMode(e.target.checked));
  }

  const refreshActivityBtn = document.getElementById('refresh-activity-btn');
  if (refreshActivityBtn) {
    refreshActivityBtn.addEventListener('click', loadActivities);
  }

  // Facebook & Modal listeners
  const btnConnectFb = document.getElementById('btn-connect-facebook');
  if (btnConnectFb) btnConnectFb.addEventListener('click', openFbModal);

  const btnCloseModal = document.getElementById('btn-close-modal');
  if (btnCloseModal) btnCloseModal.addEventListener('click', closeFbModal);

  const btnCancelModal = document.getElementById('btn-cancel-modal');
  if (btnCancelModal) btnCancelModal.addEventListener('click', closeFbModal);

  // Tab switching inside Facebook Modal
  const btnTabOAuth = document.getElementById('btn-tab-oauth');
  const btnTabManual = document.getElementById('btn-tab-manual');
  const oauthSection = document.getElementById('fb-oauth-section');
  const manualSection = document.getElementById('fb-manual-section');

  if (btnTabOAuth && btnTabManual) {
    btnTabOAuth.addEventListener('click', () => {
      btnTabOAuth.style.backgroundColor = 'var(--accent-color)';
      btnTabOAuth.style.color = 'white';
      btnTabManual.style.backgroundColor = '';
      btnTabManual.style.color = '';
      if (oauthSection) oauthSection.classList.remove('hidden');
      if (manualSection) manualSection.classList.add('hidden');
    });

    btnTabManual.addEventListener('click', () => {
      btnTabManual.style.backgroundColor = 'var(--accent-color)';
      btnTabManual.style.color = 'white';
      btnTabOAuth.style.backgroundColor = '';
      btnTabOAuth.style.color = '';
      if (manualSection) manualSection.classList.remove('hidden');
      if (oauthSection) oauthSection.classList.add('hidden');
    });
  }

  const btnSaveMetaCreds = document.getElementById('btn-save-meta-creds');
  if (btnSaveMetaCreds) btnSaveMetaCreds.addEventListener('click', saveMetaCredentials);

  const btnReconfigMeta = document.getElementById('btn-reconfigure-meta');
  if (btnReconfigMeta) {
    btnReconfigMeta.addEventListener('click', () => {
      const readyBox = document.getElementById('fb-oauth-ready');
      const formBox = document.getElementById('fb-oauth-config-form');
      if (readyBox) readyBox.classList.add('hidden');
      if (formBox) formBox.classList.remove('hidden');
    });
  }

  const btnSaveManual = document.getElementById('btn-save-facebook-manual');
  if (btnSaveManual) btnSaveManual.addEventListener('click', connectFacebookManual);

  // Page Selection Modal listeners
  const btnConfirmSelect = document.getElementById('btn-confirm-select-page');
  if (btnConfirmSelect) btnConfirmSelect.addEventListener('click', connectSelectedPage);

  const btnCloseSelect = document.getElementById('btn-close-select-modal');
  if (btnCloseSelect) btnCloseSelect.addEventListener('click', closeSelectPageModal);

  const btnCancelSelect = document.getElementById('btn-cancel-select-modal');
  if (btnCancelSelect) btnCancelSelect.addEventListener('click', closeSelectPageModal);

  const btnSyncFb = document.getElementById('btn-sync-facebook');
  if (btnSyncFb) btnSyncFb.addEventListener('click', syncFacebook);

  const btnTestSim = document.getElementById('btn-test-sim');
  if (btnTestSim) btnTestSim.addEventListener('click', runSimulatorTest);

  // Instagram listeners
  const igAutoReplyToggle = document.getElementById('settings-ig-auto-reply-toggle');
  if (igAutoReplyToggle) {
    igAutoReplyToggle.addEventListener('change', (e) => toggleIgAutoReply(e.target.checked));
  }

  const btnConnectIg = document.getElementById('btn-connect-instagram');
  if (btnConnectIg) btnConnectIg.addEventListener('click', openIgModal);

  const btnCloseIgModal = document.getElementById('btn-close-ig-modal');
  if (btnCloseIgModal) btnCloseIgModal.addEventListener('click', closeIgModal);

  const btnCancelIgModal = document.getElementById('btn-cancel-ig-modal');
  if (btnCancelIgModal) btnCancelIgModal.addEventListener('click', closeIgModal);

  const btnIgTabOAuth = document.getElementById('btn-ig-tab-oauth');
  const btnIgTabManual = document.getElementById('btn-ig-tab-manual');
  const igOAuthSection = document.getElementById('ig-oauth-section');
  const igManualSection = document.getElementById('ig-manual-section');

  if (btnIgTabOAuth && btnIgTabManual) {
    btnIgTabOAuth.addEventListener('click', () => {
      btnIgTabOAuth.style.backgroundColor = 'var(--accent-color)';
      btnIgTabOAuth.style.color = 'white';
      btnIgTabManual.style.backgroundColor = '';
      btnIgTabManual.style.color = '';
      if (igOAuthSection) igOAuthSection.classList.remove('hidden');
      if (igManualSection) igManualSection.classList.add('hidden');
    });
    btnIgTabManual.addEventListener('click', () => {
      btnIgTabManual.style.backgroundColor = 'var(--accent-color)';
      btnIgTabManual.style.color = 'white';
      btnIgTabOAuth.style.backgroundColor = '';
      btnIgTabOAuth.style.color = '';
      if (igManualSection) igManualSection.classList.remove('hidden');
      if (igOAuthSection) igOAuthSection.classList.add('hidden');
    });
  }

  const btnSaveIgMeta = document.getElementById('btn-save-ig-meta-creds');
  if (btnSaveIgMeta) btnSaveIgMeta.addEventListener('click', saveIgMetaCredentials);

  const btnReconfigIgMeta = document.getElementById('btn-reconfigure-ig-meta');
  if (btnReconfigIgMeta) {
    btnReconfigIgMeta.addEventListener('click', () => {
      const readyBox = document.getElementById('ig-oauth-ready');
      const formBox = document.getElementById('ig-oauth-config-form');
      if (readyBox) readyBox.classList.add('hidden');
      if (formBox) formBox.classList.remove('hidden');
    });
  }

  const btnSaveIgManual = document.getElementById('btn-save-instagram-manual');
  if (btnSaveIgManual) btnSaveIgManual.addEventListener('click', connectInstagramManual);

  const btnConfirmSelectIg = document.getElementById('btn-confirm-select-ig-account');
  if (btnConfirmSelectIg) btnConfirmSelectIg.addEventListener('click', connectSelectedIgAccount);

  const btnCloseSelectIg = document.getElementById('btn-close-ig-select-modal');
  if (btnCloseSelectIg) btnCloseSelectIg.addEventListener('click', closeIgSelectionModal);

  const btnCancelSelectIg = document.getElementById('btn-cancel-ig-select-modal');
  if (btnCancelSelectIg) btnCancelSelectIg.addEventListener('click', closeIgSelectionModal);

  const btnSyncIg = document.getElementById('btn-sync-instagram');
  if (btnSyncIg) btnSyncIg.addEventListener('click', syncInstagram);

  // YouTube listeners
  const ytAutoReplyToggle = document.getElementById('settings-yt-auto-reply-toggle');
  if (ytAutoReplyToggle) {
    ytAutoReplyToggle.addEventListener('change', (e) => toggleYtAutoReply(e.target.checked));
  }

  const btnConnectYt = document.getElementById('btn-connect-youtube');
  if (btnConnectYt) btnConnectYt.addEventListener('click', openYtModal);

  const btnCloseYtModal = document.getElementById('btn-close-yt-modal');
  if (btnCloseYtModal) btnCloseYtModal.addEventListener('click', closeYtModal);

  const btnCancelYtModal = document.getElementById('btn-cancel-yt-modal');
  if (btnCancelYtModal) btnCancelYtModal.addEventListener('click', closeYtModal);

  const btnYtTabOAuth = document.getElementById('btn-yt-tab-oauth');
  const btnYtTabManual = document.getElementById('btn-yt-tab-manual');
  const ytOAuthSection = document.getElementById('yt-oauth-section');
  const ytManualSection = document.getElementById('yt-manual-section');

  if (btnYtTabOAuth && btnYtTabManual) {
    btnYtTabOAuth.addEventListener('click', () => {
      btnYtTabOAuth.style.backgroundColor = 'var(--accent-color)';
      btnYtTabOAuth.style.color = 'white';
      btnYtTabManual.style.backgroundColor = '';
      btnYtTabManual.style.color = '';
      if (ytOAuthSection) ytOAuthSection.classList.remove('hidden');
      if (ytManualSection) ytManualSection.classList.add('hidden');
    });
    btnYtTabManual.addEventListener('click', () => {
      btnYtTabManual.style.backgroundColor = 'var(--accent-color)';
      btnYtTabManual.style.color = 'white';
      btnYtTabOAuth.style.backgroundColor = '';
      btnYtTabOAuth.style.color = '';
      if (ytManualSection) ytManualSection.classList.remove('hidden');
      if (ytOAuthSection) ytOAuthSection.classList.add('hidden');
    });
  }

  const btnSaveYtCreds = document.getElementById('btn-save-yt-creds');
  if (btnSaveYtCreds) btnSaveYtCreds.addEventListener('click', saveYouTubeCredentials);

  const btnReconfigYt = document.getElementById('btn-reconfigure-yt-creds');
  if (btnReconfigYt) {
    btnReconfigYt.addEventListener('click', () => {
      const readyBox = document.getElementById('yt-oauth-ready');
      const formBox = document.getElementById('yt-oauth-config-form');
      if (readyBox) readyBox.classList.add('hidden');
      if (formBox) formBox.classList.remove('hidden');
    });
  }

  const btnSaveYtManual = document.getElementById('btn-save-youtube-manual');
  if (btnSaveYtManual) btnSaveYtManual.addEventListener('click', connectYouTubeManual);

  const btnConfirmSelectYt = document.getElementById('btn-confirm-select-yt-channel');
  if (btnConfirmSelectYt) btnConfirmSelectYt.addEventListener('click', connectSelectedYtChannel);

  const btnCloseSelectYt = document.getElementById('btn-close-yt-select-modal');
  if (btnCloseSelectYt) btnCloseSelectYt.addEventListener('click', closeYtSelectionModal);

  const btnCancelSelectYt = document.getElementById('btn-cancel-yt-select-modal');
  if (btnCancelSelectYt) btnCancelSelectYt.addEventListener('click', closeYtSelectionModal);

  const btnSyncYt = document.getElementById('btn-sync-youtube');
  if (btnSyncYt) btnSyncYt.addEventListener('click', syncYouTube);

  // Initial load
  loadStatus();
  loadActivities();
  loadFacebookStatus();
  loadInstagramStatus();
  loadYouTubeStatus();
  checkAccountHealth();
  handleURLParams();
}

// --- Instagram Functions ---
let currentIgOAuthSessionId = null;

async function loadInstagramStatus() {
  try {
    const res = await fetch('/api/instagram/status');
    if (!res.ok) return;
    const data = await res.json();

    const pill = document.getElementById('ig-status-pill');
    const title = document.getElementById('ig-account-title');
    const desc = document.getElementById('ig-account-desc');
    const actionArea = document.getElementById('ig-action-area');

    if (data.connected && data.account) {
      if (pill) {
        pill.textContent = 'Connected';
        pill.className = 'status-pill connected';
      }
      if (title) title.textContent = data.account.account_name;
      if (desc) desc.textContent = `IG ID: ${data.account.account_id} • Comments & Reels ready.`;
      if (actionArea) {
        actionArea.innerHTML = `
          <button class="secondary-btn sm" id="btn-disconnect-ig" style="color: #dc2626; border-color: #fca5a5;">Disconnect</button>
        `;
        document.getElementById('btn-disconnect-ig').addEventListener('click', disconnectInstagram);
      }
    } else if (data.pending_selection && data.accounts && data.accounts.length > 0) {
      if (pill) {
        pill.textContent = 'Choose Account';
        pill.className = 'status-pill';
        pill.style.backgroundColor = '#fef3c7';
        pill.style.color = '#92400e';
      }
      if (title) title.textContent = 'Select Instagram Account';
      if (desc) desc.textContent = `Authorized! Choose from ${data.accounts.length} Instagram Professional account(s):`;
      if (actionArea) {
        const optionsHtml = data.accounts.map(a => `
          <option value="${a.id}">${a.name} (ID: ${a.id})</option>
        `).join('');
        actionArea.innerHTML = `
          <div style="display: flex; flex-direction: column; gap: 8px; width: 100%;">
            <select id="card-ig-select" style="padding: 8px; border-radius: 6px; border: 1px solid var(--border-color); font-size: 13px; width: 100%;">
              ${optionsHtml}
            </select>
            <div style="display: flex; gap: 8px;">
              <button class="primary-btn sm" id="btn-card-confirm-ig" style="flex-grow: 1;">Connect Account</button>
              <button class="secondary-btn sm" id="btn-card-ig-reauth" style="font-size: 11px;">Switch Account</button>
            </div>
          </div>
        `;
        document.getElementById('btn-card-confirm-ig').addEventListener('click', async () => {
          const selectedId = document.getElementById('card-ig-select').value;
          if (selectedId) await finalizeIgConnection(data.session_id, selectedId);
        });
        document.getElementById('btn-card-ig-reauth').addEventListener('click', openIgModal);
      }
    } else {
      if (pill) {
        pill.textContent = 'Not Connected';
        pill.className = 'status-pill disconnected';
        pill.style.backgroundColor = '';
        pill.style.color = '';
      }
      if (title) title.textContent = 'Instagram Professional';
      if (desc) desc.textContent = 'Automatic replies for comments on Instagram reels and posts.';
      if (actionArea) {
        actionArea.innerHTML = `
          <button class="primary-btn sm" id="btn-connect-instagram">Connect Instagram</button>
        `;
        document.getElementById('btn-connect-instagram').addEventListener('click', openIgModal);
      }
    }
  } catch (err) {
    console.error('Failed to load Instagram status:', err);
  }
}

async function checkIgMetaConfig() {
  try {
    const res = await fetch('/api/instagram/config');
    if (!res.ok) return;
    const data = await res.json();
    const readyBox = document.getElementById('ig-oauth-ready');
    const formBox = document.getElementById('ig-oauth-config-form');
    const appIdInput = document.getElementById('ig-app-id');
    const redirectInput = document.getElementById('ig-redirect-uri');

    if (redirectInput && data.redirect_uri) redirectInput.value = data.redirect_uri;
    if (data.configured) {
      if (readyBox) readyBox.classList.remove('hidden');
      if (formBox) formBox.classList.add('hidden');
    } else {
      if (readyBox) readyBox.classList.add('hidden');
      if (formBox) formBox.classList.remove('hidden');
      if (appIdInput && data.app_id_preview) appIdInput.value = data.app_id_preview;
    }
  } catch (err) {
    console.error('Error checking Instagram Meta config:', err);
  }
}

function openIgModal() {
  const modal = document.getElementById('ig-modal');
  if (modal) modal.classList.remove('hidden');
  checkIgMetaConfig();
}

function closeIgModal() {
  const modal = document.getElementById('ig-modal');
  if (modal) modal.classList.add('hidden');
}

async function saveIgMetaCredentials() {
  const appId = document.getElementById('ig-app-id').value.trim();
  const appSecret = document.getElementById('ig-app-secret').value.trim();
  const msg = document.getElementById('ig-connect-msg');
  if (!appId || !appSecret) {
    if (msg) {
      msg.textContent = 'Please enter both Meta App ID and App Secret.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
    return;
  }
  try {
    const res = await fetch('/api/facebook/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_id: appId, app_secret: appSecret })
    });
    if (res.ok) {
      if (msg) {
        msg.textContent = 'Credentials saved! Redirecting to Instagram / Meta login...';
        msg.className = 'form-msg success';
        msg.classList.remove('hidden');
      }
      setTimeout(() => { window.location.href = '/api/instagram/login'; }, 700);
    }
  } catch (err) {
    if (msg) {
      msg.textContent = 'Network or server error.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
  }
}

async function connectInstagramManual() {
  const name = document.getElementById('ig-input-account-name').value.trim();
  const id = document.getElementById('ig-input-account-id').value.trim();
  const token = document.getElementById('ig-input-token').value.trim();
  const msg = document.getElementById('ig-connect-msg');

  if (!id || !token) {
    if (msg) {
      msg.textContent = 'Please enter both Instagram Account ID and Access Token.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
    return;
  }
  try {
    const res = await fetch('/api/instagram/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: id, account_name: name || `IG ${id}`, access_token: token })
    });
    const result = await res.json();
    if (res.ok) {
      closeIgModal();
      loadInstagramStatus();
      loadStatus();
    } else if (msg) {
      msg.textContent = result.detail || 'Connection failed.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
  } catch (err) {
    if (msg) {
      msg.textContent = 'Network or server error.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
  }
}

async function disconnectInstagram() {
  if (!confirm('Are you sure you want to disconnect this Instagram account?')) return;
  try {
    await fetch('/api/instagram/disconnect', { method: 'POST' });
    loadInstagramStatus();
    loadStatus();
  } catch (err) {
    console.error('Failed to disconnect Instagram:', err);
  }
}

async function openIgSelectionModal(sessionId) {
  currentIgOAuthSessionId = sessionId;
  const modal = document.getElementById('ig-select-account-modal');
  const dropdown = document.getElementById('ig-accounts-dropdown');
  const msg = document.getElementById('ig-select-account-msg');
  if (modal) modal.classList.remove('hidden');
  if (dropdown) dropdown.innerHTML = '<option value="">Loading accounts...</option>';
  if (msg) msg.classList.add('hidden');

  try {
    const res = await fetch(`/api/instagram/session-accounts?session_id=${encodeURIComponent(sessionId)}`);
    if (!res.ok) return;
    const data = await res.json();
    const accounts = data.accounts || [];
    if (dropdown) {
      dropdown.innerHTML = accounts.map(a => `<option value="${a.id}">${a.name} (ID: ${a.id})</option>`).join('');
    }
  } catch (err) {
    console.error('Error loading Instagram session accounts:', err);
  }
}

function closeIgSelectionModal() {
  const modal = document.getElementById('ig-select-account-modal');
  if (modal) modal.classList.add('hidden');
  currentIgOAuthSessionId = null;
}

async function connectSelectedIgAccount() {
  if (!currentIgOAuthSessionId) return;
  const dropdown = document.getElementById('ig-accounts-dropdown');
  const accountId = dropdown ? dropdown.value : null;
  if (accountId) await finalizeIgConnection(currentIgOAuthSessionId, accountId);
}

async function finalizeIgConnection(sessionId, accountId) {
  try {
    const res = await fetch('/api/instagram/select-account', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, account_id: accountId })
    });
    const result = await res.json();
    if (res.ok) {
      closeIgSelectionModal();
      window.history.replaceState({}, document.title, window.location.pathname);
      loadInstagramStatus();
      loadStatus();
      const banner = document.getElementById('accounts-notification-banner');
      if (banner) {
        banner.textContent = `Successfully connected Instagram: ${result.connected_account.name}!`;
        banner.className = 'form-msg success';
        banner.classList.remove('hidden');
        setTimeout(() => banner.classList.add('hidden'), 5000);
      }
    } else {
      alert(result.detail || 'Failed to connect selected Instagram account.');
    }
  } catch (err) {
    alert('Network error connecting Instagram account.');
  }
}

async function syncInstagram() {
  const btn = document.getElementById('btn-sync-instagram');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Syncing...';
  }
  try {
    const res = await fetch('/api/instagram/sync', { method: 'POST' });
    const data = await res.json();
    if (!data.success && data.error) {
      alert(`Instagram Sync Note: ${data.error}`);
    } else {
      loadActivities();
      loadStatus();
    }
  } catch (err) {
    alert('Error during Instagram sync.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Sync Instagram Now';
    }
  }
}

// --- YouTube Functions ---
let currentYtOAuthSessionId = null;

async function loadYouTubeStatus() {
  try {
    const res = await fetch('/api/youtube/status');
    if (!res.ok) return;
    const data = await res.json();

    const pill = document.getElementById('yt-status-pill');
    const title = document.getElementById('yt-channel-title');
    const desc = document.getElementById('yt-channel-desc');
    const actionArea = document.getElementById('yt-action-area');

    if (data.connected && data.account) {
      if (pill) {
        pill.textContent = 'Connected';
        pill.className = 'status-pill connected';
      }
      if (title) title.textContent = data.account.account_name;
      if (desc) desc.textContent = `Channel ID: ${data.account.account_id} • Auto reply monitoring active.`;
      if (actionArea) {
        actionArea.innerHTML = `
          <button class="secondary-btn sm" id="btn-disconnect-yt" style="color: #dc2626; border-color: #fca5a5;">Disconnect</button>
        `;
        document.getElementById('btn-disconnect-yt').addEventListener('click', disconnectYouTube);
      }
    } else if (data.pending_selection && data.channels && data.channels.length > 0) {
      if (pill) {
        pill.textContent = 'Choose Channel';
        pill.className = 'status-pill';
        pill.style.backgroundColor = '#fef3c7';
        pill.style.color = '#92400e';
      }
      if (title) title.textContent = 'Select YouTube Channel';
      if (desc) desc.textContent = `Authorized! Choose from ${data.channels.length} channel(s):`;
      if (actionArea) {
        const optionsHtml = data.channels.map(c => `
          <option value="${c.id}">${c.title} (ID: ${c.id})</option>
        `).join('');
        actionArea.innerHTML = `
          <div style="display: flex; flex-direction: column; gap: 8px; width: 100%;">
            <select id="card-yt-select" style="padding: 8px; border-radius: 6px; border: 1px solid var(--border-color); font-size: 13px; width: 100%;">
              ${optionsHtml}
            </select>
            <div style="display: flex; gap: 8px;">
              <button class="primary-btn sm" id="btn-card-confirm-yt" style="flex-grow: 1;">Connect Channel</button>
              <button class="secondary-btn sm" id="btn-card-yt-reauth" style="font-size: 11px;">Switch Channel</button>
            </div>
          </div>
        `;
        document.getElementById('btn-card-confirm-yt').addEventListener('click', async () => {
          const selectedId = document.getElementById('card-yt-select').value;
          if (selectedId) await finalizeYtConnection(data.session_id, selectedId);
        });
        document.getElementById('btn-card-yt-reauth').addEventListener('click', openYtModal);
      }
    } else {
      if (pill) {
        pill.textContent = 'Not Connected';
        pill.className = 'status-pill disconnected';
        pill.style.backgroundColor = '';
        pill.style.color = '';
      }
      if (title) title.textContent = 'YouTube Channel';
      if (desc) desc.textContent = 'Automatic replies for viewers on video comments.';
      if (actionArea) {
        actionArea.innerHTML = `
          <button class="primary-btn sm" id="btn-connect-youtube">Connect YouTube</button>
        `;
        document.getElementById('btn-connect-youtube').addEventListener('click', openYtModal);
      }
    }
  } catch (err) {
    console.error('Failed to load YouTube status:', err);
  }
}

async function checkYouTubeConfig() {
  try {
    const res = await fetch('/api/youtube/config');
    if (!res.ok) return;
    const data = await res.json();
    const readyBox = document.getElementById('yt-oauth-ready');
    const formBox = document.getElementById('yt-oauth-config-form');
    const clientIdInput = document.getElementById('yt-client-id');
    const redirectInput = document.getElementById('yt-redirect-uri');

    if (redirectInput && data.redirect_uri) redirectInput.value = data.redirect_uri;
    if (data.configured) {
      if (readyBox) readyBox.classList.remove('hidden');
      if (formBox) formBox.classList.add('hidden');
    } else {
      if (readyBox) readyBox.classList.add('hidden');
      if (formBox) formBox.classList.remove('hidden');
      if (clientIdInput && data.client_id_preview) clientIdInput.value = data.client_id_preview;
    }
  } catch (err) {
    console.error('Error checking YouTube config:', err);
  }
}

function openYtModal() {
  const modal = document.getElementById('yt-modal');
  if (modal) modal.classList.remove('hidden');
  checkYouTubeConfig();
}

function closeYtModal() {
  const modal = document.getElementById('yt-modal');
  if (modal) modal.classList.add('hidden');
}

async function saveYouTubeCredentials() {
  const clientId = document.getElementById('yt-client-id').value.trim();
  const clientSecret = document.getElementById('yt-client-secret').value.trim();
  const msg = document.getElementById('yt-connect-msg');
  if (!clientId || !clientSecret) {
    if (msg) {
      msg.textContent = 'Please enter both Google Client ID and Client Secret.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
    return;
  }
  try {
    const res = await fetch('/api/youtube/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret })
    });
    const data = await res.json();
    if (res.ok) {
      if (msg) {
        msg.textContent = 'Google OAuth credentials saved. Ready to sign in!';
        msg.className = 'form-msg success';
        msg.classList.remove('hidden');
      }
      setTimeout(() => {
        if (msg) msg.classList.add('hidden');
        checkYouTubeConfig();
      }, 1000);
    } else {
      if (msg) {
        msg.textContent = data.detail || 'Failed to save Google credentials.';
        msg.className = 'form-msg error';
        msg.classList.remove('hidden');
      }
    }
  } catch (err) {
    if (msg) {
      msg.textContent = 'Network error saving Google credentials.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
  }
}

async function connectYouTubeManual() {
  const name = document.getElementById('yt-input-channel-name').value.trim();
  const channelId = document.getElementById('yt-input-channel-id').value.trim();
  const token = document.getElementById('yt-input-token').value.trim();
  const refreshToken = document.getElementById('yt-input-refresh-token').value.trim();
  const msg = document.getElementById('yt-connect-msg');

  if (!channelId || !token) {
    if (msg) {
      msg.textContent = 'Channel ID and Access Token are required.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
    return;
  }

  try {
    const res = await fetch('/api/youtube/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        channel_id: channelId,
        channel_name: name,
        access_token: token,
        refresh_token: refreshToken
      })
    });
    const data = await res.json();
    if (res.ok) {
      closeYtModal();
      loadYouTubeStatus();
      loadStatus();
    } else {
      if (msg) {
        msg.textContent = data.detail || 'Failed to save YouTube channel token.';
        msg.className = 'form-msg error';
        msg.classList.remove('hidden');
      }
    }
  } catch (err) {
    if (msg) {
      msg.textContent = 'Error saving YouTube channel token.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
  }
}

async function openYtSelectionModal(sessionId) {
  currentYtOAuthSessionId = sessionId;
  const modal = document.getElementById('yt-select-channel-modal');
  const dropdown = document.getElementById('yt-channels-dropdown');
  const msg = document.getElementById('yt-select-channel-msg');

  if (modal) modal.classList.remove('hidden');
  if (dropdown) dropdown.innerHTML = '<option value="">Loading channels...</option>';
  if (msg) msg.classList.add('hidden');

  try {
    const res = await fetch(`/api/youtube/session-channels?session_id=${encodeURIComponent(sessionId)}`);
    if (!res.ok) {
      if (dropdown) dropdown.innerHTML = '<option value="">Error loading channels</option>';
      return;
    }
    const data = await res.json();
    const channels = data.channels || [];
    if (channels.length === 0) {
      if (dropdown) dropdown.innerHTML = '<option value="">No channels found</option>';
      return;
    }
    if (dropdown) {
      dropdown.innerHTML = channels.map(c => `
        <option value="${c.id}">${c.title} (${c.custom_url || c.id})</option>
      `).join('');
    }
  } catch (err) {
    if (dropdown) dropdown.innerHTML = '<option value="">Network error loading channels</option>';
  }
}

function closeYtSelectionModal() {
  const modal = document.getElementById('yt-select-channel-modal');
  if (modal) modal.classList.add('hidden');
  currentYtOAuthSessionId = null;
}

async function connectSelectedYtChannel() {
  const dropdown = document.getElementById('yt-channels-dropdown');
  const channelId = dropdown ? dropdown.value : null;
  if (!channelId || !currentYtOAuthSessionId) return;
  await finalizeYtConnection(currentYtOAuthSessionId, channelId);
}

async function finalizeYtConnection(sessionId, channelId) {
  const msg = document.getElementById('yt-select-channel-msg');
  try {
    const res = await fetch('/api/youtube/select-channel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, channel_id: channelId })
    });
    const data = await res.json();
    if (res.ok) {
      closeYtSelectionModal();
      loadYouTubeStatus();
      loadStatus();
      window.history.replaceState({}, document.title, window.location.pathname);
    } else {
      if (msg) {
        msg.textContent = data.detail || 'Failed to connect YouTube channel.';
        msg.className = 'form-msg error';
        msg.classList.remove('hidden');
      }
    }
  } catch (err) {
    if (msg) {
      msg.textContent = 'Error connecting YouTube channel.';
      msg.className = 'form-msg error';
      msg.classList.remove('hidden');
    }
  }
}

async function disconnectYouTube() {
  if (!confirm('Are you sure you want to disconnect this YouTube Channel?')) return;
  try {
    await fetch('/api/youtube/disconnect', { method: 'POST' });
    loadYouTubeStatus();
    loadStatus();
  } catch (err) {
    console.error('Failed to disconnect YouTube:', err);
  }
}

async function syncYouTube() {
  const btn = document.getElementById('btn-sync-youtube');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Syncing...';
  }
  try {
    const res = await fetch('/api/youtube/sync', { method: 'POST' });
    const data = await res.json();
    if (!data.success && data.error) {
      alert(`YouTube Sync Note: ${data.error}`);
    } else {
      loadActivities();
      loadStatus();
    }
  } catch (err) {
    alert('Error during YouTube sync.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Sync YouTube Now';
    }
  }
}

// ==========================================
// Priority 2B: Approval Queue UI
// ==========================================
const aqState = {
  subtab: 'inbox',
  platform: 'all',
  status: 'pending',
  items: [],
  pendingCount: 0,
  editingId: null,
  confirmRejectId: null,
  processingIds: new Set()
};

const AQ_PLATFORM_META = {
  facebook: { label: 'Facebook', icon: '📘' },
  instagram: { label: 'Instagram', icon: '📸' },
  youtube: { label: 'YouTube', icon: '▶️' }
};

function aqEscapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function aqFormatDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts.includes('T') ? ts : ts.replace(' ', 'T') + 'Z');
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

function aqShowFeedback(message, type = 'success') {
  const box = document.getElementById('aq-feedback');
  if (!box) return;
  box.className = `aq-feedback ${type}`;
  box.innerHTML = `<span>${aqEscapeHtml(message)}</span><button type="button" class="secondary-btn sm" onclick="this.parentElement.classList.add('hidden')">Dismiss</button>`;
  box.classList.remove('hidden');
}

function aqHideFeedback() {
  const box = document.getElementById('aq-feedback');
  if (box) box.classList.add('hidden');
}

function aqUpdateCounts(pendingCount) {
  aqState.pendingCount = pendingCount;
  const badge = document.getElementById('aq-pending-badge');
  const summary = document.getElementById('aq-pending-summary');
  if (badge) badge.textContent = pendingCount;
  if (summary) summary.textContent = `${pendingCount} pending`;
}

function aqUpdateSafeModePill() {
  const pill = document.getElementById('aq-safe-mode-pill');
  if (!pill) return;
  if (state.safeTestMode) {
    pill.textContent = '🛡️ Safe Testing Mode ON (No public replies)';
    pill.style.background = '#ecfdf5';
    pill.style.color = '#065f46';
    pill.style.borderColor = '#a7f3d0';
  } else {
    pill.textContent = '⚠️ Safe Testing Mode OFF';
    pill.style.background = '#fef3c7';
    pill.style.color = '#92400e';
    pill.style.borderColor = '#fde68a';
  }
}

function switchAutoReplySubtab(subtab) {
  aqState.subtab = subtab;
  document.querySelectorAll('.subtab-btn[data-subtab]').forEach(btn => {
    const active = btn.dataset.subtab === subtab;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  const inboxView = document.getElementById('subview-inbox');
  const autoView = document.getElementById('subview-automatic');
  const approvalView = document.getElementById('subview-approval');
  const platformSettingsView = document.getElementById('subview-platform-settings');
  if (inboxView) inboxView.classList.toggle('hidden', subtab !== 'inbox');
  if (autoView) autoView.classList.toggle('hidden', subtab !== 'automatic');
  if (approvalView) approvalView.classList.toggle('hidden', subtab !== 'approval');
  if (platformSettingsView) platformSettingsView.classList.toggle('hidden', subtab !== 'platform-settings');

  if (subtab === 'inbox' && typeof window.initCommunityInbox === 'function') {
    window.initCommunityInbox();
  } else if (subtab === 'approval') {
    aqUpdateSafeModePill();
    loadApprovalQueue();
  } else if (subtab === 'platform-settings') {
    loadPlatformSettings();
  }
}

async function refreshPendingCount() {
  try {
    const res = await fetch('/api/approval-queue?status=pending&limit=100');
    if (!res.ok) return;
    const data = await res.json();
    aqUpdateCounts(typeof data.count === 'number' ? data.count : (data.items || []).length);
  } catch (err) {
    console.error('Failed to refresh pending count:', err);
  }
}

async function loadApprovalQueue() {
  const loadingEl = document.getElementById('aq-loading');
  const emptyEl = document.getElementById('aq-empty');
  const listEl = document.getElementById('aq-cards-list');
  if (loadingEl) loadingEl.classList.remove('hidden');
  if (emptyEl) emptyEl.classList.add('hidden');
  if (listEl) listEl.innerHTML = '';

  try {
    const params = new URLSearchParams();
    if (aqState.platform !== 'all') params.set('platform', aqState.platform);

    let url = '/api/approval-queue';
    if (aqState.status === 'history') {
      url = '/api/approval-queue/history';
    } else {
      params.set('status', aqState.status);
    }

    const queryStr = params.toString();
    const res = await fetch(queryStr ? `${url}?${queryStr}` : url);
    if (!res.ok) {
      throw new Error('Could not load approval queue.');
    }
    const data = await res.json();
    aqState.items = data.items || [];
    try {
      const attRes = await fetch('/api/publishing-attempts?limit=100');
      if (attRes.ok) {
        const attData = await attRes.json();
        const map = {};
        for (const a of (attData.attempts || [])) {
          if (!map[a.approval_queue_id]) map[a.approval_queue_id] = a;
        }
        aqState.attemptsByQueueId = map;
      }
    } catch (_) {}

    if (aqState.status === 'pending' && aqState.platform === 'all') {
      aqUpdateCounts(aqState.items.length);
    } else {
      refreshPendingCount();
    }

    renderApprovalQueue();
  } catch (err) {
    aqShowFeedback('Unable to load the approval queue right now. Please try again.', 'error');
  } finally {
    if (loadingEl) loadingEl.classList.add('hidden');
  }
}

function renderApprovalQueue() {
  const listEl = document.getElementById('aq-cards-list');
  const emptyEl = document.getElementById('aq-empty');
  const emptyTitle = document.getElementById('aq-empty-title');
  const emptyDesc = document.getElementById('aq-empty-desc');
  if (!listEl || !emptyEl) return;

  if (!aqState.items.length) {
    listEl.innerHTML = '';
    if (emptyTitle && emptyDesc) {
      if (aqState.status === 'pending') {
        emptyTitle.textContent = 'No comments need approval';
        emptyDesc.textContent = 'All caught up! New comments flagged for manual review will appear here.';
      } else if (aqState.status === 'history') {
        emptyTitle.textContent = 'No queue history yet';
        emptyDesc.textContent = 'Approved, rejected, replied, and failed items will appear here.';
      } else {
        emptyTitle.textContent = `No ${aqState.status} items`;
        emptyDesc.textContent = 'Try selecting another status or platform filter.';
      }
    }
    emptyEl.classList.remove('hidden');
    return;
  }

  emptyEl.classList.add('hidden');
  listEl.innerHTML = aqState.items.map(item => {
    const pMeta = AQ_PLATFORM_META[item.platform] || { label: item.platform || 'Unknown', icon: '💬' };
    const isPending = item.status === 'pending';
    const isApproved = item.status === 'approved';
    const isEditing = aqState.editingId === item.id;
    const isConfirmingReject = aqState.confirmRejectId === item.id;
    const isBusy = aqState.processingIds.has(item.id);
    const preparedReply = item.edited_reply || item.suggested_reply || '';
    const latestAttempt = (aqState.attemptsByQueueId && aqState.attemptsByQueueId[item.id]) || null;

    const timestampsHtml = [
      `<span>Received: <strong>${aqEscapeHtml(aqFormatDate(item.created_at))}</strong></span>`,
      item.approved_at ? `<span>Approved: <strong>${aqEscapeHtml(aqFormatDate(item.approved_at))}</strong></span>` : '',
      item.published_at ? `<span>Published: <strong>${aqEscapeHtml(aqFormatDate(item.published_at))}</strong></span>` : '',
      (!isPending && item.updated_at) ? `<span>Updated: <strong>${aqEscapeHtml(aqFormatDate(item.updated_at))}</strong></span>` : ''
    ].filter(Boolean).join('');

    const replySectionHtml = isEditing
      ? `
        <div class="aq-edit-area">
          <div class="aq-box-label">Edit Reply</div>
          <textarea id="aq-edit-input-${item.id}" class="aq-edit-textarea" ${isBusy ? 'disabled' : ''}>${aqEscapeHtml(preparedReply)}</textarea>
          <div class="aq-card-actions">
            <button type="button" class="primary-btn sm" onclick="saveApprovalEdit(${item.id})" ${isBusy ? 'disabled' : ''}>Save Changes</button>
            <button type="button" class="secondary-btn sm" onclick="cancelApprovalEdit()" ${isBusy ? 'disabled' : ''}>Cancel</button>
          </div>
        </div>
      `
      : `
        <div class="aq-box">
          <div class="aq-box-label">${item.edited_reply ? 'Prepared Reply (Edited)' : 'Suggested Reply'}</div>
          <div class="aq-reply-text">${aqEscapeHtml(preparedReply || '—')}</div>
        </div>
      `;

    const actionsHtml = isPending
      ? `
        <div class="aq-card-actions">
          ${!isEditing ? `<button type="button" class="secondary-btn sm" onclick="startApprovalEdit(${item.id})" ${isBusy ? 'disabled' : ''}>Edit &amp; Send</button>` : ''}
          <button type="button" class="secondary-btn sm" onclick="regenerateQueueItem(${item.id})" ${isBusy ? 'disabled' : ''}>Regenerate Suggestion</button>
          <button type="button" class="aq-btn-approve" onclick="approveQueueItem(${item.id})" ${isBusy ? 'disabled' : ''}>${isBusy ? 'Processing...' : 'Approve &amp; Send'}</button>
          <button type="button" class="secondary-btn sm" onclick="ignoreQueueItem(${item.id})" ${isBusy ? 'disabled' : ''}>Ignore</button>
          <button type="button" class="secondary-btn sm" onclick="manualFollowupQueueItem(${item.id})" ${isBusy ? 'disabled' : ''}>Manual Follow-up</button>
          <button type="button" class="aq-btn-reject" onclick="promptRejectQueueItem(${item.id})" ${isBusy ? 'disabled' : ''}>Reject</button>
        </div>
        <div style="font-size:0.75rem;opacity:0.75;margin-top:4px;">
          Sentiment: <strong>${aqEscapeHtml(item.sentiment || 'neutral')}</strong> ·
          Method: <strong>${aqEscapeHtml(item.generation_method || 'local_contextual')}</strong>
          ${item.account_id ? ` · Account: <strong>${aqEscapeHtml(item.account_id)}</strong>` : ''}
        </div>
        ${isConfirmingReject ? `
          <div class="aq-reject-confirm">
            <span>Reject this reply? It will be removed from pending and kept in history.</span>
            <button type="button" class="aq-btn-reject" onclick="confirmRejectQueueItem(${item.id})" ${isBusy ? 'disabled' : ''}>Yes, Reject</button>
            <button type="button" class="secondary-btn sm" onclick="cancelRejectQueueItem()" ${isBusy ? 'disabled' : ''}>Cancel</button>
          </div>
        ` : ''}
      `
      : isApproved
      ? `
        <div class="aq-card-actions">
          ${(!latestAttempt || latestAttempt.attempt_status !== 'test_prepared')
            ? `<button type="button" class="primary-btn sm" onclick="prepareTestReply(${item.id})" ${isBusy ? 'disabled' : ''}>${isBusy ? 'Preparing...' : 'Prepare Test Reply'}</button>`
            : `<span class="aq-status-badge approved">Test Prepared</span>`
          }
          ${latestAttempt && latestAttempt.attempt_status === 'blocked'
            ? `<span class="aq-status-badge rejected">Blocked: ${aqEscapeHtml(latestAttempt.blocked_reason || 'unknown')}</span>`
            : ''
          }
          ${latestAttempt && latestAttempt.attempt_status === 'failed'
            ? `<span class="aq-status-badge rejected">Failed: ${aqEscapeHtml(latestAttempt.error_details || latestAttempt.blocked_reason || 'unknown')}</span>`
            : ''
          }
        </div>
        ${latestAttempt ? `
          <div class="aq-reason">
            <strong>Publishing Attempt:</strong> ${aqEscapeHtml(latestAttempt.attempt_status)}
            (${aqEscapeHtml(aqFormatDate(latestAttempt.created_at))})
            ${latestAttempt.blocked_reason ? ` — ${aqEscapeHtml(latestAttempt.blocked_reason)}` : ''}
          </div>
        ` : `<div class="aq-reason"><strong>Publishing Readiness:</strong> Ready for test preparation</div>`}
      `
      : '';

    return `
      <article class="aq-card" data-queue-id="${item.id}">
        <div class="aq-card-header">
          <div class="aq-platform-info">
            <span class="aq-platform-pill ${aqEscapeHtml(item.platform)}">${pMeta.icon} ${aqEscapeHtml(pMeta.label)}</span>
            <span class="aq-account-name">Account: <strong>${aqEscapeHtml(item.account_id || '—')}</strong></span>
            <span class="aq-account-name">Commenter: <strong>${aqEscapeHtml(item.commenter_name || 'Anonymous')}</strong></span>
          </div>
          <span class="aq-status-badge ${aqEscapeHtml(item.status)}">${aqEscapeHtml(item.status)}</span>
        </div>

        <div class="aq-meta-row">
          <span>Language: <strong>${aqEscapeHtml(item.detected_language || 'unknown')}</strong></span>
          <span>Intent: <strong>${aqEscapeHtml(item.detected_intent || 'unknown')}</strong></span>
          ${timestampsHtml}
        </div>

        ${item.review_reason ? `<div class="aq-reason"><strong>Review Reason:</strong> ${aqEscapeHtml(item.review_reason)}</div>` : ''}

        <div class="aq-box">
          <div class="aq-box-label">Original Comment</div>
          <div class="aq-comment-text">${aqEscapeHtml(item.comment_text)}</div>
        </div>

        ${replySectionHtml}
        ${actionsHtml}
      </article>
    `;
  }).join('');
}

function startApprovalEdit(queueId) {
  aqState.editingId = queueId;
  aqState.confirmRejectId = null;
  renderApprovalQueue();
}

function cancelApprovalEdit() {
  aqState.editingId = null;
  renderApprovalQueue();
}

async function saveApprovalEdit(queueId) {
  if (aqState.processingIds.has(queueId)) return;
  const input = document.getElementById(`aq-edit-input-${queueId}`);
  const editedReply = input ? input.value.trim() : '';
  if (!editedReply) {
    aqShowFeedback('Reply cannot be empty.', 'error');
    return;
  }

  aqState.processingIds.add(queueId);
  renderApprovalQueue();

  try {
    const res = await fetch(`/api/approval-queue/${queueId}/edit`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ edited_reply: editedReply })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Could not save reply.');
    }
    aqState.items = aqState.items.map(it => (it.id === queueId ? data.item : it));
    aqState.editingId = null;
    aqShowFeedback('Reply updated and saved.', 'success');
  } catch (err) {
    aqShowFeedback(err.message || 'Failed to save reply.', 'error');
  } finally {
    aqState.processingIds.delete(queueId);
    renderApprovalQueue();
  }
}

// Priority 2E: Platform-specific Hybrid Controls
const psState = {
  activePlatform: 'facebook',
  platforms: {},
};

const PS_TEMPLATE_LABELS = [
  { id: 'ta_1', label: 'Tamil 1 (ta_1)' },
  { id: 'ta_2', label: 'Tamil 2 (ta_2)' },
  { id: 'en_1', label: 'English 1 (en_1)' },
  { id: 'en_2', label: 'English 2 (en_2)' },
  { id: 'tanglish_1', label: 'Tanglish 1 (tanglish_1)' },
  { id: 'tanglish_2', label: 'Tanglish 2 (tanglish_2)' },
];

function selectPlatformSettingsTab(platform) {
  psState.activePlatform = platform;
  document.querySelectorAll('[data-ps-platform]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.psPlatform === platform);
  });
  renderPlatformSettingsPanel();
}

async function loadPlatformSettings() {
  try {
    const res = await fetch('/api/platform-settings');
    if (!res.ok) throw new Error('Failed to load platform settings');
    const data = await res.json();
    psState.platforms = data.platforms || {};
    renderPlatformSettingsPanel();
  } catch (err) {
    const body = document.getElementById('ps-panel-body');
    if (body) body.textContent = err.message || 'Could not load platform settings.';
  }
}

function renderPlatformSettingsPanel() {
  const body = document.getElementById('ps-panel-body');
  if (!body) return;
  const p = psState.activePlatform;
  const cfg = psState.platforms[p];
  if (!cfg) {
    body.textContent = 'Loading...';
    return;
  }
  const enabledSet = new Set(cfg.enabled_templates || []);
  const disabledBanner = !cfg.auto_reply_enabled
    ? `<div class="aq-reason" style="margin-bottom:12px;"><strong>Platform Disabled:</strong> Automatic replies are currently turned OFF for ${aqEscapeHtml(p)}.</div>`
    : '';

  body.innerHTML = `
    <div style="margin-bottom:12px;">
      <strong>Connection Status:</strong>
      <span class="aq-status-badge ${cfg.connected ? 'approved' : 'rejected'}">${cfg.connected ? 'Connected' : 'Not Connected'}</span>
    </div>
    ${disabledBanner}
    <div class="settings-list">
      <label class="setting-item" style="display:flex;justify-content:space-between;align-items:center;">
        <span>Enable ${aqEscapeHtml(p)} Auto Reply</span>
        <input type="checkbox" id="ps-auto-reply" ${cfg.auto_reply_enabled ? 'checked' : ''} />
      </label>
      <label class="setting-item" style="display:flex;justify-content:space-between;align-items:center;">
        <span>Automatic Praise Replies</span>
        <input type="checkbox" id="ps-praise" ${cfg.praise_enabled ? 'checked' : ''} />
      </label>
      <label class="setting-item" style="display:flex;justify-content:space-between;align-items:center;">
        <span>Emoji Appreciation Replies</span>
        <input type="checkbox" id="ps-emoji" ${cfg.emoji_enabled ? 'checked' : ''} />
      </label>
      <label class="setting-item" style="display:flex;justify-content:space-between;align-items:center;">
        <span>Manual Approval Queue</span>
        <input type="checkbox" id="ps-manual-queue" ${cfg.manual_queue_enabled ? 'checked' : ''} />
      </label>
    </div>
    <div style="margin-top:14px;">
      <strong>Approved Reply Templates</strong>
      <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:8px;">
        ${PS_TEMPLATE_LABELS.map(t => `
          <label style="display:flex;align-items:center;gap:6px;">
            <input type="checkbox" class="ps-tpl-cb" value="${t.id}" ${enabledSet.has(t.id) ? 'checked' : ''} />
            <span>${t.label}</span>
          </label>
        `).join('')}
      </div>
    </div>
    <div style="margin-top:16px;">
      <button type="button" class="primary-btn" onclick="savePlatformSettings('${p}')">Save ${aqEscapeHtml(p)} Settings</button>
    </div>
  `;
}

async function savePlatformSettings(platform) {
  const feedback = document.getElementById('ps-feedback');
  const payload = {
    auto_reply_enabled: !!document.getElementById('ps-auto-reply')?.checked,
    praise_enabled: !!document.getElementById('ps-praise')?.checked,
    emoji_enabled: !!document.getElementById('ps-emoji')?.checked,
    manual_queue_enabled: !!document.getElementById('ps-manual-queue')?.checked,
    enabled_templates: Array.from(document.querySelectorAll('.ps-tpl-cb:checked')).map(el => el.value),
  };
  try {
    const res = await fetch(`/api/platform-settings/${platform}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Failed to save settings');
    const data = await res.json();
    psState.platforms[platform] = { ...psState.platforms[platform], ...data.settings };
    renderPlatformSettingsPanel();
    if (feedback) {
      feedback.textContent = `Saved ${platform} settings.`;
      feedback.className = 'aq-feedback success';
      feedback.classList.remove('hidden');
    }
  } catch (err) {
    if (feedback) {
      feedback.textContent = err.message || 'Error saving settings.';
      feedback.className = 'aq-feedback error';
      feedback.classList.remove('hidden');
    }
  }
}

async function prepareTestReply(queueId) {
  aqState.processingIds.add(queueId);
  renderApprovalQueue();
  try {
    const res = await fetch(`/api/approval-queue/${queueId}/prepare-publish`, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || 'Could not prepare test reply.');
    }
    if (data.attempt_status === 'test_prepared') {
      aqShowFeedback('Test reply prepared (Safe Testing Mode ON — not published publicly).', 'success');
    } else {
      aqShowFeedback(`Blocked: ${data.reason || 'ineligible'}`, 'error');
    }
    await loadApprovalQueue();
  } catch (err) {
    aqShowFeedback(err.message || 'Failed to prepare test reply.', 'error');
  } finally {
    aqState.processingIds.delete(queueId);
    renderApprovalQueue();
  }
}

async function _aqSimpleAction(queueId, endpoint, successMsg) {
  aqState.processingIds.add(queueId);
  renderApprovalQueue();
  try {
    const res = await fetch(`/api/approval-queue/${queueId}/${endpoint}`, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Action failed.');
    aqShowFeedback(successMsg, 'success');
    await loadApprovalQueue();
  } catch (err) {
    aqShowFeedback(err.message || 'Action failed.', 'error');
  } finally {
    aqState.processingIds.delete(queueId);
    renderApprovalQueue();
  }
}

function regenerateQueueItem(queueId) {
  return _aqSimpleAction(queueId, 'regenerate', 'Suggestion regenerated.');
}

function ignoreQueueItem(queueId) {
  return _aqSimpleAction(queueId, 'ignore', 'Item marked as ignored.');
}

function manualFollowupQueueItem(queueId) {
  return _aqSimpleAction(queueId, 'manual-followup', 'Marked for manual follow-up.');
}

async function approveQueueItem(queueId) {
  if (aqState.processingIds.has(queueId)) return;
  aqState.processingIds.add(queueId);
  aqState.confirmRejectId = null;
  renderApprovalQueue();

  try {
    const res = await fetch(`/api/approval-queue/${queueId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Could not approve item.');
    }
    aqState.items = aqState.items.map(it => (it.id === queueId ? data.item : it));
    aqState.editingId = null;
    await refreshPendingCount();
    loadStatus();
    aqShowFeedback(
      data.safe_test_mode
        ? 'Reply approved. Safe Testing Mode is ON — no public reply was published.'
        : 'Reply approved.',
      'success'
    );
  } catch (err) {
    aqShowFeedback(err.message || 'Failed to approve item.', 'error');
  } finally {
    aqState.processingIds.delete(queueId);
    renderApprovalQueue();
  }
}

function promptRejectQueueItem(queueId) {
  aqState.confirmRejectId = queueId;
  aqState.editingId = null;
  renderApprovalQueue();
}

function cancelRejectQueueItem() {
  aqState.confirmRejectId = null;
  renderApprovalQueue();
}

async function confirmRejectQueueItem(queueId) {
  if (aqState.processingIds.has(queueId)) return;
  aqState.processingIds.add(queueId);
  renderApprovalQueue();

  try {
    const res = await fetch(`/api/approval-queue/${queueId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Could not reject item.');
    }
    if (aqState.status === 'pending') {
      aqState.items = aqState.items.filter(it => it.id !== queueId);
    } else {
      aqState.items = aqState.items.map(it => (it.id === queueId ? data.item : it));
    }
    aqState.confirmRejectId = null;
    await refreshPendingCount();
    loadStatus();
    aqShowFeedback('Comment rejected and moved to queue history.', 'success');
  } catch (err) {
    aqShowFeedback(err.message || 'Failed to reject item.', 'error');
  } finally {
    aqState.processingIds.delete(queueId);
    renderApprovalQueue();
  }
}

function initApprovalQueue() {
  document.querySelectorAll('.subtab-btn[data-subtab]').forEach(btn => {
    btn.addEventListener('click', () => switchAutoReplySubtab(btn.dataset.subtab));
  });

  document.querySelectorAll('.aq-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      aqState.platform = btn.dataset.platform;
      document.querySelectorAll('.aq-filter-btn').forEach(b => b.classList.toggle('active', b === btn));
      aqHideFeedback();
      loadApprovalQueue();
    });
  });

  document.querySelectorAll('.aq-status-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      aqState.status = btn.dataset.status;
      document.querySelectorAll('.aq-status-btn').forEach(b => b.classList.toggle('active', b === btn));
      aqHideFeedback();
      loadApprovalQueue();
    });
  });

  const refreshBtn = document.getElementById('aq-refresh-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      aqHideFeedback();
      loadApprovalQueue();
    });
  }

  refreshPendingCount();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    initApp();
    initApprovalQueue();
  });
} else {
  initApp();
  initApprovalQueue();
}

// ==============================================================================
// Smart Lead Management (GSP V2.0 Phase 2.0A)
// ==============================================================================
async function loadLeads() {
  const business = document.getElementById('lead-filter-business')?.value || '';
  const status = document.getElementById('lead-filter-status')?.value || '';
  const platform = document.getElementById('lead-filter-platform')?.value || '';
  const category = document.getElementById('lead-filter-category')?.value || '';

  const params = new URLSearchParams();
  if (business) params.set('business_type', business);
  if (status) params.set('lead_status', status);
  if (platform) params.set('platform', platform);
  if (category) params.set('enquiry_category', category);

  try {
    const [summaryRes, listRes] = await Promise.all([
      fetch('/api/leads/summary' + (business ? `?business_type=${encodeURIComponent(business)}` : '')),
      fetch('/api/leads?' + params.toString()),
    ]);

    if (summaryRes.ok) {
      const summary = await summaryRes.json();
      const elTotal = document.getElementById('leads-total-count');
      const elAstro = document.getElementById('leads-astrology-count');
      const elVivaham = document.getElementById('leads-vivaham-count');
      const elNew = document.getElementById('leads-new-count');
      if (elTotal) elTotal.textContent = summary.total ?? 0;
      if (elAstro) elAstro.textContent = summary.by_business?.Astrology ?? 0;
      if (elVivaham) elVivaham.textContent = summary.by_business?.Vivaham ?? 0;
      if (elNew) elNew.textContent = summary.by_status?.New ?? 0;
    }

    if (listRes.ok) {
      const data = await listRes.json();
      const tbody = document.getElementById('leads-table-body');
      if (!tbody) return;
      const leads = data.leads || [];
      if (leads.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 24px; color: var(--text-muted);">No leads found.</td></tr>';
        return;
      }
      const esc = window.GSPUI ? window.GSPUI.escapeHtml : (typeof escapeHtml === 'function' ? escapeHtml : (s) => String(s ?? ''));
      const badge = (st) => window.GSPUI ? window.GSPUI.statusBadge(st) : esc(st);
      tbody.innerHTML = leads.map(lead => `
        <tr>
          <td>${esc(lead.business_type)}</td>
          <td>${esc(lead.platform)}</td>
          <td>${esc(lead.customer_name || lead.customer_username || 'Unknown')}</td>
          <td>${esc(lead.enquiry_category)}</td>
          <td>${badge(lead.lead_status)}</td>
          <td>${esc(lead.priority)}</td>
          <td>${esc(lead.original_message)}</td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Failed to load leads:', err);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  ['lead-filter-business', 'lead-filter-status', 'lead-filter-platform', 'lead-filter-category'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', loadLeads);
  });
  const refreshBtn = document.getElementById('btn-refresh-leads');
  if (refreshBtn) refreshBtn.addEventListener('click', loadLeads);
});


// ==========================================
// Auto Post Scheduler V2 (Phase 3.0A)
// ==========================================
(function initAutoPostScheduler() {
  const ZODIAC_OPTIONS = [
    { index: 1, label: "1. மேஷம் – Aries" },
    { index: 2, label: "2. ரிஷபம் – Taurus" },
    { index: 3, label: "3. மிதுனம் – Gemini" },
    { index: 4, label: "4. கடகம் – Cancer" },
    { index: 5, label: "5. சிம்மம் – Leo" },
    { index: 6, label: "6. கன்னி – Virgo" },
    { index: 7, label: "7. துலாம் – Libra" },
    { index: 8, label: "8. விருச்சிகம் – Scorpio" },
    { index: 9, label: "9. தனுசு – Sagittarius" },
    { index: 10, label: "10. மகரம் – Capricorn" },
    { index: 11, label: "11. கும்பம் – Aquarius" },
    { index: 12, label: "12. மீனம் – Pisces" },
  ];

  const DAY_NAMES = {
    "-1": "Every Day",
    "0": "Monday",
    "1": "Tuesday",
    "2": "Wednesday",
    "3": "Thursday",
    "4": "Friday",
    "5": "Saturday",
    "6": "Sunday",
  };

  let currentBatch = null;
  let draggedPostId = null;

  // Subsection switching
  document.querySelectorAll(".autopost-sub-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.subtab;
      document.querySelectorAll(".autopost-sub-btn").forEach((b) => {
        b.classList.toggle("btn-primary", b.dataset.subtab === target);
        b.classList.toggle("btn-secondary", b.dataset.subtab !== target);
      });
      document.querySelectorAll(".autopost-subsection").forEach((sec) => {
        sec.style.display = sec.id === `autopost-sub-${target}` ? "block" : "none";
      });
      if (target === "schedule") loadPostingSlots();
      if (target === "posts") loadScheduledPosts();
    });
  });

  // File upload & drag-drop
  const dropzone = document.getElementById("autopost-dropzone");
  const fileInput = document.getElementById("autopost-file-input");
  const browseBtn = document.getElementById("autopost-browse-btn");

  if (browseBtn && fileInput) {
    browseBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        uploadBatchFiles(e.target.files);
      }
    });
  }

  if (dropzone) {
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.style.background = "rgba(99,102,241,0.14)";
    });
    dropzone.addEventListener("dragleave", () => {
      dropzone.style.background = "rgba(99,102,241,0.05)";
    });
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.style.background = "rgba(99,102,241,0.05)";
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        uploadBatchFiles(e.dataTransfer.files);
      }
    });
  }

  async function uploadBatchFiles(fileList) {
    const category = document.getElementById("autopost-category-select").value;
    const formData = new FormData();
    Array.from(fileList).forEach((f) => formData.append("files", f));

    const res = await fetch(`/api/auto-post/upload-batch?category=${encodeURIComponent(category)}`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      alert("Upload failed");
      return;
    }
    currentBatch = await res.json();
    renderBatchPreview();
  }

  function renderBatchPreview() {
    if (!currentBatch) return;
    const previewEl = document.getElementById("autopost-batch-preview");
    const warningsEl = document.getElementById("autopost-batch-warnings");
    const listEl = document.getElementById("autopost-batch-list");
    const countEl = document.getElementById("autopost-batch-count");

    previewEl.style.display = "block";
    countEl.textContent = currentBatch.items.length;

    const warnings = [];
    if (currentBatch.missing_signs && currentBatch.missing_signs.length > 0) {
      warnings.push(`Missing signs: ${currentBatch.missing_signs.map((s) => s.tamil).join(", ")}`);
    }
    if (currentBatch.duplicate_signs && currentBatch.duplicate_signs.length > 0) {
      warnings.push(`Duplicate signs: ${currentBatch.duplicate_signs.map((s) => `${s.tamil} (${s.count}x)`).join(", ")}`);
    }
    if (currentBatch.undetected_files && currentBatch.undetected_files.length > 0) {
      warnings.push(`Undetected files: ${currentBatch.undetected_files.join(", ")}`);
    }

    if (warnings.length > 0) {
      warningsEl.style.display = "block";
      warningsEl.style.padding = "12px 16px";
      warningsEl.style.borderLeft = "4px solid #f59e0b";
      warningsEl.innerHTML = `<strong>Warning:</strong> ${warnings.join(" | ")}`;
    } else {
      warningsEl.style.display = "none";
    }

    listEl.innerHTML = currentBatch.items
      .map((item, idx) => {
        const opts = ZODIAC_OPTIONS.map(
          (z) => `<option value="${z.index}" ${z.index === item.zodiac_index ? "selected" : ""}>${z.label}</option>`
        ).join("");
        return `
          <div style="display:grid;grid-template-columns:1.2fr 1fr 2fr;gap:10px;align-items:center;padding:10px;border:1px solid rgba(255,255,255,0.1);border-radius:8px;">
            <div style="font-weight:600;word-break:break-all;">${item.original_filename}</div>
            <select class="form-control autopost-zodiac-fix" data-idx="${idx}" style="padding:6px;">
              <option value="">-- Select Sign --</option>
              ${opts}
            </select>
            <input type="text" class="form-control autopost-caption-edit" data-idx="${idx}" value="${(item.caption || "").replace(/"/g, "&quot;")}" style="padding:6px;" />
          </div>
        `;
      })
      .join("");

    listEl.querySelectorAll(".autopost-zodiac-fix").forEach((sel) => {
      sel.addEventListener("change", (e) => {
        const idx = parseInt(e.target.dataset.idx, 10);
        currentBatch.items[idx].zodiac_index = parseInt(e.target.value, 10) || null;
      });
    });
    listEl.querySelectorAll(".autopost-caption-edit").forEach((inp) => {
      inp.addEventListener("input", (e) => {
        const idx = parseInt(e.target.dataset.idx, 10);
        currentBatch.items[idx].caption = e.target.value;
      });
    });
  }

  // One-click SCHEDULE ALL (Multi-Channel)
  const scheduleAllBtn = document.getElementById("autopost-schedule-all-btn");
  if (scheduleAllBtn) {
    scheduleAllBtn.addEventListener("click", async () => {
      if (!currentBatch || !currentBatch.items.length) return;
      const checked = Array.from(document.querySelectorAll(".autopost-channel-checkbox:checked"));
      if (checked.length === 0) {
        alert("Please select at least one publishing channel.");
        return;
      }
      const accounts = checked.map((cb) => {
        const [account_key, platform] = cb.value.split("|");
        return { account_key, platform };
      });
      const category = document.getElementById("autopost-category-select").value;

      const payload = {
        accounts,
        category,
        batch_id: currentBatch.batch_id,
        items: currentBatch.items.map((i) => ({
          original_filename: i.original_filename,
          media_path: i.media_path,
          file_size_bytes: i.file_size_bytes || 0,
          zodiac_index: i.zodiac_index,
          caption: i.caption,
          hashtags: i.hashtags,
        })),
      };

      const res = await fetch("/api/auto-post/schedule-multichannel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      const summaryEl = document.getElementById("autopost-schedule-summary");
      if (!res.ok) {
        alert(data.detail || "Failed to schedule batch");
        return;
      }
      const firstTime = data.posts && data.posts.length ? data.posts[0].scheduled_at.replace("T", " ") : "N/A";
      summaryEl.style.display = "block";
      summaryEl.innerHTML = `
        <strong>Scheduled Successfully!</strong><br/>
        Videos imported: ${data.videos_count} |
        Channels selected: ${data.channels_count} |
        Total publishing jobs: ${data.scheduled_count} |
        First scheduled slot: ${firstTime}
      `;
    });
  }

  // Buffer-style Weekly Posting Schedule
  const WEEKLY_COLUMNS = [
    { dow: 6, label: "Sunday" },
    { dow: 0, label: "Monday" },
    { dow: 1, label: "Tuesday" },
    { dow: 2, label: "Wednesday" },
    { dow: 3, label: "Thursday" },
    { dow: 4, label: "Friday" },
    { dow: 5, label: "Saturday" },
  ];

  let currentScheduleSettings = {
    account_key: "facebook:default",
    timezone: "Asia/Kolkata",
    weekly_goal: 14,
    enabled_days: [0, 1, 2, 3, 4, 5, 6],
  };

  function showScheduleFeedback(msg, isError = false) {
    const el = document.getElementById("schedule-feedback");
    if (!el) return;
    el.textContent = msg;
    el.className = "schedule-feedback" + (isError ? " error" : "");
    el.style.display = "inline-block";
    clearTimeout(el._hideTimer);
    el._hideTimer = setTimeout(() => {
      el.style.display = "none";
    }, 2800);
  }

  function formatTime12h(hhmm) {
    const [hStr, mStr] = (hhmm || "09:00").split(":");
    let h = parseInt(hStr, 10);
    const m = mStr || "00";
    const ampm = h >= 12 ? "PM" : "AM";
    h = h % 12 || 12;
    return `${h}:${m} ${ampm}`;
  }

  function to24h(hour12, minute, ampm) {
    let h = parseInt(hour12, 10);
    if (ampm === "AM") {
      if (h === 12) h = 0;
    } else {
      if (h !== 12) h += 12;
    }
    return `${String(h).padStart(2, "0")}:${minute}`;
  }

  async function saveScheduleSettings(patch) {
    const accountKey = document.getElementById("slot-account-select").value;
    const res = await fetch("/api/auto-post/schedule-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_key: accountKey, ...patch }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showScheduleFeedback(err.detail || "Failed to save settings", true);
      return null;
    }
    currentScheduleSettings = await res.json();
    showScheduleFeedback("Schedule settings saved");
    return currentScheduleSettings;
  }

  async function loadPostingSlots() {
    const accountKey = document.getElementById("slot-account-select").value;
    const [settingsRes, slotsRes] = await Promise.all([
      fetch(`/api/auto-post/schedule-settings?account_key=${encodeURIComponent(accountKey)}`),
      fetch(`/api/auto-post/slots?account_key=${encodeURIComponent(accountKey)}`),
    ]);
    if (settingsRes.ok) {
      currentScheduleSettings = await settingsRes.json();
    }
    const slotsData = await slotsRes.json();
    const allSlots = slotsData.slots || [];

    const tzSelect = document.getElementById("schedule-timezone-select");
    if (tzSelect && currentScheduleSettings.timezone) {
      tzSelect.value = currentScheduleSettings.timezone;
    }
    const goalEl = document.getElementById("weekly-goal-value");
    if (goalEl) {
      goalEl.textContent = String(currentScheduleSettings.weekly_goal ?? 14);
    }

    const enabledSet = new Set(currentScheduleSettings.enabled_days || [0, 1, 2, 3, 4, 5, 6]);
    const gridEl = document.getElementById("weekly-schedule-grid");
    if (!gridEl) return;

    gridEl.innerHTML = WEEKLY_COLUMNS.map(({ dow, label }) => {
      const isEnabled = enabledSet.has(dow);
      const daySlots = allSlots
        .filter((s) => Number(s.day_of_week) === dow || Number(s.day_of_week) === -1)
        .sort((a, b) => (a.slot_time || "").localeCompare(b.slot_time || ""));

      const slotsHtml = daySlots.length
        ? daySlots
            .map(
              (s) => `
              <div class="day-slot-pill">
                <span>${formatTime12h(s.slot_time)}</span>
                <button type="button" class="day-slot-remove" data-id="${s.id}" title="Remove slot">&times;</button>
              </div>
            `
            )
            .join("")
        : `<div class="day-empty-label">${isEnabled ? "No slots" : "Disabled"}</div>`;

      return `
        <div class="day-column ${isEnabled ? "" : "disabled"}" data-dow="${dow}">
          <div class="day-column-header">
            <span class="day-column-title">${label}</span>
            <label class="day-toggle-switch" title="Enable/disable ${label}">
              <input type="checkbox" class="day-toggle-input" data-dow="${dow}" ${isEnabled ? "checked" : ""} />
              <span class="day-toggle-slider"></span>
            </label>
          </div>
          <div class="day-slots-list">${slotsHtml}</div>
        </div>
      `;
    }).join("");

    gridEl.querySelectorAll(".day-toggle-input").forEach((chk) => {
      chk.addEventListener("change", async () => {
        const dow = parseInt(chk.dataset.dow, 10);
        const nextSet = new Set(currentScheduleSettings.enabled_days || []);
        if (chk.checked) nextSet.add(dow);
        else nextSet.delete(dow);
        await saveScheduleSettings({ enabled_days: Array.from(nextSet).sort((a, b) => a - b) });
        loadPostingSlots();
      });
    });

    gridEl.querySelectorAll(".day-slot-remove").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const res = await fetch(`/api/auto-post/slots/${btn.dataset.id}`, { method: "DELETE" });
        if (res.ok) {
          showScheduleFeedback("Slot removed");
          loadPostingSlots();
        } else {
          showScheduleFeedback("Failed to remove slot", true);
        }
      });
    });
  }

  const slotAccSel = document.getElementById("slot-account-select");
  if (slotAccSel) slotAccSel.addEventListener("change", loadPostingSlots);

  const tzSelect = document.getElementById("schedule-timezone-select");
  if (tzSelect) {
    tzSelect.addEventListener("change", async () => {
      await saveScheduleSettings({ timezone: tzSelect.value });
    });
  }

  const goalDecBtn = document.getElementById("goal-decrease-btn");
  if (goalDecBtn) {
    goalDecBtn.addEventListener("click", async () => {
      const next = Math.max(1, (currentScheduleSettings.weekly_goal || 14) - 1);
      await saveScheduleSettings({ weekly_goal: next });
      loadPostingSlots();
    });
  }

  const goalIncBtn = document.getElementById("goal-increase-btn");
  if (goalIncBtn) {
    goalIncBtn.addEventListener("click", async () => {
      const next = Math.min(500, (currentScheduleSettings.weekly_goal || 14) + 1);
      await saveScheduleSettings({ weekly_goal: next });
      loadPostingSlots();
    });
  }

  const addSlotBtn = document.getElementById("add-slot-btn");
  if (addSlotBtn) {
    addSlotBtn.addEventListener("click", async () => {
      const accountKey = document.getElementById("slot-account-select").value;
      const dayOfWeek = parseInt(document.getElementById("slot-day-select").value, 10);
      const hour = document.getElementById("slot-hour-select").value;
      const minute = document.getElementById("slot-minute-select").value;
      const ampm = document.getElementById("slot-ampm-select").value;
      const slotTime = to24h(hour, minute, ampm);

      const res = await fetch("/api/auto-post/slots/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_key: accountKey, day_of_week: dayOfWeek, slot_time: slotTime }),
      });
      if (res.ok) {
        showScheduleFeedback("Posting slot added");
        loadPostingSlots();
      } else {
        showScheduleFeedback("Failed to add posting slot", true);
      }
    });
  }

  const genSlotsBtn = document.getElementById("generate-slots-btn");
  if (genSlotsBtn) {
    genSlotsBtn.addEventListener("click", async () => {
      const mode = document.getElementById("generate-slots-select").value;
      if (!mode) return;
      const confirmMsg =
        mode === "clear"
          ? "Clear all posting slots for this channel?"
          : "This will replace existing posting slots for the target days. Continue?";
      const confirmed = window.GSPUI
        ? await window.GSPUI.confirm({
            title: "Confirm Schedule Update",
            message: confirmMsg,
            confirmText: "Continue",
            variant: mode === "clear" ? "danger" : "primary"
          })
        : window.confirm(confirmMsg);
      if (!confirmed) return;

      const accountKey = document.getElementById("slot-account-select").value;
      const res = await fetch("/api/auto-post/slots/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_key: accountKey,
          mode,
          days: mode === "regenerate_days" ? currentScheduleSettings.enabled_days : null,
        }),
      });
      if (res.ok) {
        showScheduleFeedback(mode === "clear" ? "All slots cleared" : "Posting slots generated");
        document.getElementById("generate-slots-select").value = "";
        loadPostingSlots();
      } else {
        showScheduleFeedback("Failed to generate slots", true);
      }
    });
  }

  // Scheduled Posts & Drag-and-Drop (Grouped by Video)
  async function loadScheduledPosts() {
    const res = await fetch("/api/auto-post/posts");
    const data = await res.json();
    const grid = document.getElementById("scheduled-posts-grid");
    const allPosts = data.posts || [];

    const counts = {
      scheduled: 0,
      published: 0,
      failed: 0,
      retry_waiting: 0,
      auth_required: 0,
    };
    allPosts.forEach((p) => {
      if (p.status === "scheduled") counts.scheduled += 1;
      else if (p.status === "published" || p.status === "published_safe_mode") counts.published += 1;
      else if (p.status === "failed") counts.failed += 1;
      else if (p.status === "retry_waiting") counts.retry_waiting += 1;
      else if (p.status === "auth_required") counts.auth_required += 1;
    });
    const setCount = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = String(val);
    };
    setCount("summary-count-scheduled", counts.scheduled);
    setCount("summary-count-published", counts.published);
    setCount("summary-count-failed", counts.failed);
    setCount("summary-count-retry-waiting", counts.retry_waiting);
    setCount("summary-count-auth-required", counts.auth_required);

    const platformFilter = document.getElementById("scheduler-platform-filter")?.value || "";
    const statusFilter = document.getElementById("scheduler-status-filter")?.value || "";
    const filteredPosts = allPosts.filter((p) => {
      if (platformFilter && p.platform !== platformFilter) return false;
      if (statusFilter) {
        if (statusFilter === "published") {
          if (p.status !== "published" && p.status !== "published_safe_mode") return false;
        } else if (p.status !== statusFilter) {
          return false;
        }
      }
      return true;
    });

    if (!grid) return;
    if (filteredPosts.length === 0) {
      grid.innerHTML = `<p style="opacity:0.7;">No scheduled posts match the selected filters.</p>`;
      return;
    }

    const groups = new Map();
    filteredPosts.forEach((p) => {
      const key = p.video_id || `post_${p.id}`;
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          video_id: p.video_id || null,
          first_id: p.id,
          zodiac_tamil: p.zodiac_tamil,
          zodiac_english: p.zodiac_english,
          scheduled_at: p.scheduled_at,
          caption: p.caption,
          jobs: [],
        });
      }
      groups.get(key).jobs.push(p);
    });

    const statusLabels = {
      scheduled: "Scheduled",
      preparing: "Preparing",
      uploading: "Uploading",
      processing: "Processing",
      publishing: "Publishing",
      published: "Published",
      published_safe_mode: "Published (Safe Mode)",
      retry_waiting: "Retry Waiting",
      auth_required: "Authentication Required",
      failed: "Failed",
      cancelled: "Cancelled",
    };

    grid.innerHTML = Array.from(groups.values())
      .map((g) => {
        const destHtml = g.jobs
          .map((j) => {
            const label = statusLabels[j.status] || j.status;
            const progHtml = j.upload_progress_pct > 0 && j.status !== "published" && j.status !== "published_safe_mode"
              ? ` (${Math.round(j.upload_progress_pct)}%)`
              : "";
            const metaParts = [];
            if (j.attempt_count > 0) metaParts.push(`Attempts: ${j.attempt_count}`);
            if (j.next_retry_at) metaParts.push(`Next retry: ${j.next_retry_at.replace("T", " ")}`);
            const metaHtml = metaParts.length
              ? `<div style="font-size:0.72rem;opacity:0.7;margin-top:2px;">${metaParts.join(" • ")}</div>`
              : "";
            const errHtml = j.error_message
              ? `<div style="font-size:0.75rem;color:#f87171;margin-top:2px;">${j.error_message}</div>`
              : "";
            const refHtml = j.external_post_id
              ? `<div style="font-size:0.75rem;opacity:0.75;margin-top:2px;">ID: ${j.external_post_id}${j.permalink ? ` • <a href="${j.permalink}" target="_blank" rel="noopener">View</a>` : ""}</div>`
              : "";
            const retryBtn = ["failed", "retry_waiting", "auth_required"].includes(j.status)
              ? `<button type="button" class="btn btn-secondary retry-post-btn" data-id="${j.id}" style="padding:2px 8px;font-size:0.72rem;margin-left:6px;">Retry</button>`
              : "";
            return `
            <div style="font-size:0.82rem;padding:6px 8px;border-radius:6px;background:rgba(255,255,255,0.04);margin-bottom:4px;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="text-transform:capitalize;">${j.platform} (${j.account_key})</span>
                <span><span style="padding:2px 8px;border-radius:12px;background:rgba(99,102,241,0.2);">${label}${progHtml}</span>${retryBtn}</span>
              </div>
              ${metaHtml}${errHtml}${refHtml}
            </div>
          `;
          })
          .join("");
        return `
        <div class="card scheduled-post-card" draggable="true" data-videoid="${g.video_id || ""}" data-id="${g.first_id}" data-time="${g.scheduled_at}" style="padding:14px;border:1px solid rgba(255,255,255,0.12);cursor:grab;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <strong>${g.zodiac_tamil} (${g.zodiac_english})</strong>
            <span style="font-size:0.8rem;opacity:0.8;">${g.scheduled_at.replace("T", " ")}</span>
          </div>
          <div style="font-size:0.85rem;margin-bottom:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${g.caption}</div>
          <div style="margin-bottom:10px;">${destHtml}</div>
          <div style="display:flex;gap:6px;">
            <button type="button" class="btn btn-secondary cancel-post-btn" data-id="${g.first_id}" style="padding:4px 10px;font-size:0.8rem;">Cancel</button>
          </div>
        </div>
      `;
      })
      .join("");

    let draggedVideoId = null;
    grid.querySelectorAll(".scheduled-post-card").forEach((card) => {
      card.addEventListener("dragstart", () => {
        draggedPostId = card.dataset.id;
        draggedVideoId = card.dataset.videoid || null;
      });
      card.addEventListener("dragover", (e) => e.preventDefault());
      card.addEventListener("drop", async (e) => {
        e.preventDefault();
        const targetTime = card.dataset.time;
        if (!draggedPostId || draggedPostId === card.dataset.id) return;
        const url = draggedVideoId
          ? `/api/auto-post/videos/${encodeURIComponent(draggedVideoId)}/reschedule`
          : `/api/auto-post/posts/${draggedPostId}/reschedule`;
        const res = await fetch(url, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scheduled_at: targetTime }),
        });
        const result = await res.json();
        if (!res.ok) {
          alert(result.detail || "Reschedule conflict");
        } else {
          loadScheduledPosts();
        }
        draggedPostId = null;
        draggedVideoId = null;
      });
    });

    grid.querySelectorAll(".cancel-post-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await fetch(`/api/auto-post/posts/${btn.dataset.id}/cancel`, { method: "POST" });
        loadScheduledPosts();
      });
    });

    grid.querySelectorAll(".retry-post-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await fetch(`/api/auto-post/posts/${btn.dataset.id}/retry`, { method: "POST" });
        loadScheduledPosts();
      });
    });
  }

  const refreshPostsBtn = document.getElementById("refresh-scheduled-posts-btn");
  if (refreshPostsBtn) refreshPostsBtn.addEventListener("click", loadScheduledPosts);
  const platformFilterEl = document.getElementById("scheduler-platform-filter");
  if (platformFilterEl) platformFilterEl.addEventListener("change", loadScheduledPosts);
  const statusFilterEl = document.getElementById("scheduler-status-filter");
  if (statusFilterEl) statusFilterEl.addEventListener("change", loadScheduledPosts);

  document.getElementById('btn-check-all-connections')?.addEventListener('click', () => checkAccountHealth());
  document.getElementById('fb-btn-check-health')?.addEventListener('click', () => checkAccountHealth('facebook'));
  document.getElementById('ig-btn-check-health')?.addEventListener('click', () => checkAccountHealth('instagram'));
  document.getElementById('yt-btn-check-health')?.addEventListener('click', () => checkAccountHealth('youtube'));
  document.getElementById('yt-btn-refresh-auth')?.addEventListener('click', async () => {
    const btn = document.getElementById('yt-btn-refresh-auth');
    if (btn) btn.disabled = true;
    try {
      const res = await fetch('/api/accounts/health/refresh?platform=youtube', { method: 'POST' });
      if (res.ok) {
        await checkAccountHealth('youtube');
      } else {
        const errData = await res.json().catch(() => ({}));
        const detailEl = document.getElementById('yt-health-detail');
        if (detailEl) detailEl.textContent = errData.detail || `Refresh failed (HTTP ${res.status})`;
      }
    } catch (err) {
      console.error('YouTube authorization refresh failed:', err);
      const detailEl = document.getElementById('yt-health-detail');
      if (detailEl) detailEl.textContent = 'YouTube authorization refresh failed.';
    } finally {
      if (btn) btn.disabled = false;
    }
  });
})();

async function checkAccountHealth(platform = null) {
  const prefixMap = { facebook: 'fb', instagram: 'ig', youtube: 'yt' };
  const targets = platform && prefixMap[platform] ? [platform] : ['facebook', 'instagram', 'youtube'];
  const setEl = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };

  targets.forEach((plat) => {
    const p = prefixMap[plat];
    setEl(`${p}-health-ready`, 'Checking...');
    setEl(`${p}-health-detail`, '');
  });

  const url = platform ? `/api/accounts/health?platform=${encodeURIComponent(platform)}` : '/api/accounts/health';
  try {
    const res = await fetch(url);
    if (!res.ok) {
      targets.forEach((plat) => {
        const p = prefixMap[plat];
        setEl(`${p}-health-ready`, 'Not Verified');
        setEl(`${p}-health-detail`, `Health check failed (HTTP ${res.status}).`);
      });
      return;
    }
    const data = await res.json();
    const accounts = data.accounts || {};
    Object.entries(accounts).forEach(([plat, info]) => {
      const p = prefixMap[plat];
      if (!p || !info) return;
      setEl(`${p}-health-conn`, info.account_connection || 'Unknown');
      setEl(`${p}-health-auth`, info.authorization || 'Unknown');
      setEl(`${p}-health-ready`, info.publishing_readiness || 'Not Verified');
      setEl(`${p}-health-checked`, info.last_checked ? info.last_checked.replace('T', ' ') : '—');
      setEl(`${p}-health-detail`, info.detail || '');
      if (plat === 'youtube') {
        const refBtn = document.getElementById('yt-btn-refresh-auth');
        if (refBtn) refBtn.classList.toggle('hidden', !info.can_refresh);
      }
    });
  } catch (err) {
    console.error('Account health check failed:', err);
    targets.forEach((plat) => {
      const p = prefixMap[plat];
      setEl(`${p}-health-ready`, 'Not Verified');
      setEl(`${p}-health-detail`, 'Health check request failed.');
    });
  }
}


// =========================================================================
// Buffer-Style Publishing Workspace (Gokul Publisher)
// =========================================================================
(function () {
  const PUB_STATE = {
    channels: [],
    posts: [],
    counts: { queue: 0, drafts: 0, approvals: 0, sent: 0, failed: 0, total: 0 },
    selectedChannel: "all",
    activeTab: "queue",       // queue | drafts | approvals | sent
    activeView: "list",       // list | calendar | board
    calMode: "month",         // month | week | day
    calCursor: new Date(),
    filters: {
      search: "",
      platform: "",
      status: "",
      category: "",
      dateFrom: "",
      dateTo: "",
    },
    pendingConfirmPostId: null,
  };

  const PLATFORM_ICON = { facebook: "📘", instagram: "📸", youtube: "▶️" };
  const QUEUE_SET = new Set(["scheduled", "publishing", "uploading", "processing", "retry_waiting", "auth_required", "failed"]);
  const SENT_SET = new Set(["published", "published_safe_mode"]);
  const DRAFT_SET = new Set(["draft"]);
  const APPROVAL_SET = new Set(["pending_approval"]);

  function esc(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtDateIST(iso) {
    if (!iso) return "Unscheduled";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      return d.toLocaleString("en-IN", {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      });
    } catch {
      return iso;
    }
  }

  function fmtTimeIST(iso) {
    if (!iso) return "--:--";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso.slice(11, 16) || "--:--";
      return d.toLocaleTimeString("en-IN", {
        timeZone: "Asia/Kolkata",
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      });
    } catch {
      return "--:--";
    }
  }

  function dateKeyIST(iso) {
    if (!iso) return "Unscheduled";
    return String(iso).slice(0, 10);
  }

  async function fetchWorkspace() {
    const ak = PUB_STATE.selectedChannel === "all" ? "" : `?account_key=${encodeURIComponent(PUB_STATE.selectedChannel)}`;
    try {
      const res = await fetch(`/api/publishing/workspace${ak}`);
      if (!res.ok) throw new Error("Failed to load publishing workspace");
      const data = await res.json();
      PUB_STATE.channels = data.channels || [];
      PUB_STATE.posts = data.posts || [];
      PUB_STATE.counts = data.counts || { queue: 0, drafts: 0, approvals: 0, sent: 0 };
      renderAll();
    } catch (err) {
      console.error("Publishing workspace error:", err);
    }
  }

  function getFilteredPosts(ignoreTab = false) {
    const f = PUB_STATE.filters;
    const q = f.search.trim().toLowerCase();
    return PUB_STATE.posts.filter((p) => {
      if (!ignoreTab) {
        const st = p.status || "scheduled";
        if (PUB_STATE.activeTab === "queue" && !QUEUE_SET.has(st)) return false;
        if (PUB_STATE.activeTab === "drafts" && !DRAFT_SET.has(st)) return false;
        if (PUB_STATE.activeTab === "approvals" && !APPROVAL_SET.has(st)) return false;
        if (PUB_STATE.activeTab === "sent" && !SENT_SET.has(st)) return false;
      }
      if (f.platform && p.platform !== f.platform) return false;
      if (f.status) {
        if (f.status === "published" && !SENT_SET.has(p.status)) return false;
        else if (f.status === "failed" && !["failed", "retry_waiting", "auth_required"].includes(p.status)) return false;
        else if (f.status !== "published" && f.status !== "failed" && p.status !== f.status) return false;
      }
      if (f.category && p.category !== f.category) return false;
      if (f.dateFrom && dateKeyIST(p.scheduled_at) < f.dateFrom) return false;
      if (f.dateTo && dateKeyIST(p.scheduled_at) > f.dateTo) return false;
      if (q) {
        const hay = `${p.caption || ""} ${p.original_filename || ""} ${p.zodiac_english || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function renderSidebar() {
    const list = document.getElementById("pub-channel-list");
    if (!list) return;
    const totalQ = PUB_STATE.channels.reduce((s, c) => s + (c.queued_count || 0), 0);
    const totalP = PUB_STATE.channels.reduce((s, c) => s + (c.published_count || 0), 0);

    let html = `
      <div class="pub-channel-item ${PUB_STATE.selectedChannel === "all" ? "active" : ""}" data-channel="all">
        <div class="pub-ch-left">
          <div class="pub-ch-icon">🌐</div>
          <div>
            <div class="pub-ch-name">All Channels</div>
            <div class="pub-ch-sub"><span class="pub-dot connected"></span> Unified View</div>
          </div>
        </div>
        <div class="pub-ch-counts"><span>${totalQ} Q</span><span>${totalP} S</span></div>
      </div>
    `;

    for (const ch of PUB_STATE.channels) {
      const icon = PLATFORM_ICON[ch.platform] || "📢";
      html += `
        <div class="pub-channel-item ${PUB_STATE.selectedChannel === ch.account_key ? "active" : ""}" data-channel="${esc(ch.account_key)}">
          <div class="pub-ch-left">
            <div class="pub-ch-icon">${icon}</div>
            <div style="min-width:0;">
              <div class="pub-ch-name">${esc(ch.name)}</div>
              <div class="pub-ch-sub"><span class="pub-dot ${ch.connected ? "connected" : "disconnected"}"></span> ${ch.connected ? "Connected" : "Not Connected"}</div>
            </div>
          </div>
          <div class="pub-ch-counts"><span>${ch.queued_count} Q</span><span>${ch.published_count} S</span></div>
        </div>
      `;
    }
    list.innerHTML = html;
    list.querySelectorAll(".pub-channel-item").forEach((el) => {
      el.addEventListener("click", () => {
        PUB_STATE.selectedChannel = el.dataset.channel;
        fetchWorkspace();
      });
    });
  }

  function renderHeaderAndTabs() {
    const avatar = document.getElementById("pub-header-avatar");
    const name = document.getElementById("pub-header-name");
    const tz = document.getElementById("pub-header-tz");
    const goalText = document.getElementById("pub-header-goal-text");
    const goalBar = document.getElementById("pub-header-goal-bar");

    if (PUB_STATE.selectedChannel === "all") {
      if (avatar) avatar.textContent = "🌐";
      if (name) name.textContent = "All Channels";
      const totalGoal = PUB_STATE.channels.reduce((s, c) => s + (c.weekly_goal || 14), 0) || 42;
      const totalProg = PUB_STATE.channels.reduce((s, c) => s + (c.weekly_progress || 0), 0);
      if (tz) tz.textContent = "🕒 Asia/Kolkata";
      if (goalText) goalText.textContent = `🎯 Weekly Goal: ${totalProg} / ${totalGoal}`;
      if (goalBar) goalBar.style.width = `${Math.min(100, Math.round((totalProg / totalGoal) * 100))}%`;
    } else {
      const ch = PUB_STATE.channels.find((c) => c.account_key === PUB_STATE.selectedChannel);
      if (ch) {
        if (avatar) avatar.textContent = PLATFORM_ICON[ch.platform] || "📢";
        if (name) name.textContent = ch.name;
        if (tz) tz.textContent = `🕒 ${ch.timezone || "Asia/Kolkata"}`;
        if (goalText) goalText.textContent = `🎯 Weekly Goal: ${ch.weekly_progress} / ${ch.weekly_goal}`;
        if (goalBar) goalBar.style.width = `${Math.min(100, Math.round((ch.weekly_progress / (ch.weekly_goal || 1)) * 100))}%`;
      }
    }

    const c = PUB_STATE.counts;
    const setCnt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = String(val ?? 0); };
    setCnt("pub-count-queue", c.queue);
    setCnt("pub-count-drafts", c.drafts);
    setCnt("pub-count-approvals", c.approvals);
    setCnt("pub-count-sent", c.sent);
    const rwCount = PUB_STATE.posts.filter((p) => p.status === "retry_waiting").length;
    const arCount = PUB_STATE.posts.filter((p) => p.status === "auth_required").length;
    setCnt("summary-count-retry-waiting", rwCount);
    setCnt("summary-count-auth-required", arCount);
  }

  function renderCard(p) {
    const icon = PLATFORM_ICON[p.platform] || "📢";
    const st = p.status || "scheduled";
    const isSent = SENT_SET.has(st);
    const isDraft = DRAFT_SET.has(st);
    const isApproval = APPROVAL_SET.has(st);
    const canPublishNow = !isSent && st !== "cancelled";
    const canReschedule = ["scheduled", "failed", "retry_waiting", "draft", "pending_approval"].includes(st);
    const canMoveDraft = !isSent && !isDraft;
    const canRemove = !isSent && st !== "cancelled";

    const multiCount = p.video_id ? PUB_STATE.posts.filter((x) => x.video_id === p.video_id).length : 1;
    const multiBadge = multiCount > 1 ? `<span class="pub-meta-pill" title="Shared across ${multiCount} destination jobs">🔗 ${multiCount} platforms</span>` : "";
    const statusHtml = window.GSPUI ? window.GSPUI.statusBadge(st) : `<span class="pub-badge pub-badge-${esc(st)}">${esc(st.replace(/_/g, " "))}</span>`;
    const mediaSrc = (p.batch_id && p.original_filename)
      ? `/api/auto-post/media/${encodeURIComponent(p.batch_id)}/${encodeURIComponent(p.original_filename)}`
      : "";
    const mediaThumbHtml = mediaSrc
      ? `<div class="pub-card-thumb pub-card-thumb-right"><video src="${mediaSrc}#t=0.5" muted preload="metadata" playsinline onerror="this.style.display='none';this.nextElementSibling.style.display='flex';"></video><span class="pub-thumb-fallback" style="display:none;">🎬</span></div>`
      : `<div class="pub-card-thumb pub-card-thumb-right"><span class="pub-thumb-fallback">🎬</span></div>`;

    return `
      <div class="pub-card" draggable="true" data-post-id="${p.id}">
        <div class="pub-card-top">
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            <span>${icon}</span>
            <strong>${esc(p.account_key)}</strong>
            ${statusHtml}
            ${multiBadge}
          </div>
          <span class="pub-card-id">#${p.id}</span>
        </div>
        <div class="pub-card-media-row pub-card-media-row-right">
          <div style="min-width:0;flex:1;">
            <div class="pub-card-title">${esc(p.original_filename || p.zodiac_english || "Untitled")}</div>
            <div class="pub-card-caption">${esc(p.caption || "(No caption)")}</div>
          </div>
          ${mediaThumbHtml}
        </div>
        <div class="pub-card-meta">
          <span>📅 ${fmtDateIST(p.scheduled_at)}</span>
          <span>📁 ${esc(p.category || "General")}</span>
          <span>🕒 Created: ${fmtDateIST(p.created_at)}</span>
        </div>
        ${p.error_message ? `<div class="pub-card-error">⚠ ${esc(p.error_message)}</div>` : ""}
        <div class="pub-card-actions">
          ${canPublishNow ? `<button type="button" class="btn btn-primary btn-sm pub-act-publish" data-id="${p.id}">Publish Now</button>` : ""}
          <button type="button" class="btn btn-secondary btn-sm pub-act-edit" data-id="${p.id}">Edit</button>
          ${canReschedule ? `<button type="button" class="btn btn-secondary btn-sm pub-act-resched" data-id="${p.id}">Reschedule</button>` : ""}
          ${canMoveDraft ? `<button type="button" class="btn btn-secondary btn-sm pub-act-draft" data-id="${p.id}">Move to Draft</button>` : ""}
          ${isApproval ? `<button type="button" class="btn btn-primary btn-sm pub-act-approve" data-id="${p.id}">Approve</button>` : ""}
          ${canRemove ? `<button type="button" class="btn btn-secondary btn-sm pub-act-remove" data-id="${p.id}">Remove from Queue</button>` : ""}
          <button type="button" class="btn btn-secondary btn-sm pub-act-details" data-id="${p.id}">View Details</button>
        </div>
      </div>
    `;
  }

  function renderListView() {
    const container = document.getElementById("pub-view-list");
    if (!container) return;
    const posts = getFilteredPosts();
    if (!posts.length) {
      container.innerHTML = window.GSPUI
        ? window.GSPUI.emptyState({
            icon: "📅",
            title: `No posts in ${PUB_STATE.activeTab}`,
            description: "Adjust your filters or create a new post to populate this view."
          })
        : `<div style="padding:36px;text-align:center;opacity:0.7;">No posts in ${esc(PUB_STATE.activeTab)} matching current filters.</div>`;
      return;
    }

    const groups = {};
    for (const p of posts) {
      const k = dateKeyIST(p.scheduled_at);
      if (!groups[k]) groups[k] = [];
      groups[k].push(p);
    }

    let html = "";
    for (const dateKey of Object.keys(groups).sort()) {
      html += `<div class="pub-date-group"><div class="pub-date-header">${esc(dateKey)}</div>`;
      for (const p of groups[dateKey]) {
        html += `
          <div class="pub-timeline-row">
            <div class="pub-timeline-time">${fmtTimeIST(p.scheduled_at)}</div>
            <div>${renderCard(p)}</div>
          </div>
        `;
      }
      html += `</div>`;
    }
    container.innerHTML = html;
    bindCardActions(container);
  }

  function renderCalendarView() {
    const container = document.getElementById("pub-view-calendar");
    if (!container) return;
    const posts = getFilteredPosts();
    const cur = new Date(PUB_STATE.calCursor);
    const label = document.getElementById("pub-cal-label");

    if (PUB_STATE.calMode === "day") {
      const isoDay = cur.toISOString().slice(0, 10);
      if (label) label.textContent = isoDay;
      const dayPosts = posts.filter((p) => dateKeyIST(p.scheduled_at) === isoDay);
      container.innerHTML = `
        <div class="pub-cal-cell" data-date="${isoDay}" style="min-height:240px;">
          <div class="pub-cal-date-num">${isoDay} (${dayPosts.length} posts)</div>
          ${dayPosts.map((p) => renderCard(p)).join("") || `<div style="opacity:0.6;padding:20px;">No posts scheduled for this day.</div>`}
        </div>
      `;
      bindCardActions(container);
      return;
    }

    let dates = [];
    if (PUB_STATE.calMode === "week") {
      const start = new Date(cur);
      start.setDate(cur.getDate() - cur.getDay());
      for (let i = 0; i < 7; i++) {
        const d = new Date(start);
        d.setDate(start.getDate() + i);
        dates.push(d);
      }
      if (label) label.textContent = `Week of ${dates[0].toISOString().slice(0, 10)}`;
    } else {
      const y = cur.getFullYear(), m = cur.getMonth();
      if (label) label.textContent = cur.toLocaleString("en-IN", { month: "long", year: "numeric" });
      const first = new Date(y, m, 1);
      const start = new Date(first);
      start.setDate(1 - first.getDay());
      for (let i = 0; i < 35; i++) {
        const d = new Date(start);
        d.setDate(start.getDate() + i);
        dates.push(d);
      }
    }

    const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    let html = `<div class="pub-cal-grid">${dayNames.map((d) => `<div class="pub-cal-day-hdr">${d}</div>`).join("")}`;
    for (const d of dates) {
      const iso = d.toISOString().slice(0, 10);
      const dayPosts = posts.filter((p) => dateKeyIST(p.scheduled_at) === iso);
      html += `
        <div class="pub-cal-cell" data-date="${iso}">
          <div class="pub-cal-date-num">${d.getDate()}</div>
          ${dayPosts.map((p) => `<div class="pub-cal-chip" draggable="true" data-post-id="${p.id}" title="${esc(p.caption)}">${PLATFORM_ICON[p.platform] || ""} ${fmtTimeIST(p.scheduled_at)} ${esc(p.zodiac_english || p.original_filename)}</div>`).join("")}
        </div>
      `;
    }
    html += `</div>`;
    container.innerHTML = html;

    container.querySelectorAll(".pub-cal-chip").forEach((chip) => {
      chip.addEventListener("click", () => openPostModal(Number(chip.dataset.postId), false));
      chip.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/plain", chip.dataset.postId));
    });
    container.querySelectorAll(".pub-cal-cell").forEach((cell) => {
      cell.addEventListener("dragover", (e) => { e.preventDefault(); cell.classList.add("drag-over"); });
      cell.addEventListener("dragleave", () => cell.classList.remove("drag-over"));
      cell.addEventListener("drop", async (e) => {
        e.preventDefault();
        cell.classList.remove("drag-over");
        const postId = Number(e.dataTransfer.getData("text/plain"));
        const targetDate = cell.dataset.date;
        if (!postId || !targetDate) return;
        const post = PUB_STATE.posts.find((x) => x.id === postId);
        const timePart = post && post.scheduled_at && post.scheduled_at.length >= 16 ? post.scheduled_at.slice(11, 19) : "09:00:00";
        await apiReschedule(postId, `${targetDate}T${timePart}`);
      });
    });
  }

  function renderBoardView() {
    const container = document.getElementById("pub-view-board");
    if (!container) return;
    const posts = getFilteredPosts(true);
    const cols = [
      { key: "draft", label: "Drafts", match: (s) => s === "draft" },
      { key: "scheduled", label: "Queue", match: (s) => s === "scheduled" || s === "pending_approval" },
      { key: "processing", label: "Processing", match: (s) => ["processing", "publishing", "uploading"].includes(s) },
      { key: "published", label: "Published", match: (s) => SENT_SET.has(s) },
      { key: "failed", label: "Failed / Retry", match: (s) => ["failed", "retry_waiting", "auth_required"].includes(s) },
    ];

    let html = `<div class="pub-board">`;
    for (const col of cols) {
      const items = posts.filter((p) => col.match(p.status));
      html += `
        <div class="pub-board-col" data-col-status="${col.key}">
          <div class="pub-board-col-hdr"><span>${col.label}</span><span class="pub-tab-count">${items.length}</span></div>
          ${items.map((p) => renderCard(p)).join("") || `<div style="opacity:0.5;font-size:0.8rem;padding:10px;">Empty</div>`}
        </div>
      `;
    }
    html += `</div>`;
    container.innerHTML = html;
    bindCardActions(container);

    container.querySelectorAll(".pub-board-col").forEach((colEl) => {
      colEl.addEventListener("dragover", (e) => { e.preventDefault(); colEl.classList.add("drag-over"); });
      colEl.addEventListener("dragleave", () => colEl.classList.remove("drag-over"));
      colEl.addEventListener("drop", async (e) => {
        e.preventDefault();
        colEl.classList.remove("drag-over");
        const postId = Number(e.dataTransfer.getData("text/plain"));
        const target = colEl.dataset.colStatus;
        if (!postId || !["draft", "scheduled"].includes(target)) return;
        await apiPatchPost(postId, { status: target });
      });
    });
  }

  function renderAll() {
    renderSidebar();
    renderHeaderAndTabs();
    const listEl = document.getElementById("pub-view-list");
    const calEl = document.getElementById("pub-view-calendar");
    const boardEl = document.getElementById("pub-view-board");
    const calSub = document.getElementById("pub-cal-subcontrols");
    if (listEl) listEl.classList.toggle("hidden", PUB_STATE.activeView !== "list");
    if (calEl) calEl.classList.toggle("hidden", PUB_STATE.activeView !== "calendar");
    if (boardEl) boardEl.classList.toggle("hidden", PUB_STATE.activeView !== "board");
    if (calSub) calSub.classList.toggle("hidden", PUB_STATE.activeView !== "calendar");

    if (PUB_STATE.activeView === "list") renderListView();
    else if (PUB_STATE.activeView === "calendar") renderCalendarView();
    else renderBoardView();
  }

  async function apiPatchPost(id, payload) {
    const res = await fetch(`/api/auto-post/posts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "Update failed");
      return;
    }
    await fetchWorkspace();
  }

  async function apiReschedule(id, scheduledAt) {
    const res = await fetch(`/api/auto-post/posts/${id}/reschedule`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scheduled_at: scheduledAt }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "Reschedule failed");
      return;
    }
    await fetchWorkspace();
  }

  function openPostModal(postId, editMode = false) {
    const p = PUB_STATE.posts.find((x) => x.id === postId);
    if (!p) return;
    const modal = document.getElementById("pub-post-modal");
    const title = document.getElementById("pub-modal-title");
    const body = document.getElementById("pub-modal-body");
    if (!modal || !body) return;
    title.textContent = editMode ? `Edit Post #${p.id}` : `Post Details #${p.id}`;
    body.innerHTML = `
      <div style="display:grid;gap:10px;">
        <div><strong>Channel:</strong> ${esc(p.account_key)} (${esc(p.platform)})</div>
        <div><strong>Status:</strong> ${esc(p.status)}</div>
        <div><strong>File:</strong> ${esc(p.original_filename)}</div>
        <div>
          <label style="display:block;font-weight:600;margin-bottom:4px;">Caption</label>
          <textarea id="pub-edit-caption" class="form-control" rows="3" ${editMode ? "" : "readonly"}>${esc(p.caption)}</textarea>
        </div>
        <div>
          <label style="display:block;font-weight:600;margin-bottom:4px;">Scheduled At (Asia/Kolkata)</label>
          <input id="pub-edit-time" type="datetime-local" class="form-control" value="${esc((p.scheduled_at || "").slice(0, 16))}" ${editMode ? "" : "readonly"} />
        </div>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:8px;">
          ${editMode ? `<button type="button" id="pub-save-edit-btn" class="btn btn-primary">Save Changes</button>` : ""}
        </div>
      </div>
    `;
    modal.classList.remove("hidden");
    const saveBtn = document.getElementById("pub-save-edit-btn");
    if (saveBtn) {
      saveBtn.addEventListener("click", async () => {
        const caption = document.getElementById("pub-edit-caption").value;
        const dt = document.getElementById("pub-edit-time").value;
        await apiPatchPost(p.id, { caption, scheduled_at: dt ? `${dt}:00` : undefined });
        modal.classList.add("hidden");
      });
    }
  }

  function openNewPostModal(mode = "draft") {
    const modal = document.getElementById("pub-post-modal");
    const title = document.getElementById("pub-modal-title");
    const body = document.getElementById("pub-modal-body");
    if (!modal || !body) return;
    title.textContent = mode === "schedule" || mode === "queue" ? "Schedule / Add to Queue" : "Create Draft Post";
    const defaultStatus = mode === "draft" ? "draft" : "scheduled";
    body.innerHTML = `
      <div style="display:grid;gap:10px;">
        <div>
          <label style="display:block;font-weight:600;margin-bottom:4px;">Channel</label>
          <select id="pub-new-channel" class="form-control">
            <option value="facebook:default">Facebook Page</option>
            <option value="instagram:default">Instagram Professional</option>
            <option value="youtube:default">YouTube Channel</option>
          </select>
        </div>
        <div>
          <label style="display:block;font-weight:600;margin-bottom:4px;">Caption</label>
          <textarea id="pub-new-caption" class="form-control" rows="3" placeholder="Write your post caption..."></textarea>
        </div>
        <div>
          <label style="display:block;font-weight:600;margin-bottom:4px;">Scheduled Date &amp; Time (Asia/Kolkata)</label>
          <input id="pub-new-time" type="datetime-local" class="form-control" />
        </div>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:8px;">
          <button type="button" id="pub-create-submit-btn" class="btn btn-primary">Save Post</button>
        </div>
      </div>
    `;
    modal.classList.remove("hidden");
    document.getElementById("pub-create-submit-btn")?.addEventListener("click", async () => {
      const account_key = document.getElementById("pub-new-channel").value;
      const caption = document.getElementById("pub-new-caption").value;
      const dt = document.getElementById("pub-new-time").value;
      const res = await fetch("/api/publishing/posts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_key,
          status: defaultStatus,
          caption,
          scheduled_at: dt ? `${dt}:00` : undefined,
        }),
      });
      if (!res.ok) {
        if (window.GSPUI) window.GSPUI.toast("Failed to create post", "error");
        return;
      }
      modal.classList.add("hidden");
      if (window.GSPUI) window.GSPUI.toast("Post created", "success");
      await fetchWorkspace();
    });
  }

  function bindCardActions(root) {
    root.querySelectorAll(".pub-card").forEach((card) => {
      card.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/plain", card.dataset.postId));
    });
    root.querySelectorAll(".pub-act-publish").forEach((b) => {
      b.addEventListener("click", () => {
        PUB_STATE.pendingConfirmPostId = Number(b.dataset.id);
        document.getElementById("pub-confirm-modal")?.classList.remove("hidden");
      });
    });
    root.querySelectorAll(".pub-act-edit").forEach((b) => b.addEventListener("click", () => openPostModal(Number(b.dataset.id), true)));
    root.querySelectorAll(".pub-act-resched").forEach((b) => b.addEventListener("click", () => openPostModal(Number(b.dataset.id), true)));
    root.querySelectorAll(".pub-act-details").forEach((b) => b.addEventListener("click", () => openPostModal(Number(b.dataset.id), false)));
    root.querySelectorAll(".pub-act-draft").forEach((b) => b.addEventListener("click", async () => {
      await apiPatchPost(Number(b.dataset.id), { status: "draft" });
      if (window.GSPUI) window.GSPUI.toast("Moved to Drafts", "info");
    }));
    root.querySelectorAll(".pub-act-approve").forEach((b) => b.addEventListener("click", async () => {
      await apiPatchPost(Number(b.dataset.id), { status: "scheduled" });
      if (window.GSPUI) window.GSPUI.toast("Post approved and scheduled", "success");
    }));
    root.querySelectorAll(".pub-act-remove").forEach((b) => b.addEventListener("click", async () => {
      const ok = window.GSPUI
        ? await window.GSPUI.confirm({
            title: "Remove from Queue",
            message: "Are you sure you want to remove this post from the publishing queue?",
            confirmText: "Remove",
            variant: "danger"
          })
        : window.confirm("Remove this post from the queue?");
      if (!ok) return;
      await fetch(`/api/auto-post/posts/${Number(b.dataset.id)}/cancel`, { method: "POST" });
      if (window.GSPUI) window.GSPUI.toast("Post removed from queue", "info");
      await fetchWorkspace();
    }));
  }

  function initPublishingWorkspace() {
    document.getElementById("sidebar-new-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      document.getElementById("pub-new-post-menu")?.classList.toggle("hidden");
    });

    document.querySelectorAll(".pub-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".pub-tab").forEach((x) => x.classList.remove("active"));
        btn.classList.add("active");
        PUB_STATE.activeTab = btn.dataset.pubTab;
        renderAll();
      });
    });

    document.querySelectorAll(".pub-view-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".pub-view-btn").forEach((x) => x.classList.remove("active"));
        btn.classList.add("active");
        PUB_STATE.activeView = btn.dataset.pubView;
        renderAll();
      });
    });

    document.querySelectorAll(".pub-cal-mode-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".pub-cal-mode-btn").forEach((x) => x.classList.remove("active"));
        btn.classList.add("active");
        PUB_STATE.calMode = btn.dataset.calMode;
        renderCalendarView();
      });
    });

    document.getElementById("pub-cal-prev")?.addEventListener("click", () => {
      const d = PUB_STATE.calCursor;
      if (PUB_STATE.calMode === "day") d.setDate(d.getDate() - 1);
      else if (PUB_STATE.calMode === "week") d.setDate(d.getDate() - 7);
      else d.setMonth(d.getMonth() - 1);
      renderCalendarView();
    });

    document.getElementById("pub-cal-next")?.addEventListener("click", () => {
      const d = PUB_STATE.calCursor;
      if (PUB_STATE.calMode === "day") d.setDate(d.getDate() + 1);
      else if (PUB_STATE.calMode === "week") d.setDate(d.getDate() + 7);
      else d.setMonth(d.getMonth() + 1);
      renderCalendarView();
    });

    const bindFilter = (id, key) => {
      document.getElementById(id)?.addEventListener("input", (e) => {
        PUB_STATE.filters[key] = e.target.value;
        renderAll();
      });
    };
    bindFilter("pub-search-input", "search");
    bindFilter("scheduler-platform-filter", "platform");
    bindFilter("scheduler-status-filter", "status");
    bindFilter("pub-category-filter", "category");
    bindFilter("pub-date-from", "dateFrom");
    bindFilter("pub-date-to", "dateTo");

    document.getElementById("pub-clear-filters-btn")?.addEventListener("click", () => {
      PUB_STATE.filters = { search: "", platform: "", status: "", category: "", dateFrom: "", dateTo: "" };
      ["pub-search-input", "scheduler-platform-filter", "scheduler-status-filter", "pub-category-filter", "pub-date-from", "pub-date-to"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.value = "";
      });
      renderAll();
    });

    document.getElementById("pub-new-post-btn")?.addEventListener("click", () => {
      document.getElementById("pub-new-post-menu")?.classList.toggle("hidden");
    });

    document.querySelectorAll(".pub-quick-item").forEach((item) => {
      item.addEventListener("click", () => {
        document.getElementById("pub-new-post-menu")?.classList.add("hidden");
        const act = item.dataset.action;
        if (act === "bulk" || act === "upload") {
          if (typeof switchTab === "function") switchTab("autopost");
          document.querySelector('.autopost-sub-btn[data-subtab="upload"]')?.click();
        } else {
          openNewPostModal(act);
        }
      });
    });

    document.getElementById("pub-channel-settings-btn")?.addEventListener("click", () => {
      if (typeof switchTab === "function") switchTab("autopost");
      document.querySelector('.autopost-sub-btn[data-subtab="schedule"]')?.click();
    });

    document.getElementById("pub-modal-close")?.addEventListener("click", () => document.getElementById("pub-post-modal")?.classList.add("hidden"));
    document.getElementById("pub-confirm-close")?.addEventListener("click", () => document.getElementById("pub-confirm-modal")?.classList.add("hidden"));
    document.getElementById("pub-confirm-cancel")?.addEventListener("click", () => document.getElementById("pub-confirm-modal")?.classList.add("hidden"));
    document.getElementById("pub-confirm-ok")?.addEventListener("click", async () => {
      const id = PUB_STATE.pendingConfirmPostId;
      document.getElementById("pub-confirm-modal")?.classList.add("hidden");
      if (!id) return;
      const res = await fetch(`/api/auto-post/posts/${id}/publish-now`, { method: "POST" });
      if (!res.ok) {
        if (window.GSPUI) window.GSPUI.toast("Publish failed", "error");
      } else {
        if (window.GSPUI) window.GSPUI.toast("Post published", "success");
      }
      await fetchWorkspace();
    });

    document.getElementById("refresh-scheduled-posts-btn")?.addEventListener("click", fetchWorkspace);
    window.loadScheduledPosts = fetchWorkspace;
    fetchWorkspace();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPublishingWorkspace);
  } else {
    initPublishingWorkspace();
  }
})();
