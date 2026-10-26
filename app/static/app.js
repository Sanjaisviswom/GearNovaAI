/**
 * AutoSpare AI — Frontend Client Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // ── State ──────────────────────────────────────────────────
  let activeTab = 'tab-chat';
  let conversationId = 'web_' + Math.random().toString(36).substring(2, 9);
  let attachedImageBase64 = null;
  let attachedImageMime = null;
  let catalogParts = [];
  let currentCategory = 'all';

  // ── DOM Elements ───────────────────────────────────────────
  const navButtons = document.querySelectorAll('.nav-btn[data-tab]');
  const tabPanes = document.querySelectorAll('.tab-pane');

  const chatForm = document.getElementById('chatForm');
  const messageInput = document.getElementById('messageInput');
  const chatMessages = document.getElementById('chatMessages');
  const btnSend = document.getElementById('btnSend');
  const fileInput = document.getElementById('fileInput');
  const imagePreviewContainer = document.getElementById('imagePreviewContainer');
  const imagePreview = document.getElementById('imagePreview');
  const btnRemoveImage = document.getElementById('btnRemoveImage');
  const btnClearChat = document.getElementById('btnClearChat');
  const langSelect = document.getElementById('langSelect');
  const promptChips = document.querySelectorAll('.chip[data-prompt]');

  const diagStatusBadge = document.getElementById('diagStatusBadge');
  const diagnosisContent = document.getElementById('diagnosisContent');

  const catalogSearch = document.getElementById('catalogSearch');
  const categoryFilters = document.getElementById('categoryFilters');
  const partsGrid = document.getElementById('partsGrid');
  const totalPartsCount = document.getElementById('totalPartsCount');

  const btnSendWebhookSim = document.getElementById('btnSendWebhookSim');
  const simPhone = document.getElementById('simPhone');
  const simText = document.getElementById('simText');
  const simResult = document.getElementById('simResult');
  const toast = document.getElementById('toast');

  // ── Navigation Tabs ────────────────────────────────────────
  navButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTab = btn.getAttribute('data-tab');
      if (!targetTab) return;

      navButtons.forEach(b => b.classList.remove('active'));
      tabPanes.forEach(pane => pane.classList.remove('active'));

      btn.classList.add('active');
      const pane = document.getElementById(targetTab);
      if (pane) pane.classList.add('active');
      activeTab = targetTab;

      if (targetTab === 'tab-catalog' && catalogParts.length === 0) {
        fetchCatalog();
      }
    });
  });

  // ── System Status Check ────────────────────────────────────
  async function checkSystemStatus() {
    try {
      const res = await fetch('/api/system-status');
      if (!res.ok) return;
      const data = await res.json();

      const dbPill = document.getElementById('dbPill');
      const aiPill = document.getElementById('aiPill');
      const ytPill = document.getElementById('ytPill');
      const waPill = document.getElementById('waPill');
      const displayVerifyToken = document.getElementById('displayVerifyToken');

      if (data.database && data.database.connected) {
        dbPill.innerHTML = `<span class="dot"></span> Neon DB (${data.database.parts_in_db} parts)`;
      }

      if (data.gemini && data.gemini.configured) {
        aiPill.innerHTML = `<span class="dot"></span> Gemini AI Active`;
      }

      if (data.youtube && data.youtube.configured) {
        ytPill.innerHTML = `<span class="dot"></span> YouTube API Active`;
      }

      if (data.whatsapp && data.whatsapp.configured) {
        waPill.innerHTML = `<span class="dot"></span> WhatsApp Ready`;
      }

      if (displayVerifyToken && data.whatsapp) {
        displayVerifyToken.textContent = data.whatsapp.verify_token || 'my_verify_token';
      }
    } catch (e) {
      console.warn('System status fetch failed:', e);
    }
  }

  // ── Quick Prompt Chips ─────────────────────────────────────
  promptChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.getAttribute('data-prompt');
      messageInput.value = prompt;
      messageInput.focus();
      handleSendMessage();
    });
  });

  // ── Image Attachment Handling ──────────────────────────────
  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      showToast('Please select a valid image file');
      return;
    }

    attachedImageMime = file.type;
    const reader = new FileReader();
    reader.onload = (event) => {
      attachedImageBase64 = event.target.result;
      imagePreview.src = attachedImageBase64;
      document.getElementById('previewFilename').textContent = file.name;
      imagePreviewContainer.style.display = 'block';
    };
    reader.readAsDataURL(file);
  });

  btnRemoveImage.addEventListener('click', () => {
    attachedImageBase64 = null;
    attachedImageMime = null;
    fileInput.value = '';
    imagePreviewContainer.style.display = 'none';
  });

  // ── Reset Chat ─────────────────────────────────────────────
  btnClearChat.addEventListener('click', () => {
    conversationId = 'web_' + Math.random().toString(36).substring(2, 9);
    chatMessages.innerHTML = `
      <div class="message-bubble bot-message intro-message">
        <div class="bubble-header">
          <span class="sender-name">AutoSpare AI</span>
          <span class="time">Just now</span>
        </div>
        <p>👋 Conversation reset! Ready for your next diagnosis.</p>
        <p>Describe your machine or vehicle problem to get instant AI recommendations, parts, and repair videos.</p>
      </div>
    `;
    diagStatusBadge.className = 'badge badge-idle';
    diagStatusBadge.textContent = 'Awaiting Input';
    diagnosisContent.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
        </div>
        <h4>No Active Diagnosis Yet</h4>
        <p>Type a fault description or click any quick-test prompt on the left.</p>
      </div>
    `;
  });

  // ── Chat Form Submit ───────────────────────────────────────
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    handleSendMessage();
  });

  // Enable Enter key to send (Shift+Enter for newline)
  messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  });

  async function handleSendMessage() {
    const text = messageInput.value.trim();
    if (!text && !attachedImageBase64) return;

    // Add user message to chat UI
    appendUserMessage(text, attachedImageBase64);

    // Save image to send and clear preview
    const sendImg = attachedImageBase64;
    const sendMime = attachedImageMime;
    attachedImageBase64 = null;
    attachedImageMime = null;
    fileInput.value = '';
    imagePreviewContainer.style.display = 'none';
    messageInput.value = '';

    // Show loading state
    btnSend.disabled = true;
    diagStatusBadge.className = 'badge badge-analyzing';
    diagStatusBadge.textContent = 'Analyzing with Gemini…';

    const loadingId = appendBotLoading();

    try {
      const selectedLanguage = langSelect.value;
      const res = await fetch('/api/diagnose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          conversation_id: conversationId,
          language: selectedLanguage,
          image_base64: sendImg,
          mime_type: sendMime,
        }),
      });

      removeBotLoading(loadingId);

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error (${res.status})`);
      }

      const data = await res.json();
      renderBotReply(data);
      renderDiagnosisPanel(data);

    } catch (err) {
      removeBotLoading(loadingId);
      appendBotError(err.message);
      diagStatusBadge.className = 'badge badge-critical';
      diagStatusBadge.textContent = 'Diagnosis Error';
    } finally {
      btnSend.disabled = false;
      messageInput.focus();
    }
  }

  // ── Chat Message Appenders ─────────────────────────────────
  function appendUserMessage(text, imgBase64) {
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble user-message';

    let html = `
      <div class="bubble-header">
        <span class="sender-name">You</span>
        <span class="time">${now}</span>
      </div>
      <div>${escapeHtml(text)}</div>
    `;

    if (imgBase64) {
      html += `<img src="${imgBase64}" class="msg-img-preview" alt="User uploaded part">`;
    }

    bubble.innerHTML = html;
    chatMessages.appendChild(bubble);
    scrollChatToBottom();
  }

  function appendBotLoading() {
    const id = 'loading_' + Date.now();
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble bot-message';
    bubble.id = id;
    bubble.innerHTML = `
      <div class="bubble-header">
        <span class="sender-name">AutoSpare AI</span>
        <span class="time">Analyzing</span>
      </div>
      <div style="display: flex; align-items: center; gap: 8px;">
        <span class="pulse-dot"></span>
        <span style="color: var(--accent-cyan);">Running fault analysis & querying parts database…</span>
      </div>
    `;
    chatMessages.appendChild(bubble);
    scrollChatToBottom();
    return id;
  }

  function removeBotLoading(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  function appendBotError(errorMsg) {
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble bot-message';
    bubble.innerHTML = `
      <div class="bubble-header">
        <span class="sender-name" style="color: var(--accent-red);">AutoSpare AI (Error)</span>
        <span class="time">${now}</span>
      </div>
      <p style="color: #fca5a5;">⚠️ Could not complete diagnosis: ${escapeHtml(errorMsg)}</p>
    `;
    chatMessages.appendChild(bubble);
    scrollChatToBottom();
  }

  function renderBotReply(data) {
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble bot-message';

    let html = `
      <div class="bubble-header">
        <span class="sender-name">AutoSpare AI</span>
        <span class="time">${now}</span>
      </div>
    `;

    if (data.needs_clarification) {
      html += `
        <p>❓ <strong>Clarification Needed:</strong></p>
        <p>${escapeHtml(data.clarification_question || 'Could you provide more details about your vehicle model or symptoms?')}</p>
      `;
    } else {
      html += `
        <p><strong>Diagnosis:</strong> ${escapeHtml(data.fault_summary || 'Diagnosis completed.')}</p>
      `;

      if (data.safety_warning) {
        html += `
          <div class="safety-alert" style="margin: 8px 0;">
            <span class="safety-icon">⚠️</span>
            <span class="safety-text"><strong>Safety Alert:</strong> ${escapeHtml(data.safety_warning)}</span>
          </div>
        `;
      }

      if (data.spare_parts && data.spare_parts.length > 0) {
        html += `
          <p style="margin-top: 8px; font-weight: 600; color: #a7f3d0;">
            📦 Recommended Spare Parts (${data.spare_parts.length} identified):
          </p>
          <ul style="margin: 4px 0 8px 18px; color: #cbd5e1; font-size: 0.84rem;">
            ${data.spare_parts.map(p => `
              <li><strong>${escapeHtml(p.name)}</strong> ${p.brand ? `(${escapeHtml(p.brand)})` : ''} — 
                ${p.price_min ? `₹${p.price_min}${p.price_max ? ` - ₹${p.price_max}` : ''}` : 'Price on request'}
              </li>
            `).join('')}
          </ul>
        `;
      }

      if (data.youtube_tutorials && data.youtube_tutorials.length > 0) {
        html += `
          <p style="font-size: 0.8rem; color: #94a3b8;">
            🎥 <em>${data.youtube_tutorials.length} repair tutorial videos found. Check the right panel for video links!</em>
          </p>
        `;
      }
    }

    bubble.innerHTML = html;
    chatMessages.appendChild(bubble);
    scrollChatToBottom();
  }

  function scrollChatToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  // ── Render Diagnostic Inspector Panel ──────────────────────
  function renderDiagnosisPanel(data) {
    const sev = (data.severity || 'medium').toLowerCase();
    diagStatusBadge.className = `badge badge-${sev}`;
    diagStatusBadge.textContent = `${sev.toUpperCase()} SEVERITY`;

    let html = '';

    // Summary Section
    html += `
      <div class="diag-section">
        <div class="diag-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
          Fault Summary (${escapeHtml(data.detected_language || 'English')})
        </div>
        <p class="diag-summary-text">${escapeHtml(data.fault_summary || 'Diagnosis ready')}</p>
      </div>
    `;

    // Root Causes
    if (data.root_causes && data.root_causes.length > 0) {
      html += `
        <div class="diag-section">
          <div class="diag-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
            Identified Root Causes
          </div>
          <ul class="root-causes-list">
            ${data.root_causes.map(rc => `
              <li class="root-cause-item">
                <span class="root-cause-bullet">▸</span>
                <span>${escapeHtml(rc)}</span>
              </li>
            `).join('')}
          </ul>
        </div>
      `;
    }

    // Safety Alert
    if (data.safety_warning) {
      html += `
        <div class="safety-alert">
          <span class="safety-icon">⚠️</span>
          <span class="safety-text"><strong>High-Risk Advisory:</strong> ${escapeHtml(data.safety_warning)}</span>
        </div>
      `;
    }

    // Enriched Spare Parts
    if (data.spare_parts && data.spare_parts.length > 0) {
      html += `
        <div class="diag-section">
          <div class="diag-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg>
            Matching Spare Parts from Stock
          </div>
          <div class="parts-list">
            ${data.spare_parts.map(p => `
              <div class="part-card-mini">
                <div class="part-header">
                  <span class="part-name">${escapeHtml(p.name)}</span>
                  <span class="part-price-tag">
                    ${p.price_min ? `₹${p.price_min}${p.price_max ? ` - ₹${p.price_max}` : ''}` : '₹ Contact'}
                  </span>
                </div>
                <div class="part-meta">
                  ${p.part_number ? `<span class="oem-code">OEM: ${escapeHtml(p.part_number)}</span>` : ''}
                  ${p.brand ? `<span class="part-brand">Brand: ${escapeHtml(p.brand)}</span>` : ''}
                  <span class="part-stock-badge ${p.in_stock !== false ? 'stock-available' : 'stock-unavailable'}">
                    ${p.in_stock !== false ? `✓ In Stock (${p.stock_qty || 15} units)` : 'Out of Stock'}
                  </span>
                </div>
                ${p.reason ? `<div class="part-reason">${escapeHtml(p.reason)}</div>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    // YouTube Tutorials
    if (data.youtube_tutorials && data.youtube_tutorials.length > 0) {
      html += `
        <div class="diag-section">
          <div class="diag-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22.54 6.42a2.78 2.78 0 0 0-1.94-2C18.88 4 12 4 12 4s-6.88 0-8.6.46a2.78 2.78 0 0 0-1.94 2A29 29 0 0 0 1 11.75a29 29 0 0 0 .46 5.33A2.78 2.78 0 0 0 3.4 19c1.72.46 8.6.46 8.6.46s6.88 0 8.6-.46a2.78 2.78 0 0 0 1.94-2 29 29 0 0 0 .46-5.25 29 29 0 0 0-.46-5.33z"></path><polygon points="9.75 15.02 15.5 11.75 9.75 8.48 9.75 15.02"></polygon></svg>
            YouTube Repair Tutorials (${escapeHtml(data.detected_language || 'English')})
          </div>
          <div class="videos-list">
            ${data.youtube_tutorials.map(v => `
              <a href="${escapeHtml(v.url || `https://www.youtube.com/watch?v=${v.video_id}`)}" target="_blank" rel="noopener" class="video-card">
                <img src="${escapeHtml(v.thumbnail_url || 'https://images.unsplash.com/photo-1486006920555-c77dce18193b?w=200&auto=format&fit=crop&q=60')}" class="video-thumb" alt="${escapeHtml(v.title || '')}">
                <div class="video-info">
                  <span class="video-title" title="${escapeHtml(v.title || '')}">${escapeHtml(v.title || 'Watch Repair Tutorial')}</span>
                  <span class="video-channel">${escapeHtml(v.channel_title || 'YouTube Mechanic')}</span>
                  <span class="video-cta">Watch Video ↗</span>
                </div>
              </a>
            `).join('')}
          </div>
        </div>
      `;
    }

    diagnosisContent.innerHTML = html;
  }

  // ── Tab 2: Spare Parts Catalogue Fetch & Render ────────────
  let searchMode = 'sbert'; // 'sbert' or 'keyword'
  const btnModeSbert = document.getElementById('btnModeSbert');
  const btnModeKeyword = document.getElementById('btnModeKeyword');

  if (btnModeSbert && btnModeKeyword) {
    btnModeSbert.addEventListener('click', () => {
      searchMode = 'sbert';
      btnModeSbert.classList.add('active');
      btnModeKeyword.classList.remove('active');
      catalogSearch.placeholder = "Describe symptoms or natural phrase (e.g. 'scooter belt slipping', 'clicking sound on self')...";
      if (catalogSearch.value.trim()) {
        fetchCatalog(catalogSearch.value.trim(), currentCategory);
      }
    });

    btnModeKeyword.addEventListener('click', () => {
      searchMode = 'keyword';
      btnModeKeyword.classList.add('active');
      btnModeSbert.classList.remove('active');
      catalogSearch.placeholder = "Search by exact part name, OEM part number, brand, vehicle...";
      fetchCatalog(catalogSearch.value.trim(), currentCategory);
    });
  }

  async function fetchCatalog(search = '', category = 'all') {
    partsGrid.innerHTML = '<div class="loading-spinner">Loading catalogue...</div>';

    try {
      if (search && searchMode === 'sbert') {
        // Use Sentence-BERT semantic search
        const url = `/api/parts/semantic-search?q=${encodeURIComponent(search)}&limit=30&min_score=0.15`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        const data = await res.json();

        catalogParts = data.results || [];
        totalPartsCount.textContent = `${catalogParts.length} Semantic Matches`;
        renderPartsGrid(catalogParts, true);
        return;
      }

      let url = `/api/catalog?limit=50`;
      if (search) url += `&search=${encodeURIComponent(search)}`;
      if (category && category !== 'all') url += `&category=${encodeURIComponent(category)}`;

      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();

      catalogParts = data.parts || [];
      totalPartsCount.textContent = data.total || catalogParts.length;

      // Render category filter buttons if not rendered
      renderCategoryFilters(data.categories || []);

      // Render parts
      renderPartsGrid(catalogParts, false);

    } catch (err) {
      partsGrid.innerHTML = `<div class="loading-spinner" style="color: var(--accent-red);">Failed to load parts catalogue: ${escapeHtml(err.message)}</div>`;
    }
  }

  function renderCategoryFilters(categories) {
    if (categoryFilters.children.length > 1) return; // already rendered

    categories.forEach(cat => {
      const btn = document.createElement('button');
      btn.className = 'filter-btn';
      btn.setAttribute('data-category', cat.toLowerCase());
      btn.textContent = cat;
      btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentCategory = cat.toLowerCase();
        fetchCatalog(catalogSearch.value.trim(), currentCategory);
      });
      categoryFilters.appendChild(btn);
    });

    const allBtn = categoryFilters.querySelector('.filter-btn[data-category="all"]');
    if (allBtn) {
      allBtn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        allBtn.classList.add('active');
        currentCategory = 'all';
        fetchCatalog(catalogSearch.value.trim(), 'all');
      });
    }
  }

  function renderPartsGrid(parts, isSemantic = false) {
    if (!parts || parts.length === 0) {
      partsGrid.innerHTML = '<div class="loading-spinner">No spare parts match your query.</div>';
      return;
    }

    partsGrid.innerHTML = parts.map(p => `
      <div class="catalog-part-card">
        <div>
          <div class="part-top">
            <span class="part-category-tag">${escapeHtml(p.category || 'General')}</span>
            <div style="display: flex; gap: 6px; align-items: center;">
              ${p.similarity_score ? `<span class="similarity-badge">⚡ ${(p.similarity_score * 100).toFixed(0)}% Match</span>` : ''}
              <span class="part-price-badge">
                ${p.price_min ? `₹${p.price_min}${p.price_max ? ` - ₹${p.price_max}` : ''}` : '₹ Inquiry'}
              </span>
            </div>
          </div>
          <div class="part-title-block" style="margin-top: 10px;">
            <h4>${escapeHtml(p.name)}</h4>
            <p class="part-desc">${escapeHtml(p.description || '')}</p>
          </div>
          ${p.compatible_with && p.compatible_with.length > 0 ? `
            <div class="part-compat">
              ${p.compatible_with.slice(0, 4).map(c => `<span class="compat-chip">${escapeHtml(c)}</span>`).join('')}
              ${p.compatible_with.length > 4 ? `<span class="compat-chip">+${p.compatible_with.length - 4} more</span>` : ''}
            </div>
          ` : ''}
        </div>
        <div class="part-bottom">
          <span class="oem-code">${p.part_number ? `PN: ${escapeHtml(p.part_number)}` : 'OEM'}</span>
          <span style="color: var(--text-muted);">${escapeHtml(p.brand || 'Genuine')}</span>
          <span class="part-stock-badge ${p.in_stock ? 'stock-available' : 'stock-unavailable'}">
            ${p.in_stock ? `✓ In Stock (${p.stock_qty || 20})` : 'Out of Stock'}
          </span>
        </div>
      </div>
    `).join('');
  }

  // Debounced search on catalogue
  let searchTimeout = null;
  catalogSearch.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      fetchCatalog(catalogSearch.value.trim(), currentCategory);
    }, 300);
  });

  // ── Tab 3: Webhook Simulator ───────────────────────────────
  btnSendWebhookSim.addEventListener('click', async () => {
    const phone = simPhone.value.trim();
    const text = simText.value.trim();
    if (!phone || !text) {
      showToast('Please enter both phone and test message');
      return;
    }

    simResult.style.display = 'block';
    simResult.textContent = 'Sending simulated Meta Webhook event to /webhook…';

    const simulatedPayload = {
      object: "whatsapp_business_account",
      entry: [
        {
          id: "1345656525295909",
          changes: [
            {
              field: "messages",
              value: {
                messaging_product: "whatsapp",
                metadata: {
                  display_phone_number: "15550001234",
                  phone_number_id: "1345656525295909"
                },
                contacts: [
                  {
                    profile: { name: "Test User" },
                    wa_id: phone.replace('+', '')
                  }
                ],
                messages: [
                  {
                    from: phone.replace('+', ''),
                    id: "wamid.simulated_" + Date.now(),
                    timestamp: Math.floor(Date.now() / 1000).toString(),
                    type: "text",
                    text: { body: text }
                  }
                ]
              }
            }
          ]
        }
      ]
    };

    try {
      const res = await fetch('/webhook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(simulatedPayload),
      });

      const responseText = await res.text();
      simResult.textContent = `Status: ${res.status} ${res.statusText}\n\nResponse:\n${responseText}\n\n[SUCCESS] Webhook event was received and processed asynchronously by the backend pipeline! Check your server console for live logs.`;
      showToast('Webhook event delivered successfully!');
    } catch (e) {
      simResult.textContent = `Error: ${e.message}`;
      showToast('Webhook simulation failed');
    }
  });

  // ── Toast Notification ─────────────────────────────────────
  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => {
      toast.classList.remove('show');
    }, 3500);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // ── Initial Boot ───────────────────────────────────────────
  checkSystemStatus();
  fetchCatalog();
});
