/**
 * auth.js - Supabase Auth 전역 세션 관리 및 Google 로그인 모듈
 * - window.sbClient : Supabase 클라이언트 인스턴스
 * - window.sbUser   : 현재 로그인된 유저 객체 (비로그인 시 null)
 * - CustomEvent 'sb-auth-changed' ({ detail: { user } }) 발행
 */
(function () {
  'use strict';

  const DEFAULT_SUPABASE_URL = '[여기에_Project_URL_붙여넣기]';
  const DEFAULT_SUPABASE_ANON_KEY = '[여기에_anon_public_key_붙여넣기]';

  window.sbClient = window.sbClient || null;
  window.sbUser = window.sbUser || null;

  function getSupabaseConfig() {
    return {
      url: (window.SUPABASE_URL || DEFAULT_SUPABASE_URL).trim(),
      anonKey: (window.SUPABASE_ANON_KEY || DEFAULT_SUPABASE_ANON_KEY).trim()
    };
  }

  function dispatchAuthChanged(user) {
    window.sbUser = user || null;
    updateAuthModalUI();
    window.dispatchEvent(new CustomEvent('sb-auth-changed', {
      detail: { user: window.sbUser }
    }));
  }

  async function initSupabaseAuth() {
    const cfg = getSupabaseConfig();
    if (!cfg.url || !cfg.anonKey || !window.supabase || typeof window.supabase.createClient !== 'function') {
      window.sbClient = null;
      dispatchAuthChanged(null);
      return false;
    }

    try {
      window.sbClient = window.supabase.createClient(cfg.url, cfg.anonKey);
      const { data } = await window.sbClient.auth.getSession();
      const currentUser = data && data.session ? data.session.user : null;
      dispatchAuthChanged(currentUser);

      window.sbClient.auth.onAuthStateChange((_event, session) => {
        const nextUser = session && session.user ? session.user : null;
        dispatchAuthChanged(nextUser);
      });
      return true;
    } catch (err) {
      console.warn('[Auth] Supabase 초기화 실패:', err);
      window.sbClient = null;
      dispatchAuthChanged(null);
      return false;
    }
  }

  function updateAuthModalUI() {
    const statusEl = document.getElementById('sbLoginStatusMsg');
    if (statusEl) {
      if (window.sbUser) {
        statusEl.textContent = `로그인됨: ${window.sbUser.email || window.sbUser.id}`;
        statusEl.style.color = '#6ee7b7';
      } else {
        statusEl.textContent = 'Google 계정으로 로그인하면 커리어 모드 자산이 클라우드에 저장됩니다.';
        statusEl.style.color = '#94a3b8';
      }
    }
  }

  function openLoginModal() {
    const modal = document.getElementById('sbLoginModal');
    if (modal) {
      updateAuthModalUI();
      modal.classList.add('show');
      modal.style.display = 'flex';
    }
  }

  function closeLoginModal() {
    const modal = document.getElementById('sbLoginModal');
    if (modal) {
      modal.classList.remove('show');
      modal.style.display = 'none';
    }
  }

  async function signInWithGoogle() {
    if (!window.sbClient) {
      const statusEl = document.getElementById('sbLoginStatusMsg');
      if (statusEl) {
        statusEl.textContent = '인증 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.';
        statusEl.style.color = '#fca5a5';
      }
      return;
    }

    try {
      const { error } = await window.sbClient.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: window.location.href
        }
      });
      if (error) throw error;
    } catch (err) {
      const statusEl = document.getElementById('sbLoginStatusMsg');
      if (statusEl) {
        statusEl.textContent = `Google 로그인 오류: ${err.message}`;
        statusEl.style.color = '#fca5a5';
      }
    }
  }

  async function signOut() {
    if (!window.sbClient) return;
    try {
      await window.sbClient.auth.signOut();
    } catch (e) {}
  }

  function bindModalEvents() {
    const closeBtn = document.getElementById('sbBtnCloseLoginModal');
    const googleBtn = document.getElementById('sbGoogleLoginBtn');
    const modal = document.getElementById('sbLoginModal');

    if (closeBtn) closeBtn.addEventListener('click', closeLoginModal);
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeLoginModal();
      });
    }
    if (googleBtn) googleBtn.addEventListener('click', signInWithGoogle);
  }

  window.sbAuth = {
    initSupabaseAuth,
    openLoginModal,
    closeLoginModal,
    signInWithGoogle,
    signOut,
    isConfigured: () => Boolean(window.sbClient)
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      bindModalEvents();
      initSupabaseAuth();
    });
  } else {
    bindModalEvents();
    initSupabaseAuth();
  }
})();
