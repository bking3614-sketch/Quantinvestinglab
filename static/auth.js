/**
 * auth.js - Supabase Auth 전역 세션 관리 및 Google 로그인 모듈
 * - window.sbClient : Supabase 클라이언트 인스턴스
 * - window.sbUser   : 현재 로그인된 유저 객체 (비로그인 시 null)
 * - CustomEvent 'sb-auth-changed' ({ detail: { user } }) 발행
 */
(function () {
  'use strict';

  const SUPABASE_URL = "https://uajiubjthfwgvndvxhxq.supabase.co";
  const SUPABASE_ANON_KEY = "sb_publishable_pCNdOspjwWg94vT3GFEusQ_mBrB9Vob";

  window.sbClient = window.sbClient || null;
  window.sbUser = window.sbUser || null;
  let lastInitError = null;

  function handlePendingCareerRedirect(user) {
    if (!user) return;
    try {
      if (sessionStorage.getItem('cg_pending_career') === '1') {
        closeLoginModal();
        const tabBtn = document.getElementById('tabBtnChartGame');
        if (tabBtn && !tabBtn.classList.contains('active')) {
          tabBtn.click();
        }
      }
    } catch (e) {}
  }

  function dispatchAuthChanged(user) {
    window.sbUser = user || null;
    updateAuthModalUI();
    handlePendingCareerRedirect(window.sbUser);
    window.dispatchEvent(new CustomEvent('sb-auth-changed', {
      detail: { user: window.sbUser }
    }));
  }

  async function initSupabaseAuth() {
    lastInitError = null;

    // 기존 localStorage에 남아있을 수 있는 잘못된 설정 무시 및 정리
    try {
      localStorage.removeItem('sb_project_config_v1');
    } catch (e) {}

    if (!window.supabase || typeof window.supabase.createClient !== 'function') {
      lastInitError = 'Supabase JS SDK(@supabase/supabase-js@2)가 로드되지 않았습니다.';
      window.sbClient = null;
      dispatchAuthChanged(null);
      return false;
    }

    try {
      const url = SUPABASE_URL.trim();
      const anonKey = SUPABASE_ANON_KEY.trim();
      window.sbClient = window.supabase.createClient(url, anonKey);

      const { data, error } = await window.sbClient.auth.getSession();
      if (error) throw error;

      const currentUser = data && data.session ? data.session.user : null;
      dispatchAuthChanged(currentUser);

      window.sbClient.auth.onAuthStateChange((_event, session) => {
        const nextUser = session && session.user ? session.user : null;
        dispatchAuthChanged(nextUser);
      });
      return true;
    } catch (err) {
      lastInitError = err && err.message ? err.message : String(err);
      console.warn('[Auth] Supabase 초기화 실패:', lastInitError);
      window.sbClient = null;
      dispatchAuthChanged(null);
      return false;
    }
  }

  function updateAuthModalUI() {
    const statusEl = document.getElementById('sbLoginStatusMsg');
    if (!statusEl) return;

    if (window.sbUser) {
      statusEl.textContent = `로그인됨: ${window.sbUser.email || window.sbUser.id}`;
      statusEl.style.color = '#6ee7b7';
    } else if (lastInitError) {
      statusEl.textContent = `Supabase 연결 오류: ${lastInitError}`;
      statusEl.style.color = '#fca5a5';
    } else {
      statusEl.textContent = 'Google 계정으로 로그인하면 커리어 모드 자산이 클라우드에 저장됩니다.';
      statusEl.style.color = '#94a3b8';
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
    const statusEl = document.getElementById('sbLoginStatusMsg');

    if (!window.sbClient) {
      await initSupabaseAuth();
    }

    if (!window.sbClient) {
      if (statusEl) {
        statusEl.textContent = `Supabase 연결 오류: ${lastInitError || '클라이언트 초기화에 실패했습니다.'}`;
        statusEl.style.color = '#fca5a5';
      }
      return;
    }

    try {
      sessionStorage.setItem('cg_pending_career', '1');
    } catch (e) {}

    try {
      const { error } = await window.sbClient.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: window.location.href
        }
      });
      if (error) throw error;
    } catch (err) {
      const msg = err && err.message ? err.message : String(err);
      if (statusEl) {
        statusEl.textContent = `Google 로그인 오류: ${msg}`;
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
