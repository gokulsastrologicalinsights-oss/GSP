// Buffer-Style Post-Centric Community Inbox UI

(function () {
  const CI_STATE = {
    platform: 'all',
    status: 'all',
    date: 'all',
    search: '',
    posts: [],
    selectedPost: null, // { platform, post_id }
    postDetail: null,
    comments: [],
    commentFilter: 'all',
    offset: 0,
    limit: 15,
    hasMore: false,
    safeTestMode: true,
    activeComposers: {}, // comment_id -> { level, text, open, sending }
    initialized: false,
  };

  function ciEscape(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function ciFormatDate(isoStr) {
    if (!isoStr) return '—';
    try {
      const normalized = isoStr.includes('T') ? isoStr : isoStr.replace(' ', 'T') + 'Z';
      const d = new Date(normalized);
      if (isNaN(d.getTime())) return isoStr;
      return d.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch (_) {
      return isoStr;
    }
  }

  function ciPlatformLabel(platform) {
    const p = (platform || '').toLowerCase();
    if (p === 'facebook') return 'Facebook';
    if (p === 'instagram') return 'Instagram';
    if (p === 'youtube') return 'YouTube';
    return platform || 'Social';
  }

  function ciPlatformIcon(platform) {
    const p = (platform || '').toLowerCase();
    if (p === 'facebook') return '📘';
    if (p === 'instagram') return '📸';
    if (p === 'youtube') return '▶️';
    return '💬';
  }

  function ciLangLabel(lang) {
    if (lang === 'ta') return 'Tamil';
    if (lang === 'tanglish') return 'Tanglish';
    if (lang === 'emoji') return 'Emoji';
    return 'English';
  }

  function ciInitials(name) {
    const clean = (name || 'U').trim().replace(/^@/, '');
    const parts = clean.split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return clean.slice(0, 2).toUpperCase() || 'U';
  }

  function ciShowFeedback(message, type = 'info') {
    const el = document.getElementById('ci-feedback');
    if (!el) return;
    el.textContent = message;
    el.className = `aq-feedback ${type}`;
    el.classList.remove('hidden');
    clearTimeout(ciShowFeedback._timer);
    ciShowFeedback._timer = setTimeout(() => {
      el.classList.add('hidden');
    }, 5000);
  }

  function ciUpdateSafePill() {
    const pill = document.getElementById('ci-safe-pill');
    if (!pill) return;
    if (CI_STATE.safeTestMode) {
      pill.textContent = '🛡️ Safe Mode ON';
      pill.classList.remove('live');
      pill.title = 'Safe Testing Mode is ON — replies are recorded locally without calling live platform APIs.';
    } else {
      pill.textContent = '🔴 Live Mode';
      pill.classList.add('live');
      pill.title = 'Live Mode — explicit Send Reply will publish to the platform API.';
    }
  }

  async function loadInboxPosts(autoSelectFirst = true) {
    const listEl = document.getElementById('ci-posts-list');
    if (!listEl) return;
    listEl.innerHTML = '<div class="ci-loading-state">Loading posts...</div>';

    try {
      const params = new URLSearchParams();
      if (CI_STATE.platform !== 'all') params.set('platform', CI_STATE.platform);
      if (CI_STATE.status !== 'all') params.set('status', CI_STATE.status);
      if (CI_STATE.date !== 'all') params.set('date', CI_STATE.date);
      if (CI_STATE.search.trim()) params.set('search', CI_STATE.search.trim());
      params.set('limit', '50');

      const res = await fetch(`/api/inbox/posts?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to load inbox posts');
      const data = await res.json();
      CI_STATE.posts = data.posts || [];
      CI_STATE.safeTestMode = data.safe_test_mode !== false;
      ciUpdateSafePill();
      renderInboxPosts();

      if (autoSelectFirst && CI_STATE.posts.length > 0) {
        const stillExists =
          CI_STATE.selectedPost &&
          CI_STATE.posts.some(
            (p) => p.platform === CI_STATE.selectedPost.platform && p.post_id === CI_STATE.selectedPost.post_id
          );
        const target = stillExists ? CI_STATE.selectedPost : CI_STATE.posts[0];
        await selectInboxPost(target.platform, target.post_id);
      } else if (CI_STATE.posts.length === 0) {
        CI_STATE.selectedPost = null;
        CI_STATE.postDetail = null;
        CI_STATE.comments = [];
        renderInboxRightPanel();
      }
    } catch (err) {
      listEl.innerHTML = '<div class="ci-loading-state">Unable to load posts right now.</div>';
      ciShowFeedback('Failed to load Community Inbox posts.', 'error');
    }
  }

  function renderInboxPosts() {
    const listEl = document.getElementById('ci-posts-list');
    if (!listEl) return;

    if (!CI_STATE.posts.length) {
      listEl.innerHTML = '<div class="ci-loading-state">No posts match the current filters.</div>';
      return;
    }

    listEl.innerHTML = CI_STATE.posts
      .map((post) => {
        const isSelected =
          CI_STATE.selectedPost &&
          CI_STATE.selectedPost.platform === post.platform &&
          CI_STATE.selectedPost.post_id === post.post_id;
        const thumbHtml = post.thumbnail_url
          ? `<img src="${ciEscape(post.thumbnail_url)}" alt="Post thumbnail" loading="lazy" />`
          : `<span class="ci-post-thumb-fallback">${ciPlatformIcon(post.platform)}</span>`;
        const unanswered = post.unanswered_count || 0;
        const total = post.total_comments || 0;
        const answered = post.answered_count || 0;
        const pct = post.progress_pct || 0;

        return `
          <button type="button" class="ci-post-card ${isSelected ? 'selected' : ''}" data-platform="${ciEscape(post.platform)}" data-post-id="${ciEscape(post.post_id)}">
            <div class="ci-post-thumb">${thumbHtml}</div>
            <div class="ci-post-card-body">
              <div class="ci-post-card-top">
                <span class="ci-plat-badge ${ciEscape(post.platform)}">${ciPlatformIcon(post.platform)} ${ciEscape(ciPlatformLabel(post.platform))}</span>
                <span class="ci-post-account" title="${ciEscape(post.account_name)}">${ciEscape(post.account_name)}</span>
              </div>
              <div class="ci-post-caption">${ciEscape(post.caption)}</div>
              <div class="ci-post-metrics">
                <span>${total} total</span>
                <span class="ci-unanswered-pill ${unanswered === 0 ? 'done' : ''}">
                  ${unanswered === 0 ? 'All answered' : `${unanswered} unanswered`}
                </span>
                <span style="margin-left:auto;">${answered}/${total}</span>
              </div>
              <div class="ci-progress-track" title="${pct}% replied">
                <div class="ci-progress-fill" style="width:${pct}%"></div>
              </div>
            </div>
          </button>
        `;
      })
      .join('');
  }

  async function selectInboxPost(platform, postId) {
    CI_STATE.selectedPost = { platform, post_id: postId };
    CI_STATE.offset = 0;
    CI_STATE.comments = [];
    renderInboxPosts();
    await loadInboxPostComments(false);
  }

  async function loadInboxPostComments(append = false) {
    if (!CI_STATE.selectedPost) return;
    const { platform, post_id } = CI_STATE.selectedPost;
    const listEl = document.getElementById('ci-comments-list');
    if (!append && listEl) {
      listEl.innerHTML = '<div class="ci-loading-state">Loading comments...</div>';
    }

    try {
      const params = new URLSearchParams({
        limit: String(CI_STATE.limit),
        offset: String(append ? CI_STATE.offset : 0),
        status: CI_STATE.commentFilter,
      });
      const url = `/api/inbox/posts/${encodeURIComponent(platform)}/${encodeURIComponent(post_id)}/comments?${params.toString()}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to load post comments');
      const data = await res.json();

      CI_STATE.postDetail = data.post;
      CI_STATE.hasMore = !!data.has_more;
      CI_STATE.safeTestMode = data.safe_test_mode !== false;
      ciUpdateSafePill();

      if (append) {
        CI_STATE.comments = CI_STATE.comments.concat(data.comments || []);
      } else {
        CI_STATE.comments = data.comments || [];
      }
      CI_STATE.offset = CI_STATE.comments.length;

      // Sync post counts in middle list
      const idx = CI_STATE.posts.findIndex((p) => p.platform === platform && p.post_id === post_id);
      if (idx !== -1 && data.post) {
        CI_STATE.posts[idx] = { ...CI_STATE.posts[idx], ...data.post };
        renderInboxPosts();
      }

      renderInboxRightPanel(data.total_filtered);
    } catch (err) {
      ciShowFeedback('Could not load comments for this post.', 'error');
    }
  }

  function renderInboxRightPanel(totalFiltered) {
    const emptyEl = document.getElementById('ci-empty-right');
    const detailEl = document.getElementById('ci-post-detail');
    const headerEl = document.getElementById('ci-post-header');
    const listEl = document.getElementById('ci-comments-list');
    const showingEl = document.getElementById('ci-comments-showing');
    const loadMoreWrap = document.getElementById('ci-load-more-wrap');

    if (!CI_STATE.postDetail) {
      if (emptyEl) emptyEl.classList.remove('hidden');
      if (detailEl) detailEl.classList.add('hidden');
      return;
    }

    if (emptyEl) emptyEl.classList.add('hidden');
    if (detailEl) detailEl.classList.remove('hidden');

    const p = CI_STATE.postDetail;
    const thumbHtml = p.thumbnail_url
      ? `<img src="${ciEscape(p.thumbnail_url)}" alt="Post thumbnail" />`
      : `<span class="ci-post-thumb-fallback">${ciPlatformIcon(p.platform)}</span>`;

    if (headerEl) {
      headerEl.innerHTML = `
        <div class="ci-post-header-thumb">${thumbHtml}</div>
        <div class="ci-post-header-info">
          <div class="ci-post-header-meta">
            <span class="ci-plat-badge ${ciEscape(p.platform)}">${ciPlatformIcon(p.platform)} ${ciEscape(ciPlatformLabel(p.platform))}</span>
            <strong>${ciEscape(p.account_name)}</strong>
            <span>•</span>
            <span>${ciEscape(ciFormatDate(p.post_date))}</span>
          </div>
          <div class="ci-post-header-caption">${ciEscape(p.caption)}</div>
          <div class="ci-post-header-stats">
            <span><strong>${p.total_comments || 0}</strong> Total Comments</span>
            <span><strong>${p.answered_count || 0}</strong> Answered</span>
            <span><strong>${p.unanswered_count || 0}</strong> Unanswered</span>
            <span><strong>${p.progress_pct || 0}%</strong> Complete</span>
          </div>
        </div>
      `;
    }

    if (showingEl) {
      const total = typeof totalFiltered === 'number' ? totalFiltered : CI_STATE.comments.length;
      showingEl.textContent = `Showing ${CI_STATE.comments.length} of ${total} comments`;
    }

    if (listEl) {
      if (!CI_STATE.comments.length) {
        listEl.innerHTML = '<div class="ci-loading-state">No comments match this filter.</div>';
      } else {
        listEl.innerHTML = CI_STATE.comments.map(renderCommentCard).join('');
      }
    }

    if (loadMoreWrap) {
      loadMoreWrap.classList.toggle('hidden', !CI_STATE.hasMore);
    }
  }

  function renderCommentCard(c) {
    const cid = c.comment_id;
    const sugg = c.suggestions || {};
    const intent = sugg.intent || c.detected_intent || 'neutral';
    const sentiment = sugg.sentiment || c.sentiment || 'neutral';
    const lang = sugg.language || c.detected_language || 'en';
    const isAnswered = !!c.is_answered;
    const isReconcile = c.status === 'reconciliation_required';
    const isFlagged = intent === 'threatening' || intent === 'abusive' || intent === 'complaint' || isReconcile;
    const comp = CI_STATE.activeComposers[cid] || { level: null, text: '', open: false, sending: false };

    let statusBadge = '<span class="ci-badge status-pending">Unanswered</span>';
    if (c.status === 'replied') {
      statusBadge = '<span class="ci-badge status-replied">✓ Replied</span>';
    } else if (isAnswered && c.status === 'test_prepared') {
      statusBadge = '<span class="ci-badge status-test">🛡️ Safe Test Sent</span>';
    } else if (isReconcile) {
      statusBadge = '<span class="ci-badge status-reconcile">⚠️ Verify Platform State</span>';
    } else if (intent === 'threatening') {
      statusBadge = '<span class="ci-badge status-reconcile">🚨 Manual Review</span>';
    } else if (intent === 'spam') {
      statusBadge = '<span class="ci-badge sentiment-spam">Spam — No Reply</span>';
    }

    const avatarHtml = c.author_avatar
      ? `<img src="${ciEscape(c.author_avatar)}" alt="${ciEscape(c.author_name)}" />`
      : ciEscape(ciInitials(c.author_name));

    const existingReplyHtml = isAnswered && c.reply_text
      ? `
        <div class="ci-existing-reply">
          <div class="ci-existing-reply-label">${c.status === 'replied' ? 'Published Reply' : 'Safe Test Reply'} ${c.replied_at ? `• ${ciEscape(ciFormatDate(c.replied_at))}` : ''}</div>
          <div class="ci-existing-reply-text">${ciEscape(c.reply_text)}</div>
        </div>
      `
      : '';

    let warningHtml = '';
    if (sugg.manual_review_required && !isAnswered) {
      warningHtml = `<div class="ci-warning-banner">⚠️ ${ciEscape(sugg.reason || 'Flagged for manual review. Never auto-sent.')}</div>`;
    } else if (sugg.recommend_no_reply && !isAnswered) {
      warningHtml = `<div class="ci-warning-banner spam">🚫 ${ciEscape(sugg.reason || 'Spam detected. Recommended: No reply.')}</div>`;
    }

    const showSuggestions = !isAnswered && (sugg.short || sugg.medium || sugg.detailed);
    const suggestionsHtml = showSuggestions
      ? `
        <div class="ci-sugg-section">
          <div class="ci-sugg-header">
            <span>Intelligent Reply Suggestions (${ciEscape(ciLangLabel(lang))})</span>
            <button type="button" class="secondary-btn sm ci-regen-btn" data-platform="${ciEscape(c.platform)}" data-comment-id="${ciEscape(cid)}">↻ Regenerate</button>
          </div>
          <div class="ci-sugg-grid">
            ${['short', 'medium', 'detailed']
              .map((lvl) => {
                const txt = sugg[lvl] || '';
                const isSel = comp.open && comp.level === lvl;
                return `
                  <div class="ci-sugg-card ${isSel ? 'selected' : ''}">
                    <div class="ci-sugg-label">${lvl}</div>
                    <div class="ci-sugg-text">${ciEscape(txt)}</div>
                    <button type="button" class="ci-sugg-select-btn" data-comment-id="${ciEscape(cid)}" data-level="${lvl}">
                      ${isSel ? '✓ Selected' : 'Select'}
                    </button>
                  </div>
                `;
              })
              .join('')}
          </div>
        </div>
      `
      : '';

    const composerHtml = !isAnswered && comp.open
      ? `
        <div class="ci-composer" data-comment-id="${ciEscape(cid)}">
          <div class="ci-composer-context">
            <span>Replying on <strong>${ciEscape(ciPlatformLabel(c.platform))}</strong> as <strong>${ciEscape(c.account_name)}</strong> to <strong>${ciEscape(c.author_name)}</strong></span>
            <span>${comp.level ? `Template: ${ciEscape(comp.level.toUpperCase())}` : 'Custom Reply'}</span>
          </div>
          <textarea class="ci-composer-textarea" data-comment-id="${ciEscape(cid)}" placeholder="Edit your reply before sending...">${ciEscape(comp.text)}</textarea>
          <div class="ci-composer-footer">
            <span class="ci-char-count" id="ci-char-${ciEscape(cid)}">${(comp.text || '').length} characters</span>
            <div class="ci-composer-actions">
              <button type="button" class="secondary-btn sm ci-regen-btn" data-platform="${ciEscape(c.platform)}" data-comment-id="${ciEscape(cid)}">Regenerate</button>
              <button type="button" class="secondary-btn sm ci-cancel-btn" data-comment-id="${ciEscape(cid)}">Cancel</button>
              <button type="button" class="primary-btn sm ci-send-btn" data-platform="${ciEscape(c.platform)}" data-comment-id="${ciEscape(cid)}" ${comp.sending ? 'disabled' : ''}>
                ${comp.sending ? 'Sending...' : CI_STATE.safeTestMode ? 'Send Reply (Safe Test)' : 'Send Reply'}
              </button>
            </div>
          </div>
        </div>
      `
      : !isAnswered
      ? `
        <div style="display:flex;justify-content:flex-end;">
          <button type="button" class="secondary-btn sm ci-open-custom-btn" data-comment-id="${ciEscape(cid)}">Write Custom Reply</button>
        </div>
      `
      : '';

    return `
      <article class="ci-comment-card ${isAnswered ? 'answered' : ''} ${isFlagged && !isAnswered ? 'flagged' : ''}" data-comment-id="${ciEscape(cid)}">
        <div class="ci-comment-top">
          <div class="ci-avatar">${avatarHtml}</div>
          <div class="ci-comment-author-wrap">
            <span class="ci-comment-author">${ciEscape(c.author_name)}</span>
            <span class="ci-comment-time">${ciEscape(ciFormatDate(c.comment_timestamp))}</span>
          </div>
          <div class="ci-comment-badges">
            <span class="ci-plat-badge ${ciEscape(c.platform)}">${ciPlatformIcon(c.platform)} ${ciEscape(ciPlatformLabel(c.platform))}</span>
            <span class="ci-badge">${ciEscape(ciLangLabel(lang))}</span>
            <span class="ci-badge sentiment-${ciEscape(sentiment)}">${ciEscape(sentiment)} / ${ciEscape(intent)}</span>
            ${statusBadge}
          </div>
        </div>
        <div class="ci-comment-text">${ciEscape(c.comment_text)}</div>
        ${existingReplyHtml}
        ${warningHtml}
        ${suggestionsHtml}
        ${composerHtml}
      </article>
    `;
  }

  function selectSuggestion(commentId, level) {
    const comment = CI_STATE.comments.find((c) => c.comment_id === commentId);
    if (!comment || !comment.suggestions) return;
    const text = comment.suggestions[level] || '';
    CI_STATE.activeComposers[commentId] = {
      level,
      text,
      open: true,
      sending: false,
    };
    renderInboxRightPanel();
    const ta = document.querySelector(`.ci-composer-textarea[data-comment-id="${CSS.escape(commentId)}"]`);
    if (ta) ta.focus();
  }

  function openCustomComposer(commentId) {
    CI_STATE.activeComposers[commentId] = {
      level: 'custom',
      text: '',
      open: true,
      sending: false,
    };
    renderInboxRightPanel();
    const ta = document.querySelector(`.ci-composer-textarea[data-comment-id="${CSS.escape(commentId)}"]`);
    if (ta) ta.focus();
  }

  function cancelComposer(commentId) {
    delete CI_STATE.activeComposers[commentId];
    renderInboxRightPanel();
  }

  async function regenerateSuggestions(platform, commentId) {
    try {
      const url = `/api/inbox/comments/${encodeURIComponent(platform)}/${encodeURIComponent(commentId)}/regenerate`;
      const res = await fetch(url, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to regenerate suggestions');
      const data = await res.json();
      const comment = CI_STATE.comments.find((c) => c.comment_id === commentId);
      if (comment && data.suggestions) {
        comment.suggestions = data.suggestions;
        const comp = CI_STATE.activeComposers[commentId];
        if (comp && comp.open && comp.level && data.suggestions[comp.level]) {
          comp.text = data.suggestions[comp.level];
        }
        renderInboxRightPanel();
        ciShowFeedback('Regenerated 3 personalized reply suggestions.', 'success');
      }
    } catch (err) {
      ciShowFeedback('Could not regenerate suggestions.', 'error');
    }
  }

  async function sendInboxReply(platform, commentId) {
    const comp = CI_STATE.activeComposers[commentId];
    if (!comp || comp.sending) return;
    const replyText = (comp.text || '').trim();
    if (!replyText) {
      ciShowFeedback('Reply text cannot be empty.', 'error');
      return;
    }

    comp.sending = true;
    renderInboxRightPanel();

    try {
      const url = `/api/inbox/comments/${encodeURIComponent(platform)}/${encodeURIComponent(commentId)}/reply`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reply_text: replyText,
          selected_level: comp.level || 'custom',
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        comp.sending = false;
        renderInboxRightPanel();
        ciShowFeedback(data.error || data.detail || 'Failed to send reply.', 'error');
        return;
      }

      delete CI_STATE.activeComposers[commentId];
      ciShowFeedback(
        data.safe_test_mode
          ? 'Reply recorded in Safe Testing Mode (no live API call made).'
          : 'Reply published successfully!',
        'success'
      );
      await loadInboxPostComments(false);
    } catch (err) {
      comp.sending = false;
      renderInboxRightPanel();
      ciShowFeedback('Network error while sending reply.', 'error');
    }
  }

  async function syncInboxNow() {
    const btn = document.getElementById('ci-sync-btn');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Syncing...';
    }
    try {
      const platParam = CI_STATE.platform !== 'all' ? `?platform=${encodeURIComponent(CI_STATE.platform)}` : '';
      const res = await fetch(`/api/inbox/sync${platParam}`, { method: 'POST' });
      if (!res.ok) throw new Error('Sync failed');
      ciShowFeedback('Comments synchronized from connected platforms.', 'success');
      await loadInboxPosts(true);
    } catch (err) {
      ciShowFeedback('Comment sync encountered an error.', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '↻ Sync';
      }
    }
  }

  function initCommunityInbox() {
    if (CI_STATE.initialized) {
      loadInboxPosts(true);
      return;
    }
    CI_STATE.initialized = true;

    // Platform filter chips
    document.querySelectorAll('.ci-chip[data-ci-platform]').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.ci-chip[data-ci-platform]').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        CI_STATE.platform = btn.dataset.ciPlatform || 'all';
        loadInboxPosts(true);
      });
    });

    // Status & date dropdowns
    document.getElementById('ci-status-filter')?.addEventListener('change', (e) => {
      CI_STATE.status = e.target.value;
      loadInboxPosts(true);
    });
    document.getElementById('ci-date-filter')?.addEventListener('change', (e) => {
      CI_STATE.date = e.target.value;
      loadInboxPosts(true);
    });

    // Search input (debounced)
    let searchTimer = null;
    document.getElementById('ci-search-input')?.addEventListener('input', (e) => {
      CI_STATE.search = e.target.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadInboxPosts(true), 250);
    });

    // Sync button
    document.getElementById('ci-sync-btn')?.addEventListener('click', syncInboxNow);

    // Comment filter pills inside selected post
    document.querySelectorAll('.ci-chip[data-ci-comment-filter]').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.ci-chip[data-ci-comment-filter]').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        CI_STATE.commentFilter = btn.dataset.ciCommentFilter || 'all';
        CI_STATE.offset = 0;
        loadInboxPostComments(false);
      });
    });

    // Load more button
    document.getElementById('ci-load-more-btn')?.addEventListener('click', () => {
      loadInboxPostComments(true);
    });

    // Middle panel post click delegation
    document.getElementById('ci-posts-list')?.addEventListener('click', (e) => {
      const card = e.target.closest('.ci-post-card');
      if (!card) return;
      selectInboxPost(card.dataset.platform, card.dataset.postId);
    });

    // Right panel click delegation (Select suggestion, Regenerate, Cancel, Send, Write Custom)
    const commentsList = document.getElementById('ci-comments-list');
    commentsList?.addEventListener('click', (e) => {
      const selBtn = e.target.closest('.ci-sugg-select-btn');
      if (selBtn) {
        selectSuggestion(selBtn.dataset.commentId, selBtn.dataset.level);
        return;
      }
      const customBtn = e.target.closest('.ci-open-custom-btn');
      if (customBtn) {
        openCustomComposer(customBtn.dataset.commentId);
        return;
      }
      const regenBtn = e.target.closest('.ci-regen-btn');
      if (regenBtn) {
        regenerateSuggestions(regenBtn.dataset.platform, regenBtn.dataset.commentId);
        return;
      }
      const cancelBtn = e.target.closest('.ci-cancel-btn');
      if (cancelBtn) {
        cancelComposer(cancelBtn.dataset.commentId);
        return;
      }
      const sendBtn = e.target.closest('.ci-send-btn');
      if (sendBtn) {
        sendInboxReply(sendBtn.dataset.platform, sendBtn.dataset.commentId);
      }
    });

    commentsList?.addEventListener('input', (e) => {
      const ta = e.target.closest('.ci-composer-textarea');
      if (!ta) return;
      const cid = ta.dataset.commentId;
      if (CI_STATE.activeComposers[cid]) {
        CI_STATE.activeComposers[cid].text = ta.value;
      }
      const countEl = document.getElementById(`ci-char-${cid}`);
      if (countEl) {
        countEl.textContent = `${ta.value.length} characters`;
      }
    });

    loadInboxPosts(true);
  }

  window.initCommunityInbox = initCommunityInbox;
})();

// Account-wise 30-minute Automatic Sync & Reply Mode Controls
async function loadAccountSyncControls() {
  const container = document.getElementById("inbox-account-sync-panel");
  if (!container) return;
  try {
    const res = await fetch("/api/sync/accounts");
    const data = await res.json();
    const accounts = data.accounts || [];
    if (!accounts.length) {
      container.innerHTML = '<div style="padding:8px;color:#64748b;font-size:12px;">No connected accounts for auto-sync.</div>';
      return;
    }
    container.innerHTML = `
      <div style="padding:10px;border-bottom:1px solid #e2e8f0;background:#f8fafc;">
        <div style="font-weight:600;font-size:13px;margin-bottom:8px;">Account Auto-Sync (30 min) & Reply Mode</div>
        <div style="display:flex;flex-wrap:wrap;gap:10px;">
          ${accounts.map(acc => `
            <div style="border:1px solid #cbd5e1;border-radius:8px;padding:8px 10px;background:#fff;min-width:260px;font-size:12px;">
              <div style="font-weight:600;">${acc.platform.toUpperCase()} — ${acc.account_name || acc.account_id}</div>
              <div style="color:#475569;margin:4px 0;">
                Last sync: ${acc.last_successful_sync_ist || 'Never'}<br/>
                Next sync: ${acc.next_sync_ist || 'Pending'}<br/>
                Processed: ${acc.comments_processed || 0} | Auto-sent: ${acc.auto_replies_sent || 0} | Review: ${acc.manual_review_count || 0} | Failed: ${acc.failed_sync_count || 0}
              </div>
              <div style="display:flex;gap:6px;align-items:center;margin-top:6px;">
                <label><input type="checkbox" ${acc.auto_sync_enabled ? 'checked' : ''} onchange="updateAccountSyncSetting('${acc.platform}','${acc.account_id}',{auto_sync_enabled:this.checked})"/> Auto-Sync</label>
                <select onchange="updateAccountSyncSetting('${acc.platform}','${acc.account_id}',{reply_mode:this.value})" style="font-size:11px;padding:2px;">
                  <option value="MANUAL_APPROVAL" ${acc.reply_mode === 'MANUAL_APPROVAL' ? 'selected' : ''}>Manual Approval</option>
                  <option value="AUTOMATIC_REPLY" ${acc.reply_mode === 'AUTOMATIC_REPLY' ? 'selected' : ''}>Automatic Reply</option>
                  <option value="DISABLED" ${acc.reply_mode === 'DISABLED' ? 'selected' : ''}>Disabled</option>
                </select>
                <button onclick="triggerAccountSyncNow('${acc.platform}','${acc.account_id}')" style="font-size:11px;padding:2px 6px;cursor:pointer;">Sync Now</button>
              </div>
            </div>
          `).join("")}
        </div>
      </div>
    `;
  } catch (e) {
    console.error("Failed to load account sync controls", e);
  }
}

async function updateAccountSyncSetting(platform, accountId, payload) {
  await fetch(`/api/sync/accounts/${encodeURIComponent(platform)}/${encodeURIComponent(accountId)}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await loadAccountSyncControls();
}

async function triggerAccountSyncNow(platform, accountId) {
  await fetch(`/api/sync/accounts/${encodeURIComponent(platform)}/${encodeURIComponent(accountId)}/now`, {
    method: "POST",
  });
  await loadAccountSyncControls();
}

document.addEventListener("DOMContentLoaded", () => {
  loadAccountSyncControls();
});
