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

  const titles = {
    dashboard: 'Dashboard',
    accounts: 'Connected Accounts',
    autoreply: 'Auto Reply Configuration',
    activity: 'Activity Log'
  };
  document.getElementById('page-title').textContent = titles[tabId] || 'Dashboard';
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

  tbody.innerHTML = activities.map(item => `
    <tr>
      <td><strong>${item.platform}</strong></td>
      <td>${item.author_name || 'Anonymous'}</td>
      <td>${item.comment_text}</td>
      <td>${item.detected_language} / ${item.detected_intent}</td>
      <td>${item.reply_text || '—'}</td>
      <td><span class="badge ${item.status === 'replied' ? 'on' : 'off'}">${item.status}</span></td>
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
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

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
  subtab: 'automatic',
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
  document.querySelectorAll('.subtab-btn').forEach(btn => {
    const active = btn.dataset.subtab === subtab;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  const autoView = document.getElementById('subview-automatic');
  const approvalView = document.getElementById('subview-approval');
  if (autoView) autoView.classList.toggle('hidden', subtab !== 'automatic');
  if (approvalView) approvalView.classList.toggle('hidden', subtab !== 'approval');

  if (subtab === 'approval') {
    aqUpdateSafeModePill();
    loadApprovalQueue();
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
          ${!isEditing ? `<button type="button" class="secondary-btn sm" onclick="startApprovalEdit(${item.id})" ${isBusy ? 'disabled' : ''}>Edit Reply</button>` : ''}
          <button type="button" class="aq-btn-approve" onclick="approveQueueItem(${item.id})" ${isBusy ? 'disabled' : ''}>${isBusy ? 'Processing...' : 'Approve'}</button>
          <button type="button" class="aq-btn-reject" onclick="promptRejectQueueItem(${item.id})" ${isBusy ? 'disabled' : ''}>Reject</button>
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

function initApprovalQueue() {
  document.querySelectorAll('.subtab-btn').forEach(btn => {
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
