/**
 * ai_chat.js - 공통 AI 퀀트 애널리스트 채팅 컴포넌트 & 전역 API 설정 모달
 * - Gemini, OpenAI (ChatGPT), Anthropic (Claude) 지원
 * - localStorage ('quant_ai_settings_v1') 기반 전역 설정 공유
 * - 탭별 독립 대화 이력 유지 + 마크다운 렌더링 + 추천 질문 칩
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'quant_ai_settings_v1';

  const PROVIDER_MODELS = {
    gemini: [
      { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
      { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' }
    ],
    openai: [
      { value: 'gpt-4o-mini', label: 'GPT-4o mini' },
      { value: 'gpt-4o', label: 'GPT-4o' }
    ],
    anthropic: [
      { value: 'claude-3-5-sonnet-latest', label: 'Claude 3.5 Sonnet' },
      { value: 'claude-3-5-haiku-latest', label: 'Claude 3.5 Haiku' }
    ]
  };

  const DEFAULT_SUGGESTIONS = [
    '현재 결과의 핵심 리스크와 MDD 방어법 분석',
    '수익률 대비 샤프지수를 높일 비중 조정 제안',
    '스크리닝 상위 종목 중 핵심 추천 3선'
  ];

  const histories = {};
  const mountedInstances = [];

  function loadSettings() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && parsed.provider && PROVIDER_MODELS[parsed.provider]) {
          return {
            provider: parsed.provider,
            model: parsed.model || PROVIDER_MODELS[parsed.provider][0].value,
            apiKey: parsed.apiKey || ''
          };
        }
      }
    } catch (e) {}
    return {
      provider: 'gemini',
      model: 'gemini-2.5-flash',
      apiKey: ''
    };
  }

  function saveSettings(settings) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch (e) {}
    refreshAllModelBadges();
  }

  function getModelLabel(provider, modelValue) {
    const list = PROVIDER_MODELS[provider] || PROVIDER_MODELS.gemini;
    const found = list.find(m => m.value === modelValue);
    return found ? found.label : (modelValue || list[0].label);
  }

  function refreshAllModelBadges() {
    const s = loadSettings();
    const label = getModelLabel(s.provider, s.model);
    document.querySelectorAll('.ai-model-badge').forEach(el => {
      el.textContent = label;
    });
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function formatInlineMd(text) {
    return escapeHtml(text)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  }

  function renderMarkdown(mdText) {
    const lines = String(mdText || '').split(/\r?\n/);
    let html = '';
    let inUl = false;
    let inOl = false;
    let tableRows = [];

    function flushLists() {
      if (inUl) { html += '</ul>'; inUl = false; }
      if (inOl) { html += '</ol>'; inOl = false; }
    }

    function flushTable() {
      if (tableRows.length === 0) return;
      const parsed = tableRows.map(r =>
        r.replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim())
      );
      html += '<div class="ai-md-table-wrap"><table class="ai-md-table">';
      parsed.forEach((cells, idx) => {
        if (idx === 1 && cells.every(c => /^:?-{2,}:?$/.test(c))) return;
        const tag = idx === 0 ? 'th' : 'td';
        html += '<tr>' + cells.map(c => `<${tag}>${formatInlineMd(c)}</${tag}>`).join('') + '</tr>';
      });
      html += '</table></div>';
      tableRows = [];
    }

    lines.forEach(rawLine => {
      const line = rawLine.trimEnd();
      if (/^\s*\|.+\|\s*$/.test(line)) {
        flushLists();
        tableRows.push(line.trim());
        return;
      }
      flushTable();

      const ulMatch = line.match(/^\s*[-*•]\s+(.+)/);
      const olMatch = line.match(/^\s*\d+\.\s+(.+)/);
      if (ulMatch) {
        if (inOl) { html += '</ol>'; inOl = false; }
        if (!inUl) { html += '<ul>'; inUl = true; }
        html += `<li>${formatInlineMd(ulMatch[1])}</li>`;
      } else if (olMatch) {
        if (inUl) { html += '</ul>'; inUl = false; }
        if (!inOl) { html += '<ol>'; inOl = true; }
        html += `<li>${formatInlineMd(olMatch[1])}</li>`;
      } else {
        flushLists();
        if (line.trim() === '') {
          html += '<br>';
        } else {
          html += `<div>${formatInlineMd(line)}</div>`;
        }
      }
    });

    flushLists();
    flushTable();
    return `<div class="ai-md-body">${html}</div>`;
  }

  // ── 전역 설정 모달 제어 ──
  function syncModalFields(providerOverride = null) {
    const s = loadSettings();
    const prov = providerOverride || s.provider;
    const modal = document.getElementById('aiSettingsModal');
    if (!modal) return;

    modal.querySelectorAll('.ai-provider-radio').forEach(lbl => {
      const inp = lbl.querySelector('input[name="aiProviderRadio"]');
      const checked = inp && inp.value === prov;
      if (inp) inp.checked = checked;
      lbl.classList.toggle('active', checked);
    });

    const modelSel = document.getElementById('aiModelSelect');
    if (modelSel) {
      const options = PROVIDER_MODELS[prov] || PROVIDER_MODELS.gemini;
      modelSel.innerHTML = options.map(m => `<option value="${m.value}">${m.label}</option>`).join('');
      if (!providerOverride && options.some(m => m.value === s.model)) {
        modelSel.value = s.model;
      } else {
        modelSel.value = options[0].value;
      }
    }

    const keyInp = document.getElementById('aiApiKeyInput');
    if (keyInp && !providerOverride) {
      keyInp.value = s.apiKey || '';
    }
  }

  function openSettingsModal() {
    const modal = document.getElementById('aiSettingsModal');
    if (!modal) return;
    syncModalFields();
    modal.classList.add('show');
    modal.style.display = 'flex';
  }

  function closeSettingsModal() {
    const modal = document.getElementById('aiSettingsModal');
    if (!modal) return;
    modal.classList.remove('show');
    modal.style.display = 'none';
  }

  function bindGlobalSettingsModal() {
    const modal = document.getElementById('aiSettingsModal');
    if (!modal) return;

    const closeBtn = document.getElementById('aiBtnCloseSettings');
    const saveBtn = document.getElementById('aiSaveSettingsBtn');
    const eyeBtn = document.getElementById('aiToggleKeyVisBtn');
    const keyInp = document.getElementById('aiApiKeyInput');

    if (closeBtn) closeBtn.addEventListener('click', closeSettingsModal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeSettingsModal();
    });

    modal.querySelectorAll('.ai-provider-radio').forEach(lbl => {
      lbl.addEventListener('click', () => {
        const inp = lbl.querySelector('input[name="aiProviderRadio"]');
        if (inp) syncModalFields(inp.value);
      });
    });

    if (eyeBtn && keyInp) {
      eyeBtn.addEventListener('click', () => {
        const isPwd = keyInp.type === 'password';
        keyInp.type = isPwd ? 'text' : 'password';
        eyeBtn.innerHTML = isPwd ? '<i class="fa-regular fa-eye-slash"></i>' : '<i class="fa-regular fa-eye"></i>';
      });
    }

    if (saveBtn) {
      saveBtn.addEventListener('click', () => {
        const checkedRadio = modal.querySelector('input[name="aiProviderRadio"]:checked');
        const provider = checkedRadio ? checkedRadio.value : 'gemini';
        const modelSel = document.getElementById('aiModelSelect');
        const model = modelSel ? modelSel.value : PROVIDER_MODELS[provider][0].value;
        const apiKey = keyInp ? keyInp.value.trim() : '';
        saveSettings({ provider, model, apiKey });
        closeSettingsModal();
      });
    }
  }

  // ── 탭별 채팅 UI 마운트 ──
  function mount(containerOrId, options = {}) {
    const container = typeof containerOrId === 'string'
      ? document.getElementById(containerOrId)
      : containerOrId;
    if (!container) return null;

    const tabKey = options.tabKey || 'default';
    const tabName = options.tabName || '퀀트 대시보드';
    const suggestions = Array.isArray(options.suggestions) && options.suggestions.length > 0
      ? options.suggestions.slice(0, 3)
      : DEFAULT_SUGGESTIONS;
    const getContextSummary = typeof options.getContextSummary === 'function'
      ? options.getContextSummary
      : () => '';

    if (!histories[tabKey]) histories[tabKey] = [];

    const s = loadSettings();
    const badgeLabel = getModelLabel(s.provider, s.model);

    container.innerHTML = `
      <div class="ai-chat-card" data-ai-tab="${tabKey}">
        <div class="ai-chat-header">
          <div class="ai-chat-title-wrap">
            <span class="ai-chat-title-icon"><i class="fa-solid fa-sparkles"></i></span>
            <h3 class="ai-chat-title">AI 퀀트 애널리스트 (${escapeHtml(tabName)})</h3>
          </div>
          <div class="ai-chat-header-actions">
            <span class="ai-model-badge">${escapeHtml(badgeLabel)}</span>
            <button type="button" class="ai-header-btn ai-btn-reset" title="대화 초기화">
              <i class="fa-solid fa-rotate-left"></i> 초기화
            </button>
            <button type="button" class="ai-header-btn ai-btn-settings" title="AI API 설정">
              <i class="fa-solid fa-gear"></i> 설정
            </button>
          </div>
        </div>
        <div class="ai-chat-messages"></div>
        <div class="ai-chat-input-bar">
          <textarea class="ai-chat-textarea" rows="1" placeholder="현재 전략 수치에 대해 질문하세요... (Enter 전송, Shift+Enter 줄바꿈)"></textarea>
          <button type="button" class="ai-chat-send-btn">
            <i class="fa-solid fa-paper-plane"></i> 전송
          </button>
        </div>
      </div>
    `;

    const msgBox = container.querySelector('.ai-chat-messages');
    const textarea = container.querySelector('.ai-chat-textarea');
    const sendBtn = container.querySelector('.ai-chat-send-btn');
    const resetBtn = container.querySelector('.ai-btn-reset');
    const settingsBtn = container.querySelector('.ai-btn-settings');

    let isSending = false;

    function renderMessages() {
      const msgs = histories[tabKey] || [];
      if (msgs.length === 0) {
        msgBox.innerHTML = `
          <div class="ai-empty-state">
            <p class="ai-empty-desc">
              현재 <strong>${escapeHtml(tabName)}</strong> 탭의 실제 백테스트·스크리닝 결과를 기반으로 질문할 수 있습니다.
            </p>
            <div class="ai-suggestions">
              ${suggestions.map(q => `<button type="button" class="ai-suggestion-chip">${escapeHtml(q)}</button>`).join('')}
            </div>
          </div>
        `;
        msgBox.querySelectorAll('.ai-suggestion-chip').forEach(chip => {
          chip.addEventListener('click', () => sendMessage(chip.textContent));
        });
        return;
      }

      msgBox.innerHTML = '';
      msgs.forEach(m => {
        const row = document.createElement('div');
        row.className = `ai-msg-row ${m.role}`;
        const bubble = document.createElement('div');
        bubble.className = `ai-bubble ${m.role}${m.isError ? ' error' : ''}`;

        if (m.role === 'user') {
          bubble.innerHTML = escapeHtml(m.content).replace(/\n/g, '<br>');
        } else {
          bubble.innerHTML = renderMarkdown(m.content) + `
            <div class="ai-bubble-actions">
              <button type="button" class="ai-copy-btn"><i class="fa-regular fa-copy"></i> 답변 복사</button>
            </div>
          `;
          const copyBtn = bubble.querySelector('.ai-copy-btn');
          if (copyBtn) {
            copyBtn.addEventListener('click', async () => {
              try {
                await navigator.clipboard.writeText(m.content);
                copyBtn.innerHTML = '<i class="fa-solid fa-check"></i> 복사됨';
                setTimeout(() => {
                  copyBtn.innerHTML = '<i class="fa-regular fa-copy"></i> 답변 복사';
                }, 1500);
              } catch (e) {}
            });
          }
        }
        row.appendChild(bubble);
        msgBox.appendChild(row);
      });

      msgBox.scrollTop = msgBox.scrollHeight;
    }

    async function sendMessage(rawText) {
      const text = String(rawText !== undefined ? rawText : textarea.value).trim();
      if (!text || isSending) return;

      const cfg = loadSettings();
      histories[tabKey].push({ role: 'user', content: text });
      if (rawText === undefined) {
        textarea.value = '';
        textarea.style.height = 'auto';
      }
      renderMessages();

      isSending = true;
      sendBtn.disabled = true;

      const loadingRow = document.createElement('div');
      loadingRow.className = 'ai-msg-row assistant';
      loadingRow.innerHTML = '<div class="ai-bubble assistant"><i class="fa-solid fa-spinner fa-spin"></i> AI 애널리스트가 분석 중입니다...</div>';
      msgBox.appendChild(loadingRow);
      msgBox.scrollTop = msgBox.scrollHeight;

      try {
        const contextSummary = String(getContextSummary() || '').trim();
        const resp = await fetch('/api/ai_analyst_chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            provider: cfg.provider,
            model: cfg.model,
            api_key: cfg.apiKey,
            tab_name: tabName,
            context_summary: contextSummary,
            messages: histories[tabKey].filter(m => !m.isError).map(m => ({ role: m.role, content: m.content }))
          })
        });
        const res = await resp.json();
        if (!resp.ok || !res.ok) {
          histories[tabKey].push({
            role: 'assistant',
            content: res.error || `요청 실패 (${resp.status})`,
            isError: true
          });
        } else {
          histories[tabKey].push({ role: 'assistant', content: res.reply || '' });
        }
      } catch (err) {
        histories[tabKey].push({
          role: 'assistant',
          content: `네트워크 오류: ${err.message}`,
          isError: true
        });
      } finally {
        isSending = false;
        sendBtn.disabled = false;
        renderMessages();
      }
    }

    sendBtn.addEventListener('click', () => sendMessage());
    textarea.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    textarea.addEventListener('input', () => {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(110, textarea.scrollHeight)}px`;
    });

    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        histories[tabKey] = [];
        renderMessages();
      });
    }
    if (settingsBtn) {
      settingsBtn.addEventListener('click', openSettingsModal);
    }

    renderMessages();
    const inst = { tabKey, renderMessages, sendMessage };
    mountedInstances.push(inst);
    return inst;
  }

  window.QuantAiChat = {
    mount,
    openSettingsModal,
    closeSettingsModal,
    getSettings: loadSettings
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      bindGlobalSettingsModal();
      refreshAllModelBadges();
    });
  } else {
    bindGlobalSettingsModal();
    refreshAllModelBadges();
  }
})();
