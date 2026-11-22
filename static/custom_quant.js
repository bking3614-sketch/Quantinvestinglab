/**
 * custom_quant.js - 사용자 정의 퀀트 (Quantus 스타일) 대시보드 모듈
 * 
 * 주요 기능:
 * 1. 국가별 시장 동적 전환 (한국 선택 시 KOSPI/KOSDAQ 표시)
 * 2. 커스텀 필터 행 동적 추가 및 삭제
 * 3. 5개 카테고리 팩터 선택 및 오름차순(저평가)/내림차순(고수익) 토글
 * 4. 조건 종목 스크리닝 API 연동 및 테이블 렌더링
 * 5. 전략 백테스트 실행 API 연동, KPI 카드 및 Chart.js 누적수익률 차트 렌더링
 */

(function () {
  'use strict';

  // ─────────────────────────────────────────────────────────────
  // 1. 상태 및 상수 관리
  // ─────────────────────────────────────────────────────────────
  const state = {
    country: 'KR',
    market: 'ALL',
    weightMethod: 'EQUAL',
    activeFactorCategory: 'PRICE',
    chartInstance: null
  };

  // 팩터 카테고리별 기본 정렬 방향
  const DEFAULT_FACTOR_DIRECTIONS = {
    PER: 'ASC',
    PBR: 'ASC',
    PSR: 'ASC',
    PCR: 'ASC',
    DIV_YIELD: 'DESC',
    EV_EBITDA: 'ASC',
    EV_EBIT: 'ASC',
    EV_SALES: 'ASC',
    EV_FCF: 'ASC',
    ROE: 'DESC',
    ROA: 'DESC',
    OP_MARGIN: 'DESC',
    DEBT_RATIO: 'ASC',
    CURRENT_RATIO: 'DESC',
    MOM_1M: 'DESC',
    MOM_3M: 'DESC',
    MOM_6M: 'DESC',
    MOM_12M: 'DESC',
    HIGH_52W: 'DESC',
    REV_GROWTH: 'DESC',
    OP_GROWTH: 'DESC',
    NET_GROWTH: 'DESC'
  };

  // ─────────────────────────────────────────────────────────────
  // 2. DOM 요소 캐싱
  // ─────────────────────────────────────────────────────────────
  let dom = {};

  function initDomReferences() {
    dom = {
      countryGroup: document.getElementById('cqCountryGroup'),
      marketGroup: document.getElementById('cqMarketGroup'),
      industrySelect: document.getElementById('cqIndustrySelect'),
      filterNoFinance: document.getElementById('cqFilterNoFinance'),
      filterNoHolding: document.getElementById('cqFilterNoHolding'),
      filterNoManaged: document.getElementById('cqFilterNoManaged'),
      filterNoDeficitQuarter: document.getElementById('cqFilterNoDeficitQuarter'),
      filterNoDeficitAnnual: document.getElementById('cqFilterNoDeficitAnnual'),
      filterNoChinese: document.getElementById('cqFilterNoChinese'),
      filterSmallCapOnly: document.getElementById('cqFilterSmallCapOnly'),
      btnAddFilter: document.getElementById('cqBtnAddFilter'),
      filterList: document.getElementById('cqFilterList'),
      weightGroup: document.getElementById('cqWeightGroup'),
      weightDynamicBtn: document.getElementById('cqWeightDynamicBtn'),
      weightOptimizeBtn: document.getElementById('cqWeightOptimizeBtn'),
      dynamicWeightBox: document.getElementById('cqDynamicWeightBox'),
      optimizeWeightBox: document.getElementById('cqOptimizeWeightBox'),
      optObjectiveSelect: document.getElementById('cqOptObjectiveSelect'),
      optLookback: document.getElementById('cqOptLookback'),
      optMinWeight: document.getElementById('cqOptMinWeight'),
      optMaxWeight: document.getElementById('cqOptMaxWeight'),
      optLambda: document.getElementById('cqOptLambda'),
      optLambdaVal: document.getElementById('cqOptLambdaVal'),
      optEta: document.getElementById('cqOptEta'),
      optEtaVal: document.getElementById('cqOptEtaVal'),
      optShrinkage: document.getElementById('cqOptShrinkage'),
      optFlipNegativeIC: document.getElementById('cqOptFlipNegativeIC'),
      dynamicMethodSelect: document.getElementById('cqDynamicMethodSelect'),
      manualWeightSection: document.getElementById('cqManualWeightSection'),
      manualWeightList: document.getElementById('cqManualWeightList'),
      manualWeightSumBadge: document.getElementById('cqManualWeightSumBadge'),
      autoDynamicSection: document.getElementById('cqAutoDynamicSection'),
      dynamicLookback: document.getElementById('cqDynamicLookback'),
      dynamicUnit: document.getElementById('cqDynamicUnit'),
      dynamicLambda: document.getElementById('cqDynamicLambda'),
      dynamicLambdaVal: document.getElementById('cqDynamicLambdaVal'),
      factorCatNav: document.getElementById('cqFactorCatNav'),
      factorPool: document.getElementById('cqFactorPool'),
      factorWeightsCard: document.getElementById('cqFactorWeightsCard'),
      factorWeightsList: document.getElementById('cqFactorWeightsList'),
      factorWeightsModeBadge: document.getElementById('cqFactorWeightsModeBadge'),
      startDate: document.getElementById('cqStartDate'),
      endDate: document.getElementById('cqEndDate'),
      benchmarkSelect: document.getElementById('cqBenchmarkSelect'),
      chartTitleText: document.getElementById('cqChartTitleText'),
      initCapital: document.getElementById('cqInitCapital'),
      rebalance: document.getElementById('cqRebalance'),
      topN: document.getElementById('cqTopN'),
      costRate: document.getElementById('cqCostRate'),
      btnRunScreen: document.getElementById('cqBtnRunScreen'),
      btnRunBacktest: document.getElementById('cqBtnRunBacktest'),
      kpiFinalWealth: document.getElementById('cqKpiFinalWealth'),
      kpiTotalReturn: document.getElementById('cqKpiTotalReturn'),
      kpiCAGR: document.getElementById('cqKpiCAGR'),
      kpiMDD: document.getElementById('cqKpiMDD'),
      kpiSharpe: document.getElementById('cqKpiSharpe'),
      kpiMAR: document.getElementById('cqKpiMAR'),
      chartCanvas: document.getElementById('customQuantChart'),
      screeningCount: document.getElementById('cqScreeningCount'),
      tableBody: document.getElementById('cqScreeningTableBody'),
      loadingOverlay: document.getElementById('loadingOverlay'),
      loadingText: document.getElementById('loadingText'),
      statusBanner: document.getElementById('cqStatusBanner'),
      statusBannerMsg: document.getElementById('cqStatusBannerMsg'),
      statusBannerIcon: document.getElementById('cqStatusBannerIcon'),
      statusBannerClose: document.getElementById('cqStatusBannerClose')
    };
  }

  // ─────────────────────────────────────────────────────────────
  // 3. UI 헬퍼 함수
  // ─────────────────────────────────────────────────────────────
  let bannerTimeout = null;
  function showStatusBanner(msg, type = 'error') {
    if (!dom.statusBanner || !dom.statusBannerMsg) return;
    if (bannerTimeout) clearTimeout(bannerTimeout);

    dom.statusBannerMsg.textContent = msg;
    dom.statusBanner.style.display = 'flex';

    if (type === 'error') {
      dom.statusBanner.style.background = 'rgba(239, 68, 68, 0.15)';
      dom.statusBanner.style.borderColor = 'rgba(239, 68, 68, 0.4)';
      dom.statusBanner.style.color = '#fca5a5';
      if (dom.statusBannerIcon) dom.statusBannerIcon.className = 'fa-solid fa-triangle-exclamation';
    } else if (type === 'warning') {
      dom.statusBanner.style.background = 'rgba(245, 158, 11, 0.15)';
      dom.statusBanner.style.borderColor = 'rgba(245, 158, 11, 0.4)';
      dom.statusBanner.style.color = '#fcd34d';
      if (dom.statusBannerIcon) dom.statusBannerIcon.className = 'fa-solid fa-circle-exclamation';
    } else {
      dom.statusBanner.style.background = 'rgba(16, 185, 129, 0.15)';
      dom.statusBanner.style.borderColor = 'rgba(16, 185, 129, 0.4)';
      dom.statusBanner.style.color = '#6ee7b7';
      if (dom.statusBannerIcon) dom.statusBannerIcon.className = 'fa-solid fa-circle-check';
    }

    bannerTimeout = setTimeout(() => {
      hideStatusBanner();
    }, 8000);
  }

  function hideStatusBanner() {
    if (dom.statusBanner) {
      dom.statusBanner.style.display = 'none';
    }
  }

  function showLoading(msg) {
    if (dom.loadingOverlay) {
      if (dom.loadingText) dom.loadingText.textContent = msg || '데이터 연산 중...';
      dom.loadingOverlay.classList.add('active');
    }
  }

  function hideLoading() {
    if (dom.loadingOverlay) {
      dom.loadingOverlay.classList.remove('active');
    }
  }

  function setButtonLoading(btn, isLoading, loadingText) {
    if (!btn) return;
    if (isLoading) {
      btn.disabled = true;
      btn.dataset.origHtml = btn.innerHTML;
      btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${loadingText || '연산 중...'}`;
    } else {
      btn.disabled = false;
      if (btn.dataset.origHtml) {
        btn.innerHTML = btn.dataset.origHtml;
      }
    }
  }

  function formatCurrency(val, country) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    const num = Math.round(Number(val));
    if (country === 'US') {
      return '$ ' + num.toLocaleString();
    }
    return '₩ ' + num.toLocaleString();
  }

  function formatCap(cap, country) {
    if (!cap || isNaN(cap) || cap <= 0) return '-';
    if (country === 'KR') {
      if (cap >= 1e12) {
        return (cap / 1e12).toFixed(1) + '조원';
      } else if (cap >= 1e8) {
        return Math.round(cap / 1e8).toLocaleString() + '억원';
      }
      return Number(cap).toLocaleString() + '원';
    } else {
      if (cap >= 1e9) {
        return '$' + (cap / 1e9).toFixed(1) + 'B';
      } else if (cap >= 1e6) {
        return '$' + (cap / 1e6).toFixed(1) + 'M';
      }
      return '$' + Number(cap).toLocaleString();
    }
  }

  function formatNumber(val, decimals = 2) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    return Number(val).toFixed(decimals);
  }

  function formatPercent(val) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    const n = Number(val);
    return (n >= 0 ? '+' : '') + n.toFixed(1) + '%';
  }

  function normalizeCountryCode(c) {
    if (!c) return 'KR';
    const s = String(c).trim();
    if (['KR', '한국', '대한민국', 'KOREA', 'Korea', 'kor'].includes(s) || s.includes('한국')) return 'KR';
    if (['US', '미국', 'USA', 'United States'].includes(s) || s.includes('미국')) return 'US';
    if (['JP', '일본', 'JAPAN', 'Japan'].includes(s) || s.includes('일본')) return 'JP';
    if (['HK', '홍콩', 'HONG KONG', 'Hong Kong', 'HongKong'].includes(s) || s.includes('홍콩')) return 'HK';
    return s.toUpperCase();
  }

  function isAllIndustry(ind) {
    if (!ind) return true;
    const s = String(ind).trim().toLowerCase();
    if (s === '' || s === 'all' || s === '전체' || s === 'none' || s === 'null') return true;
    if (s.includes('전체')) return true;
    return false;
  }

  // ─────────────────────────────────────────────────────────────
  // 4. 국가 및 시장 선택 로직
  // ─────────────────────────────────────────────────────────────
  function setupCountryAndMarket() {
    if (!dom.countryGroup || !dom.marketGroup) return;

    function updateMarketVisibility(country) {
      let isCurrentMarketVisible = false;

      dom.marketGroup.querySelectorAll('.cq-pill-btn').forEach(btn => {
        const forCountry = btn.dataset.forCountry;
        const marketVal = btn.dataset.market || 'ALL';

        if (marketVal === 'ALL') {
          btn.style.display = '';
          if (state.market === 'ALL') isCurrentMarketVisible = true;
        } else if (forCountry === country) {
          btn.style.display = '';
          if (state.market === marketVal) isCurrentMarketVisible = true;
        } else {
          btn.style.display = 'none';
        }
      });

      // 현재 선택된 시장이 숨겨졌으면 'ALL'로 리셋
      if (!isCurrentMarketVisible) {
        state.market = 'ALL';
        dom.marketGroup.querySelectorAll('.cq-pill-btn').forEach(btn => {
          btn.classList.toggle('active', (btn.dataset.market || 'ALL') === 'ALL');
        });
      }
    }

    // 국가 버튼 클릭
    dom.countryGroup.querySelectorAll('.cq-pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        dom.countryGroup.querySelectorAll('.cq-pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.country = normalizeCountryCode(btn.dataset.country || 'KR');
        updateMarketVisibility(state.country);
      });
    });

    // 시장 버튼 클릭
    dom.marketGroup.querySelectorAll('.cq-pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        dom.marketGroup.querySelectorAll('.cq-pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.market = btn.dataset.market || 'ALL';
      });
    });

    // 초기 표시 상태 적용
    updateMarketVisibility(state.country);
  }

  // ─────────────────────────────────────────────────────────────
  // 5. 커스텀 필터 동적 추가 / 삭제 로직
  // ─────────────────────────────────────────────────────────────
  function createFilterRow(metric = 'PER', op = 'LTE', val = '20') {
    const row = document.createElement('div');
    row.className = 'cq-filter-row';

    row.innerHTML = `
      <select class="cq-select cq-filter-metric">
        <option value="PER" ${metric === 'PER' ? 'selected' : ''}>PER</option>
        <option value="PBR" ${metric === 'PBR' ? 'selected' : ''}>PBR</option>
        <option value="PCR" ${metric === 'PCR' ? 'selected' : ''}>PCR</option>
        <option value="PSR" ${metric === 'PSR' ? 'selected' : ''}>PSR</option>
        <option value="ROE" ${metric === 'ROE' ? 'selected' : ''}>ROE (%)</option>
        <option value="ROA" ${metric === 'ROA' ? 'selected' : ''}>ROA (%)</option>
        <option value="OP_MARGIN" ${metric === 'OP_MARGIN' ? 'selected' : ''}>영업이익률 (%)</option>
        <option value="EV_EBITDA" ${metric === 'EV_EBITDA' ? 'selected' : ''}>EV/EBITDA</option>
        <option value="DEBT_RATIO" ${metric === 'DEBT_RATIO' ? 'selected' : ''}>부채비율 (%)</option>
        <option value="MOM_12M" ${metric === 'MOM_12M' ? 'selected' : ''}>12M 모멘텀 (%)</option>
        <option value="DIV_YIELD" ${metric === 'DIV_YIELD' ? 'selected' : ''}>배당수익률 (%)</option>
      </select>
      <select class="cq-select cq-filter-op" style="width: 80px;">
        <option value="LTE" ${op === 'LTE' ? 'selected' : ''}>&le;</option>
        <option value="GTE" ${op === 'GTE' ? 'selected' : ''}>&ge;</option>
        <option value="LT" ${op === 'LT' ? 'selected' : ''}>&lt;</option>
        <option value="GT" ${op === 'GT' ? 'selected' : ''}>&gt;</option>
        <option value="BETWEEN" ${op === 'BETWEEN' ? 'selected' : ''}>범위</option>
      </select>
      <input type="number" class="cq-input cq-filter-val" value="${val}" step="0.1" placeholder="값">
      <button type="button" class="cq-btn-icon-del" title="삭제"><i class="fa-solid fa-xmark"></i></button>
    `;

    // 삭제 버튼 리스너
    row.querySelector('.cq-btn-icon-del').addEventListener('click', () => {
      row.remove();
    });

    return row;
  }

  function setupCustomFilters() {
    if (!dom.btnAddFilter || !dom.filterList) return;

    // 기존에 HTML에 하드코딩된 삭제 버튼들에 이벤트 연결
    dom.filterList.querySelectorAll('.cq-filter-row .cq-btn-icon-del').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const row = e.target.closest('.cq-filter-row');
        if (row) row.remove();
      });
    });

    // 필터 추가 버튼 클릭
    dom.btnAddFilter.addEventListener('click', () => {
      const newRow = createFilterRow('PER', 'LTE', '15');
      dom.filterList.appendChild(newRow);
      // 포커스 이동
      const input = newRow.querySelector('.cq-filter-val');
      if (input) input.focus();
    });
  }

  // ─────────────────────────────────────────────────────────────
  // 6. 팩터 카테고리 탭 & 팩터 태그 선택 및 방향 토글 로직
  // ─────────────────────────────────────────────────────────────
  function setupFactorSelection() {
    if (!dom.factorCatNav || !dom.factorPool) return;

    // 카테고리 탭 전환
    dom.factorCatNav.querySelectorAll('.cq-factor-cat-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        dom.factorCatNav.querySelectorAll('.cq-factor-cat-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        const cat = btn.dataset.cat || 'PRICE';
        state.activeFactorCategory = cat;

        // 해당 카테고리 태그만 노출
        dom.factorPool.querySelectorAll('.cq-factor-tag').forEach(tag => {
          if (tag.dataset.cat === cat) {
            tag.style.display = 'inline-flex';
          } else {
            tag.style.display = 'none';
          }
        });
      });
    });

    // 팩터 태그 클릭 (선택 추가 / 방향 토글 / 선택 해제)
    dom.factorPool.querySelectorAll('.cq-factor-tag').forEach(tag => {
      tag.addEventListener('click', (e) => {
        const isSelected = tag.classList.contains('selected');
        let currentDir = tag.dataset.direction || DEFAULT_FACTOR_DIRECTIONS[tag.dataset.factor] || 'DESC';
        let orderBadge = tag.querySelector('.order-badge');

        if (!isSelected) {
          // 1) 미선택 -> 선택
          tag.classList.add('selected');
          tag.dataset.direction = currentDir;
          if (orderBadge) {
            orderBadge.innerHTML = currentDir === 'ASC' ? '오름차순 &darr;' : '내림차순 &uarr;';
          }
        } else {
          // 2) 이미 선택된 상태: 클릭 시 오름차순 <-> 내림차순 토글
          // 만약 Alt 또는 Shift 키를 누르고 클릭했거나, 2회 토글 후 3회차 클릭 시 해제 지원
          if (e.altKey || e.shiftKey) {
            tag.classList.remove('selected');
            return;
          }

          const nextDir = currentDir === 'ASC' ? 'DESC' : 'ASC';
          tag.dataset.direction = nextDir;
          if (orderBadge) {
            orderBadge.innerHTML = nextDir === 'ASC' ? '오름차순 &darr;' : '내림차순 &uarr;';
          }
        }

        // 수동 비중 모드 활성화 시 입력칸 실시간 동기화
        if (state.weightMethod === 'DYNAMIC' && dom.dynamicMethodSelect && dom.dynamicMethodSelect.value === 'manual') {
          renderManualWeightInputs();
        }
      });

      // 우클릭 시 선택 해제 지원
      tag.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        tag.classList.remove('selected');
        if (state.weightMethod === 'DYNAMIC' && dom.dynamicMethodSelect && dom.dynamicMethodSelect.value === 'manual') {
          renderManualWeightInputs();
        }
      });
    });
  }

  // ─────────────────────────────────────────────────────────────
  // 6-1. 가변 비중 (Dynamic Factor Weighting) 설정 모듈
  // ─────────────────────────────────────────────────────────────
  const FACTOR_LABEL_MAP = {
    'per': 'PER',
    'pbr': 'PBR',
    'psr': 'PSR',
    'pcr': 'PCR',
    'por': 'POR',
    'pfcr': 'PFCR',
    'prr': 'PRR',
    'pgpr': 'PGPR',
    'peg': 'PEG',
    'ncav': 'NCAV',
    'ncav_ratio': 'NCAV',
    'shareholder_yield': '주주수익률',
    'dividend_yield': '배당수익률',
    'ev_ebitda': 'EV/EBITDA',
    'ev_ebit': 'EV/EBIT',
    'ev_sales': 'EV/Sales',
    'ev_fcf': 'EV/FCF',
    'roe': 'ROE',
    'roa': 'ROA',
    'roic': 'ROIC',
    'gpa': 'GP/A',
    'f_score': 'F-Score',
    'altman_z': 'Altman Z',
    'operating_margin': '영업이익률',
    'net_margin': '순이익률',
    'debt_ratio': '부채비율',
    'current_ratio': '유동비율',
    'momentum_1m': '1M 모멘텀',
    'momentum_3m': '3M 모멘텀',
    'momentum_6m': '6M 모멘텀',
    'momentum_12m': '12M 모멘텀',
    'high_52w': '52주 신고가',
    'high_52w_ratio': '52주 신고가',
    'rsi_14': 'RSI(14)',
    'volatility': '변동성',
    'sharpe': '샤프비율',
    'sortino': '소르티노',
    'beta': '베타',
    'rev_growth': '매출증가율',
    'op_growth': '영업이익증가율',
    'net_growth': '순이익증가율',
    'foreign_holding_ratio': '외인소진율',
    'foreign_net_buy_20d': '외인순매수',
    'inst_net_buy_20d': '기관순매수',
    'retail_net_buy_20d': '개인순매수'
  };

  function setupDynamicWeight() {
    if (!dom.weightGroup) return;

    // 비중 모드 버튼 (동일 비중 vs 가변 비중 vs 최적화 비중) 클릭 이벤트
    dom.weightGroup.querySelectorAll('.cq-pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        if (btn.classList.contains('disabled')) return;

        dom.weightGroup.querySelectorAll('.cq-pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        const weightMode = (btn.dataset.weight || 'EQUAL').toUpperCase();
        state.weightMethod = weightMode;

        if (weightMode === 'OPTIMIZE') {
          if (dom.optimizeWeightBox) dom.optimizeWeightBox.style.display = 'flex';
          if (dom.dynamicWeightBox) dom.dynamicWeightBox.style.display = 'none';
        } else if (weightMode === 'DYNAMIC') {
          if (dom.dynamicWeightBox) dom.dynamicWeightBox.style.display = 'flex';
          if (dom.optimizeWeightBox) dom.optimizeWeightBox.style.display = 'none';
          updateDynamicWeightUI();
        } else {
          if (dom.dynamicWeightBox) dom.dynamicWeightBox.style.display = 'none';
          if (dom.optimizeWeightBox) dom.optimizeWeightBox.style.display = 'none';
        }
      });
    });

    // 방식 선택 드롭다운 변경 이벤트
    if (dom.dynamicMethodSelect) {
      dom.dynamicMethodSelect.addEventListener('change', () => {
        updateDynamicWeightUI();
      });
    }

    // 가변 강도 람다(lambda) 슬라이더 이벤트
    if (dom.dynamicLambda && dom.dynamicLambdaVal) {
      dom.dynamicLambda.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        dom.dynamicLambdaVal.textContent = isNaN(val) ? '0.50' : val.toFixed(2);
      });
    }

    // 최적화 중복·상관 억제 람다(lambda) 슬라이더 이벤트
    if (dom.optLambda && dom.optLambdaVal) {
      dom.optLambda.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        dom.optLambdaVal.textContent = isNaN(val) ? '0.50' : val.toFixed(2);
      });
    }

    // 최적화 비중 급변 억제 에타(eta) 슬라이더 이벤트
    if (dom.optEta && dom.optEtaVal) {
      dom.optEta.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        dom.optEtaVal.textContent = isNaN(val) ? '0.10' : val.toFixed(2);
      });
    }
  }

  function updateDynamicWeightUI() {
    const method = dom.dynamicMethodSelect ? dom.dynamicMethodSelect.value : 'momentum';
    if (method === 'manual') {
      if (dom.manualWeightSection) dom.manualWeightSection.style.display = 'flex';
      if (dom.autoDynamicSection) dom.autoDynamicSection.style.display = 'none';
      renderManualWeightInputs();
    } else {
      if (dom.manualWeightSection) dom.manualWeightSection.style.display = 'none';
      if (dom.autoDynamicSection) dom.autoDynamicSection.style.display = 'block';
    }
  }

  function renderManualWeightInputs() {
    if (!dom.manualWeightList) return;

    const factors = collectSelectedFactors();
    if (!factors || factors.length === 0) {
      dom.manualWeightList.innerHTML = `
        <div style="font-size: 0.78rem; color: #94a3b8; padding: 6px;">
          선택된 팩터가 없습니다. 위 팩터 카테고리에서 팩터를 선택해 주세요.
        </div>
      `;
      if (dom.manualWeightSumBadge) dom.manualWeightSumBadge.textContent = '합계: 0%';
      return;
    }

    const defaultPct = Math.floor(100 / factors.length);
    let remainder = 100 - (defaultPct * factors.length);

    // 기존 입력된 값 보존
    const currentValues = {};
    dom.manualWeightList.querySelectorAll('.cq-manual-weight-input').forEach(inp => {
      const f = inp.dataset.factor;
      if (f) currentValues[f] = parseFloat(inp.value);
    });

    const rowsHtml = factors.map((f, idx) => {
      const metric = f.metric;
      const label = FACTOR_LABEL_MAP[metric] || metric.toUpperCase();
      let initVal = currentValues[metric];
      if (initVal === undefined || isNaN(initVal)) {
        initVal = defaultPct + (idx === 0 ? remainder : 0);
      }

      return `
        <div class="cq-manual-weight-row">
          <span class="cq-manual-weight-name">
            <i class="fa-solid fa-cube text-primary" style="font-size: 0.7rem;"></i>
            ${label}
          </span>
          <div class="cq-manual-weight-input-wrap">
            <input type="number" class="cq-manual-weight-input" data-factor="${metric}" value="${initVal}" min="0" max="100" step="1">
            <span class="cq-manual-weight-unit">%</span>
          </div>
        </div>
      `;
    }).join('');

    dom.manualWeightList.innerHTML = rowsHtml;

    dom.manualWeightList.querySelectorAll('.cq-manual-weight-input').forEach(inp => {
      inp.addEventListener('input', updateManualWeightSum);
    });

    updateManualWeightSum();
  }

  function updateManualWeightSum() {
    if (!dom.manualWeightList || !dom.manualWeightSumBadge) return;
    let total = 0;
    dom.manualWeightList.querySelectorAll('.cq-manual-weight-input').forEach(inp => {
      const val = parseFloat(inp.value);
      if (!isNaN(val)) total += val;
    });

    dom.manualWeightSumBadge.textContent = `합계: ${Math.round(total)}%`;
    if (Math.abs(total - 100) < 0.1) {
      dom.manualWeightSumBadge.classList.remove('invalid');
    } else {
      dom.manualWeightSumBadge.classList.add('invalid');
    }
  }

  function collectWeightConfig() {
    if (state.weightMethod === 'OPTIMIZE') {
      const obj = dom.optObjectiveSelect ? dom.optObjectiveSelect.value : 'ic_regularized';
      const lb = dom.optLookback ? dom.optLookback.value : '12M';
      const minW = dom.optMinWeight ? parseFloat(dom.optMinWeight.value) || 5.0 : 5.0;
      const maxW = dom.optMaxWeight ? parseFloat(dom.optMaxWeight.value) || 50.0 : 50.0;
      const lambdaV = dom.optLambda ? parseFloat(dom.optLambda.value) : 0.5;
      const etaV = dom.optEta ? parseFloat(dom.optEta.value) : 0.1;
      const shrink = dom.optShrinkage ? dom.optShrinkage.checked : true;
      const flipIC = dom.optFlipNegativeIC ? dom.optFlipNegativeIC.checked : false;

      return {
        weight_mode: 'optimize',
        optimize_weight_config: {
          objective: obj,
          lookback: lb,
          min_weight: minW,
          max_weight: maxW,
          lambda_val: isNaN(lambdaV) ? 0.5 : lambdaV,
          eta_val: isNaN(etaV) ? 0.1 : etaV,
          shrinkage: shrink,
          flip_negative_ic: flipIC
        }
      };
    }

    const isDynamic = state.weightMethod === 'DYNAMIC';
    const method = dom.dynamicMethodSelect ? dom.dynamicMethodSelect.value : 'momentum';
    const lookback = dom.dynamicLookback ? dom.dynamicLookback.value : '3M';
    const unit = dom.dynamicUnit ? dom.dynamicUnit.value : 'factor';
    const lambdaVal = dom.dynamicLambda ? parseFloat(dom.dynamicLambda.value) : 0.5;

    const manualWeights = {};
    if (method === 'manual' && dom.manualWeightList) {
      dom.manualWeightList.querySelectorAll('.cq-manual-weight-input').forEach(input => {
        const factorKey = input.dataset.factor;
        const val = parseFloat(input.value) || 0;
        manualWeights[factorKey] = val;
      });
    }

    return {
      weight_mode: isDynamic ? 'dynamic' : 'equal',
      dynamic_weight_config: {
        method: method,
        lookback: lookback,
        unit: unit,
        lambda_val: isNaN(lambdaVal) ? 0.5 : lambdaVal,
        manual_weights: manualWeights
      }
    };
  }

  function renderAppliedFactorWeights(appliedWeights, diagnostics) {
    if (!dom.factorWeightsCard || !dom.factorWeightsList) return;

    if (!appliedWeights || Object.keys(appliedWeights).length === 0) {
      dom.factorWeightsCard.style.display = 'none';
      return;
    }

    if (dom.factorWeightsModeBadge) {
      if (state.weightMethod === 'OPTIMIZE') {
        const objNames = {
          'ic_regularized': '정규화 예측력',
          'ic_prop': '예측력(IC) 비례',
          'ic_ir': '안정성(IR) 기반',
          'risk_parity': '위험균등(ERC)',
          'min_variance': '최소분산',
          'hrp': 'HRP 군집'
        };
        const objKey = diagnostics?.objective || (dom.optObjectiveSelect ? dom.optObjectiveSelect.value : 'ic_regularized');
        const objLabel = objNames[objKey] || objKey.toUpperCase();
        dom.factorWeightsModeBadge.textContent = `최적화 비중 (${objLabel})`;
        dom.factorWeightsModeBadge.style.background = 'rgba(168, 85, 247, 0.2)';
        dom.factorWeightsModeBadge.style.color = '#c084fc';
        dom.factorWeightsModeBadge.style.borderColor = 'rgba(168, 85, 247, 0.4)';
      } else if (state.weightMethod === 'DYNAMIC') {
        dom.factorWeightsModeBadge.textContent = '가변 비중 적용됨';
        dom.factorWeightsModeBadge.style.background = '';
        dom.factorWeightsModeBadge.style.color = '';
        dom.factorWeightsModeBadge.style.borderColor = '';
      } else {
        dom.factorWeightsModeBadge.textContent = '동일 비중 결합';
        dom.factorWeightsModeBadge.style.background = '';
        dom.factorWeightsModeBadge.style.color = '';
        dom.factorWeightsModeBadge.style.borderColor = '';
      }
    }

    let badgesHtml = Object.entries(appliedWeights).map(([metric, pct]) => {
      const label = FACTOR_LABEL_MAP[metric] || metric.toUpperCase();
      const pctVal = typeof pct === 'number' ? pct.toFixed(1) : pct;
      return `
        <span class="cq-factor-weight-pill">
          <strong>${label}</strong>
          <span class="weight-pct">${pctVal}%</span>
        </span>
      `;
    }).join('');

    // 최적화 진단 정보 (평균 Rank IC) 렌더링
    if (diagnostics && diagnostics.mean_rank_ic && Object.keys(diagnostics.mean_rank_ic).length > 0) {
      const icPills = Object.entries(diagnostics.mean_rank_ic).map(([metric, icVal]) => {
        const label = FACTOR_LABEL_MAP[metric] || metric.toUpperCase();
        const icNum = Number(icVal);
        const sign = icNum >= 0 ? '+' : '';
        const cls = icNum >= 0 ? 'positive' : 'negative';
        return `
          <span class="cq-opt-ic-pill ${cls}">
            <span>${label} IC:</span>
            <strong>${sign}${icNum.toFixed(3)}</strong>
          </span>
        `;
      }).join('');

      badgesHtml += `
        <div class="cq-opt-diag-container" style="width: 100%;">
          <div class="cq-opt-diag-header">
            <span><i class="fa-solid fa-chart-simple text-primary"></i> 팩터별 평균 Rank IC (예측력)</span>
          </div>
          <div class="cq-opt-diag-row">
            ${icPills}
          </div>
        </div>
      `;
    }

    // 최적화 대체 적용 안내 메시지가 있을 경우 배너 렌더링
    if (diagnostics && diagnostics.fallback_reason) {
      badgesHtml += `
        <div class="cq-fallback-banner" style="width: 100%;">
          <i class="fa-solid fa-triangle-exclamation"></i>
          <span>${diagnostics.fallback_reason}</span>
        </div>
      `;
      showStatusBanner(diagnostics.fallback_reason, 'warning');
    }

    dom.factorWeightsList.innerHTML = badgesHtml;
    dom.factorWeightsCard.style.display = 'flex';
  }

  // ─────────────────────────────────────────────────────────────
  // 7. 필터 및 팩터 데이터 수집
  // ─────────────────────────────────────────────────────────────
  function collectGeneralFilters() {
    return {
      exclude_financials: !!dom.filterNoFinance?.checked,
      exclude_holding: !!dom.filterNoHolding?.checked,
      exclude_administrative: !!dom.filterNoManaged?.checked,
      exclude_loss: !!dom.filterNoDeficitQuarter?.checked || !!dom.filterNoDeficitAnnual?.checked,
      exclude_china: !!dom.filterNoChinese?.checked,
      small_cap_bottom_20: !!dom.filterSmallCapOnly?.checked
    };
  }

  function collectCustomFilters() {
    if (!dom.filterList) return [];
    const filters = [];
    const opMap = {
      'LTE': '<=',
      'GTE': '>=',
      'LT': '<',
      'GT': '>',
      'BETWEEN': 'range'
    };

    dom.filterList.querySelectorAll('.cq-filter-row').forEach(row => {
      const metricEl = row.querySelector('.cq-filter-metric');
      const opEl = row.querySelector('.cq-filter-op');
      const valEl = row.querySelector('.cq-filter-val');

      if (!metricEl || !opEl || !valEl) return;
      const metric = metricEl.value.toLowerCase();
      const rawOp = opEl.value;
      const op = opMap[rawOp] || '<=';
      const val = parseFloat(valEl.value);

      if (isNaN(val)) return;

      if (op === 'range') {
        filters.push({
          metric: metric,
          operator: 'range',
          min: Math.min(val * 0.5, val),
          max: Math.max(val * 1.5, val)
        });
      } else {
        filters.push({
          metric: metric,
          operator: op,
          value: val
        });
      }
    });

    return filters;
  }

  function collectSelectedFactors() {
    if (!dom.factorPool) return [{ metric: 'momentum_12m', direction: 'desc' }];
    const factors = [];

    const factorKeyMap = {
      'PER': 'per',
      'PBR': 'pbr',
      'PSR': 'psr',
      'PCR': 'pcr',
      'DIV_YIELD': 'dividend_yield',
      'EV_EBITDA': 'ev_ebitda',
      'EV_EBIT': 'ev_ebit',
      'EV_SALES': 'ev_sales',
      'EV_FCF': 'ev_fcf',
      'ROE': 'roe',
      'ROA': 'roa',
      'OP_MARGIN': 'operating_margin',
      'DEBT_RATIO': 'debt_ratio',
      'CURRENT_RATIO': 'current_ratio',
      'MOM_1M': 'momentum_1m',
      'MOM_3M': 'momentum_3m',
      'MOM_6M': 'momentum_6m',
      'MOM_12M': 'momentum_12m',
      'HIGH_52W': 'high_52w',
      'REV_GROWTH': 'rev_growth',
      'OP_GROWTH': 'op_growth',
      'NET_GROWTH': 'net_growth'
    };

    dom.factorPool.querySelectorAll('.cq-factor-tag.selected').forEach(tag => {
      const rawFactor = tag.dataset.factor;
      const metric = factorKeyMap[rawFactor] || rawFactor.toLowerCase();
      const direction = (tag.dataset.direction || DEFAULT_FACTOR_DIRECTIONS[rawFactor] || 'DESC').toLowerCase();

      factors.push({
        metric: metric,
        direction: direction
      });
    });

    if (factors.length === 0) {
      factors.push({ metric: 'per', direction: 'asc' });
      factors.push({ metric: 'roe', direction: 'desc' });
    }

    return factors;
  }

  // ─────────────────────────────────────────────────────────────
  // 8. 종목 스크리닝 API 연동 및 테이블 렌더링
  // ─────────────────────────────────────────────────────────────
  async function runScreening() {
    const rawIndustryVal = dom.industrySelect ? dom.industrySelect.value : 'ALL';
    const isAll = isAllIndustry(rawIndustryVal);
    const topN = parseInt(dom.topN?.value || '20', 10);
    const normCountry = normalizeCountryCode(state.country);

    const weightCfg = collectWeightConfig();

    const payload = {
      country: normCountry,
      market: state.market,
      industry: isAll ? null : rawIndustryVal,
      industry_filter: isAll ? [] : [rawIndustryVal],
      general_filters: collectGeneralFilters(),
      custom_filters: collectCustomFilters(),
      factors: collectSelectedFactors(),
      top_n: topN,
      ...weightCfg
    };

    setButtonLoading(dom.btnRunScreen, true, '스크리닝 중...');
    showLoading(`[${normCountry}] 조건 종목 스크리닝 및 팩터 랭킹 연산 중...`);
    hideStatusBanner();

    try {
      const response = await fetch('/api/custom_quant/screen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.message || `서버 에러 (${response.status})`);
      }

      const res = await response.json();
      if (res.status === 'error') {
        throw new Error(res.message || '종목 스크리닝 실패');
      }
      const stockList = res.results || res.stocks || [];

      if (stockList.length === 0) {
        const diagMsg = res.message || (res.diagnostic && res.diagnostic.message) || '';
        showStatusBanner(`[${normCountry}] 조건에 부합하는 종목이 없습니다. ${diagMsg} 필터(금융주/지주사/중국기업 제외 등)를 완화해 보세요.`, 'warning');
      } else {
        showStatusBanner(`[${normCountry}] ${stockList.length}개 종목 스크리닝이 완료되었습니다.`, 'success');
      }

      renderScreeningTable(stockList);
      renderAppliedFactorWeights(res.applied_factor_weights, res.optimization_diagnostics);

    } catch (err) {
      console.error('[Custom Quant] 스크리닝 실패:', err);
      showStatusBanner(`종목 스크리닝 실패: ${err.message}`, 'error');
      alert(`종목 스크리닝 중 오류가 발생했습니다: ${err.message}`);
      if (dom.tableBody) {
        dom.tableBody.innerHTML = `
          <tr>
            <td colspan="10" style="text-align: center; color: #fca5a5; padding: 28px;">
              <i class="fa-solid fa-triangle-exclamation"></i> 종목 스크리닝 실패: ${err.message}
            </td>
          </tr>
        `;
      }
    } finally {
      hideLoading();
      setButtonLoading(dom.btnRunScreen, false);
    }
  }

  function renderScreeningTable(stocks) {
    if (!dom.tableBody) return;

    if (dom.screeningCount) {
      dom.screeningCount.textContent = `총 ${stocks.length}개 종목 편입`;
    }

    if (!stocks || stocks.length === 0) {
      dom.tableBody.innerHTML = `
        <tr>
          <td colspan="10" style="text-align: center; color: var(--text-secondary); padding: 30px;">
            설정된 필터 및 팩터 조건을 충족하는 종목이 없습니다. 필터 범위를 완화해 보세요.
          </td>
        </tr>
      `;
      return;
    }

    const rowsHtml = stocks.map((s, idx) => {
      const rank = s.rank || (idx + 1);
      const ticker = s.ticker || '-';
      const name = s.name || ticker;
      const industry = s.industry || s.sector || '-';

      // 복합 점수 (composite_score 또는 factors.composite_rank)
      let score = '-';
      if (s.composite_score !== undefined) {
        score = (Number(s.composite_score) * 100).toFixed(1);
      } else if (s.factors && s.factors.composite_rank !== undefined) {
        score = Number(s.factors.composite_rank).toFixed(1);
      }

      // 팩터 추출
      const per = s.per !== undefined ? s.per : (s.factors ? s.factors.per : null);
      const pbr = s.pbr !== undefined ? s.pbr : (s.factors ? s.factors.pbr : null);
      const roe = s.roe !== undefined ? s.roe : (s.factors ? s.factors.roe : null);
      const mom12m = s.momentum_12m !== undefined ? s.momentum_12m : (s.factors ? s.factors.momentum_12m : null);
      const marketCap = s.market_cap;

      return `
        <tr>
          <td style="font-weight: 700; color: #6366f1;">${rank}</td>
          <td><span class="cq-ticker-code">${ticker}</span></td>
          <td style="font-weight: 600;">${name}</td>
          <td style="color: var(--text-secondary); font-size: 0.8rem;">${industry}</td>
          <td><span class="cq-score-pill">${score}</span></td>
          <td>${formatNumber(per, 1)}</td>
          <td>${formatNumber(pbr, 2)}</td>
          <td class="${roe > 0 ? 'text-positive' : ''}">${formatPercent(roe)}</td>
          <td class="${mom12m > 0 ? 'text-positive' : (mom12m < 0 ? 'text-negative' : '')}">${formatPercent(mom12m)}</td>
          <td style="font-size: 0.8rem; color: #cbd5e1;">${formatCap(marketCap, state.country)}</td>
        </tr>
      `;
    }).join('');

    dom.tableBody.innerHTML = rowsHtml;
  }

  // ─────────────────────────────────────────────────────────────
  // 9. 전략 백테스트 API 연동, KPI 카드 및 차트 렌더링
  // ─────────────────────────────────────────────────────────────
  async function runBacktest() {
    const rawIndustryVal = dom.industrySelect ? dom.industrySelect.value : 'ALL';
    const isAll = isAllIndustry(rawIndustryVal);
    const topN = parseInt(dom.topN?.value || '20', 10);
    const costRateVal = parseFloat(dom.costRate?.value || '0.2');
    const normCountry = normalizeCountryCode(state.country);

    const weightCfg = collectWeightConfig();

    const payload = {
      country: normCountry,
      market: state.market,
      benchmark: document.getElementById('cqBenchmarkSelect')?.value || 'AUTO',
      industry: isAll ? null : rawIndustryVal,
      industry_filter: isAll ? [] : [rawIndustryVal],
      general_filters: collectGeneralFilters(),
      custom_filters: collectCustomFilters(),
      factors: collectSelectedFactors(),
      start_date: dom.startDate?.value || '2018-01-02',
      end_date: dom.endDate?.value || new Date().toISOString().split('T')[0],
      initial_capital: parseFloat(dom.initCapital?.value || '10000000'),
      rebalance_period: dom.rebalance?.value || 'Q',
      top_n: topN,
      num_holdings: topN,
      transaction_cost: costRateVal / 100.0,
      ...weightCfg
    };

    setButtonLoading(dom.btnRunBacktest, true, '백테스트 중...');
    showLoading(`[${normCountry}] 사용자 정의 퀀트 백테스트 시뮬레이션 실행 중...`);
    hideStatusBanner();

    try {
      const response = await fetch('/api/custom_quant/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.message || `백테스트 에러 (${response.status})`);
      }

      const res = await response.json();

      if (res.status === 'error') {
        throw new Error(res.message || '백테스트 실패');
      }

      // 1) KPI 카드 갱신
      renderKPIs(res, payload.initial_capital);

      // 2) Chart.js 수익률 차트 렌더링
      renderBacktestChart(res);

      // 3) 적용된 팩터 비중 배지 렌더링
      renderAppliedFactorWeights(res.latest_factor_weights || res.applied_factor_weights, res.optimization_diagnostics);

      // 3) 최신 편입 종목 목록이 함께 응답된 경우 테이블 자동 갱신
      if (res.latest_portfolio && Array.isArray(res.latest_portfolio) && res.latest_portfolio.length > 0) {
        renderScreeningTable(res.latest_portfolio);
      }

      showStatusBanner(`[${state.country}] 퀀트 전략 백테스트 완료! (CAGR: ${res.metrics?.cagr || 0}%, MDD: -${Math.abs(res.metrics?.mdd || 0)}%)`, 'success');

    } catch (err) {
      console.error('[Custom Quant] 백테스트 실패:', err);
      showStatusBanner(`백테스트 실행 실패: ${err.message}`, 'error');
      alert(`백테스트 실행 중 오류가 발생했습니다: ${err.message}`);
    } finally {
      hideLoading();
      setButtonLoading(dom.btnRunBacktest, false);
    }
  }

  function renderKPIs(res, initialCapital) {
    const metrics = res.metrics || {};

    // 1) 최종 자산 계산
    let finalWealth = 0;
    if (res.portfolio_curve && res.portfolio_curve.length > 0) {
      finalWealth = res.portfolio_curve[res.portfolio_curve.length - 1].value;
    } else if (metrics.total_return !== undefined) {
      finalWealth = initialCapital * (1 + metrics.total_return / 100);
    }

    if (dom.kpiFinalWealth) {
      dom.kpiFinalWealth.textContent = formatCurrency(finalWealth, state.country);
    }
    if (dom.kpiTotalReturn) {
      const totRet = metrics.total_return || 0;
      dom.kpiTotalReturn.textContent = `누적수익률 ${totRet >= 0 ? '+' : ''}${totRet.toFixed(1)}%`;
    }

    // 2) CAGR
    if (dom.kpiCAGR) {
      const cagr = metrics.cagr || 0;
      dom.kpiCAGR.textContent = `${cagr >= 0 ? '+' : ''}${cagr.toFixed(1)}%`;
      dom.kpiCAGR.className = `cq-kpi-value ${cagr >= 0 ? 'positive' : 'negative'}`;
    }

    // 3) MDD
    if (dom.kpiMDD) {
      const mdd = Math.abs(metrics.mdd || 0);
      dom.kpiMDD.textContent = `-${mdd.toFixed(1)}%`;
      dom.kpiMDD.className = 'cq-kpi-value negative';
    }

    // 4) Sharpe
    if (dom.kpiSharpe) {
      dom.kpiSharpe.textContent = (metrics.sharpe || 0).toFixed(2);
    }

    // 5) MAR
    if (dom.kpiMAR) {
      let mar = metrics.mar;
      if (mar === undefined || mar === null) {
        const cagr = metrics.cagr || 0;
        const mdd = Math.abs(metrics.mdd || 0);
        mar = mdd > 0 ? (cagr / mdd) : 0;
      }
      dom.kpiMAR.textContent = Number(mar).toFixed(2);
    }
  }

  function renderBacktestChart(res) {
    if (!dom.chartCanvas || typeof Chart === 'undefined') return;

    // 차트 데이터 추출
    let dates = [];
    let portfolioValues = [];
    let benchmarkValues = [];
    let isPercentMode = false;

    if (res.portfolio_curve && res.portfolio_curve.length > 0) {
      dates = res.portfolio_curve.map(pt => pt.date);
      portfolioValues = res.portfolio_curve.map(pt => pt.value);
      benchmarkValues = res.portfolio_curve.map(pt => pt.benchmark_value);
      isPercentMode = false;
    } else if (res.cumulative_returns && res.cumulative_returns.length > 0) {
      dates = res.cumulative_returns.map(pt => pt.date);
      portfolioValues = res.cumulative_returns.map(pt => pt.portfolio);
      benchmarkValues = res.cumulative_returns.map(pt => pt.benchmark);
      isPercentMode = true;
    } else {
      console.warn('[Custom Quant] 백테스트 차트 시계열 데이터가 없습니다.');
      return;
    }

    // 기존 인스턴스 파괴
    if (state.chartInstance) {
      state.chartInstance.destroy();
      state.chartInstance = null;
    }

    const ctx = dom.chartCanvas.getContext('2d');

    // 그라데이션 채우기 생성
    const gradient = ctx.createLinearGradient(0, 0, 0, 320);
    gradient.addColorStop(0, 'rgba(99, 102, 241, 0.35)');
    gradient.addColorStop(1, 'rgba(99, 102, 241, 0.0)');

    const rawBmLabel = res.benchmark_label || res.parameters?.benchmark_label || (state.country === 'KR' ? '한국 KOSPI (^KS11)' : '미국 S&P 500 (SPY 100%)');

    // 우측 차트 제목 동적 업데이트
    const chartTitleEl = dom.chartTitleText || document.getElementById('cqChartTitleText') || document.querySelector('.cq-chart-card .cq-chart-title span:last-child');
    if (chartTitleEl) {
      chartTitleEl.textContent = `포트폴리오 누적 자산 성장 추이 vs 벤치마크 (${rawBmLabel})`;
    }

    const benchmarkLegend = rawBmLabel.includes('벤치마크') ? rawBmLabel : `${rawBmLabel} (벤치마크)`;

    state.chartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: dates,
        datasets: [
          {
            label: '마법공식 전략',
            data: portfolioValues,
            borderColor: '#6366f1',
            backgroundColor: gradient,
            borderWidth: 2.2,
            fill: true,
            tension: 0.15,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: '#6366f1'
          },
          {
            label: benchmarkLegend,
            data: benchmarkValues,
            borderColor: '#94a3b8',
            borderWidth: 1.5,
            borderDash: [5, 5],
            fill: false,
            tension: 0.15,
            pointRadius: 0,
            pointHoverRadius: 4,
            pointHoverBackgroundColor: '#94a3b8'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: {
            display: true,
            position: 'top',
            labels: {
              color: '#cbd5e1',
              font: { family: 'inherit', size: 12, weight: '600' },
              boxWidth: 16,
              padding: 15
            }
          },
          tooltip: {
            backgroundColor: '#0f172a',
            titleColor: '#f8fafc',
            bodyColor: '#cbd5e1',
            borderColor: '#334155',
            borderWidth: 1,
            padding: 10,
            callbacks: {
              label: function (context) {
                const label = context.dataset.label || '';
                const val = context.parsed.y;
                if (isPercentMode) {
                  return `${label}: ${(val >= 0 ? '+' : '')}${val.toFixed(1)}%`;
                }
                if (state.country === 'KR') {
                  return `${label}: ₩ ${Math.round(val).toLocaleString()}`;
                }
                return `${label}: $ ${Math.round(val).toLocaleString()}`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: {
              color: 'rgba(255, 255, 255, 0.05)',
              drawBorder: false
            },
            ticks: {
              color: '#94a3b8',
              maxTicksLimit: 8,
              font: { size: 11 }
            }
          },
          y: {
            grid: {
              color: 'rgba(255, 255, 255, 0.06)',
              drawBorder: false
            },
            ticks: {
              color: '#94a3b8',
              font: { size: 11 },
              callback: function (val) {
                if (isPercentMode) return val + '%';
                if (state.country === 'KR') {
                  if (val >= 1e8) return (val / 1e8).toFixed(1) + '억';
                  if (val >= 1e4) return Math.round(val / 1e4) + '만';
                  return val.toLocaleString();
                }
                if (val >= 1e6) return '$' + (val / 1e6).toFixed(1) + 'M';
                if (val >= 1e3) return '$' + (val / 1e3).toFixed(0) + 'k';
                return '$' + val;
              }
            }
          }
        }
      }
    });
  }

  // ─────────────────────────────────────────────────────────────
  // 10. 초기화 실행
  // ─────────────────────────────────────────────────────────────
  function init() {
    initDomReferences();

    // 마법공식 탭의 종료일을 현재 최신 날짜로 자동 설정
    if (dom.endDate) {
      dom.endDate.value = new Date().toISOString().split('T')[0];
    }

    setupCountryAndMarket();
    setupCustomFilters();
    setupFactorSelection();
    setupDynamicWeight();

    if (dom.btnRunScreen) {
      dom.btnRunScreen.addEventListener('click', runScreening);
    }

    if (dom.btnRunBacktest) {
      dom.btnRunBacktest.addEventListener('click', runBacktest);
    }

    if (dom.statusBannerClose) {
      dom.statusBannerClose.addEventListener('click', hideStatusBanner);
    }

    // 전역 export (필요시 외부 호출 가능)
    window.customQuant = {
      runScreening,
      runBacktest,
      state
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
