/**
 * chart_game.js - 차트 트레이딩 게임 (Chart Trading Game) 프론트엔드 모듈
 * TradingView Lightweight Charts 기반 일봉/주봉/월봉 리샘플링 & 6대 보조지표 & 트레이딩 엔진
 */
(function () {
  'use strict';

  // ─────────────────────────────────────────────────────────────
  // 1. 게임 전역 상태 (Game State)
  // ─────────────────────────────────────────────────────────────
  const state = {
    initialized: false,
    chartCreated: false,
    mainChart: null,
    rsiChart: null,
    volumeChart: null,
    candlestickSeries: null,
    avgPriceLine: null,
    indicatorSeries: {},
    markers: [],

    // 캔들 시계열 데이터
    candles: [],         // 전체 일봉 원본 데이터 [{ date, open, high, low, close, volume }]
    startIdx: 0,         // 게임 시작 캔들 인덱스 (기본 >= 150)
    currentIdx: 0,       // 현재까지 공개된 캔들 인덱스
    maxTurns: 50,        // 총 진행 턴 수
    currentTurn: 0,      // 현재 진행 턴 (0 ~ maxTurns)
    timeframe: '1d',     // '1d', '1w', '1m'
    currency: 'KRW',     // 'KRW' 또는 'USD'
    tickerInfo: null,    // 게임 종료 후 공개할 실제 종목 메타데이터

    // 계좌 및 트레이딩 상태
    gameMode: 'practice', // 'practice' | 'career'
    gameEnded: false,
    pendingCareerEnter: false,
    initialCapital: 10000000,
    cash: 10000000,
    holdingQty: 0,
    avgBuyPrice: 0,
    trades: [],          // [{ turn, date, type: 'BUY'|'SELL', price, qty, amount, pnl }]
    orderRatio: 1.0,     // 0.1, 0.25, 0.5, 1.0 또는 직접 입력 비율
    orderMode: 'NORMAL', // 'NORMAL' 또는 'RR'
    rrTakeProfitPct: 10,
    rrStopLossPct: 5,
    activeRR: null,      // { tpPrice, slPrice, qty }

    // 6대 기술적 지표 설정
    indicators: {
      ma: {
        on: true,
        lines: [
          { period: 5, on: true, color: '#eab308' },
          { period: 20, on: true, color: '#ef4444' },
          { period: 60, on: true, color: '#10b981' },
          { period: 120, on: true, color: '#3b82f6' },
          { period: 240, on: false, color: '#a855f7' }
        ]
      },
      vol: { on: true, maPeriod: 20 },
      rsi: { on: true, period: 14, overbought: 70, oversold: 30 },
      env: { on: false, period: 20, ratio: 10, showUpper: true, showMid: true, showLower: true },
      st: { on: false, period: 10, multiplier: 3.0 },
      ichimoku: { on: false, conversion: 9, base: 26, spanB: 52 }
    },

    // 하단 인사이트 패널 상태 (재무제표 & 뉴스/시황)
    activeInsightTab: 'financials', // 'financials' | 'news'
    newsDays: 30,
    apiSettings: {
      llmProvider: 'gemini',
      llmApiKey: '',
      naverClientId: '',
      naverClientSecret: ''
    },
    lastFinKey: null,
    lastNewsKey: null,
    insightDebounceTimer: null
  };

  // DOM 캐시
  let dom = {};

  function initDom() {
    dom = {
      pane: document.getElementById('paneChartGame'),
      tickerInput: document.getElementById('cgTickerInput'),
      tickerDatalist: document.getElementById('cgTickerDatalist'),
      btnApplyTicker: document.getElementById('cgBtnApplyTicker'),
      loadingOverlay: document.getElementById('cgLoadingOverlay'),
      loadingText: document.getElementById('cgLoadingText'),
      quickTurnsGroup: document.getElementById('cgQuickTurnsGroup'),
      maxTurnsInput: document.getElementById('cgMaxTurnsInput'),
      timeframeGroup: document.getElementById('cgTimeframeGroup'),
      btnOpenIndicators: document.getElementById('cgBtnOpenIndicators'),
      btnNewGame: document.getElementById('cgBtnNewGame'),

      // 차트 컨테이너 (3-패널)
      mainChartEl: document.getElementById('cgMainChart'),
      rsiPane: document.getElementById('cgRsiPane'),
      rsiChartEl: document.getElementById('cgRsiChart'),
      rsiVal: document.getElementById('cgRsiVal'),
      rsiPeriodLabel: document.getElementById('cgRsiPeriodLabel'),
      volumePane: document.getElementById('cgVolumePane'),
      volumeChartEl: document.getElementById('cgVolumeChart'),
      volumeVal: document.getElementById('cgVolumeVal'),

      // 퀵 툴바 버튼들
      toolMa: document.getElementById('cgToolMa'),
      toolEnv: document.getElementById('cgToolEnv'),
      toolSt: document.getElementById('cgToolSt'),
      toolIchimoku: document.getElementById('cgToolIchimoku'),
      toolRsi: document.getElementById('cgToolRsi'),
      toolVol: document.getElementById('cgToolVol'),
      toolSettings: document.getElementById('cgToolSettings'),

      // 상단 오버레이 수치
      valDate: document.getElementById('cgValDate'),
      valOpen: document.getElementById('cgValOpen'),
      valHigh: document.getElementById('cgValHigh'),
      valLow: document.getElementById('cgValLow'),
      valClose: document.getElementById('cgValClose'),
      valChange: document.getElementById('cgValChange'),
      valVolume: document.getElementById('cgValVolume'),
      valMa5: document.getElementById('cgValMa5'),
      valMa20: document.getElementById('cgValMa20'),
      valMa60: document.getElementById('cgValMa60'),
      valMa120: document.getElementById('cgValMa120'),

      // 우측 트레이딩 콘솔
      totalReturnBadge: document.getElementById('cgTotalReturnBadge'),
      totalAssetVal: document.getElementById('cgTotalAssetVal'),
      cashVal: document.getElementById('cgCashVal'),
      holdingQtyVal: document.getElementById('cgHoldingQtyVal'),
      avgPriceVal: document.getElementById('cgAvgPriceVal'),
      turnText: document.getElementById('cgTurnText'),
      progressBarFill: document.getElementById('cgProgressBarFill'),
      btnRevealAnswer: document.getElementById('cgBtnRevealAnswer'),

      // 주문 관련
      orderModeTabs: document.getElementById('cgOrderModeTabs'),
      rrInputsArea: document.getElementById('cgRrInputsArea'),
      rrTakeProfit: document.getElementById('cgRrTakeProfit'),
      rrStopLoss: document.getElementById('cgRrStopLoss'),
      orderRatioGroup: document.getElementById('cgOrderRatioGroup'),
      customRatioInput: document.getElementById('cgCustomRatioInput'),
      calcOrderQty: document.getElementById('cgCalcOrderQty'),
      calcOrderAmount: document.getElementById('cgCalcOrderAmount'),

      // 액션 버튼
      btnBuy: document.getElementById('cgBtnBuy'),
      btnHold: document.getElementById('cgBtnHold'),
      btnSell: document.getElementById('cgBtnSell'),

      // 지표 설정 모달
      indicatorModal: document.getElementById('cgIndicatorModal'),
      btnCloseIndModal: document.getElementById('cgBtnCloseIndModal'),
      btnCancelIndModal: document.getElementById('cgBtnCancelIndModal'),
      btnApplyIndicators: document.getElementById('cgBtnApplyIndicators'),

      // 결과 공개 모달
      resultModal: document.getElementById('cgResultModal'),
      btnCloseResultModal: document.getElementById('cgBtnCloseResultModal'),
      btnCloseResultModal2: document.getElementById('cgBtnCloseResultModal2'),
      btnReplayGame: document.getElementById('cgBtnReplayGame'),
      resTickerName: document.getElementById('cgResTickerName'),
      resPeriodText: document.getElementById('cgResPeriodText'),
      resMyReturn: document.getElementById('cgResMyReturn'),
      resBnhReturn: document.getElementById('cgResBnhReturn'),
      resFinalAsset: document.getElementById('cgResFinalAsset'),
      resTradesInfo: document.getElementById('cgResTradesInfo'),

      // 로비 & 커리어 모드 UI
      lobbyView: document.getElementById('cgLobbyView'),
      gamePlayView: document.getElementById('cgGamePlayView'),
      btnStartPractice: document.getElementById('cgBtnStartPractice'),
      btnStartCareer: document.getElementById('cgBtnStartCareer'),
      btnResetCareer: document.getElementById('cgBtnResetCareer'),
      btnBackToLobby: document.getElementById('cgBtnBackToLobby'),
      gameModeBadge: document.getElementById('cgGameModeBadge'),
      careerTierBadge: document.getElementById('cgCareerTierBadge'),
      careerCapitalVal: document.getElementById('cgCareerCapitalVal'),
      careerGamesCount: document.getElementById('cgCareerGamesCount'),
      initCapitalInput: document.getElementById('cgInitCapitalInput'),
      capitalLockIcon: document.getElementById('cgCapitalLockIcon'),
      btnResetCapitalInGame: document.getElementById('cgBtnResetCapitalInGame'),

      // 내 트레이딩 성적 카드
      statsNicknameTitle: document.getElementById('cgStatsNicknameTitle'),
      statsGamesBadge: document.getElementById('cgStatsGamesBadge'),
      btnEditNickname: document.getElementById('cgBtnEditNickname'),
      nickEditRow: document.getElementById('cgNickEditRow'),
      nickEditInput: document.getElementById('cgNickEditInput'),
      btnSaveNickname: document.getElementById('cgBtnSaveNickname'),
      btnCancelNickname: document.getElementById('cgBtnCancelNickname'),
      winRateRingCircle: document.getElementById('cgWinRateRingCircle'),
      winRateRingText: document.getElementById('cgWinRateRingText'),
      statsAvgReturn: document.getElementById('cgStatsAvgReturn'),
      statsPayoffRatio: document.getElementById('cgStatsPayoffRatio'),
      statsTpiScore: document.getElementById('cgStatsTpiScore'),
      btnToggleLogs: document.getElementById('cgBtnToggleLogs'),
      logsChevron: document.getElementById('cgLogsChevron'),
      gameLogsCollapse: document.getElementById('cgGameLogsCollapse'),
      gameLogsTableBody: document.getElementById('cgGameLogsTableBody'),

      // 명예의 전당
      hofFilterBadge: document.getElementById('cgHofFilterBadge'),
      hofPeriodTabs: document.getElementById('cgHofPeriodTabs'),
      hofPodium1: document.getElementById('cgHofPodium1'),
      hofPodium2: document.getElementById('cgHofPodium2'),
      hofPodium3: document.getElementById('cgHofPodium3'),
      hofTableBody: document.getElementById('cgHofTableBody'),

      // 우측 하단 인사이트 패널 (재무제표 & 뉴스/시황 2-탭)
      bottomInsightPanel: document.getElementById('cgBottomInsightPanel'),
      tabFinancials: document.getElementById('cgTabFinancials'),
      tabNews: document.getElementById('cgTabNews'),
      paneFinancials: document.getElementById('cgPaneFinancials'),
      paneNews: document.getElementById('cgPaneNews'),

      // 재무제표 탭
      finLatestBadge: document.getElementById('cgFinLatestBadge'),
      finSourceBadge: document.getElementById('cgFinSourceBadge'),
      finDateHint: document.getElementById('cgFinDateHint'),
      btnDartApiToggle: document.getElementById('cgBtnDartApiToggle'),
      dartApiCard: document.getElementById('cgDartApiCard'),
      btnCloseDartCard: document.getElementById('cgBtnCloseDartCard'),
      dartApiKeyInput: document.getElementById('cgDartApiKeyInput'),
      btnSaveDartKey: document.getElementById('cgBtnSaveDartKey'),
      btnDeleteDartKey: document.getElementById('cgBtnDeleteDartKey'),
      finChartWrap: document.getElementById('cgFinChartWrap'),
      finSvgChart: document.getElementById('cgFinSvgChart'),
      finTable: document.getElementById('cgFinTable'),
      finTableHeadRow: document.getElementById('cgFinTableHeadRow'),
      finTableBody: document.getElementById('cgFinTableBody'),
      finEmpty: document.getElementById('cgFinEmpty'),

      // 뉴스 및 시황 탭
      newsDaysGroup: document.getElementById('cgNewsDaysGroup'),
      btnApiToggle: document.getElementById('cgBtnApiToggle'),
      apiSettingsPanel: document.getElementById('cgApiSettingsPanel'),
      llmProvider: document.getElementById('cgLlmProvider'),
      llmApiKey: document.getElementById('cgLlmApiKey'),
      naverClientId: document.getElementById('cgNaverClientId'),
      naverClientSecret: document.getElementById('cgNaverClientSecret'),
      btnSaveApiSettings: document.getElementById('cgBtnSaveApiSettings'),
      sentimentBadge: document.getElementById('cgSentimentBadge'),
      summaryOneliner: document.getElementById('cgSummaryOneliner'),
      summaryBullets: document.getElementById('cgSummaryBullets'),
      newsCount: document.getElementById('cgNewsCount'),
      newsList: document.getElementById('cgNewsList')
    };
  }

  // ─────────────────────────────────────────────────────────────
  // 2. TradingView Lightweight Charts 초기화 및 테마 구성
  // ─────────────────────────────────────────────────────────────
  function setupCharts() {
    if (!dom.mainChartEl || state.chartCreated) return;
    if (typeof LightweightCharts === 'undefined') {
      console.warn('[ChartGame] LightweightCharts 라이브러리가 로드되지 않았습니다.');
      return;
    }

    const baseOpts = {
      layout: {
        background: { color: '#161b26' },
        textColor: '#94a3b8',
        fontFamily: 'Inter, -apple-system, sans-serif',
        fontSize: 11
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.04)' }
      },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: { color: '#6366f1', width: 1, style: 2 },
        horzLine: { color: '#6366f1', width: 1, style: 2 }
      },
      rightPriceScale: {
        borderColor: '#232d3f',
        minimumWidth: 60
      }
    };

    // 1) 메인 캔들스틱 차트 생성
    state.mainChart = LightweightCharts.createChart(dom.mainChartEl, {
      ...baseOpts,
      width: dom.mainChartEl.clientWidth,
      height: dom.mainChartEl.clientHeight || 420,
      timeScale: {
        borderColor: '#232d3f',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 8,
        visible: false
      },
      rightPriceScale: {
        ...baseOpts.rightPriceScale,
        scaleMargins: { top: 0.1, bottom: 0.15 }
      }
    });

    // 한국형 캔들 테마 (양봉 빨강 #ef4444, 음봉 파랑 #3b82f6)
    state.candlestickSeries = state.mainChart.addCandlestickSeries({
      upColor: '#ef4444',
      downColor: '#3b82f6',
      borderUpColor: '#ef4444',
      borderDownColor: '#3b82f6',
      wickUpColor: '#ef4444',
      wickDownColor: '#3b82f6'
    });

    // 2) RSI 전용 차트 생성
    state.rsiChart = LightweightCharts.createChart(dom.rsiChartEl, {
      ...baseOpts,
      width: dom.rsiChartEl.clientWidth,
      height: dom.rsiChartEl.clientHeight || 165,
      timeScale: {
        borderColor: '#232d3f',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 8,
        visible: false
      },
      rightPriceScale: {
        ...baseOpts.rightPriceScale,
        scaleMargins: { top: 0.1, bottom: 0.1 }
      }
    });

    state.indicatorSeries.rsiSeries = state.rsiChart.addLineSeries({
      color: '#a855f7',
      lineWidth: 1.8,
      priceScaleId: 'right'
    });
    state.indicatorSeries.rsiSeries.createPriceLine({
      price: 70,
      color: 'rgba(239, 68, 68, 0.5)',
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      title: '과매수 (70)'
    });
    state.indicatorSeries.rsiSeries.createPriceLine({
      price: 30,
      color: 'rgba(59, 130, 246, 0.5)',
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      title: '과매도 (30)'
    });

    // 3) Volume 전용 차트 생성
    state.volumeChart = LightweightCharts.createChart(dom.volumeChartEl, {
      ...baseOpts,
      width: dom.volumeChartEl.clientWidth,
      height: dom.volumeChartEl.clientHeight || 165,
      timeScale: {
        borderColor: '#232d3f',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 8,
        visible: true
      },
      rightPriceScale: {
        ...baseOpts.rightPriceScale,
        scaleMargins: { top: 0.2, bottom: 0 }
      }
    });

    // 거래량 히스토그램 시리즈
    state.indicatorSeries.volSeries = state.volumeChart.addHistogramSeries({
      color: '#64748b',
      priceFormat: { type: 'volume' },
      priceScaleId: 'right'
    });

    // 거래량 이동평균선
    state.indicatorSeries.volMaSeries = state.volumeChart.addLineSeries({
      color: '#e2e8f0',
      lineWidth: 1.2,
      priceScaleId: 'right'
    });

    // 3-way 타임스케일 줌/팬 양방향 동기화
    let isSyncing = false;
    const charts = [state.mainChart, state.rsiChart, state.volumeChart];
    charts.forEach((src, si) => {
      src.timeScale().subscribeVisibleLogicalRangeChange(range => {
        if (isSyncing || !range) return;
        isSyncing = true;
        charts.forEach((dst, di) => {
          if (si !== di) dst.timeScale().setVisibleLogicalRange(range);
        });
        isSyncing = false;
      });
    });

    // 마우스 호버 크로스헤어 캔들 정보 연동
    state.mainChart.subscribeCrosshairMove(param => {
      if (!param || !param.time || !param.seriesData) {
        updateCandleHeaderOverlay(getLastCandle());
        return;
      }
      const data = param.seriesData.get(state.candlestickSeries);
      if (data) {
        updateCandleHeaderOverlay(data);
      }
    });

    // 윈도우 리사이즈 대응
    window.addEventListener('resize', handleResize);

    updateTimeScaleVisibility();
    state.chartCreated = true;
  }

  /**
   * 가장 아래에 보이는 차트 1개만 timeScale visible: true (날짜축 표시)
   */
  function updateTimeScaleVisibility() {
    const volVisible = state.indicators.vol.on && dom.volumePane && dom.volumePane.style.display !== 'none';
    const rsiVisible = state.indicators.rsi.on && dom.rsiPane && dom.rsiPane.style.display !== 'none';

    if (state.volumeChart) state.volumeChart.timeScale().applyOptions({ visible: volVisible });
    if (state.rsiChart) state.rsiChart.timeScale().applyOptions({ visible: !volVisible && rsiVisible });
    if (state.mainChart) state.mainChart.timeScale().applyOptions({ visible: !volVisible && !rsiVisible });
  }

  function handleResize() {
    if (!state.mainChart || !dom.mainChartEl) return;
    const w = dom.mainChartEl.clientWidth;
    state.mainChart.applyOptions({ width: w, height: dom.mainChartEl.clientHeight });
    if (state.rsiChart && dom.rsiChartEl) {
      state.rsiChart.applyOptions({ width: dom.rsiChartEl.clientWidth, height: dom.rsiChartEl.clientHeight });
    }
    if (state.volumeChart && dom.volumeChartEl) {
      state.volumeChart.applyOptions({ width: dom.volumeChartEl.clientWidth, height: dom.volumeChartEl.clientHeight });
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 3. 일봉/주봉/월봉 무누수 리샘플링 엔진 (Leak-Free Resampling)
  // ─────────────────────────────────────────────────────────────
  /**
   * 미래 캔들을 절대 노출하지 않고 현재 턴(currentIdx)까지의 캔들만 추출하여 타임프레임별 병합
   */
  function getVisibleCandles() {
    if (!state.candles || state.candles.length === 0) return [];
    const sliced = state.candles.slice(0, state.currentIdx + 1);

    if (state.timeframe === '1d') {
      return sliced.map(c => ({
        time: c.date,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume
      }));
    }

    if (state.timeframe === '1w') {
      return resampleWeekly(sliced);
    }

    if (state.timeframe === '1m') {
      return resampleMonthly(sliced);
    }

    return sliced;
  }

  function resampleWeekly(dailyCandles) {
    const weekly = [];
    let currentBucket = null;

    for (const c of dailyCandles) {
      const dt = new Date(c.date);
      // 주차 기준 계산: 해당 주의 월요일을 키로 사용
      const day = dt.getDay();
      const diff = dt.getDate() - day + (day === 0 ? -6 : 1);
      const monday = new Date(dt.setDate(diff)).toISOString().split('T')[0];

      if (!currentBucket || currentBucket.weekKey !== monday) {
        if (currentBucket) {
          weekly.push(currentBucket.candle);
        }
        currentBucket = {
          weekKey: monday,
          candle: {
            time: c.date,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
            volume: c.volume
          }
        };
      } else {
        currentBucket.candle.high = Math.max(currentBucket.candle.high, c.high);
        currentBucket.candle.low = Math.min(currentBucket.candle.low, c.low);
        currentBucket.candle.close = c.close;
        currentBucket.candle.volume += c.volume;
        currentBucket.candle.time = c.date; // 마지막 거래일 기준
      }
    }
    if (currentBucket) weekly.push(currentBucket.candle);
    return weekly;
  }

  function resampleMonthly(dailyCandles) {
    const monthly = [];
    let currentMonthKey = null;
    let currentBucket = null;

    for (const c of dailyCandles) {
      const monthKey = c.date.slice(0, 7); // 'YYYY-MM'
      if (monthKey !== currentMonthKey) {
        if (currentBucket) monthly.push(currentBucket);
        currentMonthKey = monthKey;
        currentBucket = {
          time: c.date,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
          volume: c.volume
        };
      } else {
        currentBucket.high = Math.max(currentBucket.high, c.high);
        currentBucket.low = Math.min(currentBucket.low, c.low);
        currentBucket.close = c.close;
        currentBucket.volume += c.volume;
        currentBucket.time = c.date;
      }
    }
    if (currentBucket) monthly.push(currentBucket);
    return monthly;
  }

  function getLastCandle() {
    const arr = getVisibleCandles();
    return arr.length > 0 ? arr[arr.length - 1] : null;
  }

  // ─────────────────────────────────────────────────────────────
  // 4. 6대 기술적 지표 실시간 계산기
  // ─────────────────────────────────────────────────────────────
  function formatIndicatorVal(val, currPrice) {
    if (val === undefined || val === null || isNaN(val) || val === '-') return '-';
    const num = Number(val);
    const refPrice = currPrice !== undefined && currPrice !== null ? currPrice : num;
    return refPrice < 5 ? num.toFixed(4) : num.toFixed(2);
  }

  function getDynamicPriceFormat(price) {
    if (price !== undefined && price !== null && price < 5) {
      return { type: 'price', precision: 4, minMove: 0.0001 };
    }
    return { type: 'price', precision: 2, minMove: 0.01 };
  }

  function calcSMA(candles, period) {
    const res = [];
    if (candles.length < period) return res;
    let sum = 0;
    for (let i = 0; i < candles.length; i++) {
      sum += candles[i].close !== undefined ? candles[i].close : candles[i].volume;
      if (i >= period) {
        sum -= candles[i - period].close !== undefined ? candles[i - period].close : candles[i - period].volume;
      }
      if (i >= period - 1) {
        res.push({
          time: candles[i].time,
          value: sum / period
        });
      }
    }
    return res;
  }

  function calcWilderRSI(candles, period = 14) {
    const res = [];
    if (candles.length <= period) return res;

    let gains = 0;
    let losses = 0;

    for (let i = 1; i <= period; i++) {
      const diff = candles[i].close - candles[i - 1].close;
      if (diff >= 0) gains += diff;
      else losses -= diff;
    }

    let avgGain = gains / period;
    let avgLoss = losses / period;

    let rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    let rsi = avgLoss === 0 ? 100 : 100 - (100 / (1 + rs));
    res.push({ time: candles[period].time, value: rsi });

    for (let i = period + 1; i < candles.length; i++) {
      const diff = candles[i].close - candles[i - 1].close;
      const gain = diff > 0 ? diff : 0;
      const loss = diff < 0 ? -diff : 0;

      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;

      rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      rsi = avgLoss === 0 ? 100 : 100 - (100 / (1 + rs));
      res.push({ time: candles[i].time, value: rsi });
    }
    return res;
  }

  function calcSuperTrend(candles, period = 10, multiplier = 3.0) {
    const res = [];
    if (candles.length < period) return res;

    // 1) True Range 계산
    const tr = [candles[0].high - candles[0].low];
    for (let i = 1; i < candles.length; i++) {
      const h = candles[i].high;
      const l = candles[i].low;
      const prevC = candles[i - 1].close;
      tr.push(Math.max(h - l, Math.abs(h - prevC), Math.abs(l - prevC)));
    }

    // 2) ATR 초기값 및 롤링 계산
    let atrSum = 0;
    for (let i = 0; i < period; i++) atrSum += tr[i];
    let atr = atrSum / period;

    let prevUpper = (candles[period - 1].high + candles[period - 1].low) / 2 + multiplier * atr;
    let prevLower = (candles[period - 1].high + candles[period - 1].low) / 2 - multiplier * atr;
    let trend = 1; // 1: 상승추세, -1: 하락추세

    for (let i = period; i < candles.length; i++) {
      atr = (atr * (period - 1) + tr[i]) / period;
      const hl2 = (candles[i].high + candles[i].low) / 2;
      let upper = hl2 + multiplier * atr;
      let lower = hl2 - multiplier * atr;

      if (lower > prevLower || candles[i - 1].close < prevLower) {
        // lower 유지
      } else {
        lower = prevLower;
      }

      if (upper < prevUpper || candles[i - 1].close > prevUpper) {
        // upper 유지
      } else {
        upper = prevUpper;
      }

      if (trend === 1 && candles[i].close < lower) {
        trend = -1;
      } else if (trend === -1 && candles[i].close > upper) {
        trend = 1;
      }

      prevUpper = upper;
      prevLower = lower;

      res.push({
        time: candles[i].time,
        value: trend === 1 ? lower : upper,
        color: trend === 1 ? '#10b981' : '#ef4444'
      });
    }
    return res;
  }

  function calcIchimoku(candles, convP = 9, baseP = 26, spanBP = 52) {
    const conversion = [];
    const base = [];
    const spanA = [];
    const spanB = [];

    const getHL2 = (sub) => {
      let maxH = -Infinity;
      let minL = Infinity;
      for (const item of sub) {
        if (item.high > maxH) maxH = item.high;
        if (item.low < minL) minL = item.low;
      }
      return (maxH + minL) / 2;
    };

    for (let i = 0; i < candles.length; i++) {
      if (i >= convP - 1) {
        const val = getHL2(candles.slice(i - convP + 1, i + 1));
        conversion.push({ time: candles[i].time, value: val });
      }
      if (i >= baseP - 1) {
        const val = getHL2(candles.slice(i - baseP + 1, i + 1));
        base.push({ time: candles[i].time, value: val });
      }
      if (i >= Math.max(convP, baseP) - 1 && conversion.length > 0 && base.length > 0) {
        const cVal = conversion[conversion.length - 1].value;
        const bVal = base[base.length - 1].value;
        spanA.push({ time: candles[i].time, value: (cVal + bVal) / 2 });
      }
      if (i >= spanBP - 1) {
        const val = getHL2(candles.slice(i - spanBP + 1, i + 1));
        spanB.push({ time: candles[i].time, value: val });
      }
    }

    return { conversion, base, spanA, spanB };
  }

  // ─────────────────────────────────────────────────────────────
  // 5. 차트 렌더링 및 지표 오버레이 동기화
  // ─────────────────────────────────────────────────────────────
  function renderChart() {
    if (!state.mainChart || !state.candlestickSeries) return;

    const visibleCandles = getVisibleCandles();
    if (visibleCandles.length === 0) return;

    const lastCandle = visibleCandles[visibleCandles.length - 1];
    const currPrice = lastCandle ? lastCandle.close : 0;
    const priceFormat = getDynamicPriceFormat(currPrice);

    // 1) 메인 캔들 동적 priceFormat 및 데이터 반영
    state.candlestickSeries.applyOptions({ priceFormat });
    state.candlestickSeries.setData(visibleCandles);

    // 2) 매매 마커 동기화
    state.candlestickSeries.setMarkers(state.markers);

    // 3) 평단가 수평선 반영
    if (state.avgPriceLine) {
      state.candlestickSeries.removePriceLine(state.avgPriceLine);
      state.avgPriceLine = null;
    }
    if (state.holdingQty > 0 && state.avgBuyPrice > 0) {
      state.avgPriceLine = state.candlestickSeries.createPriceLine({
        price: state.avgBuyPrice,
        color: '#10b981',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: `평단가 (${formatPrice(state.avgBuyPrice)})`
      });
    }

    // 4) 이동평균선(MA) 렌더링
    renderMovingAverages(visibleCandles, currPrice, priceFormat);

    // 5) 엔벨로프(Envelope) 렌더링
    renderEnvelope(visibleCandles, priceFormat);

    // 6) Super Trend 렌더링
    renderSuperTrend(visibleCandles, priceFormat);

    // 7) 일목균형표 렌더링
    renderIchimoku(visibleCandles, priceFormat);

    // 8) 하단 보조지표 (RSI / 거래량) 독립 패널 렌더링
    renderRsiChart(visibleCandles);
    renderVolumeChart(visibleCandles);
    updateTimeScaleVisibility();

    // 상단 오버레이 수치 최신 캔들로 업데이트
    updateCandleHeaderOverlay(lastCandle);
  }

  function renderMovingAverages(candles, currPrice, priceFormat) {
    const curvedType = (typeof LightweightCharts !== 'undefined' && LightweightCharts.LineType?.Curved !== undefined)
      ? LightweightCharts.LineType.Curved : 2;

    state.indicators.ma.lines.forEach((cfg, idx) => {
      const key = `ma_${idx}`;
      if (state.indicators.ma.on && cfg.on) {
        if (!state.indicatorSeries[key]) {
          state.indicatorSeries[key] = state.mainChart.addLineSeries({
            color: cfg.color,
            lineWidth: idx === 1 ? 2 : 1.2,
            lineType: curvedType,
            crosshairMarkerVisible: false,
            priceFormat: priceFormat
          });
        } else {
          state.indicatorSeries[key].applyOptions({ lineType: curvedType, priceFormat });
        }
        const maData = calcSMA(candles, cfg.period);
        state.indicatorSeries[key].setData(maData);

        // 오버레이 레전드에 최신값 표시 (소액주 4자리, 일반 2자리)
        const latestVal = maData.length > 0 ? maData[maData.length - 1].value : '-';
        const formattedVal = formatIndicatorVal(latestVal, currPrice);
        if (idx === 0 && dom.valMa5) dom.valMa5.textContent = formattedVal;
        if (idx === 1 && dom.valMa20) dom.valMa20.textContent = formattedVal;
        if (idx === 2 && dom.valMa60) dom.valMa60.textContent = formattedVal;
        if (idx === 3 && dom.valMa120) dom.valMa120.textContent = formattedVal;
      } else if (state.indicatorSeries[key]) {
        state.indicatorSeries[key].setData([]);
      }
    });
  }

  function renderEnvelope(candles, priceFormat) {
    const keys = ['env_up', 'env_mid', 'env_dn'];
    const curvedType = (typeof LightweightCharts !== 'undefined' && LightweightCharts.LineType?.Curved !== undefined)
      ? LightweightCharts.LineType.Curved : 2;

    if (state.indicators.env.on) {
      if (!state.indicatorSeries.env_up) {
        state.indicatorSeries.env_up = state.mainChart.addLineSeries({
          color: '#f59e0b', lineWidth: 1.2, lineStyle: 2, lineType: curvedType, priceFormat
        });
        state.indicatorSeries.env_mid = state.mainChart.addLineSeries({
          color: '#fbbf24', lineWidth: 1, lineType: curvedType, priceFormat
        });
        state.indicatorSeries.env_dn = state.mainChart.addLineSeries({
          color: '#f59e0b', lineWidth: 1.2, lineStyle: 2, lineType: curvedType, priceFormat
        });
      } else {
        state.indicatorSeries.env_up.applyOptions({ lineType: curvedType, priceFormat });
        state.indicatorSeries.env_mid.applyOptions({ lineType: curvedType, priceFormat });
        state.indicatorSeries.env_dn.applyOptions({ lineType: curvedType, priceFormat });
      }
      const mid = calcSMA(candles, state.indicators.env.period);
      const ratio = state.indicators.env.ratio / 100.0;
      const up = mid.map(m => ({ time: m.time, value: m.value * (1 + ratio) }));
      const dn = mid.map(m => ({ time: m.time, value: m.value * (1 - ratio) }));

      state.indicatorSeries.env_up.setData(state.indicators.env.showUpper ? up : []);
      state.indicatorSeries.env_mid.setData(state.indicators.env.showMid ? mid : []);
      state.indicatorSeries.env_dn.setData(state.indicators.env.showLower ? dn : []);
    } else {
      keys.forEach(k => {
        if (state.indicatorSeries[k]) state.indicatorSeries[k].setData([]);
      });
    }
  }

  function renderSuperTrend(candles, priceFormat) {
    if (state.indicators.st.on) {
      if (!state.indicatorSeries.stSeries) {
        state.indicatorSeries.stSeries = state.mainChart.addLineSeries({
          color: state.indicators.st.colorUp || '#10b981',
          lineWidth: 2,
          priceFormat
        });
      } else {
        state.indicatorSeries.stSeries.applyOptions({ priceFormat });
      }
      const stData = calcSuperTrendColored(candles, state.indicators.st.period, state.indicators.st.multiplier);
      state.indicatorSeries.stSeries.setData(stData);
    } else if (state.indicatorSeries.stSeries) {
      state.indicatorSeries.stSeries.setData([]);
    }
  }

  function renderIchimoku(candles, priceFormat) {
    const keys = ['ichi_conv', 'ichi_base', 'ichi_spanA', 'ichi_spanB'];
    const curvedType = (typeof LightweightCharts !== 'undefined' && LightweightCharts.LineType?.Curved !== undefined)
      ? LightweightCharts.LineType.Curved : 2;
    if (state.indicators.ichimoku.on) {
      if (!state.indicatorSeries.ichi_conv) {
        state.indicatorSeries.ichi_conv = state.mainChart.addLineSeries({ color: '#38bdf8', lineWidth: 1.2, lineType: curvedType, priceFormat });
        state.indicatorSeries.ichi_base = state.mainChart.addLineSeries({ color: '#f43f5e', lineWidth: 1.5, lineType: curvedType, priceFormat });
        state.indicatorSeries.ichi_spanA = state.mainChart.addLineSeries({ color: 'rgba(34, 197, 94, 0.7)', lineWidth: 1, lineStyle: 1, lineType: curvedType, priceFormat });
        state.indicatorSeries.ichi_spanB = state.mainChart.addLineSeries({ color: 'rgba(239, 68, 68, 0.7)', lineWidth: 1, lineStyle: 1, lineType: curvedType, priceFormat });
      } else {
        keys.forEach(k => {
          if (state.indicatorSeries[k]) state.indicatorSeries[k].applyOptions({ lineType: curvedType, priceFormat });
        });
      }
      const chi = calcIchimoku(candles, state.indicators.ichimoku.conversion, state.indicators.ichimoku.base, state.indicators.ichimoku.spanB);
      state.indicatorSeries.ichi_conv.setData(chi.conversion);
      state.indicatorSeries.ichi_base.setData(chi.base);
      state.indicatorSeries.ichi_spanA.setData(chi.spanA);
      state.indicatorSeries.ichi_spanB.setData(chi.spanB);
    } else {
      keys.forEach(k => {
        if (state.indicatorSeries[k]) state.indicatorSeries[k].setData([]);
      });
    }
  }

  function renderRsiChart(candles) {
    if (state.indicators.rsi.on && state.indicatorSeries.rsiSeries) {
      const rsiData = calcWilderRSI(candles, state.indicators.rsi.period);
      state.indicatorSeries.rsiSeries.setData(rsiData);
      // RSI 최신값 라벨 업데이트
      if (dom.rsiVal && rsiData.length > 0) {
        dom.rsiVal.textContent = rsiData[rsiData.length - 1].value.toFixed(1);
      }
      if (dom.rsiPeriodLabel) {
        dom.rsiPeriodLabel.textContent = state.indicators.rsi.period;
      }
      if (dom.rsiPane) dom.rsiPane.style.display = '';
    } else {
      if (state.indicatorSeries.rsiSeries) state.indicatorSeries.rsiSeries.setData([]);
      if (dom.rsiPane) dom.rsiPane.style.display = 'none';
    }
  }

  function renderVolumeChart(candles) {
    if (state.indicators.vol.on && state.indicatorSeries.volSeries) {
      const volData = candles.map(c => ({
        time: c.time,
        value: c.volume,
        color: c.close >= c.open ? 'rgba(239, 68, 68, 0.65)' : 'rgba(59, 130, 246, 0.65)'
      }));
      state.indicatorSeries.volSeries.setData(volData);

      const volMaData = calcSMA(candles, state.indicators.vol.maPeriod);
      state.indicatorSeries.volMaSeries.setData(volMaData);

      // 최신 거래량 라벨 업데이트
      if (dom.volumeVal && candles.length > 0) {
        dom.volumeVal.textContent = candles[candles.length - 1].volume.toLocaleString();
      }
      if (dom.volumePane) dom.volumePane.style.display = '';
    } else {
      if (state.indicatorSeries.volSeries) state.indicatorSeries.volSeries.setData([]);
      if (state.indicatorSeries.volMaSeries) state.indicatorSeries.volMaSeries.setData([]);
      if (dom.volumePane) dom.volumePane.style.display = 'none';
    }
  }

  function updateCandleHeaderOverlay(candle) {
    if (!candle) return;
    if (dom.valDate) dom.valDate.textContent = candle.time || candle.date || '-';
    if (dom.valOpen) dom.valOpen.textContent = formatPrice(candle.open);
    if (dom.valHigh) dom.valHigh.textContent = formatPrice(candle.high);
    if (dom.valLow) dom.valLow.textContent = formatPrice(candle.low);
    if (dom.valClose) dom.valClose.textContent = formatPrice(candle.close);
    if (dom.valVolume) dom.valVolume.textContent = (candle.volume || 0).toLocaleString();

    if (dom.valChange && candle.open) {
      const diff = candle.close - candle.open;
      const pct = ((diff / candle.open) * 100).toFixed(2);
      const isUp = diff >= 0;
      dom.valChange.className = `val ${isUp ? 'up' : 'down'}`;
      dom.valChange.textContent = `${isUp ? '+' : ''}${pct}% (${diff > 0 ? '+' : ''}${formatPrice(diff)})`;
    }
  }

  function formatPrice(val) {
    if (val === undefined || val === null || isNaN(val)) return '0';
    const num = Number(val);
    if (state.currency === 'USD') {
      return Math.abs(num) < 5 ? `$${num.toFixed(4)}` : `$${num.toFixed(2)}`;
    }
    if (Math.abs(num) < 5) {
      return `${num.toFixed(4)}원`;
    }
    return `${Math.round(num).toLocaleString()}원`;
  }

  // ─────────────────────────────────────────────────────────────
  // 6. 트레이딩 엔진 (매수 / 다음턴 / 매도 & R:R 자동 익절/손절)
  // ─────────────────────────────────────────────────────────────
  function executeBuy() {
    const candle = getLastCandle();
    if (!candle) return;

    const price = candle.close;
    if (price <= 0) return;

    const allocCash = state.cash * state.orderRatio;
    const qty = Math.floor(allocCash / price);

    if (qty <= 0) {
      alert('매수 가능한 예수금(현금)이 부족합니다.');
      return;
    }

    const totalCost = qty * price;
    const newQty = state.holdingQty + qty;
    const newAvg = (state.holdingQty * state.avgBuyPrice + totalCost) / newQty;

    state.cash -= totalCost;
    state.holdingQty = newQty;
    state.avgBuyPrice = newAvg;

    // 매수 마커 등록
    state.markers.push({
      time: candle.time,
      position: 'belowBar',
      color: '#10b981',
      shape: 'arrowUp',
      text: `매수 ${qty}주`
    });

    state.trades.push({
      turn: state.currentTurn,
      date: candle.time,
      type: 'BUY',
      price: price,
      qty: qty,
      amount: totalCost,
      pnl: 0
    });

    // R:R 자동 주문 설정 시 목표 익절가/손절가 활성화
    if (state.orderMode === 'RR') {
      const tp = state.avgBuyPrice * (1 + state.rrTakeProfitPct / 100);
      const sl = state.avgBuyPrice * (1 - state.rrStopLossPct / 100);
      state.activeRR = { tp, sl, qty: state.holdingQty };
    }

    updateUI();
    renderChart();
  }

  function executeSell() {
    const candle = getLastCandle();
    if (!candle) return;

    if (state.holdingQty <= 0) {
      alert('매도할 수 있는 보유 주식이 없습니다.');
      return;
    }

    const sellQty = Math.max(1, Math.floor(state.holdingQty * state.orderRatio));
    const price = candle.close;
    const revenue = sellQty * price;
    const cost = sellQty * state.avgBuyPrice;
    const pnl = revenue - cost;

    state.cash += revenue;
    state.holdingQty -= sellQty;

    if (state.holdingQty === 0) {
      state.avgBuyPrice = 0;
      state.activeRR = null;
    }

    // 매도 마커 등록
    state.markers.push({
      time: candle.time,
      position: 'aboveBar',
      color: '#ef4444',
      shape: 'arrowDown',
      text: `매도 ${sellQty}주`
    });

    state.trades.push({
      turn: state.currentTurn,
      date: candle.time,
      type: 'SELL',
      price: price,
      qty: sellQty,
      amount: revenue,
      pnl: pnl
    });

    updateUI();
    renderChart();
  }

  function nextTurn() {
    if (state.currentTurn >= state.maxTurns || state.currentIdx >= state.candles.length - 1) {
      revealGameResult();
      return;
    }

    // 1턴 전진
    state.currentTurn++;
    state.currentIdx++;

    const newCandle = state.candles[state.currentIdx];

    // R:R 자동 익절/손절 체크
    if (state.activeRR && state.holdingQty > 0) {
      if (newCandle.high >= state.activeRR.tp) {
        // 익절 도달 -> 자동 청산
        executeAutoLiquidation(state.activeRR.tp, '익절');
      } else if (newCandle.low <= state.activeRR.sl) {
        // 손절 도달 -> 자동 청산
        executeAutoLiquidation(state.activeRR.sl, '손절');
      }
    }

    updateUI();
    renderChart();
    triggerInsightUpdate();

    // 마지막 턴 종료 판정
    if (state.currentTurn >= state.maxTurns) {
      setTimeout(revealGameResult, 400);
    }
  }

  function executeAutoLiquidation(execPrice, reason) {
    const candle = state.candles[state.currentIdx];
    const qty = state.holdingQty;
    const revenue = qty * execPrice;
    const cost = qty * state.avgBuyPrice;
    const pnl = revenue - cost;

    state.cash += revenue;
    state.holdingQty = 0;
    state.avgBuyPrice = 0;
    state.activeRR = null;

    state.markers.push({
      time: candle.date,
      position: 'aboveBar',
      color: reason === '익절' ? '#10b981' : '#ef4444',
      shape: 'circle',
      text: `자동${reason} (${execPrice.toFixed(0)})`
    });

    state.trades.push({
      turn: state.currentTurn,
      date: candle.date,
      type: `AUTO_${reason}`,
      price: execPrice,
      qty: qty,
      amount: revenue,
      pnl: pnl
    });
  }

  // ─────────────────────────────────────────────────────────────
  // 7. 실시간 자산 및 콘솔 UI 동기화
  // ─────────────────────────────────────────────────────────────
  function updateUI() {
    const candle = getLastCandle();
    const currPrice = candle ? candle.close : 0;
    const stockVal = state.holdingQty * currPrice;
    const totalAsset = state.cash + stockVal;
    const totalReturn = ((totalAsset - state.initialCapital) / state.initialCapital) * 100;

    // 수익률 배지
    if (dom.totalReturnBadge) {
      const isPlus = totalReturn >= 0;
      dom.totalReturnBadge.className = `cg-return-badge ${isPlus ? 'plus' : 'minus'}`;
      dom.totalReturnBadge.textContent = `${isPlus ? '+' : ''}${totalReturn.toFixed(2)}%`;
    }

    // 자산 정보
    if (dom.totalAssetVal) dom.totalAssetVal.textContent = formatPrice(totalAsset);
    if (dom.cashVal) dom.cashVal.textContent = formatPrice(state.cash);
    if (dom.holdingQtyVal) dom.holdingQtyVal.textContent = `${state.holdingQty.toLocaleString()}주`;
    if (dom.avgPriceVal) dom.avgPriceVal.textContent = state.avgBuyPrice > 0 ? formatPrice(state.avgBuyPrice) : '0원';

    // 턴 진행 상황
    if (dom.turnText) dom.turnText.textContent = `턴 ${state.currentTurn} / ${state.maxTurns}`;
    if (dom.progressBarFill) {
      const pct = Math.min(100, (state.currentTurn / state.maxTurns) * 100);
      dom.progressBarFill.style.width = `${pct}%`;
    }

    // 주문 가능 주수/금액 계산
    if (currPrice > 0 && dom.calcOrderQty && dom.calcOrderAmount) {
      const allocCash = state.cash * state.orderRatio;
      const buyableQty = Math.floor(allocCash / currPrice);
      dom.calcOrderQty.textContent = `${buyableQty.toLocaleString()}주`;
      dom.calcOrderAmount.textContent = formatPrice(buyableQty * currPrice);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 8. 새 게임 시작 & 결과 공개 모달
  // ─────────────────────────────────────────────────────────────
  function showLoading(tickerName) {
    if (!dom.loadingOverlay) return;
    const t = tickerName || '종목';
    if (dom.loadingText) {
      dom.loadingText.textContent = `Yahoo Finance에서 [${t}] 시세 불러오는 중...`;
    }
    dom.loadingOverlay.style.display = 'flex';
  }

  function hideLoading() {
    if (dom.loadingOverlay) {
      dom.loadingOverlay.style.display = 'none';
    }
  }

  async function startNewGame(targetTicker) {
    initDom();
    setupCharts();

    let tickerVal = targetTicker;
    if (!tickerVal) {
      tickerVal = dom.tickerInput?.value.trim() || 'RANDOM';
    }
    const turnsVal = parseInt(dom.maxTurnsInput?.value || '50', 10);

    // 모드별 초기 자본금 결정 (연습 모드: 입력값 / 커리어 1회차: 입력값 저장 / 커리어 2회차~: 이월 자본금)
    let reqInitCap = 10000000;
    if (state.gameMode === 'career') {
      const career = loadCareerState();
      if (career.gamesPlayed >= 1) {
        reqInitCap = Math.max(100000, Math.round(career.currentCapital));
      } else {
        const inpVal = parseFloat(dom.initCapitalInput?.value || '10000000');
        reqInitCap = (!isNaN(inpVal) && inpVal >= 100000) ? Math.round(inpVal) : 10000000;
        career.currentCapital = reqInitCap;
        saveCareerState(career);
      }
    } else {
      const inpVal = parseFloat(dom.initCapitalInput?.value || '10000000');
      reqInitCap = (!isNaN(inpVal) && inpVal >= 100000) ? Math.round(inpVal) : 10000000;
    }

    if (dom.btnNewGame) dom.btnNewGame.disabled = true;
    if (dom.btnApplyTicker) dom.btnApplyTicker.disabled = true;

    showLoading(tickerVal);

    try {
      const res = await fetch('/api/chart_game/new_game', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: tickerVal,
          max_turns: turnsVal,
          initial_capital: reqInitCap
        })
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok || data.status !== 'success') {
        throw new Error(data.message || `차트 데이터 로드 실패 (${res.status})`);
      }

      // 게임 상태 리셋
      state.candles = data.candles || [];
      state.startIdx = data.start_idx || 150;
      state.currentIdx = state.startIdx;
      state.maxTurns = data.max_turns || turnsVal;
      state.currentTurn = 0;
      state.gameEnded = false;
      state.currency = data.currency || 'KRW';
      state.initialCapital = reqInitCap;
      state.cash = state.initialCapital;
      state.holdingQty = 0;
      state.avgBuyPrice = 0;
      state.trades = [];
      state.markers = [];
      state.tickerInfo = data.ticker_info || null;
      state.activeRR = null;

      // 차트 및 UI 갱신
      renderChart();
      updateUI();

      // 타임스케일 전체 맞춤
      if (state.mainChart) {
        state.mainChart.timeScale().fitContent();
      }

      // 우측 하단 인사이트 패널 갱신 (재무제표 & 뉴스)
      triggerInsightUpdate(true);

    } catch (err) {
      console.error('[ChartGame] 새 게임 시작 에러:', err);
      alert(err.message || '차트 게임 데이터를 불러오지 못했습니다.');
    } finally {
      hideLoading();
      if (dom.btnNewGame) dom.btnNewGame.disabled = false;
      if (dom.btnApplyTicker) dom.btnApplyTicker.disabled = false;
    }
  }

  function revealGameResult() {
    if (!state.candles || state.candles.length === 0) return;

    const startCandle = state.candles[state.startIdx];
    const endCandle = state.candles[state.currentIdx];

    const currPrice = endCandle ? endCandle.close : 0;
    const finalAsset = state.cash + state.holdingQty * currPrice;
    const myReturn = ((finalAsset - state.initialCapital) / state.initialCapital) * 100;

    const bnhReturn = startCandle && startCandle.close > 0
      ? ((endCandle.close - startCandle.close) / startCandle.close) * 100
      : 0;

    const totalTrades = state.trades.filter(t => t.type.includes('SELL')).length;
    const winTrades = state.trades.filter(t => t.pnl > 0).length;
    const winRate = totalTrades > 0 ? (winTrades / totalTrades) * 100 : 0;

    // 모달 내용 바인딩
    if (dom.resTickerName) {
      dom.resTickerName.textContent = state.tickerInfo
        ? `${state.tickerInfo.name} (${state.tickerInfo.ticker})`
        : '블라인드 종목';
    }
    if (dom.resPeriodText && startCandle && endCandle) {
      dom.resPeriodText.textContent = `${startCandle.date} ~ ${endCandle.date} (${state.currentTurn}턴 진행)`;
    }
    if (dom.resMyReturn) {
      dom.resMyReturn.textContent = `${myReturn >= 0 ? '+' : ''}${myReturn.toFixed(2)}%`;
      dom.resMyReturn.style.color = myReturn >= 0 ? '#ef4444' : '#3b82f6';
    }
    if (dom.resBnhReturn) {
      dom.resBnhReturn.textContent = `${bnhReturn >= 0 ? '+' : ''}${bnhReturn.toFixed(2)}%`;
      dom.resBnhReturn.style.color = bnhReturn >= 0 ? '#ef4444' : '#3b82f6';
    }
    if (dom.resFinalAsset) dom.resFinalAsset.textContent = formatPrice(finalAsset);
    if (dom.resTradesInfo) dom.resTradesInfo.textContent = `${totalTrades}회 / ${winRate.toFixed(1)}%`;

    // 커리어 모드 종료 시 최종 평가자산 저장 (Supabase DB + localStorage 폴백)
    if (state.gameMode === 'career' && !state.gameEnded) {
      state.gameEnded = true;
      const profitAmount = Math.round(finalAsset - state.initialCapital);
      const endCapital = Math.max(0, Math.round(finalAsset));
      const tickerCode = state.tickerInfo?.ticker || dom.tickerInput?.value?.trim() || 'RANDOM';
      recordCareerGameResult({
        ticker: tickerCode,
        returnPct: Number(myReturn.toFixed(2)),
        profitAmount,
        endCapital
      });
    } else {
      state.gameEnded = true;
    }

    // 모달 표시
    if (dom.resultModal) {
      dom.resultModal.classList.add('show');
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 9. 이벤트 리스너 및 키보드 단축키 연동
  // ─────────────────────────────────────────────────────────────
  function setupEventListeners() {
    // 새 게임 버튼 (랜덤 시점)
    if (dom.btnNewGame) dom.btnNewGame.addEventListener('click', () => startNewGame());

    // 종목 적용 버튼
    if (dom.btnApplyTicker) {
      dom.btnApplyTicker.addEventListener('click', () => {
        const val = dom.tickerInput?.value.trim();
        startNewGame(val);
      });
    }

    // 티커 입력창 Enter 키 및 선택(change) 즉시 차트 전환
    if (dom.tickerInput) {
      dom.tickerInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const val = dom.tickerInput.value.trim();
          startNewGame(val);
        }
      });
      dom.tickerInput.addEventListener('change', () => {
        const val = dom.tickerInput.value.trim();
        if (val) {
          startNewGame(val);
        }
      });
    }

    // 액션 버튼 (매수, 다음, 매도)
    if (dom.btnBuy) dom.btnBuy.addEventListener('click', executeBuy);
    if (dom.btnHold) dom.btnHold.addEventListener('click', nextTurn);
    if (dom.btnSell) dom.btnSell.addEventListener('click', executeSell);

    // 정답 공개 버튼
    if (dom.btnRevealAnswer) dom.btnRevealAnswer.addEventListener('click', revealGameResult);

    // 턴 수 퀵 버튼들
    if (dom.quickTurnsGroup) {
      dom.quickTurnsGroup.addEventListener('click', e => {
        const btn = e.target.closest('.cg-pill-btn');
        if (!btn) return;
        dom.quickTurnsGroup.querySelectorAll('.cg-pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if (dom.maxTurnsInput) dom.maxTurnsInput.value = btn.dataset.turns;
      });
    }

    // 타임프레임 토글 (일봉 / 주봉 / 월봉)
    if (dom.timeframeGroup) {
      dom.timeframeGroup.addEventListener('click', e => {
        const btn = e.target.closest('.cg-pill-btn');
        if (!btn) return;
        dom.timeframeGroup.querySelectorAll('.cg-pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.timeframe = btn.dataset.tf;
        renderChart();
      });
    }

    // 주문 비중 버튼
    if (dom.orderRatioGroup) {
      dom.orderRatioGroup.addEventListener('click', e => {
        const btn = e.target.closest('.cg-ratio-btn');
        if (!btn) return;
        dom.orderRatioGroup.querySelectorAll('.cg-ratio-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.orderRatio = parseFloat(btn.dataset.ratio || '1.0');
        if (dom.customRatioInput) dom.customRatioInput.value = '';
        updateUI();
      });
    }
    if (dom.customRatioInput) {
      dom.customRatioInput.addEventListener('input', e => {
        const val = parseFloat(e.target.value);
        if (!isNaN(val) && val > 0) {
          dom.orderRatioGroup.querySelectorAll('.cg-ratio-btn').forEach(b => b.classList.remove('active'));
          state.orderRatio = Math.min(1.0, val / 100);
          updateUI();
        }
      });
    }

    // 주문 모드 탭 (일반 매수 vs R:R 매수)
    if (dom.orderModeTabs) {
      dom.orderModeTabs.addEventListener('click', e => {
        const tab = e.target.closest('.cg-mode-tab');
        if (!tab) return;
        dom.orderModeTabs.querySelectorAll('.cg-mode-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        state.orderMode = tab.dataset.mode;
        if (dom.rrInputsArea) {
          dom.rrInputsArea.style.display = state.orderMode === 'RR' ? 'grid' : 'none';
        }
      });
    }

    // R:R 값 실시간 연동
    if (dom.rrTakeProfit) {
      dom.rrTakeProfit.addEventListener('input', e => {
        state.rrTakeProfitPct = parseFloat(e.target.value) || 10;
      });
    }
    if (dom.rrStopLoss) {
      dom.rrStopLoss.addEventListener('input', e => {
        state.rrStopLossPct = parseFloat(e.target.value) || 5;
      });
    }

    // 퀵 툴바 지표 ON/OFF 토글
    const bindTool = (el, toggleFn) => {
      if (!el) return;
      el.addEventListener('click', () => {
        el.classList.toggle('active');
        toggleFn(el.classList.contains('active'));
        renderChart();
      });
    };
    bindTool(dom.toolMa, (on) => { state.indicators.ma.on = on; });
    bindTool(dom.toolEnv, (on) => { state.indicators.env.on = on; });
    bindTool(dom.toolSt, (on) => { state.indicators.st.on = on; });
    bindTool(dom.toolIchimoku, (on) => { state.indicators.ichimoku.on = on; });
    bindTool(dom.toolRsi, (on) => {
      state.indicators.rsi.on = on;
      if (dom.rsiPane) dom.rsiPane.style.display = on ? '' : 'none';
      updateTimeScaleVisibility();
      handleResize();
    });
    bindTool(dom.toolVol, (on) => {
      state.indicators.vol.on = on;
      if (dom.volumePane) dom.volumePane.style.display = on ? '' : 'none';
      updateTimeScaleVisibility();
      handleResize();
    });

    // 지표 설정 모달 오픈/닫기
    const openIndModal = () => {
      if (!dom.indicatorModal) return;
      // 엔벨로프 라인별 표시 체크박스를 현재 상태로 동기화
      const envShowUpper = document.getElementById('cgEnvShowUpper');
      const envShowMid = document.getElementById('cgEnvShowMid');
      const envShowLower = document.getElementById('cgEnvShowLower');
      if (envShowUpper) envShowUpper.checked = state.indicators.env.showUpper;
      if (envShowMid) envShowMid.checked = state.indicators.env.showMid;
      if (envShowLower) envShowLower.checked = state.indicators.env.showLower;
      dom.indicatorModal.classList.add('show');
    };
    const closeIndModal = () => { if (dom.indicatorModal) dom.indicatorModal.classList.remove('show'); };
    if (dom.btnOpenIndicators) dom.btnOpenIndicators.addEventListener('click', openIndModal);
    if (dom.toolSettings) dom.toolSettings.addEventListener('click', openIndModal);
    if (dom.btnCloseIndModal) dom.btnCloseIndModal.addEventListener('click', closeIndModal);
    if (dom.btnCancelIndModal) dom.btnCancelIndModal.addEventListener('click', closeIndModal);

    // 지표 모달 탭 전환
    if (dom.indicatorModal) {
      const tabs = dom.indicatorModal.querySelectorAll('.cg-indicator-tab-btn');
      tabs.forEach(tab => {
        tab.addEventListener('click', () => {
          tabs.forEach(t => t.classList.remove('active'));
          tab.classList.add('active');
          dom.indicatorModal.querySelectorAll('.cg-indicator-content-section').forEach(s => s.classList.remove('active'));
          const target = document.getElementById(`cgIndSec_${tab.dataset.tab}`);
          if (target) target.classList.add('active');
        });
      });
    }

    // 지표 모달 설정 적용 버튼
    if (dom.btnApplyIndicators) {
      dom.btnApplyIndicators.addEventListener('click', () => {
        applyIndicatorModalSettings();
        closeIndModal();
        renderChart();
      });
    }

    // 결과 모달 닫기 및 다시 플레이
    const closeResModal = () => { if (dom.resultModal) dom.resultModal.classList.remove('show'); };
    if (dom.btnCloseResultModal) dom.btnCloseResultModal.addEventListener('click', closeResModal);
    if (dom.btnCloseResultModal2) dom.btnCloseResultModal2.addEventListener('click', closeResModal);
    if (dom.btnReplayGame) {
      dom.btnReplayGame.addEventListener('click', () => {
        closeResModal();
        startNewGame();
      });
    }

    // 하단 인사이트 패널 (재무제표 & 뉴스 2-탭 전환)
    if (dom.tabFinancials) {
      dom.tabFinancials.addEventListener('click', () => {
        state.activeInsightTab = 'financials';
        dom.tabFinancials.classList.add('active');
        if (dom.tabNews) dom.tabNews.classList.remove('active');
        if (dom.paneFinancials) dom.paneFinancials.classList.add('active');
        if (dom.paneNews) dom.paneNews.classList.remove('active');
        triggerInsightUpdate(true);
      });
    }

    if (dom.tabNews) {
      dom.tabNews.addEventListener('click', () => {
        state.activeInsightTab = 'news';
        dom.tabNews.classList.add('active');
        if (dom.tabFinancials) dom.tabFinancials.classList.remove('active');
        if (dom.paneNews) dom.paneNews.classList.add('active');
        if (dom.paneFinancials) dom.paneFinancials.classList.remove('active');
        triggerInsightUpdate(true);
      });
    }

    // 뉴스 기간 변경 버튼 (1주~3달)
    if (dom.newsDaysGroup) {
      dom.newsDaysGroup.addEventListener('click', e => {
        const btn = e.target.closest('.cg-pill-btn');
        if (!btn) return;
        dom.newsDaysGroup.querySelectorAll('.cg-pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.newsDays = parseInt(btn.dataset.days || '30', 10);
        loadNewsData(true);
      });
    }

    // 뉴스 API 설정 패널 토글 및 저장
    if (dom.btnApiToggle && dom.apiSettingsPanel) {
      dom.btnApiToggle.addEventListener('click', () => {
        const isHidden = dom.apiSettingsPanel.style.display === 'none';
        dom.apiSettingsPanel.style.display = isHidden ? 'flex' : 'none';
      });
    }

    if (dom.btnSaveApiSettings) {
      dom.btnSaveApiSettings.addEventListener('click', () => {
        saveApiSettings();
        if (dom.apiSettingsPanel) dom.apiSettingsPanel.style.display = 'none';
        loadNewsData(true);
      });
    }

    // OpenDART 전자공시 API 설정 카드 토글 및 등록/삭제
    if (dom.btnDartApiToggle && dom.dartApiCard) {
      dom.btnDartApiToggle.addEventListener('click', () => {
        const isHidden = dom.dartApiCard.style.display === 'none';
        dom.dartApiCard.style.display = isHidden ? 'flex' : 'none';
        if (isHidden && dom.dartApiKeyInput) {
          dom.dartApiKeyInput.value = localStorage.getItem('cg_opendart_api_key') || '';
        }
      });
    }

    if (dom.finSourceBadge) {
      dom.finSourceBadge.addEventListener('click', () => {
        if (dom.finSourceBadge.classList.contains('nodart') && dom.dartApiCard) {
          dom.dartApiCard.style.display = 'flex';
          if (dom.dartApiKeyInput) {
            dom.dartApiKeyInput.value = localStorage.getItem('cg_opendart_api_key') || '';
            dom.dartApiKeyInput.focus();
          }
        }
      });
    }

    if (dom.btnCloseDartCard && dom.dartApiCard) {
      dom.btnCloseDartCard.addEventListener('click', () => {
        dom.dartApiCard.style.display = 'none';
      });
    }

    if (dom.btnSaveDartKey) {
      dom.btnSaveDartKey.addEventListener('click', () => {
        const val = (dom.dartApiKeyInput?.value || '').trim();
        if (!val) {
          alert('OpenDART API 인증키를 입력해 주세요.');
          return;
        }
        localStorage.setItem('cg_opendart_api_key', val);
        alert('OpenDART 인증키가 등록되었습니다. 실제 공시 데이터를 조회합니다.');
        if (dom.dartApiCard) dom.dartApiCard.style.display = 'none';
        loadFinancialsData(true);
      });
    }

    if (dom.btnDeleteDartKey) {
      dom.btnDeleteDartKey.addEventListener('click', () => {
        if (confirm('등록된 OpenDART API 인증키를 삭제하시겠습니까?')) {
          localStorage.removeItem('cg_opendart_api_key');
          if (dom.dartApiKeyInput) dom.dartApiKeyInput.value = '';
          alert('OpenDART 인증키가 삭제되었습니다.');
          loadFinancialsData(true);
        }
      });
    }

    // 키보드 단축키: input에 포커스되지 않은 경우 작동
    window.addEventListener('keydown', e => {
      // 1) 입력 요소에 포커스된 경우 단축키 동작 전면 차단
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;

      // 차트게임 탭이 활성화되지 않은 경우 무시
      if (!dom.pane || dom.pane.style.display === 'none') return;

      const key = e.key.toUpperCase();
      if (key === 'B') {
        e.preventDefault();
        executeBuy();
      } else if (key === 'H' || e.key === ' ' || e.key === 'ArrowRight') {
        e.preventDefault();
        nextTurn();
      } else if (key === 'S') {
        e.preventDefault();
        executeSell();
      } else if (key === 'R') {
        e.preventDefault();
        toggleOrderMode();
      }
    });
  }

  function toggleOrderMode() {
    state.orderMode = state.orderMode === 'NORMAL' ? 'RR' : 'NORMAL';
    if (dom.orderModeTabs) {
      dom.orderModeTabs.querySelectorAll('.cg-mode-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.mode === state.orderMode);
      });
    }
    if (dom.rrInputsArea) {
      dom.rrInputsArea.style.display = state.orderMode === 'RR' ? 'grid' : 'none';
    }
  }

  function applyIndicatorModalSettings() {
    // MA 1~5
    const maIds = [1, 2, 3, 4, 5];
    maIds.forEach((id, idx) => {
      const chk = document.getElementById(`cgCfgMa${id}On`);
      const input = document.getElementById(`cgCfgMa${id}Period`);
      if (chk && input) {
        state.indicators.ma.lines[idx].on = chk.checked;
        state.indicators.ma.lines[idx].period = parseInt(input.value || '20', 10);
      }
    });

    // 거래량
    const volChk = document.getElementById('cgCfgVolOn');
    const volMa = document.getElementById('cgCfgVolMaPeriod');
    if (volChk) state.indicators.vol.on = volChk.checked;
    if (volMa) state.indicators.vol.maPeriod = parseInt(volMa.value || '20', 10);

    // RSI
    const rsiChk = document.getElementById('cgCfgRsiOn');
    const rsiP = document.getElementById('cgCfgRsiPeriod');
    const rsiOb = document.getElementById('cgCfgRsiOverbought');
    const rsiOs = document.getElementById('cgCfgRsiOversold');
    if (rsiChk) state.indicators.rsi.on = rsiChk.checked;
    if (rsiP) state.indicators.rsi.period = parseInt(rsiP.value || '14', 10);
    if (rsiOb) state.indicators.rsi.overbought = parseInt(rsiOb.value || '70', 10);
    if (rsiOs) state.indicators.rsi.oversold = parseInt(rsiOs.value || '30', 10);

    // 엔벨로프
    const envChk = document.getElementById('cgCfgEnvOn');
    const envP = document.getElementById('cgCfgEnvPeriod');
    const envR = document.getElementById('cgCfgEnvRatio');
    const envShowUpper = document.getElementById('cgEnvShowUpper');
    const envShowMid = document.getElementById('cgEnvShowMid');
    const envShowLower = document.getElementById('cgEnvShowLower');
    if (envChk) state.indicators.env.on = envChk.checked;
    if (envP) state.indicators.env.period = parseInt(envP.value || '20', 10);
    if (envR) state.indicators.env.ratio = parseFloat(envR.value || '10');
    if (envShowUpper) state.indicators.env.showUpper = envShowUpper.checked;
    if (envShowMid) state.indicators.env.showMid = envShowMid.checked;
    if (envShowLower) state.indicators.env.showLower = envShowLower.checked;

    // Super Trend
    const stChk = document.getElementById('cgCfgStOn');
    const stP = document.getElementById('cgCfgStPeriod');
    const stM = document.getElementById('cgCfgStMultiplier');
    if (stChk) state.indicators.st.on = stChk.checked;
    if (stP) state.indicators.st.period = parseInt(stP.value || '10', 10);
    if (stM) state.indicators.st.multiplier = parseFloat(stM.value || '3.0');

    // 일목균형표
    const ichiChk = document.getElementById('cgCfgIchiOn');
    const ichiC = document.getElementById('cgCfgIchiConversion');
    const ichiB = document.getElementById('cgCfgIchiBase');
    const ichiS = document.getElementById('cgCfgIchiSpanB');
    if (ichiChk) state.indicators.ichimoku.on = ichiChk.checked;
    if (ichiC) state.indicators.ichimoku.conversion = parseInt(ichiC.value || '9', 10);
    if (ichiB) state.indicators.ichimoku.base = parseInt(ichiB.value || '26', 10);
    if (ichiS) state.indicators.ichimoku.spanB = parseInt(ichiS.value || '52', 10);

    // 툴바 버튼 동기화
    if (dom.toolMa) dom.toolMa.classList.toggle('active', state.indicators.ma.on);
    if (dom.toolEnv) dom.toolEnv.classList.toggle('active', state.indicators.env.on);
    if (dom.toolSt) dom.toolSt.classList.toggle('active', state.indicators.st.on);
    if (dom.toolIchimoku) dom.toolIchimoku.classList.toggle('active', state.indicators.ichimoku.on);
    if (dom.toolRsi) dom.toolRsi.classList.toggle('active', state.indicators.rsi.on);
    if (dom.toolVol) dom.toolVol.classList.toggle('active', state.indicators.vol.on);

    // 패널 가시성 및 타임스케일 동기화
    if (dom.rsiPane) dom.rsiPane.style.display = state.indicators.rsi.on ? '' : 'none';
    if (dom.volumePane) dom.volumePane.style.display = state.indicators.vol.on ? '' : 'none';
    updateTimeScaleVisibility();
    handleResize();
  }

  // ─────────────────────────────────────────────────────────────
  // 10. 티커 자동완성 Datalist 로드 및 모듈 초기화
  // ─────────────────────────────────────────────────────────────
  async function loadTickerDatalist() {
    try {
      const res = await fetch('/api/chart_game/tickers');
      if (!res.ok) return;
      const data = await res.json();
      if (!dom.tickerDatalist || !data) return;

      let html = '<option value="RANDOM">🎲 랜덤 종목 (한국/미국 50종)</option>';
      if (Array.isArray(data.kr_stocks)) {
        data.kr_stocks.forEach(s => {
          const cleanTicker = s.ticker.replace(/\.(KS|KQ)$/i, '');
          html += `<option value="${cleanTicker}">${s.name} (${s.ticker})</option>`;
        });
      }
      if (Array.isArray(data.us_stocks)) {
        data.us_stocks.forEach(s => {
          html += `<option value="${s.ticker}">${s.name} (${s.ticker})</option>`;
        });
      }
      dom.tickerDatalist.innerHTML = html;
    } catch (e) {
      // 실패 시 HTML에 하드코딩된 기본 datalist 유지
    }
  }

  const CAREER_STORAGE_KEY = 'cg_career_state_v1';
  const GAME_LOGS_STORAGE_KEY = 'cg_game_logs_v1';

  function loadLocalGameLogs() {
    try {
      const raw = localStorage.getItem(GAME_LOGS_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  function saveLocalGameLog(entry) {
    try {
      const logs = loadLocalGameLogs();
      logs.unshift(entry);
      localStorage.setItem(GAME_LOGS_STORAGE_KEY, JSON.stringify(logs.slice(0, 20)));
    } catch (e) {}
  }

  function loadCareerState() {
    try {
      const raw = localStorage.getItem(CAREER_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        return {
          gamesPlayed: Number(parsed.gamesPlayed) || 0,
          winsCount: Number(parsed.winsCount) || 0,
          avgWinPct: Number(parsed.avgWinPct) || 0,
          avgLossPct: Number(parsed.avgLossPct) || 0,
          nickname: parsed.nickname || '',
          currentCapital: parsed.currentCapital !== undefined ? Number(parsed.currentCapital) : 10000000
        };
      }
    } catch (e) {}
    return { gamesPlayed: 0, winsCount: 0, avgWinPct: 0, avgLossPct: 0, nickname: '', currentCapital: 10000000 };
  }

  function saveCareerState(career) {
    try {
      localStorage.setItem(CAREER_STORAGE_KEY, JSON.stringify(career));
    } catch (e) {}
  }

  async function fetchCareerProfileFromDB() {
    const user = window.sbUser;
    const sb = window.sbClient;
    if (!user || !sb) {
      updateLobbyCareerUI();
      return;
    }

    try {
      const { data, error } = await sb
        .from('cg_career_profiles')
        .select('*')
        .eq('user_id', user.id)
        .maybeSingle();

      if (error) throw error;

      const defaultNick = (user.email || 'trader').split('@')[0];
      if (!data) {
        const initProfile = {
          user_id: user.id,
          nickname: defaultNick,
          current_capital: 10000000,
          games_count: 0,
          wins_count: 0,
          avg_win_pct: 0,
          avg_loss_pct: 0
        };
        try {
          await sb.from('cg_career_profiles').upsert(initProfile, { onConflict: 'user_id' });
        } catch (e) {}

        saveCareerState({
          gamesPlayed: 0,
          winsCount: 0,
          avgWinPct: 0,
          avgLossPct: 0,
          nickname: defaultNick,
          currentCapital: 10000000
        });
      } else {
        saveCareerState({
          gamesPlayed: Number(data.games_count) || 0,
          winsCount: Number(data.wins_count) || 0,
          avgWinPct: Number(data.avg_win_pct) || 0,
          avgLossPct: Number(data.avg_loss_pct) || 0,
          nickname: data.nickname || defaultNick,
          currentCapital: data.current_capital !== undefined ? Number(data.current_capital) : 10000000
        });
      }
    } catch (err) {
      console.warn('[ChartGame] Supabase 커리어 프로필 조회 실패 (localStorage 폴백 사용):', err);
    }

    updateLobbyCareerUI();
    if (state.gameMode === 'career') {
      syncCapitalControlForMode();
    }
  }

  async function recordCareerGameResult({ ticker, returnPct, profitAmount, endCapital }) {
    const career = loadCareerState();
    const prevGames = career.gamesPlayed || 0;
    const prevWins = career.winsCount || 0;
    const prevLosses = Math.max(0, prevGames - prevWins);

    const isWin = profitAmount > 0;
    const nextGames = prevGames + 1;
    const nextWins = prevWins + (isWin ? 1 : 0);

    let nextAvgWin = career.avgWinPct || 0;
    let nextAvgLoss = career.avgLossPct || 0;
    if (isWin) {
      nextAvgWin = ((nextAvgWin * prevWins) + returnPct) / Math.max(1, nextWins);
    } else if (returnPct < 0) {
      const nextLosses = prevLosses + 1;
      nextAvgLoss = ((nextAvgLoss * prevLosses) + returnPct) / Math.max(1, nextLosses);
    }

    const updatedLocal = {
      gamesPlayed: nextGames,
      winsCount: nextWins,
      avgWinPct: Number(nextAvgWin.toFixed(2)),
      avgLossPct: Number(nextAvgLoss.toFixed(2)),
      nickname: career.nickname || (window.sbUser?.email || 'trader').split('@')[0],
      currentCapital: endCapital
    };

    // 1) localStorage 즉시 저장 (폴백 보장)
    saveCareerState(updatedLocal);
    saveLocalGameLog({
      created_at: new Date().toISOString(),
      ticker,
      return_pct: returnPct,
      profit_amount: profitAmount,
      end_capital: endCapital
    });
    syncCapitalControlForMode();
    updateLobbyCareerUI();
    if (dom.gameLogsCollapse && dom.gameLogsCollapse.style.display !== 'none') {
      loadAndRenderGameLogs();
    }

    // 2) Supabase DB (cg_game_logs + cg_career_profiles) 동기화
    const user = window.sbUser;
    const sb = window.sbClient;
    if (!user || !sb) return;

    try {
      await sb.from('cg_game_logs').insert({
        user_id: user.id,
        mode: 'CAREER',
        ticker,
        return_pct: returnPct,
        profit_amount: profitAmount,
        end_capital: endCapital
      });
    } catch (err) {
      console.warn('[ChartGame] cg_game_logs insert 실패 (로컬 저장 유지):', err);
    }

    try {
      await sb.from('cg_career_profiles').upsert({
        user_id: user.id,
        nickname: updatedLocal.nickname,
        current_capital: endCapital,
        games_count: nextGames,
        wins_count: nextWins,
        avg_win_pct: updatedLocal.avgWinPct,
        avg_loss_pct: updatedLocal.avgLossPct,
        updated_at: new Date().toISOString()
      }, { onConflict: 'user_id' });
    } catch (err) {
      console.warn('[ChartGame] cg_career_profiles upsert 실패 (로컬 저장 유지):', err);
    }
  }

  function getCareerTier(capital) {
    const cap = Number(capital) || 0;
    if (cap >= 100000000) return { name: 'ORACLE', cls: 'tier-oracle' };
    if (cap >= 50000000) return { name: 'PLATINUM', cls: 'tier-platinum' };
    if (cap >= 30000000) return { name: 'GOLD', cls: 'tier-gold' };
    if (cap >= 15000000) return { name: 'SILVER', cls: 'tier-silver' };
    return { name: 'BRONZE', cls: 'tier-bronze' };
  }

  function renderMyStatsCard(career) {
    const c = career || loadCareerState();
    const nick = (c.nickname || (window.sbUser?.email || '').split('@')[0] || '트레이더').trim();
    const games = Number(c.gamesPlayed) || 0;
    const wins = Number(c.winsCount) || 0;
    const losses = Math.max(0, games - wins);
    const avgWin = Number(c.avgWinPct) || 0;
    const avgLoss = Number(c.avgLossPct) || 0;

    if (dom.statsNicknameTitle) {
      dom.statsNicknameTitle.textContent = `${nick}의 트레이딩 성적`;
    }
    if (dom.statsGamesBadge) {
      dom.statsGamesBadge.textContent = `${games}게임`;
    }

    const winRate = games > 0 ? (wins / games) * 100 : 0;
    const avgReturn = games > 0 ? ((avgWin * wins) + (avgLoss * losses)) / games : 0;
    const payoffRatio = Math.abs(avgLoss) > 0.001
      ? Math.abs(avgWin / avgLoss)
      : (avgWin > 0 ? avgWin : 0);
    const tpi = (winRate / 100.0) * payoffRatio;

    if (dom.winRateRingText) {
      dom.winRateRingText.textContent = `${Math.round(winRate)}%`;
    }
    if (dom.winRateRingCircle) {
      const circumference = 2 * Math.PI * 32; // ~201.06
      const clamped = Math.max(0, Math.min(100, winRate));
      dom.winRateRingCircle.style.strokeDasharray = circumference.toFixed(2);
      dom.winRateRingCircle.style.strokeDashoffset = (circumference * (1 - clamped / 100)).toFixed(2);
    }

    if (dom.statsAvgReturn) {
      dom.statsAvgReturn.textContent = `${avgReturn >= 0 ? '+' : ''}${avgReturn.toFixed(1)}%`;
      dom.statsAvgReturn.className = `cg-stats-kpi-val ${avgReturn > 0 ? 'pos' : (avgReturn < 0 ? 'neg' : '')}`;
    }
    if (dom.statsPayoffRatio) {
      dom.statsPayoffRatio.textContent = payoffRatio.toFixed(2);
    }
    if (dom.statsTpiScore) {
      dom.statsTpiScore.textContent = tpi.toFixed(2);
    }
  }

  async function saveNewNickname(newNick) {
    const cleanNick = (newNick || '').trim().slice(0, 20);
    if (!cleanNick) return;

    const career = loadCareerState();
    career.nickname = cleanNick;
    saveCareerState(career);
    renderMyStatsCard(career);

    if (window.sbClient && window.sbUser) {
      try {
        await window.sbClient.from('cg_career_profiles').upsert({
          user_id: window.sbUser.id,
          nickname: cleanNick,
          current_capital: career.currentCapital,
          games_count: career.gamesPlayed,
          wins_count: career.winsCount,
          avg_win_pct: career.avgWinPct,
          avg_loss_pct: career.avgLossPct,
          updated_at: new Date().toISOString()
        }, { onConflict: 'user_id' });
      } catch (err) {
        console.warn('[ChartGame] Supabase 닉네임 업데이트 실패 (로컬 저장 유지):', err);
      }
    }
  }

  async function loadAndRenderGameLogs() {
    if (!dom.gameLogsTableBody) return;

    let rows = [];
    if (window.sbClient && window.sbUser) {
      try {
        const { data, error } = await window.sbClient
          .from('cg_game_logs')
          .select('created_at, ticker, return_pct, profit_amount, end_capital')
          .eq('user_id', window.sbUser.id)
          .order('created_at', { ascending: false })
          .limit(20);
        if (!error && Array.isArray(data)) {
          rows = data;
        }
      } catch (err) {
        console.warn('[ChartGame] Supabase 게임 기록 조회 실패 (localStorage 폴백):', err);
      }
    }

    if (rows.length === 0) {
      rows = loadLocalGameLogs().slice(0, 20);
    }

    if (rows.length === 0) {
      dom.gameLogsTableBody.innerHTML = '<tr><td colspan="5" class="cg-logs-empty">아직 기록된 게임이 없습니다.</td></tr>';
      return;
    }

    dom.gameLogsTableBody.innerHTML = rows.map(r => {
      const dtStr = r.created_at ? String(r.created_at).slice(0, 10) : '-';
      const ret = Number(r.return_pct || 0);
      const profit = Number(r.profit_amount || 0);
      const endCap = Number(r.end_capital || 0);
      const cls = ret >= 0 ? 'style="color:#34d399;"' : 'style="color:#f87171;"';
      return `
        <tr>
          <td>${dtStr}</td>
          <td style="font-weight:700;">${escapeHtml(r.ticker || '-')}</td>
          <td ${cls}>${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%</td>
          <td ${cls}>${profit >= 0 ? '+' : ''}${Math.round(profit).toLocaleString()}원</td>
          <td>${Math.round(endCap).toLocaleString()}원</td>
        </tr>
      `;
    }).join('');
  }

  let activeHofPeriod = 'all';

  function formatHofCapital(cap) {
    const val = Math.round(Number(cap) || 0);
    if (val >= 100000000) {
      const eok = Math.floor(val / 100000000);
      const man = Math.round((val % 100000000) / 10000);
      return man > 0 ? `${eok}억 ${man.toLocaleString()}만 원` : `${eok}억 원`;
    }
    if (val >= 10000) {
      return `${Math.round(val / 10000).toLocaleString()}만 원`;
    }
    return `${val.toLocaleString()}원`;
  }

  function renderHofPodiumSlot(slotEl, entry) {
    if (!slotEl) return;
    const nickEl = slotEl.querySelector('.cg-podium-nick');
    const capEl = slotEl.querySelector('.cg-podium-cap');
    if (!entry) {
      if (nickEl) {
        nickEl.textContent = '도전자 대기 중';
        nickEl.classList.add('waiting');
      }
      if (capEl) capEl.textContent = '-';
      return;
    }
    if (nickEl) {
      nickEl.textContent = entry.nickname || '익명 트레이더';
      nickEl.classList.remove('waiting');
    }
    if (capEl) {
      capEl.textContent = formatHofCapital(entry.current_capital);
    }
  }

  async function fetchAndRenderHallOfFame(period = activeHofPeriod) {
    activeHofPeriod = period || 'all';
    if (dom.hofFilterBadge) {
      const badgeMap = {
        all: '커리어 전체 부문',
        week: '주간 부문 (최근 7일)',
        month: '월간 부문 (최근 30일)'
      };
      dom.hofFilterBadge.textContent = badgeMap[activeHofPeriod] || '커리어 전체 부문';
    }

    let entries = [];
    if (window.sbClient) {
      try {
        let query = window.sbClient
          .from('cg_career_profiles')
          .select('user_id, nickname, current_capital, games_count, updated_at')
          .gt('games_count', 0)
          .order('current_capital', { ascending: false })
          .limit(20);

        if (activeHofPeriod === 'week' || activeHofPeriod === 'month') {
          const days = activeHofPeriod === 'week' ? 7 : 30;
          const cutoff = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
          query = query.gte('updated_at', cutoff);
        }

        const { data, error } = await query;
        if (!error && Array.isArray(data)) {
          entries = data;
        }
      } catch (err) {
        console.warn('[ChartGame] 명예의 전당 조회 실패:', err);
      }
    }

    // Supabase 미연결 또는 빈 응답 시 로컬 커리어 기록이 있으면 표시
    if (entries.length === 0) {
      const localCareer = loadCareerState();
      if (localCareer.gamesPlayed > 0) {
        entries = [{
          user_id: window.sbUser?.id || 'local',
          nickname: localCareer.nickname || '나 (로컬)',
          current_capital: localCareer.currentCapital,
          games_count: localCareer.gamesPlayed
        }];
      }
    }

    renderHofPodiumSlot(dom.hofPodium1, entries[0] || null);
    renderHofPodiumSlot(dom.hofPodium2, entries[1] || null);
    renderHofPodiumSlot(dom.hofPodium3, entries[2] || null);

    if (!dom.hofTableBody) return;
    const rest = entries.slice(3, 20);
    if (rest.length === 0) {
      dom.hofTableBody.innerHTML = '<tr><td colspan="5" class="cg-logs-empty">4위 이하 순위 데이터가 없습니다.</td></tr>';
      return;
    }

    const myId = window.sbUser ? window.sbUser.id : null;
    dom.hofTableBody.innerHTML = rest.map((row, idx) => {
      const rank = idx + 4;
      const tier = getCareerTier(row.current_capital);
      const isMe = myId && row.user_id === myId;
      return `
        <tr class="${isMe ? 'cg-hof-my-row' : ''}">
          <td style="font-family:'JetBrains Mono',monospace; font-weight:700;">#${rank}</td>
          <td><span class="cg-tier-badge ${tier.cls}">${tier.name}</span></td>
          <td>${escapeHtml(row.nickname || '트레이더')}${isMe ? ' <span style="color:#818cf8;font-size:0.72rem;">(나)</span>' : ''}</td>
          <td style="font-family:'JetBrains Mono',monospace;">${Number(row.games_count || 0)}게임</td>
          <td style="text-align:right; font-family:'JetBrains Mono',monospace; color:#34d399;">${formatHofCapital(row.current_capital)}</td>
        </tr>
      `;
    }).join('');
  }

  function updateLobbyCareerUI() {
    const career = loadCareerState();
    const tier = getCareerTier(career.currentCapital);
    if (dom.careerTierBadge) {
      dom.careerTierBadge.textContent = tier.name;
      dom.careerTierBadge.className = `cg-tier-badge ${tier.cls}`;
    }
    if (dom.careerCapitalVal) {
      dom.careerCapitalVal.textContent = `${Math.round(career.currentCapital).toLocaleString()}원`;
    }
    if (dom.careerGamesCount) {
      dom.careerGamesCount.textContent = `${career.gamesPlayed}회`;
    }
    renderMyStatsCard(career);
  }

  function syncCapitalControlForMode() {
    const isCareer = state.gameMode === 'career';
    if (dom.gameModeBadge) {
      dom.gameModeBadge.textContent = isCareer ? '커리어 모드' : '연습 모드';
      dom.gameModeBadge.classList.toggle('career', isCareer);
    }

    if (!dom.initCapitalInput) return;

    if (!isCareer) {
      dom.initCapitalInput.readOnly = false;
      if (dom.capitalLockIcon) dom.capitalLockIcon.style.display = 'none';
      if (dom.btnResetCapitalInGame) dom.btnResetCapitalInGame.style.display = 'none';
      return;
    }

    const career = loadCareerState();
    if (career.gamesPlayed === 0) {
      dom.initCapitalInput.readOnly = false;
      dom.initCapitalInput.value = Math.round(career.currentCapital || 10000000);
      if (dom.capitalLockIcon) dom.capitalLockIcon.style.display = 'none';
      if (dom.btnResetCapitalInGame) dom.btnResetCapitalInGame.style.display = 'none';
    } else {
      dom.initCapitalInput.readOnly = true;
      dom.initCapitalInput.value = Math.max(0, Math.round(career.currentCapital));
      if (dom.capitalLockIcon) dom.capitalLockIcon.style.display = 'inline-block';
      if (dom.btnResetCapitalInGame) dom.btnResetCapitalInGame.style.display = 'inline-flex';
    }
  }

  async function resetCareerToDefault(restartGame = false) {
    const nick = (window.sbUser?.email || 'trader').split('@')[0];
    const fresh = {
      gamesPlayed: 0,
      winsCount: 0,
      avgWinPct: 0,
      avgLossPct: 0,
      nickname: nick,
      currentCapital: 10000000
    };
    saveCareerState(fresh);
    updateLobbyCareerUI();
    syncCapitalControlForMode();

    if (window.sbClient && window.sbUser) {
      try {
        await window.sbClient.from('cg_career_profiles').upsert({
          user_id: window.sbUser.id,
          nickname: nick,
          current_capital: 10000000,
          games_count: 0,
          wins_count: 0,
          avg_win_pct: 0,
          avg_loss_pct: 0,
          updated_at: new Date().toISOString()
        }, { onConflict: 'user_id' });
      } catch (e) {}
    }

    if (restartGame && state.gameMode === 'career') {
      startNewGame();
    }
  }

  function enterGameMode(mode) {
    state.gameMode = mode === 'career' ? 'career' : 'practice';
    if (dom.lobbyView) dom.lobbyView.style.display = 'none';
    if (dom.gamePlayView) dom.gamePlayView.style.display = 'block';
    syncCapitalControlForMode();
    startNewGame();
  }

  function returnToLobby() {
    if (dom.gamePlayView) dom.gamePlayView.style.display = 'none';
    if (dom.lobbyView) dom.lobbyView.style.display = 'flex';
    updateLobbyCareerUI();
  }

  function setupLobbyAndCareerListeners() {
    if (dom.btnStartPractice) {
      dom.btnStartPractice.addEventListener('click', () => enterGameMode('practice'));
    }
    if (dom.btnStartCareer) {
      dom.btnStartCareer.addEventListener('click', () => {
        if (window.sbUser) {
          try { sessionStorage.removeItem('cg_pending_career'); } catch (e) {}
          state.pendingCareerEnter = false;
          enterGameMode('career');
          return;
        }
        state.pendingCareerEnter = true;
        try { sessionStorage.setItem('cg_pending_career', '1'); } catch (e) {}
        if (window.sbAuth && typeof window.sbAuth.openLoginModal === 'function') {
          window.sbAuth.openLoginModal();
        } else {
          alert('커리어 모드는 Google 로그인 후 이용할 수 있습니다.');
        }
      });
    }
    if (dom.btnResetCareer) {
      dom.btnResetCareer.addEventListener('click', () => {
        if (confirm('커리어 모드 누적 자본금과 플레이 기록을 1,000만 원으로 초기화하시겠습니까?')) {
          resetCareerToDefault(false);
        }
      });
    }
    if (dom.btnBackToLobby) {
      dom.btnBackToLobby.addEventListener('click', returnToLobby);
    }
    if (dom.btnResetCapitalInGame) {
      dom.btnResetCapitalInGame.addEventListener('click', () => {
        if (confirm('커리어 자본금을 1,000만 원으로 초기화하고 새 게임을 시작하시겠습니까?')) {
          resetCareerToDefault(true);
        }
      });
    }

    if (dom.btnEditNickname && dom.nickEditRow) {
      dom.btnEditNickname.addEventListener('click', () => {
        const isOpen = dom.nickEditRow.style.display !== 'none';
        dom.nickEditRow.style.display = isOpen ? 'none' : 'flex';
        if (!isOpen && dom.nickEditInput) {
          const career = loadCareerState();
          dom.nickEditInput.value = career.nickname || '';
          dom.nickEditInput.focus();
        }
      });
    }
    if (dom.btnCancelNickname && dom.nickEditRow) {
      dom.btnCancelNickname.addEventListener('click', () => {
        dom.nickEditRow.style.display = 'none';
      });
    }
    if (dom.btnSaveNickname && dom.nickEditInput) {
      dom.btnSaveNickname.addEventListener('click', async () => {
        await saveNewNickname(dom.nickEditInput.value);
        if (dom.nickEditRow) dom.nickEditRow.style.display = 'none';
      });
    }
    if (dom.nickEditInput) {
      dom.nickEditInput.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          await saveNewNickname(dom.nickEditInput.value);
          if (dom.nickEditRow) dom.nickEditRow.style.display = 'none';
        }
      });
    }

    if (dom.btnToggleLogs && dom.gameLogsCollapse) {
      dom.btnToggleLogs.addEventListener('click', () => {
        const isOpen = dom.gameLogsCollapse.style.display !== 'none';
        dom.gameLogsCollapse.style.display = isOpen ? 'none' : 'block';
        if (dom.logsChevron) dom.logsChevron.classList.toggle('open', !isOpen);
        if (!isOpen) {
          loadAndRenderGameLogs();
        }
      });
    }

    if (dom.hofPeriodTabs) {
      dom.hofPeriodTabs.querySelectorAll('.cg-pill-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          dom.hofPeriodTabs.querySelectorAll('.cg-pill-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          fetchAndRenderHallOfFame(btn.dataset.period || 'all');
        });
      });
    }
  }

  async function handleAuthUserReady(user) {
    if (!user) {
      updateLobbyCareerUI();
      return;
    }

    init();
    await fetchCareerProfileFromDB();

    let hasPendingFlag = false;
    try {
      hasPendingFlag = sessionStorage.getItem('cg_pending_career') === '1';
    } catch (e) {}

    if (state.pendingCareerEnter || hasPendingFlag) {
      state.pendingCareerEnter = false;
      try { sessionStorage.removeItem('cg_pending_career'); } catch (e) {}
      if (window.sbAuth && typeof window.sbAuth.closeLoginModal === 'function') {
        window.sbAuth.closeLoginModal();
      }
      const tabBtn = document.getElementById('tabBtnChartGame');
      if (tabBtn && !tabBtn.classList.contains('active')) {
        tabBtn.click();
      }
      enterGameMode('career');
    }
  }

  window.addEventListener('sb-auth-changed', (e) => {
    const user = e && e.detail ? e.detail.user : null;
    handleAuthUserReady(user);
  });

  function init() {
    if (state.initialized) return;
    initDom();
    setupEventListeners();
    setupLobbyAndCareerListeners();
    loadTickerDatalist();
    loadApiSettings();
    updateLobbyCareerUI();
    state.initialized = true;
  }

  // 탭 전환 시 로비 뷰 우선 표시 + Supabase 커리어 프로필 & 명예의 전당 동기화
  window.initChartGameIfNeeded = function () {
    init();
    fetchCareerProfileFromDB();
    fetchAndRenderHallOfFame(activeHofPeriod);

    let hasPendingFlag = false;
    try {
      hasPendingFlag = sessionStorage.getItem('cg_pending_career') === '1';
    } catch (e) {}

    if (window.sbUser && (hasPendingFlag || state.pendingCareerEnter)) {
      state.pendingCareerEnter = false;
      try { sessionStorage.removeItem('cg_pending_career'); } catch (e) {}
      if (window.sbAuth && typeof window.sbAuth.closeLoginModal === 'function') {
        window.sbAuth.closeLoginModal();
      }
      enterGameMode('career');
      return;
    }

    if (dom.gamePlayView && dom.gamePlayView.style.display !== 'none') {
      handleResize();
      triggerInsightUpdate(true);
    } else if (dom.lobbyView) {
      dom.lobbyView.style.display = 'flex';
    }
  };

  // ─────────────────────────────────────────────────────────────
  // 10-2. 우측 하단 인사이트 패널 (재무제표 & 뉴스/시황 시스템)
  // ─────────────────────────────────────────────────────────────

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatFinAmount(val, currency) {
    if (val === undefined || val === null || isNaN(val)) return '-';
    const num = Number(val);
    const isNeg = num < 0;
    const abs = Math.abs(num);

    if (currency === 'USD') {
      if (abs >= 1e9) {
        return `${isNeg ? '-' : ''}$${(abs / 1e9).toFixed(2)}B`;
      }
      if (abs >= 1e6) {
        return `${isNeg ? '-' : ''}$${(abs / 1e6).toFixed(1)}M`;
      }
      return `${isNeg ? '-' : ''}$${Math.round(abs).toLocaleString()}`;
    }

    // KRW
    if (abs >= 1e12) {
      const jo = Math.floor(abs / 1e12);
      const eok = Math.round((abs % 1e12) / 1e8);
      return `${isNeg ? '-' : ''}${jo}조${eok > 0 ? ' ' + eok.toLocaleString() + '억' : ''}원`;
    }
    if (abs >= 1e8) {
      return `${isNeg ? '-' : ''}${Math.round(abs / 1e8).toLocaleString()}억원`;
    }
    return `${isNeg ? '-' : ''}${Math.round(abs).toLocaleString()}원`;
  }

  function loadApiSettings() {
    try {
      const raw = localStorage.getItem('cgApiSettings');
      if (raw) {
        const saved = JSON.parse(raw);
        state.apiSettings = { ...state.apiSettings, ...saved };
      }
    } catch (e) {}

    if (dom.llmProvider) dom.llmProvider.value = state.apiSettings.llmProvider || 'gemini';
    if (dom.llmApiKey) dom.llmApiKey.value = state.apiSettings.llmApiKey || '';
    if (dom.naverClientId) dom.naverClientId.value = state.apiSettings.naverClientId || '';
    if (dom.naverClientSecret) dom.naverClientSecret.value = state.apiSettings.naverClientSecret || '';

    // OpenDART 저장된 키 UI 반영
    const savedDartKey = localStorage.getItem('cg_opendart_api_key') || '';
    if (dom.dartApiKeyInput) dom.dartApiKeyInput.value = savedDartKey;
  }

  function saveApiSettings() {
    if (dom.llmProvider) state.apiSettings.llmProvider = dom.llmProvider.value;
    if (dom.llmApiKey) state.apiSettings.llmApiKey = dom.llmApiKey.value.trim();
    if (dom.naverClientId) state.apiSettings.naverClientId = dom.naverClientId.value.trim();
    if (dom.naverClientSecret) state.apiSettings.naverClientSecret = dom.naverClientSecret.value.trim();

    try {
      localStorage.setItem('cgApiSettings', JSON.stringify(state.apiSettings));
    } catch (e) {}
  }

  function triggerInsightUpdate(force = false) {
    if (state.insightDebounceTimer) {
      clearTimeout(state.insightDebounceTimer);
    }
    state.insightDebounceTimer = setTimeout(() => {
      if (state.activeInsightTab === 'financials') {
        loadFinancialsData(force);
      } else {
        loadNewsData(force);
      }
    }, force ? 0 : 250);
  }

  async function loadFinancialsData(force = false) {
    const candle = getLastCandle();
    if (!candle || !state.tickerInfo) return;
    const ticker = state.tickerInfo.resolved_ticker || state.tickerInfo.ticker;
    const curDate = candle.time || candle.date;
    if (!ticker || !curDate) return;

    const dartApiKey = localStorage.getItem('cg_opendart_api_key') || '';
    const key = `${ticker}_${curDate}_${dartApiKey ? 'dart' : 'nodart'}`;
    if (!force && state.lastFinKey === key) return;
    state.lastFinKey = key;

    try {
      let url = `/api/chart_game/financials?ticker=${encodeURIComponent(ticker)}&date=${encodeURIComponent(curDate)}`;
      if (dartApiKey) {
        url += `&dart_api_key=${encodeURIComponent(dartApiKey)}`;
      }
      const res = await fetch(url);
      if (!res.ok) throw new Error('재무제표 조회 실패');
      const data = await res.json();
      if (data.status !== 'success') throw new Error(data.message || '오류');

      renderFinancialsUI(data, curDate);
    } catch (err) {
      console.warn('[Financials] load error:', err);
      renderFinancialsUI({ quarters: [], currency: state.currency }, curDate);
    }
  }

  function renderFinancialsUI(data, curDate) {
    const quarters = data.quarters || [];
    const currency = data.currency || state.currency;

    if (dom.finLatestBadge) {
      dom.finLatestBadge.textContent = data.latest_quarter ? `최신 실적: ${data.latest_quarter}` : '실적 공시 없음';
    }
    if (dom.finDateHint) {
      dom.finDateHint.textContent = `기준일: ${curDate}`;
    }

    // 데이터 출처 및 OpenDART 연동 상태 배지
    if (dom.finSourceBadge) {
      dom.finSourceBadge.classList.remove('sec', 'dart', 'nodart');
      const isUsd = (currency === 'USD') || (data.source && data.source.includes('SEC'));

      if (isUsd) {
        dom.finSourceBadge.classList.add('sec');
        dom.finSourceBadge.textContent = 'SEC 공시 연동됨';
        dom.finSourceBadge.title = '미국 증권거래위원회(SEC EDGAR) 공식 분기 공시 실적 연동';
        if (dom.btnDartApiToggle) dom.btnDartApiToggle.style.display = 'none';
      } else {
        // 한국 주식
        if (dom.btnDartApiToggle) dom.btnDartApiToggle.style.display = 'inline-flex';
        if (data.dart_required) {
          dom.finSourceBadge.classList.add('nodart');
          dom.finSourceBadge.textContent = 'OpenDART 미등록';
          dom.finSourceBadge.title = '클릭하여 OpenDART 공식 인증키를 등록하면 실제 분기 공시를 조회합니다.';
          // 한국 주식이고 키가 없을 때 최초 1회 카드 자동 오픈
          if (dom.dartApiCard && dom.dartApiCard.style.display === 'none' && !localStorage.getItem('cg_dart_card_shown')) {
            dom.dartApiCard.style.display = 'flex';
            localStorage.setItem('cg_dart_card_shown', '1');
          }
        } else {
          dom.finSourceBadge.classList.add('dart');
          dom.finSourceBadge.textContent = 'OpenDART 연동됨';
          dom.finSourceBadge.title = '금융감독원 OpenDART 전자공시 공식 분기 실적 연동';
        }
      }
    }

    if (!quarters || quarters.length === 0) {
      if (dom.finEmpty) dom.finEmpty.style.display = 'block';
      if (dom.finChartWrap) dom.finChartWrap.style.display = 'none';
      if (dom.finTable) dom.finTable.style.display = 'none';
      return;
    }

    if (dom.finEmpty) dom.finEmpty.style.display = 'none';
    if (dom.finChartWrap) dom.finChartWrap.style.display = 'flex';
    if (dom.finTable) dom.finTable.style.display = 'table';

    renderFinancialsSvg(quarters, currency);
    renderFinancialsTable(quarters, currency);
  }

  function renderFinancialsSvg(quarters, currency) {
    if (!dom.finSvgChart || !quarters || quarters.length === 0) return;

    const W = 340;
    const H = 135;
    const padT = 16;
    const padB = 22;
    const padL = 8;
    const padR = 8;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;
    const N = quarters.length;
    const groupW = chartW / N;

    // 최대/최소 금액 스케일 계산
    let maxVal = 1;
    let minVal = 0;
    quarters.forEach(q => {
      maxVal = Math.max(maxVal, q.revenue, q.operating_income, q.net_income);
      minVal = Math.min(minVal, q.operating_income, q.net_income);
    });
    const rangeVal = (maxVal - minVal) || 1;
    const yZero = padT + chartH * (maxVal / rangeVal);

    // 영업이익률 최대/최소 스케일 계산
    let maxMargin = 10;
    let minMargin = -5;
    quarters.forEach(q => {
      if (!isNaN(q.op_margin)) {
        maxMargin = Math.max(maxMargin, q.op_margin);
        minMargin = Math.min(minMargin, q.op_margin);
      }
    });
    const rangeMargin = (maxMargin - minMargin) || 1;

    let svgHtml = '';

    // 기준선 0 (yZero)
    svgHtml += `<line x1="${padL}" y1="${yZero}" x2="${W - padR}" y2="${yZero}" stroke="rgba(255,255,255,0.12)" stroke-dasharray="2 2" stroke-width="1" />`;

    // 막대 너비
    const barW = Math.max(6, Math.min(14, (groupW - 14) / 3));
    const marginPoints = [];

    quarters.forEach((q, i) => {
      const groupCenter = padL + i * groupW + groupW / 2;
      const xStart = groupCenter - (barW * 3 + 4) / 2;

      // 1) 매출액 바 (파랑)
      const revH = (q.revenue / rangeVal) * chartH;
      const revY = yZero - revH;
      svgHtml += `<rect x="${xStart}" y="${revY}" width="${barW}" height="${Math.max(1, revH)}" fill="#3b82f6" rx="2">
        <title>${q.quarter_label} 매출액: ${formatFinAmount(q.revenue, currency)}</title>
      </rect>`;

      // 2) 영업이익 바 (초록 / 음수 빨강)
      const opH = Math.abs((q.operating_income / rangeVal) * chartH);
      const opY = q.operating_income >= 0 ? yZero - opH : yZero;
      const opColor = q.operating_income >= 0 ? '#10b981' : '#ef4444';
      svgHtml += `<rect x="${xStart + barW + 2}" y="${opY}" width="${barW}" height="${Math.max(1, opH)}" fill="${opColor}" rx="2">
        <title>${q.quarter_label} 영업이익: ${formatFinAmount(q.operating_income, currency)}</title>
      </rect>`;

      // 3) 당기순익 바 (보라 / 음수 핑크)
      const netH = Math.abs((q.net_income / rangeVal) * chartH);
      const netY = q.net_income >= 0 ? yZero - netH : yZero;
      const netColor = q.net_income >= 0 ? '#a855f7' : '#f43f5e';
      svgHtml += `<rect x="${xStart + (barW + 2) * 2}" y="${netY}" width="${barW}" height="${Math.max(1, netH)}" fill="${netColor}" rx="2">
        <title>${q.quarter_label} 당기순익: ${formatFinAmount(q.net_income, currency)}</title>
      </rect>`;

      // X축 분기 라벨
      svgHtml += `<text x="${groupCenter}" y="${H - 6}" font-size="9" fill="#94a3b8" text-anchor="middle" font-family="'JetBrains Mono', monospace">${q.quarter_label}</text>`;

      // 영업이익률 포인트
      const marginY = padT + chartH * (1 - (q.op_margin - minMargin) / rangeMargin);
      marginPoints.push({ x: groupCenter, y: Math.max(padT + 4, Math.min(H - padB - 4, marginY)), val: q.op_margin });
    });

    // 영업이익률 라인 및 도트
    if (marginPoints.length > 1) {
      const d = marginPoints.map((pt, idx) => `${idx === 0 ? 'M' : 'L'} ${pt.x} ${pt.y}`).join(' ');
      svgHtml += `<path d="${d}" stroke="#f59e0b" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" />`;
    }

    marginPoints.forEach(pt => {
      svgHtml += `<circle cx="${pt.x}" cy="${pt.y}" r="3" fill="#f59e0b" stroke="#161b26" stroke-width="1.5">
        <title>영업이익률: ${pt.val.toFixed(1)}%</title>
      </circle>`;
      svgHtml += `<text x="${pt.x}" y="${Math.max(10, pt.y - 5)}" font-size="8.5" fill="#fbbf24" font-weight="700" text-anchor="middle" font-family="'JetBrains Mono', monospace">${pt.val.toFixed(1)}%</text>`;
    });

    dom.finSvgChart.innerHTML = svgHtml;
  }

  function renderFinancialsTable(quarters, currency) {
    if (!dom.finTableHeadRow || !dom.finTableBody || !quarters) return;

    // Head
    let headHtml = '<th>지표 항목</th>';
    quarters.forEach(q => {
      headHtml += `<th>${q.quarter_label}</th>`;
    });
    dom.finTableHeadRow.innerHTML = headHtml;

    // Body
    const rowsDef = [
      { label: '매출액', key: 'revenue', type: 'amount' },
      { label: '영업이익', key: 'operating_income', type: 'amount' },
      { label: '당기순이익', key: 'net_income', type: 'amount' },
      { label: '영업이익률', key: 'op_margin', type: 'ratio' },
      { label: '순이익률', key: 'net_margin', type: 'ratio' },
      { label: '자산총계', key: 'total_assets', type: 'amount' },
      { label: '부채총계', key: 'total_liabilities', type: 'amount' },
      { label: '자본총계', key: 'total_equity', type: 'amount' },
      { label: '부채비율', key: 'debt_ratio', type: 'ratio' },
      { label: '영업활동현금흐름', key: 'operating_cash_flow', type: 'amount' }
    ];

    let bodyHtml = '';
    rowsDef.forEach(row => {
      bodyHtml += `<tr><td>${row.label}</td>`;
      quarters.forEach(q => {
        const val = q[row.key];
        const isNeg = val !== undefined && val !== null && val < 0;
        let formatted = '-';
        if (val !== undefined && val !== null && !isNaN(val)) {
          if (row.type === 'amount') {
            formatted = formatFinAmount(val, currency);
          } else if (row.type === 'ratio') {
            formatted = `${Number(val).toFixed(1)}%`;
          }
        }
        bodyHtml += `<td class="${isNeg ? 'negative' : 'positive'}">${formatted}</td>`;
      });
      bodyHtml += '</tr>';
    });

    dom.finTableBody.innerHTML = bodyHtml;
  }

  async function loadNewsData(force = false) {
    const candle = getLastCandle();
    if (!candle || !state.tickerInfo) return;
    const ticker = state.tickerInfo.resolved_ticker || state.tickerInfo.ticker;
    const companyName = state.tickerInfo.name || ticker;
    const curDate = candle.time || candle.date;
    if (!ticker || !curDate) return;

    const key = `${ticker}_${curDate}_${state.newsDays}`;
    if (!force && state.lastNewsKey === key) return;
    state.lastNewsKey = key;

    // 로딩 UI
    if (dom.sentimentBadge) {
      dom.sentimentBadge.className = 'cg-sentiment-badge neutral';
      dom.sentimentBadge.textContent = '수집중';
    }
    if (dom.summaryOneliner) {
      dom.summaryOneliner.textContent = `${curDate} 기준 뉴스 및 시황 수집 중...`;
    }
    if (dom.summaryBullets) {
      dom.summaryBullets.innerHTML = '<li>관련 뉴스를 수집하고 분석 중입니다...</li>';
    }

    try {
      const res = await fetch('/api/chart_game/news_summary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: ticker,
          company_name: companyName,
          current_date: curDate,
          days: state.newsDays,
          llm_provider: state.apiSettings.llmProvider || 'gemini',
          llm_api_key: state.apiSettings.llmApiKey || '',
          naver_client_id: state.apiSettings.naverClientId || '',
          naver_client_secret: state.apiSettings.naverClientSecret || ''
        })
      });

      if (!res.ok) throw new Error('뉴스 요약 조회 실패');
      const data = await res.json();
      if (data.status !== 'success') throw new Error(data.message || '오류');

      renderNewsUI(data);
    } catch (err) {
      console.warn('[News] load error:', err);
      if (dom.sentimentBadge) {
        dom.sentimentBadge.className = 'cg-sentiment-badge neutral';
        dom.sentimentBadge.textContent = '조회 실패';
      }
      if (dom.summaryOneliner) {
        dom.summaryOneliner.textContent = '뉴스 데이터를 가져오지 못했습니다.';
      }
      if (dom.summaryBullets) {
        dom.summaryBullets.innerHTML = '<li>네트워크 연결 상태를 확인해 주세요.</li>';
      }
      if (dom.newsCount) dom.newsCount.textContent = '0';
      if (dom.newsList) dom.newsList.innerHTML = '<div class="cg-fin-empty">수집된 기사가 없습니다.</div>';
    }
  }

  function renderNewsUI(data) {
    if (!data) return;

    // 감성 배지
    if (dom.sentimentBadge) {
      const sent = data.sentiment || '중립';
      let cls = 'neutral';
      if (sent === '호재') cls = 'positive';
      else if (sent === '악재') cls = 'negative';
      dom.sentimentBadge.className = `cg-sentiment-badge ${cls}`;
      dom.sentimentBadge.textContent = sent;
    }

    // 한줄 요약
    if (dom.summaryOneliner) {
      dom.summaryOneliner.textContent = data.one_liner || `${data.current_date} 시황 요약`;
    }

    // 핵심 이슈 불릿
    if (dom.summaryBullets) {
      const bullets = data.bullets || [];
      if (bullets.length > 0) {
        dom.summaryBullets.innerHTML = bullets.map(b => `<li>${escapeHtml(b)}</li>`).join('');
      } else {
        dom.summaryBullets.innerHTML = '<li>수집된 핵심 이슈가 없습니다.</li>';
      }
    }

    // 기사 리스트
    const articles = data.articles || [];
    if (dom.newsCount) dom.newsCount.textContent = articles.length;

    if (dom.newsList) {
      if (articles.length === 0) {
        dom.newsList.innerHTML = '<div class="cg-fin-empty">해당 기간 동안 수집된 기사가 없습니다.</div>';
      } else {
        dom.newsList.innerHTML = articles.map(a => `
          <a href="${escapeHtml(a.link)}" target="_blank" rel="noopener noreferrer" class="cg-news-item">
            <span class="cg-news-item-title">${escapeHtml(a.title)}</span>
            <span class="cg-news-item-meta">
              <span>${escapeHtml(a.source)}</span>
              <span>${escapeHtml(a.date)}</span>
            </span>
          </a>
        `).join('');
      }
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 11. 커스텀 컬러 피커 엔진 (Adobe/PowerPoint 스타일)
  // ─────────────────────────────────────────────────────────────

  /** ── 색상 변환 유틸 ── **/
  const ColorUtil = {
    // HSV → RGB (0~1 범위)
    hsvToRgb(h, s, v) {
      h = h % 360;
      const c = v * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = v - c;
      let r = 0, g = 0, b = 0;
      if (h < 60)       { r = c; g = x; b = 0; }
      else if (h < 120) { r = x; g = c; b = 0; }
      else if (h < 180) { r = 0; g = c; b = x; }
      else if (h < 240) { r = 0; g = x; b = c; }
      else if (h < 300) { r = x; g = 0; b = c; }
      else              { r = c; g = 0; b = x; }
      return { r: Math.round((r + m) * 255), g: Math.round((g + m) * 255), b: Math.round((b + m) * 255) };
    },
    // RGB → HSV
    rgbToHsv(r, g, b) {
      r /= 255; g /= 255; b /= 255;
      const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
      let h = 0, s = max === 0 ? 0 : d / max, v = max;
      if (d !== 0) {
        if (max === r) h = ((g - b) / d + 6) % 6;
        else if (max === g) h = (b - r) / d + 2;
        else h = (r - g) / d + 4;
        h *= 60;
      }
      return { h, s, v };
    },
    // HEX → RGB
    hexToRgb(hex) {
      hex = hex.replace('#', '');
      if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
      const n = parseInt(hex, 16);
      if (isNaN(n)) return null;
      return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
    },
    // RGB → HEX
    rgbToHex(r, g, b) {
      return [r, g, b].map(x => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, '0')).join('').toUpperCase();
    },
    // HSV를 CSS hex 문자열로
    hsvToHex(h, s, v) {
      const { r, g, b } = this.hsvToRgb(h, s, v);
      return '#' + this.rgbToHex(r, g, b);
    }
  };

  /** ── localStorage 색상 저장/로드 ── **/
  const COLOR_STORAGE_KEY = 'cgIndicatorColors_v1';
  const DEFAULT_COLORS = {
    ma: ['#eab308', '#ef4444', '#10b981', '#3b82f6', '#a855f7'],
    stUp: '#10b981',
    stDn: '#ef4444'
  };

  function loadSavedColors() {
    try {
      const raw = localStorage.getItem(COLOR_STORAGE_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch { return null; }
  }

  function saveColors() {
    try {
      const data = {
        ma: state.indicators.ma.lines.map(l => l.color),
        stUp: state.indicators.st.colorUp || DEFAULT_COLORS.stUp,
        stDn: state.indicators.st.colorDn || DEFAULT_COLORS.stDn
      };
      localStorage.setItem(COLOR_STORAGE_KEY, JSON.stringify(data));
    } catch {}
  }

  function applyStoredColors() {
    const saved = loadSavedColors();
    if (!saved) return;
    if (Array.isArray(saved.ma)) {
      saved.ma.forEach((c, i) => {
        if (state.indicators.ma.lines[i]) state.indicators.ma.lines[i].color = c;
      });
    }
    if (saved.stUp) state.indicators.st.colorUp = saved.stUp;
    if (saved.stDn) state.indicators.st.colorDn = saved.stDn;
  }

  function resetColors() {
    DEFAULT_COLORS.ma.forEach((c, i) => {
      if (state.indicators.ma.lines[i]) state.indicators.ma.lines[i].color = c;
    });
    state.indicators.st.colorUp = DEFAULT_COLORS.stUp;
    state.indicators.st.colorDn = DEFAULT_COLORS.stDn;
    saveColors();
    syncSwatchUI();
    renderChart();
  }

  /** ── 스와치 버튼 UI 동기화 ── **/
  function syncSwatchUI() {
    state.indicators.ma.lines.forEach((line, i) => {
      const btn = document.getElementById(`cgSwatchMa${i + 1}`);
      if (btn) btn.style.background = line.color;
    });
    const stUp = document.getElementById('cgSwatchStUp');
    const stDn = document.getElementById('cgSwatchStDn');
    if (stUp) stUp.style.background = state.indicators.st.colorUp || DEFAULT_COLORS.stUp;
    if (stDn) stDn.style.background = state.indicators.st.colorDn || DEFAULT_COLORS.stDn;

    // MA 범례 점 색상 동기화
    state.indicators.ma.lines.forEach((line, i) => {
      const dot = document.querySelector(`#cgSwatchMa${i + 1}`);
      if (dot) dot.style.background = line.color;
    });
  }

  /** ── 컬러 피커 상태 ── **/
  const cpState = {
    h: 0, s: 1, v: 1,   // 현재 HSV
    origHex: '#ffffff',  // 열릴 때의 원본 색상
    onPreview: null,     // 실시간 미리보기 콜백 (hex) => void
    onApply: null        // 적용 콜백 (hex) => void
  };

  let cpDomCache = null;
  function getCP() {
    if (cpDomCache) return cpDomCache;
    cpDomCache = {
      overlay:    document.getElementById('cgColorPickerOverlay'),
      picker:     document.getElementById('cgCustomColorPicker'),
      swatchOrig: document.getElementById('cgcpSwatchOrig'),
      swatchCurr: document.getElementById('cgcpSwatchCurr'),
      hexInput:   document.getElementById('cgcpHexInput'),
      applyBtn:   document.getElementById('cgcpApplyBtn'),
      svField:    document.getElementById('cgcpSvField'),
      svCanvas:   document.getElementById('cgcpSvCanvas'),
      svHandle:   document.getElementById('cgcpSvHandle'),
      hueBar:     document.getElementById('cgcpHueBar'),
      hueHandle:  document.getElementById('cgcpHueHandle'),
      modeSelect: document.getElementById('cgcpModeSelect'),
      channels:   document.getElementById('cgcpChannels'),
      swatchComp: document.getElementById('cgcpSwatchCompare')
    };
    return cpDomCache;
  }

  /** ── 2D SV 그라데이션 그리기 ── **/
  function drawSvCanvas() {
    const cp = getCP();
    if (!cp.svCanvas) return;
    const W = cp.svField.clientWidth || 262;
    const H = cp.svField.clientHeight || 160;
    if (cp.svCanvas.width !== W) cp.svCanvas.width = W;
    if (cp.svCanvas.height !== H) cp.svCanvas.height = H;
    const ctx = cp.svCanvas.getContext('2d');
    // 순수 Hue 색상
    const hueRgb = ColorUtil.hsvToRgb(cpState.h, 1, 1);
    const hueColor = `rgb(${hueRgb.r},${hueRgb.g},${hueRgb.b})`;
    // 흰색 → Hue (좌→우)
    const gradH = ctx.createLinearGradient(0, 0, W, 0);
    gradH.addColorStop(0, '#ffffff');
    gradH.addColorStop(1, hueColor);
    ctx.fillStyle = gradH;
    ctx.fillRect(0, 0, W, H);
    // 투명 → 검정 (상→하)
    const gradV = ctx.createLinearGradient(0, 0, 0, H);
    gradV.addColorStop(0, 'rgba(0,0,0,0)');
    gradV.addColorStop(1, 'rgba(0,0,0,1)');
    ctx.fillStyle = gradV;
    ctx.fillRect(0, 0, W, H);
    // 핸들 위치 갱신
    cp.svHandle.style.left = `${cpState.s * 100}%`;
    cp.svHandle.style.top  = `${(1 - cpState.v) * 100}%`;
  }

  /** ── Hue 핸들 위치 갱신 ── **/
  function updateHueHandle() {
    const cp = getCP();
    if (!cp.hueHandle) return;
    cp.hueHandle.style.left = `${(cpState.h / 360) * 100}%`;
  }

  /** ── 채널 슬라이더 그리기 ── **/
  function drawChannelSliders() {
    const cp = getCP();
    if (!cp.channels) return;
    const mode = cp.modeSelect.value;
    const { r, g, b } = ColorUtil.hsvToRgb(cpState.h, cpState.s, cpState.v);

    const defs = mode === 'rgb'
      ? [
          { key: 'R', val: r,   min: 0, max: 255, getGrad: (v) => `linear-gradient(to right, rgb(0,${g},${b}), rgb(255,${g},${b}))` },
          { key: 'G', val: g,   min: 0, max: 255, getGrad: (v) => `linear-gradient(to right, rgb(${r},0,${b}), rgb(${r},255,${b}))` },
          { key: 'B', val: b,   min: 0, max: 255, getGrad: (v) => `linear-gradient(to right, rgb(${r},${g},0), rgb(${r},${g},255))` }
        ]
      : [
          { key: 'H', val: Math.round(cpState.h),       min: 0, max: 360, getGrad: () => 'linear-gradient(to right,#ff0000,#ffff00,#00ff00,#00ffff,#0000ff,#ff00ff,#ff0000)' },
          { key: 'S', val: Math.round(cpState.s * 100), min: 0, max: 100, getGrad: () => { const hRgb = ColorUtil.hsvToRgb(cpState.h,0,cpState.v), hRgb2 = ColorUtil.hsvToRgb(cpState.h,1,cpState.v); return `linear-gradient(to right,rgb(${hRgb.r},${hRgb.g},${hRgb.b}),rgb(${hRgb2.r},${hRgb2.g},${hRgb2.b}))`; } },
          { key: 'V', val: Math.round(cpState.v * 100), min: 0, max: 100, getGrad: () => { const hRgb = ColorUtil.hsvToRgb(cpState.h,cpState.s,0), hRgb2 = ColorUtil.hsvToRgb(cpState.h,cpState.s,1); return `linear-gradient(to right,rgb(${hRgb.r},${hRgb.g},${hRgb.b}),rgb(${hRgb2.r},${hRgb2.g},${hRgb2.b}))`; } }
        ];

    // 기존 채널 행 재사용 또는 생성
    if (cp.channels.children.length !== 3) {
      cp.channels.innerHTML = '';
      defs.forEach((d, idx) => {
        const row = document.createElement('div');
        row.className = 'cgcp-channel-row';
        row.dataset.idx = idx;
        row.innerHTML = `
          <span class="cgcp-channel-label" data-lbl></span>
          <div class="cgcp-channel-track" data-track>
            <div class="cgcp-channel-handle" data-handle></div>
          </div>
          <input type="number" class="cgcp-channel-num" data-num min="0" max="${d.max}">`;
        cp.channels.appendChild(row);
        // 슬라이더 드래그
        const track = row.querySelector('[data-track]');
        attachSliderDrag(track, idx, mode);
        // 숫자 입력
        const numInput = row.querySelector('[data-num]');
        numInput.addEventListener('change', () => onChannelNumChange(idx, parseFloat(numInput.value), mode));
        numInput.addEventListener('input', () => onChannelNumChange(idx, parseFloat(numInput.value), mode));
      });
    }

    // 값 업데이트
    Array.from(cp.channels.children).forEach((row, idx) => {
      const d = defs[idx];
      row.querySelector('[data-lbl]').textContent = d.key;
      const track = row.querySelector('[data-track]');
      track.style.background = d.getGrad(d.val);
      const pct = (d.val - d.min) / (d.max - d.min) * 100;
      row.querySelector('[data-handle]').style.left = `${pct}%`;
      const numInput = row.querySelector('[data-num]');
      numInput.max = d.max;
      if (document.activeElement !== numInput) numInput.value = d.val;
    });
  }

  function attachSliderDrag(trackEl, idx, mode) {
    const onMove = (e) => {
      const rect = trackEl.getBoundingClientRect();
      const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      onChannelDrag(idx, x, mode);
    };
    trackEl.addEventListener('mousedown', (e) => {
      onMove(e);
      const up = () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', up); };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', up);
    });
    trackEl.addEventListener('touchstart', (e) => { e.preventDefault(); onMove(e.touches[0]); }, { passive: false });
  }

  function onChannelDrag(idx, ratio, mode) {
    if (mode === 'rgb') {
      const { r, g, b } = ColorUtil.hsvToRgb(cpState.h, cpState.s, cpState.v);
      let nr = r, ng = g, nb = b;
      if (idx === 0) nr = Math.round(ratio * 255);
      if (idx === 1) ng = Math.round(ratio * 255);
      if (idx === 2) nb = Math.round(ratio * 255);
      const hsv = ColorUtil.rgbToHsv(nr, ng, nb);
      cpState.h = hsv.h; cpState.s = hsv.s; cpState.v = hsv.v;
    } else {
      if (idx === 0) cpState.h = ratio * 360;
      if (idx === 1) cpState.s = ratio;
      if (idx === 2) cpState.v = ratio;
    }
    cpUpdate('all');
  }

  function onChannelNumChange(idx, val, mode) {
    if (isNaN(val)) return;
    if (mode === 'rgb') {
      const { r, g, b } = ColorUtil.hsvToRgb(cpState.h, cpState.s, cpState.v);
      let nr = r, ng = g, nb = b;
      if (idx === 0) nr = Math.max(0, Math.min(255, val));
      if (idx === 1) ng = Math.max(0, Math.min(255, val));
      if (idx === 2) nb = Math.max(0, Math.min(255, val));
      const hsv = ColorUtil.rgbToHsv(nr, ng, nb);
      cpState.h = hsv.h; cpState.s = hsv.s; cpState.v = hsv.v;
    } else {
      if (idx === 0) cpState.h = Math.max(0, Math.min(360, val));
      if (idx === 1) cpState.s = Math.max(0, Math.min(100, val)) / 100;
      if (idx === 2) cpState.v = Math.max(0, Math.min(100, val)) / 100;
    }
    cpUpdate('no-num');
  }

  /** ── 전체 UI 동기화 ── **/
  function cpUpdate(skip) {
    const cp = getCP();
    const hex = ColorUtil.hsvToHex(cpState.h, cpState.s, cpState.v);
    // 현재 색상 스와치
    if (cp.swatchCurr) cp.swatchCurr.style.background = hex;
    // HEX 입력
    if (skip !== 'hex' && cp.hexInput && document.activeElement !== cp.hexInput) {
      cp.hexInput.value = hex.replace('#', '');
    }
    // SV 캔버스
    if (skip !== 'sv') { drawSvCanvas(); }
    // Hue 핸들
    updateHueHandle();
    // 채널 슬라이더
    drawChannelSliders();
    // 미리보기 콜백
    if (cpState.onPreview) cpState.onPreview(hex);
  }

  /** ── 2D SV 필드 드래그 ── **/
  function initSvDrag() {
    const cp = getCP();
    if (!cp.svField) return;
    const onMove = (e) => {
      const rect = cp.svField.getBoundingClientRect();
      const cx = e.clientX !== undefined ? e.clientX : e.touches[0].clientX;
      const cy = e.clientY !== undefined ? e.clientY : e.touches[0].clientY;
      cpState.s = Math.max(0, Math.min(1, (cx - rect.left) / rect.width));
      cpState.v = Math.max(0, Math.min(1, 1 - (cy - rect.top) / rect.height));
      cpUpdate('all');
    };
    cp.svField.addEventListener('mousedown', (e) => {
      onMove(e);
      const up = () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', up); };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', up);
    });
    cp.svField.addEventListener('touchstart', (e) => { e.preventDefault(); onMove(e); }, { passive: false });
    cp.svField.addEventListener('touchmove', (e) => { e.preventDefault(); onMove(e); }, { passive: false });
  }

  /** ── Hue 바 드래그 ── **/
  function initHueDrag() {
    const cp = getCP();
    if (!cp.hueBar) return;
    const onMove = (e) => {
      const rect = cp.hueBar.getBoundingClientRect();
      const cx = e.clientX !== undefined ? e.clientX : e.touches[0].clientX;
      cpState.h = Math.max(0, Math.min(360, ((cx - rect.left) / rect.width) * 360));
      cpUpdate('all');
    };
    cp.hueBar.addEventListener('mousedown', (e) => {
      onMove(e);
      const up = () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', up); };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', up);
    });
    cp.hueBar.addEventListener('touchstart', (e) => { e.preventDefault(); onMove(e); }, { passive: false });
    cp.hueBar.addEventListener('touchmove', (e) => { e.preventDefault(); onMove(e); }, { passive: false });
  }

  /** ── HEX 입력 처리 ── **/
  function initHexInput() {
    const cp = getCP();
    if (!cp.hexInput) return;
    cp.hexInput.addEventListener('input', () => {
      const hex = cp.hexInput.value.replace(/[^0-9a-fA-F]/g, '');
      cp.hexInput.value = hex;
      if (hex.length === 6) {
        const rgb = ColorUtil.hexToRgb(hex);
        if (rgb) {
          const hsv = ColorUtil.rgbToHsv(rgb.r, rgb.g, rgb.b);
          cpState.h = hsv.h; cpState.s = hsv.s; cpState.v = hsv.v;
          cpUpdate('hex');
        }
      }
    });
  }

  /** ── 모드 셀렉트 ── **/
  function initModeSelect() {
    const cp = getCP();
    if (!cp.modeSelect) return;
    cp.modeSelect.addEventListener('change', () => {
      cp.channels.innerHTML = ''; // 행 초기화 → drawChannelSliders에서 재생성
      drawChannelSliders();
    });
  }

  /** ── 오버레이 클릭 닫기 + 원본 복원 버튼 ── **/
  function initPickerEvents() {
    const cp = getCP();
    if (cp.overlay) {
      cp.overlay.addEventListener('click', () => closeColorPicker(false));
    }
    if (cp.swatchComp) {
      cp.swatchComp.addEventListener('click', () => {
        // 원본 색상으로 복원
        const rgb = ColorUtil.hexToRgb(cpState.origHex);
        if (rgb) {
          const hsv = ColorUtil.rgbToHsv(rgb.r, rgb.g, rgb.b);
          cpState.h = hsv.h; cpState.s = hsv.s; cpState.v = hsv.v;
          cpUpdate('all');
        }
      });
    }
    if (cp.applyBtn) {
      cp.applyBtn.addEventListener('click', () => closeColorPicker(true));
    }
  }

  let _cpInited = false;
  function ensurePickerInited() {
    if (_cpInited) return;
    initSvDrag();
    initHueDrag();
    initHexInput();
    initModeSelect();
    initPickerEvents();
    _cpInited = true;
  }

  /**
   * 컬러 피커 열기
   * @param {string} initialHex - 초기 색상 (예: '#ef4444')
   * @param {HTMLElement} anchorEl - 팝오버 위치 기준 버튼 엘리먼트
   * @param {function} onPreview - 실시간 미리보기 콜백 (hex) => void
   * @param {function} onApply - 확정 적용 콜백 (hex) => void
   */
  function openColorPicker(initialHex, anchorEl, onPreview, onApply) {
    ensurePickerInited();
    const cp = getCP();
    if (!cp.picker) return;

    // 상태 초기화
    const cleanHex = initialHex.startsWith('#') ? initialHex : '#' + initialHex;
    const rgb = ColorUtil.hexToRgb(cleanHex) || { r: 255, g: 255, b: 255 };
    const hsv = ColorUtil.rgbToHsv(rgb.r, rgb.g, rgb.b);
    cpState.h = hsv.h; cpState.s = hsv.s; cpState.v = hsv.v;
    cpState.origHex = cleanHex;
    cpState.onPreview = onPreview;
    cpState.onApply = onApply;

    // 원본 스와치
    if (cp.swatchOrig) cp.swatchOrig.style.background = cleanHex;

    // 채널 행 재생성 (모드 초기화)
    if (cp.channels) cp.channels.innerHTML = '';

    // 오버레이 + 피커 표시
    if (cp.overlay) cp.overlay.classList.add('show');
    cp.picker.classList.add('show');

    // 위치 계산 (앵커 아래)
    if (anchorEl) {
      const rect = anchorEl.getBoundingClientRect();
      const pw = 290, ph = 420;
      let left = rect.left;
      let top = rect.bottom + 6;
      if (left + pw > window.innerWidth - 10) left = window.innerWidth - pw - 10;
      if (top + ph > window.innerHeight - 10) top = rect.top - ph - 6;
      cp.picker.style.left = `${Math.max(6, left)}px`;
      cp.picker.style.top  = `${Math.max(6, top)}px`;
    }

    // 초기 렌더
    setTimeout(() => {
      drawSvCanvas();
      cpUpdate('all');
    }, 10);
  }

  function closeColorPicker(apply) {
    const cp = getCP();
    if (!cp.picker) return;
    if (apply && cpState.onApply) {
      const hex = ColorUtil.hsvToHex(cpState.h, cpState.s, cpState.v);
      cpState.onApply(hex);
    }
    cp.picker.classList.remove('show');
    if (cp.overlay) cp.overlay.classList.remove('show');
    cpState.onPreview = null;
    cpState.onApply = null;
  }

  // ─────────────────────────────────────────────────────────────
  // 12. 스와치 버튼 이벤트 연결 & localStorage 적용
  // ─────────────────────────────────────────────────────────────

  function setupColorSwatches() {
    // MA 스와치 버튼 (1~5)
    for (let i = 0; i < 5; i++) {
      const btn = document.getElementById(`cgSwatchMa${i + 1}`);
      if (!btn) continue;
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const maIdx = i;
        const currentColor = state.indicators.ma.lines[maIdx].color;

        openColorPicker(
          currentColor,
          btn,
          // 실시간 미리보기
          (hex) => {
            state.indicators.ma.lines[maIdx].color = hex;
            btn.style.background = hex;
            // 차트 라인 실시간 반영
            const seriesKey = `ma_${maIdx}`;
            if (state.indicatorSeries[seriesKey]) {
              state.indicatorSeries[seriesKey].applyOptions({ color: hex });
            }
            // 헤더 범례 색상 반영
            updateMaLegendColor(maIdx, hex);
          },
          // 적용
          (hex) => {
            state.indicators.ma.lines[maIdx].color = hex;
            btn.style.background = hex;
            const seriesKey = `ma_${maIdx}`;
            if (state.indicatorSeries[seriesKey]) {
              state.indicatorSeries[seriesKey].applyOptions({ color: hex });
            }
            updateMaLegendColor(maIdx, hex);
            saveColors();
          }
        );
      });
    }

    // Super Trend 상승 색상
    const stUpBtn = document.getElementById('cgSwatchStUp');
    if (stUpBtn) {
      stUpBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const currentColor = state.indicators.st.colorUp || DEFAULT_COLORS.stUp;
        openColorPicker(
          currentColor, stUpBtn,
          (hex) => {
            state.indicators.st.colorUp = hex;
            stUpBtn.style.background = hex;
            recolorSuperTrend();
          },
          (hex) => {
            state.indicators.st.colorUp = hex;
            stUpBtn.style.background = hex;
            recolorSuperTrend();
            saveColors();
          }
        );
      });
    }

    // Super Trend 하락 색상
    const stDnBtn = document.getElementById('cgSwatchStDn');
    if (stDnBtn) {
      stDnBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const currentColor = state.indicators.st.colorDn || DEFAULT_COLORS.stDn;
        openColorPicker(
          currentColor, stDnBtn,
          (hex) => {
            state.indicators.st.colorDn = hex;
            stDnBtn.style.background = hex;
            recolorSuperTrend();
          },
          (hex) => {
            state.indicators.st.colorDn = hex;
            stDnBtn.style.background = hex;
            recolorSuperTrend();
            saveColors();
          }
        );
      });
    }

    // 기본 색상 초기화 버튼
    const resetBtn = document.getElementById('cgBtnResetColors');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        if (confirm('모든 이평선과 Super Trend 색상을 기본값으로 초기화할까요?')) {
          resetColors();
        }
      });
    }
  }

  /** MA 범례 텍스트 옆 색상 점(dot) 업데이트 **/
  function updateMaLegendColor(maIdx, hex) {
    // 헤더 오버레이의 MA 아이템 색상 점
    const dots = document.querySelectorAll('.cg-ma-dot');
    if (dots[maIdx]) dots[maIdx].style.background = hex;
  }

  /** SuperTrend 데이터를 현재 색상으로 다시 칠하기 **/
  function recolorSuperTrend() {
    if (!state.indicatorSeries.stSeries) return;
    const visibleCandles = getVisibleCandles();
    if (visibleCandles.length === 0) return;
    const stData = calcSuperTrendColored(visibleCandles, state.indicators.st.period, state.indicators.st.multiplier);
    state.indicatorSeries.stSeries.setData(stData);
  }

  // ─────────────────────────────────────────────────────────────
  // renderSuperTrend 색상 패치 (colorUp/colorDn 반영)
  // ─────────────────────────────────────────────────────────────

  // calcSuperTrend 내 color 필드를 colorUp/colorDn 설정값으로 덮어씌움
  function calcSuperTrendColored(candles, period, multiplier) {
    const res = calcSuperTrend(candles, period, multiplier);
    const upColor = state.indicators.st.colorUp || DEFAULT_COLORS.stUp;
    const dnColor = state.indicators.st.colorDn || DEFAULT_COLORS.stDn;
    return res.map(item => ({
      ...item,
      color: item.color === '#10b981' ? upColor : dnColor
    }));
  }

  // ─────────────────────────────────────────────────────────────
  // 모듈 초기화 (DOM 준비 후 실행)
  // ─────────────────────────────────────────────────────────────
  function initColorSystem() {
    // 1) localStorage에서 저장된 색상 불러오기
    applyStoredColors();

    // 2) SuperTrend 기본 색상 초기화
    if (!state.indicators.st.colorUp) state.indicators.st.colorUp = DEFAULT_COLORS.stUp;
    if (!state.indicators.st.colorDn) state.indicators.st.colorDn = DEFAULT_COLORS.stDn;

    // 3) 스와치 버튼 이벤트 연결
    setupColorSwatches();

    // 4) 초기 UI 동기화
    syncSwatchUI();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { init(); initColorSystem(); });
  } else {
    init();
    initColorSystem();
  }
})();
