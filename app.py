import datetime
import os
import re
import threading
import time
import warnings
import numpy as np
import pandas as pd
import re
import requests
import yfinance as yf
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from naver_stock import fetch_all_stock_data, resolve_korean_ticker, search_korean_stocks
from cache import load_or_fetch_stock
from flask import request, jsonify
from bs4 import BeautifulSoup
import yfinance as yf


# pykrx가 설치된 환경이면 우선 사용, 없으면 yfinance로 자동 전환
try:
    from pykrx import stock as krx
    HAS_PYKRX = True
except ImportError:
    HAS_PYKRX = False


# ==============================================================================
# [Helper] 국내주식 종목명/종목코드 변환 및 조회 보조
# ==============================================================================
KR_NAME_TO_CODE = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "현대차": "005380",
    "기아": "000270",
    "NAVER": "035420",
    "네이버": "035420",
    "카카오": "035720",
    "셀트리온": "068270",
    "알테오젠": "196170",
    "LG에너지솔루션": "373220",
    "KB금융": "105560",
}

def resolve_kr_ticker(query: str):
    q = query.strip()
    # 이미 6자리 숫자 코드인 경우
    if re.fullmatch(r"\d{6}", q):
        try:
            url = f"https://finance.naver.com/item/main.naver?code={q}"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
            title_el = soup.select_one(".wrap_company h2 a")
            name = title_el.get_text(strip=True) if title_el else q
            return q, name
        except Exception:
            return q, q

    # 한글/영문 종목명 검색 (예: "sk이노베이션", "삼성전자")
    try:
        ac_url = "https://ac.stock.naver.com/ac"
        params = {"q": q, "target": "stock,ipo,index,marketindicator"}
        res = requests.get(ac_url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        items = res.json().get("items", [])
        for it in items:
            code = str(it.get("code", "")).strip()
            nation = str(it.get("nationCode", "")).upper()
            if re.fullmatch(r"\d{6}", code) and (not nation or nation == "KOR"):
                return code, it.get("name", q)
    except Exception:
        pass

    clean = q.upper().split(".")[0]
    return clean, q

warnings.filterwarnings('ignore')

app = Flask(__name__, static_folder='static', static_url_path='')
app.json.ensure_ascii = False
CORS(app)

try:
    from custom_quant import custom_quant_bp
    app.register_blueprint(custom_quant_bp)
except Exception as e:
    warnings.warn(f"Failed to load custom_quant blueprint: {e}")

try:
    from chart_game import chart_game_bp
    app.register_blueprint(chart_game_bp)
except Exception as e:
    warnings.warn(f"Failed to load chart_game blueprint: {e}")

# ── 상수 및 ETF 메타데이터 ──────────────────────────────────────
TICKER_INFO = {
    "SOXL": {"name": "SOXL", "name_kr": "필라델피아 반도체 3X", "category": "레버리지 ETF", "color": "#3b82f6", "inception": "2010-03-11"},
    "TQQQ": {"name": "TQQQ", "name_kr": "나스닥100 3X", "category": "레버리지 ETF", "color": "#ec4899", "inception": "2010-02-11"},
    "SOXX": {"name": "SOXX", "name_kr": "iShares 반도체 1X", "category": "지수 ETF", "color": "#60a5fa", "inception": "2001-07-10"},
    "QLD":  {"name": "QLD",  "name_kr": "나스닥100 2X", "category": "레버리지 ETF", "color": "#a855f7", "inception": "2006-06-21"},
    "QQQ":  {"name": "QQQ",  "name_kr": "Invesco 나스닥100 1X", "category": "지수 ETF", "color": "#06b6d4", "inception": "1999-03-10"},
    "SPY":  {"name": "SPY",  "name_kr": "S&P 500 1X", "category": "지수 ETF", "color": "#10b981", "inception": "1993-01-22"},
    "GLD":  {"name": "GLD",  "name_kr": "SPDR 금 현물", "category": "원자재 ETF", "color": "#f59e0b", "inception": "2004-11-18"},
    "SLV":  {"name": "SLV",  "name_kr": "iShares 은 현물", "category": "원자재 ETF", "color": "#94a3b8", "inception": "2006-04-21"},
    "KORU": {"name": "KORU", "name_kr": "MSCI 한국 3X", "category": "레버리지 ETF", "color": "#f97316", "inception": "2013-04-10"},
    "SOXS": {"name": "SOXS", "name_kr": "반도체 인버스 3X", "category": "인버스 ETF", "color": "#ef4444", "inception": "2010-03-11"},
    "SQQQ": {"name": "SQQQ", "name_kr": "나스닥100 인버스 3X", "category": "인버스 ETF", "color": "#dc2626", "inception": "2010-02-11"},
    "BIL":  {"name": "BIL",  "name_kr": "초단기 국채 1-3M (안전자산)", "category": "초단기채 ETF", "color": "#14b8a6", "inception": "2007-05-30"},
    "SGOV": {"name": "SGOV", "name_kr": "초단기 국채 0-3M (안전자산)", "category": "초단기채 ETF", "color": "#0ea5e9", "inception": "2020-05-26"},
    "TLT":  {"name": "TLT",  "name_kr": "미국 20년+ 장기국채", "category": "장기채 ETF", "color": "#8b5cf6", "inception": "2002-07-22"},
    "IEF":  {"name": "IEF",  "name_kr": "미국 7-10년 중기국채", "category": "중기채 ETF", "color": "#06b6d4", "inception": "2002-07-22"},
    "DBC":  {"name": "DBC",  "name_kr": "Invesco DB 원자재 지수", "category": "원자재 ETF", "color": "#eab308", "inception": "2006-02-03"},
    "005930.KS": {"name": "005930.KS", "name_kr": "삼성전자", "category": "국내주식", "color": "#1d4ed8", "inception": "1975-06-11"},
    "000660.KS": {"name": "000660.KS", "name_kr": "SK하이닉스", "category": "국내주식", "color": "#dc2626", "inception": "1996-12-26"},
    "VEA":  {"name": "VEA",  "name_kr": "Vanguard 선진국 주식 (ex-US)", "category": "해외주식 ETF", "color": "#2563eb", "inception": "2007-07-26"},
    "VWO":  {"name": "VWO",  "name_kr": "Vanguard 신흥국 주식", "category": "해외주식 ETF", "color": "#db2777", "inception": "2005-03-10"},
    "BND":  {"name": "BND",  "name_kr": "Vanguard 미국 종합채권", "category": "채권 ETF", "color": "#4f46e5", "inception": "2007-04-10"},
    "EFA":  {"name": "EFA",  "name_kr": "iShares 선진국 주식 (EAFE)", "category": "해외주식 ETF", "color": "#38bdf8", "inception": "2001-08-27"},
    "EEM":  {"name": "EEM",  "name_kr": "iShares 신흥국 주식 (MSCI)", "category": "해외주식 ETF", "color": "#f43f5e", "inception": "2003-04-14"},
    "AGG":  {"name": "AGG",  "name_kr": "iShares 미국 종합채권", "category": "채권 ETF", "color": "#6366f1", "inception": "2003-09-29"},
    "LQD":  {"name": "LQD",  "name_kr": "iShares 미국 투자등급 회사채", "category": "채권 ETF", "color": "#8b5cf6", "inception": "2002-07-30"},
    "TIP":  {"name": "TIP",  "name_kr": "iShares 미국 물가연동채 (TIPS)", "category": "채권 ETF", "color": "#10b981", "inception": "2003-12-05"},
    "IWM":  {"name": "IWM",  "name_kr": "iShares 러셀 2000 소형주", "category": "지수 ETF", "color": "#ea580c", "inception": "2000-05-26"},
    "VNQ":  {"name": "VNQ",  "name_kr": "Vanguard 미국 리츠/부동산", "category": "부동산 ETF", "color": "#d97706", "inception": "2004-09-29"},
    "SHY":  {"name": "SHY",  "name_kr": "iShares 미국 단기국채 1-3Y", "category": "단기채 ETF", "color": "#14b8a6", "inception": "2002-07-30"}
}

ALL_TICKERS = list(TICKER_INFO.keys())
PROXIES = ['^NDX', '^SOX', '^GSPC', '^TYX', '^TNX', '^IRX', 'GC=F', 'CL=F']
ALL_DOWNLOAD_TICKERS = sorted(list(set(ALL_TICKERS + PROXIES)))
SAFE_PROXY = "BIL"
BUNDLED_CACHE_FILE = os.path.join(os.path.dirname(__file__), "data_cache.csv")
CACHE_FILE = "/tmp/data_cache.csv" if os.environ.get("VERCEL") else BUNDLED_CACHE_FILE

# ── 전역 상태 ──────────────────────────────────────────────
_data: pd.DataFrame | None = None
_data_status = {
    "ready": False,
    "loading": False,
    "error": None,
    "source": "Yahoo Finance",
    "updated_at": None,
    "start_date": None,
    "end_date": None,
    "row_count": 0
}
_lock = threading.Lock()


# ── 동적 종목 다운로드 및 캐시 통합 ────────────────────────────
def _ensure_tickers_loaded(tickers: list[str]):
    """
    주어진 티커 목록 중 _data에 없는 티커가 있다면 Yahoo Finance에서 다운로드하여
    _data에 병합하고 data_cache.csv를 갱신합니다.
    """
    global _data
    with _lock:
        if _data is None:
            return
        current_cols = set(_data.columns)
        missing = [t.upper().strip() for t in tickers if t.upper().strip() not in current_cols]
    
    if not missing:
        return

    print(f"[YAHOO FINANCE] 추가 티커 동적 다운로드 진행: {missing}")
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    try:
        raw = yf.download(
            tickers=missing,
            start="2007-01-01",
            end=today_str,
            auto_adjust=True,
            progress=False
        )
        if isinstance(raw.columns, pd.MultiIndex):
            if 'Close' in raw.columns.levels[0]:
                new_df = raw['Close'].copy()
            else:
                new_df = raw.xs('Close', axis=1, level=0).copy()
        else:
            new_df = raw.copy()

        # 만약 단일 티커라 Series인 경우 DataFrame 변환
        if isinstance(new_df, pd.Series):
            new_df = new_df.to_frame(name=missing[0])
        elif len(missing) == 1 and len(new_df.columns) == 1:
            new_df.columns = missing

        new_df.index = pd.to_datetime(new_df.index)
        new_df.ffill(inplace=True)

        with _lock:
            for col in new_df.columns:
                col_name = str(col).strip()
                _data[col_name] = new_df[col]
            _data.ffill(inplace=True)
            _data.to_csv(CACHE_FILE)
            print(f"[CACHE] 추가 티커 반영 및 CSV 저장 완료. 전체 컬럼: {list(_data.columns)}")
    except Exception as e:
        print(f"[ERROR] 추가 티커 다운로드 중 오류: {e}")
        # 오류가 나더라도 이미 캐시에 존재하는 티커는 사용 가능하게 함


# ── 레버리지 ETF 및 자산 배분 ETF 상장 전 가상 데이터 합성 (Synthetic Stitching) ──
def _synthesize_leverage_etfs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Yahoo Finance 기초 지수(^NDX, ^SOX, ^GSPC, ^TYX, ^TNX, ^IRX)를 활용하여
    상장 이전(Pre-Inception) 과거 결측치 구간에 대해 가상 일일 수익률을 역산(Backward Compounding) 결합합니다.
    - 2010년 이후 실제 주가(Real Post-Inception Data)는 100% 원본 그대로 보존합니다.
    - QQQ, QLD, TQQQ, SQQQ: ^NDX 일일 수익률 기반 (*1, *2, *3, *-3), 1985년 이전은 ^GSPC 기반
    - SOXX, SOXL, SOXS: ^SOX 일일 수익률 기반 (*1, *3, *-3), 1994년 이전은 ^NDX/^GSPC 기반
    - SPY: ^GSPC 일일 수익률 기반 (*1.0)
    - TLT / IEF: ^TYX(30년물, D~17) 및 ^TNX(10년물, D~7.5) 금리 변동 역산
    - GLD / DBC / SLV: 금/원자재 선물 및 헤지 프록시 역산
    - SGOV / BIL: ^IRX(13주 단기국채 금리) 기준 일일 무위험 수익률 역산
    """
    df = df.copy()

    def _backward_compound(s_col: str, r_series: pd.Series, mult: float = 1.0, clamp_min: float = -0.99):
        if s_col not in df.columns:
            return
        # Yahoo Finance 배당/감자 보정 오류로 발생한 0 이하(음수) 가격을 결측치(NaN)로 초기화
        df.loc[df[s_col] <= 0, s_col] = np.nan
        first_idx = df[s_col].first_valid_index()
        if first_idx is None:
            return
        loc = df.index.get_loc(first_idx)
        for i in range(loc - 1, -1, -1):
            r = r_series.iloc[i + 1] if i + 1 < len(r_series) else 0.0
            if pd.isna(r) or np.isinf(r):
                df.loc[df.index[i], s_col] = df.loc[df.index[i + 1], s_col]
            else:
                r_eff = max(clamp_min, r * mult)
                df.loc[df.index[i], s_col] = df.loc[df.index[i + 1], s_col] / (1.0 + r_eff)

    # 0. S&P 500 마스터 지수
    gspc_r = df['^GSPC'].pct_change() if '^GSPC' in df.columns else None

    # 1. ^NDX (1985 이전 구간 ^GSPC 역산)
    if '^NDX' in df.columns and gspc_r is not None:
        _backward_compound('^NDX', gspc_r, mult=1.1)
    ndx_r = df['^NDX'].pct_change() if '^NDX' in df.columns else gspc_r

    # 2. ^SOX (1994 이전 구간 ^NDX 역산)
    if '^SOX' in df.columns and ndx_r is not None:
        _backward_compound('^SOX', ndx_r, mult=1.2)
    sox_r = df['^SOX'].pct_change() if '^SOX' in df.columns else ndx_r

    # 3. 미국 주식 및 나스닥 레버리지 ETF
    if gspc_r is not None:
        _backward_compound('SPY', gspc_r, mult=1.0)
    if ndx_r is not None:
        _backward_compound('QQQ', ndx_r, mult=1.0)
        _backward_compound('QLD', ndx_r, mult=2.0)
        _backward_compound('TQQQ', ndx_r, mult=3.0)
        _backward_compound('SQQQ', ndx_r, mult=-3.0)

    # 4. 반도체 레버리지 ETF
    if sox_r is not None:
        _backward_compound('SOXX', sox_r, mult=1.0)
        _backward_compound('SOXL', sox_r, mult=3.0)
        _backward_compound('SOXS', sox_r, mult=-3.0)

    # 5. 안전자산 BIL & SGOV (^IRX 13주 단기국채 금리 역산)
    if '^IRX' in df.columns:
        irx = df['^IRX'].ffill().bfill() / 100.0
        daily_safe_r = (1.0 + np.maximum(0.0001, irx)) ** (1.0 / 252.0) - 1.0
        _backward_compound('BIL', daily_safe_r, mult=1.0)
    elif 'BIL' in df.columns:
        daily_safe_r = pd.Series((1.0 + 0.028) ** (1.0 / 252.0) - 1.0, index=df.index)
        _backward_compound('BIL', daily_safe_r, mult=1.0)

    if 'BIL' in df.columns:
        bil_r = df['BIL'].pct_change()
        _backward_compound('SGOV', bil_r, mult=1.0)

    # 6. 국채 ETF (TLT, IEF)
    if '^TYX' in df.columns:
        tyx = df['^TYX'].ffill().bfill() / 100.0
        tlt_synth_r = -17.0 * tyx.diff() + (tyx.shift(1) / 252.0)
        _backward_compound('TLT', tlt_synth_r, mult=1.0)
    elif '^TNX' in df.columns:
        tnx = df['^TNX'].ffill().bfill() / 100.0
        tlt_synth_r = -17.0 * tnx.diff() + (tnx.shift(1) / 252.0)
        _backward_compound('TLT', tlt_synth_r, mult=1.0)

    if '^TNX' in df.columns:
        tnx = df['^TNX'].ffill().bfill() / 100.0
        ief_synth_r = -7.5 * tnx.diff() + (tnx.shift(1) / 252.0)
        _backward_compound('IEF', ief_synth_r, mult=1.0)

    # 7. 원자재 & 대체자산 (GLD, DBC, SLV, KORU)
    if 'GC=F' in df.columns:
        _backward_compound('GLD', df['GC=F'].pct_change(), mult=1.0)
    if gspc_r is not None:
        _backward_compound('GLD', gspc_r, mult=0.2)
    if 'CL=F' in df.columns:
        _backward_compound('DBC', df['CL=F'].pct_change(), mult=0.6)
    if gspc_r is not None:
        _backward_compound('DBC', gspc_r, mult=0.5)
    if 'GLD' in df.columns:
        _backward_compound('SLV', df['GLD'].pct_change(), mult=1.2)
    if gspc_r is not None:
        _backward_compound('KORU', gspc_r, mult=3.0)

    # 8. 국내 주식
    if gspc_r is not None:
        _backward_compound('005930.KS', gspc_r, mult=1.2)
    if sox_r is not None:
        _backward_compound('000660.KS', sox_r, mult=1.3)

    return df


# ── 데이터 로드 & 전처리 (Yahoo Finance 연동) ────────────────
def _load_or_fetch_data(force_download=False):
    global _data
    with _lock:
        if _data_status["loading"]:
            return
        _data_status["loading"] = True
        _data_status["error"] = None

    try:
        df = None
        # 1. 로컬 캐시 확인 (Vercel 임시 캐시 -> 내장 캐시 순으로 읽기)
        cache_path = CACHE_FILE if os.path.exists(CACHE_FILE) else BUNDLED_CACHE_FILE
        if not force_download and os.path.exists(cache_path):
            try:
                df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
                # 주요 티커 컬럼이 존재하는지 검증
                if all(t in df.columns for t in ['TQQQ', 'SOXL', 'BIL']):
                    if (df <= 0).any().any():
                        df = _synthesize_leverage_etfs(df)
                        try:
                            df.to_csv(CACHE_FILE)
                        except Exception:
                            pass
                    print(f"[CACHE] 로컬 캐시에서 데이터 로드 완료 ({len(df)} 행)")
                else:
                    df = None
            except Exception as e:
                print(f"[CACHE] 캐시 파일 읽기 실패: {e}")
                df = None

        # 2. 없거나 강제 다운로드 시 Yahoo Finance API 직접 수집 (1970-01-01부터)
        if df is None:
            print(f"[YAHOO FINANCE] yfinance 라이브러리를 통해 {len(ALL_DOWNLOAD_TICKERS)}개 ETF/종목 다운로드 시작 (1970-01-01 ~ 현재)...")
            today_str = datetime.date.today().strftime('%Y-%m-%d')
            
            raw = yf.download(
                tickers=ALL_DOWNLOAD_TICKERS,
                start="1970-01-01",
                end=today_str,
                auto_adjust=True,
                progress=False
            )

            if isinstance(raw.columns, pd.MultiIndex):
                if 'Close' in raw.columns.levels[0]:
                    df = raw['Close'].copy()
                else:
                    df = raw.xs('Close', axis=1, level=0).copy()
            else:
                df = raw.copy()

            # 전방향 보간 (휴일 처리)
            df.ffill(inplace=True)

            # 레버리지 ETF 상장 전 가상 데이터 역산 및 합성
            df = _synthesize_leverage_etfs(df)

            # CSV 캐시 저장
            try:
                df.to_csv(CACHE_FILE)
                print(f"[CACHE] Yahoo Finance 데이터 CSV 저장 완료: {CACHE_FILE}")
            except Exception as e:
                print(f"[CACHE] CSV 저장 실패: {e}")

        # 정렬 및 인덱스 정리
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)

        with _lock:
            _data = df
            _data_status["ready"] = True
            _data_status["loading"] = False
            _data_status["source"] = "Yahoo Finance (Synthetic & Auto Adjusted)"
            _data_status["updated_at"] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            _data_status["start_date"] = df.index[0].strftime('%Y-%m-%d')
            _data_status["end_date"] = df.index[-1].strftime('%Y-%m-%d')
            _data_status["row_count"] = len(df)

        print(f"[READY] Yahoo Finance 데이터 로드 완료: {_data_status['start_date']} ~ {_data_status['end_date']} (총 {len(df)} 거래일)")

    except Exception as e:
        with _lock:
            _data_status["ready"] = False
            _data_status["loading"] = False
            _data_status["error"] = str(e)
        print(f"[ERROR] Yahoo Finance 데이터 수집 실패: {e}")

# app.py (337행 부근에 추가)
def _ensure_data_ready() -> bool:
    """서버리스 콜드 스타트 시 메모리에 데이터가 없으면 즉시 캐시를 동기 로드합니다."""
    with _lock:
        if _data_status["ready"] and _data is not None:
            return True

    # 여러 경로 후보에서 data_cache.csv 탐색
    candidates = [
        CACHE_FILE,
        BUNDLED_CACHE_FILE,
        os.path.join(os.getcwd(), "data_cache.csv"),
    ]
    has_local_cache = any(os.path.exists(p) for p in candidates)

    # Vercel 환경인데 로컬 CSV 캐시조차 없으면 무한 대기 방지를 위해 즉시 에러 반환
    if os.environ.get("VERCEL") and not has_local_cache:
        with _lock:
            _data_status["ready"] = False
            _data_status["error"] = "배포 번들에 data_cache.csv 파일이 누락되었습니다."
        return False

    _load_or_fetch_data(force_download=False)
    with _lock:
        return bool(_data_status["ready"] and _data is not None)

# ── 연도별 MDD 및 최악의 해 계산 ─────────────────────────────
def _calc_worst_year_mdd(values: np.ndarray, dates: pd.DatetimeIndex):
    """
    각 연도별로 독립적인 MDD를 산출하여, 가장 낙폭이 심했던 최악의 해(Worst Year)와 그 해의 MDD를 반환
    """
    df_temp = pd.DataFrame({'val': values}, index=dates)
    years = sorted(list(set(dates.year)))
    
    worst_year = None
    worst_mdd = 0.0
    yearly_mdds = {}

    for yr in years:
        yr_vals = df_temp[df_temp.index.year == yr]['val'].values
        if len(yr_vals) < 2:
            continue
        peaks = np.maximum.accumulate(yr_vals)
        dd = (yr_vals - peaks) / peaks
        yr_mdd = float(np.min(dd)) * 100.0
        yearly_mdds[yr] = round(yr_mdd, 2)
        if yr_mdd < worst_mdd:
            worst_mdd = yr_mdd
            worst_year = yr

    return worst_year, round(worst_mdd, 2), yearly_mdds


# ── 보조 퀀트 지표 연산 (TR, CAGR, MDD, MAR, 최악의 해의 MDD) ─────
def _calc_perf_metrics(values: np.ndarray, invested: np.ndarray, dates: pd.DatetimeIndex, daily_ret: np.ndarray):
    n = len(values)
    if n < 2:
        return {}

    final_val = float(values[-1])
    total_inv = float(invested[-1])
    net_profit = final_val - total_inv
    
    # 1. TR (Total Return, 총 누적 수익률 %)
    total_ret_pct = (net_profit / total_inv) * 100.0 if total_inv > 0 else 0.0

    days = (dates[-1] - dates[0]).days
    years = max(days / 365.25, 0.08)

    # 2. CAGR (연평균 복리 수익률 %) - TWRR 연환산 기하평균 (장기 시계열 부동소수점 언더플로 방지를 위해 log-sum 사용)
    mean_daily = np.mean(daily_ret)
    std_daily = np.std(daily_ret)
    log_growth = np.sum(np.log(np.maximum(1e-12, 1.0 + daily_ret)))
    prod_growth = float(np.exp(log_growth))
    twrr_cagr = (prod_growth ** (252.0 / n) - 1.0) * 100.0 if n > 0 and prod_growth > 0 else 0.0

    # 3. MDD (전체 기간 최대 낙폭 %)
    peaks = np.maximum.accumulate(values)
    dd = (values - peaks) / peaks
    mdd_pct = float(np.min(dd)) * 100.0

    # 4. MAR Ratio (CAGR / |MDD|)
    mar_ratio = abs(twrr_cagr / mdd_pct) if abs(mdd_pct) > 0.01 else 0.0

    # 5. 최악의 해의 MDD (Worst Year MDD)
    worst_year, worst_year_mdd, yearly_mdds = _calc_worst_year_mdd(values, dates)

    # 6. 연율화 변동성 & 위험조정지수
    vol_ann = float(std_daily * np.sqrt(252.0)) * 100.0
    rf_daily = 0.025 / 252.0
    excess_ret = daily_ret - rf_daily
    excess_std = np.std(excess_ret)
    sharpe = float(np.mean(excess_ret) / excess_std * np.sqrt(252.0)) if excess_std > 1e-8 else 0.0

    downside_ret = np.where(excess_ret < 0, excess_ret, 0)
    downside_std = np.std(downside_ret)
    sortino = float(np.mean(excess_ret) / downside_std * np.sqrt(252.0)) if downside_std > 1e-8 else 0.0

    return {
        "final_value": round(final_val),
        "total_invested": round(total_inv),
        "net_profit": round(net_profit),
        "tr_pct": round(total_ret_pct, 2),            # TR (Total Return)
        "total_return_pct": round(total_ret_pct, 2),  # 호환성 유지
        "cagr_pct": round(twrr_cagr, 2),              # 연평균 CAGR
        "mdd_pct": round(mdd_pct, 2),                # 전체 MDD
        "worst_year": worst_year,                     # 최악의 해 (예: 2022)
        "worst_year_mdd_pct": worst_year_mdd,        # 최악의 해의 MDD (%)
        "mar_ratio": round(mar_ratio, 2),             # MAR (CAGR / |MDD|)
        "volatility_pct": round(vol_ann, 2),
        "sharpe": round(sharpe, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "years": round(years, 1),
        "yearly_mdds": yearly_mdds
    }


# ── 영구 포트폴리오 (Harry Browne Permanent Portfolio) 백테스트 엔진 ──
def _run_permanent_portfolio_backtest(
    w_spy: float = 0.25,
    w_tlt: float = 0.25,
    w_gld: float = 0.25,
    w_bil: float = 0.25,
    init_cap: float = 50000000,
    monthly_add: float = 500000,
    rebal_months: int = 12,
    season_months: list[int] = None,
    start_date: str = None,
    end_date: str = None,
    fee_rate: float = 0.001
):
    if _data is None:
        raise ValueError("데이터셋이 아직 준비되지 않았습니다.")

    if season_months is None:
        season_months = list(range(1, 13))
    else:
        season_months = [int(m) for m in season_months]

    req_tickers = ['SPY', 'TLT', 'GLD', 'BIL']
    for t in req_tickers:
        if t not in _data.columns:
            raise ValueError(f"영구 포트폴리오 필수 티커 {t} 가 데이터셋에 없습니다.")

    sub_df = _data[req_tickers].dropna().copy()
    if len(sub_df) < 20:
        raise ValueError("분석에 필요한 충분한 데이터가 없습니다.")

    avail_min = sub_df.index[0]
    avail_max = sub_df.index[-1]

    # 시작일 필터링 (1970년 1월 1일부터 지원)
    if start_date:
        s_ts = pd.Timestamp(start_date)
        if s_ts > avail_max:
            raise ValueError(f"시작일({start_date})이 데이터 마지막 날({avail_max.strftime('%Y-%m-%d')})보다 늦습니다.")
        if s_ts < avail_min:
            s_ts = avail_min
        sub_df = sub_df[sub_df.index >= s_ts]

    # 종료일 필터링
    if end_date:
        e_ts = pd.Timestamp(end_date)
        if e_ts < sub_df.index[0]:
            raise ValueError(f"종료일({end_date})이 시작일({sub_df.index[0].strftime('%Y-%m-%d')})보다 빠릅니다.")
        sub_df = sub_df[sub_df.index <= e_ts]

    n = len(sub_df)
    if n < 15:
        raise ValueError(f"선택한 기간 내 거래일이 너무 적습니다 (최소 15 거래일 필요, 현재 {n}일).")

    dates = sub_df.index
    months = dates.month

    # 비중 정규화 (합이 1이 되도록)
    total_w = w_spy + w_tlt + w_gld + w_bil
    if total_w <= 0:
        w_spy, w_tlt, w_gld, w_bil = 0.25, 0.25, 0.25, 0.25
        total_w = 1.0
    w_spy /= total_w
    w_tlt /= total_w
    w_gld /= total_w
    w_bil /= total_w

    p_spy = sub_df['SPY'].values
    p_tlt = sub_df['TLT'].values
    p_gld = sub_df['GLD'].values
    p_bil = sub_df['BIL'].values

    r_spy = np.zeros(n)
    r_tlt = np.zeros(n)
    r_gld = np.zeros(n)
    r_bil = np.zeros(n)

    r_spy[1:] = (p_spy[1:] / p_spy[:-1]) - 1.0
    r_tlt[1:] = (p_tlt[1:] / p_tlt[:-1]) - 1.0
    r_gld[1:] = (p_gld[1:] / p_gld[:-1]) - 1.0
    r_bil[1:] = (p_bil[1:] / p_bil[:-1]) - 1.0

    # 포트폴리오 자산별 가치 추적
    # 1. 영구 포트폴리오 (계절성 반영: 매수월 vs 파킹월)
    is_init_bull = (months[0] in season_months)
    if is_init_bull:
        v_spy = init_cap * w_spy
        v_tlt = init_cap * w_tlt
        v_gld = init_cap * w_gld
        v_bil = init_cap * w_bil
        v_safe = 0.0
        prev_mode = "BULL"
    else:
        v_spy, v_tlt, v_gld, v_bil = 0.0, 0.0, 0.0, 0.0
        v_safe = init_cap
        prev_mode = "SAFE"

    # 2. 벤치마크 1: S&P 500 (SPY 100%)
    v_bm_spy = init_cap

    # 3. 벤치마크 2: 전통 60/40 (SPY 60% + TLT 40%)
    v_6040_spy = init_cap * 0.6
    v_6040_tlt = init_cap * 0.4

    port_val = np.zeros(n)
    bm_spy_val = np.zeros(n)
    bm_6040_val = np.zeros(n)
    invested = np.zeros(n)

    port_daily_r = np.zeros(n)
    bm_spy_daily_r = np.zeros(n)
    bm_6040_daily_r = np.zeros(n)

    curr_inv = init_cap
    port_val[0] = v_spy + v_tlt + v_gld + v_bil + v_safe
    bm_spy_val[0] = v_bm_spy
    bm_6040_val[0] = v_6040_spy + v_6040_tlt
    invested[0] = curr_inv

    curr_month = months[0]
    months_elapsed_perm = 0
    months_elapsed_6040 = 0
    total_rebalances_perm = 0

    for i in range(1, n):
        m = months[i]

        # ── 월 첫 거래일 처리 (적립금 투입 + 계절성 스위칭 + 리밸런싱 판별) ──
        if m != curr_month:
            curr_month = m
            curr_inv += monthly_add

            # 벤치마크 적립금
            v_bm_spy += monthly_add
            v_6040_spy += monthly_add * 0.6
            v_6040_tlt += monthly_add * 0.4

            # 60/40 리밸런싱
            months_elapsed_6040 += 1
            if months_elapsed_6040 >= rebal_months:
                tot_6040 = v_6040_spy + v_6040_tlt
                turnover_6040 = abs(v_6040_spy - tot_6040 * 0.6)
                tot_6040_after = tot_6040 - turnover_6040 * fee_rate
                v_6040_spy = tot_6040_after * 0.6
                v_6040_tlt = tot_6040_after * 0.4
                months_elapsed_6040 = 0

            # 영구 포트폴리오 계절성 판별
            is_bull_m = (m in season_months)
            next_mode = "BULL" if is_bull_m else "SAFE"

            if next_mode == "BULL":
                if prev_mode == "SAFE":
                    # 파킹 -> 4대 자산 스위칭 매수
                    tot_prev = (v_safe + monthly_add) * (1.0 - fee_rate)
                    v_spy = tot_prev * w_spy
                    v_tlt = tot_prev * w_tlt
                    v_gld = tot_prev * w_gld
                    v_bil = tot_prev * w_bil
                    v_safe = 0.0
                    prev_mode = "BULL"
                    months_elapsed_perm = 0
                else:
                    # 연속 보유: 적립금 투입
                    v_spy += monthly_add * w_spy
                    v_tlt += monthly_add * w_tlt
                    v_gld += monthly_add * w_gld
                    v_bil += monthly_add * w_bil
                    months_elapsed_perm += 1

                    if months_elapsed_perm >= rebal_months:
                        tot_p = v_spy + v_tlt + v_gld + v_bil
                        target_spy = tot_p * w_spy
                        target_tlt = tot_p * w_tlt
                        target_gld = tot_p * w_gld
                        target_bil = tot_p * w_bil

                        turnover = (abs(v_spy - target_spy) + abs(v_tlt - target_tlt) + abs(v_gld - target_gld) + abs(v_bil - target_bil)) / 2.0
                        fee = turnover * fee_rate
                        tot_p_after = tot_p - fee

                        v_spy = tot_p_after * w_spy
                        v_tlt = tot_p_after * w_tlt
                        v_gld = tot_p_after * w_gld
                        v_bil = tot_p_after * w_bil

                        months_elapsed_perm = 0
                        total_rebalances_perm += 1
            else:
                if prev_mode == "BULL":
                    # 4대 자산 전량 매도 -> 안전자산 100% 파킹
                    tot_prev = (v_spy + v_tlt + v_gld + v_bil) * (1.0 - fee_rate) + monthly_add
                    v_safe = tot_prev
                    v_spy, v_tlt, v_gld, v_bil = 0.0, 0.0, 0.0, 0.0
                    prev_mode = "SAFE"
                    months_elapsed_perm = 0
                else:
                    v_safe += monthly_add

        # ── 일일 가격 변동 반영 ──
        prev_p = v_spy + v_tlt + v_gld + v_bil + v_safe
        if prev_mode == "BULL":
            v_spy *= (1.0 + r_spy[i])
            v_tlt *= (1.0 + r_tlt[i])
            v_gld *= (1.0 + r_gld[i])
            v_bil *= (1.0 + r_bil[i])
        else:
            v_safe *= (1.0 + r_bil[i])
        curr_p = v_spy + v_tlt + v_gld + v_bil + v_safe

        port_val[i] = curr_p
        port_daily_r[i] = (curr_p / prev_p - 1.0) if prev_p > 0 else 0.0

        prev_bm = v_bm_spy
        v_bm_spy *= (1.0 + r_spy[i])
        bm_spy_val[i] = v_bm_spy
        bm_spy_daily_r[i] = (v_bm_spy / prev_bm - 1.0) if prev_bm > 0 else 0.0

        prev_6040 = v_6040_spy + v_6040_tlt
        v_6040_spy *= (1.0 + r_spy[i])
        v_6040_tlt *= (1.0 + r_tlt[i])
        curr_6040 = v_6040_spy + v_6040_tlt
        bm_6040_val[i] = curr_6040
        bm_6040_daily_r[i] = (curr_6040 / prev_6040 - 1.0) if prev_6040 > 0 else 0.0

        invested[i] = curr_inv

    # 성과 지표 산출
    port_metrics = _calc_perf_metrics(port_val, invested, dates, port_daily_r[1:])
    bm_spy_metrics = _calc_perf_metrics(bm_spy_val, invested, dates, bm_spy_daily_r[1:])
    bm_6040_metrics = _calc_perf_metrics(bm_6040_val, invested, dates, bm_6040_daily_r[1:])

    # MDD 시계열
    p_peaks = np.maximum.accumulate(port_val)
    port_dd = ((port_val - p_peaks) / p_peaks) * 100.0

    spy_peaks = np.maximum.accumulate(bm_spy_val)
    spy_dd = ((bm_spy_val - spy_peaks) / spy_peaks) * 100.0

    f6040_peaks = np.maximum.accumulate(bm_6040_val)
    f6040_dd = ((bm_6040_val - f6040_peaks) / f6040_peaks) * 100.0

    # ── 역사적 위기 구간(Crisis Periods) 하이라이트 & 방어력 분석 ──
    crisis_defs = [
        {"name": "1973 1차 오일쇼크", "desc": "스태그플레이션 & 주식 폭락", "start": "1973-10-01", "end": "1974-12-31"},
        {"name": "1987 블랙먼데이", "desc": "사상 최대 일일 주가 폭락", "start": "1987-10-01", "end": "1987-11-30"},
        {"name": "2000 닷컴 버블 붕괴", "desc": "나스닥 -80% 대폭락", "start": "2000-03-24", "end": "2002-10-09"},
        {"name": "2008 글로벌 금융위기", "desc": "서브프라임 & 리먼 파산", "start": "2007-10-09", "end": "2009-03-09"},
        {"name": "2020 코로나 쇼크", "desc": "팬데믹 단기 패닉셀", "start": "2020-02-19", "end": "2020-03-23"},
        {"name": "2022 긴축 약세장", "desc": "주식·채권 동반 하락", "start": "2022-01-03", "end": "2022-10-13"}
    ]

    df_series = pd.DataFrame({
        'port': port_val,
        'spy': bm_spy_val,
        'f6040': bm_6040_val
    }, index=dates)

    crisis_results = []
    for c in crisis_defs:
        s_d = pd.Timestamp(c['start'])
        e_d = pd.Timestamp(c['end'])
        if s_d >= dates[0] and e_d <= dates[-1]:
            c_sub = df_series.loc[(df_series.index >= s_d) & (df_series.index <= e_d)]
            if len(c_sub) > 1:
                p_ret = (c_sub['port'].iloc[-1] / c_sub['port'].iloc[0] - 1.0) * 100.0
                spy_ret = (c_sub['spy'].iloc[-1] / c_sub['spy'].iloc[0] - 1.0) * 100.0
                f6040_ret = (c_sub['f6040'].iloc[-1] / c_sub['f6040'].iloc[0] - 1.0) * 100.0

                p_pk = np.maximum.accumulate(c_sub['port'].values)
                p_mdd = float(np.min((c_sub['port'].values - p_pk) / p_pk)) * 100.0

                s_pk = np.maximum.accumulate(c_sub['spy'].values)
                s_mdd = float(np.min((c_sub['spy'].values - s_pk) / s_pk)) * 100.0

                f_pk = np.maximum.accumulate(c_sub['f6040'].values)
                f_mdd = float(np.min((c_sub['f6040'].values - f_pk) / f_pk)) * 100.0

                crisis_results.append({
                    "name": c['name'],
                    "desc": c['desc'],
                    "start": c['start'],
                    "end": c['end'],
                    "port_ret_pct": round(p_ret, 2),
                    "spy_ret_pct": round(spy_ret, 2),
                    "f6040_ret_pct": round(f6040_ret, 2),
                    "port_mdd_pct": round(p_mdd, 2),
                    "spy_mdd_pct": round(s_mdd, 2),
                    "f6040_mdd_pct": round(f_mdd, 2),
                    "defense_alpha": round(p_ret - spy_ret, 2)
                })

    # 다운샘플링 (차트 렌더링용)
    step = max(1, n // 800)
    chart_indices = list(range(0, n, step))
    if chart_indices[-1] != n - 1:
        chart_indices.append(n - 1)

    chart_dates = [dates[idx].strftime('%Y-%m-%d') for idx in chart_indices]
    chart_port_val = [round(port_val[idx]) for idx in chart_indices]
    chart_spy_val = [round(bm_spy_val[idx]) for idx in chart_indices]
    chart_6040_val = [round(bm_6040_val[idx]) for idx in chart_indices]
    chart_invested = [round(invested[idx]) for idx in chart_indices]

    chart_port_dd = [round(float(port_dd[idx]), 2) for idx in chart_indices]
    chart_spy_dd = [round(float(spy_dd[idx]), 2) for idx in chart_indices]
    chart_6040_dd = [round(float(f6040_dd[idx]), 2) for idx in chart_indices]

    return {
        "status": "success",
        "info": {
            "w_spy": round(w_spy * 100, 1),
            "w_tlt": round(w_tlt * 100, 1),
            "w_gld": round(w_gld * 100, 1),
            "w_bil": round(w_bil * 100, 1),
            "season_months": sorted(season_months),
            "rebal_months": rebal_months,
            "total_rebalances": total_rebalances_perm,
            "start_date": dates[0].strftime('%Y-%m-%d'),
            "end_date": dates[-1].strftime('%Y-%m-%d'),
            "trading_days": n,
            "fee_rate_pct": round(fee_rate * 100, 2),
            "has_synthetic": True,
            "synthetic_notice": "⚠️ 1970~2000년대 데이터는 S&P 500(^GSPC), 30년 국채수익률(^TYX), 금 선물(GC=F), 3개월 국채수익률(^IRX)을 활용해 역산 합성된 가상 데이터(Synthetic Data)입니다."
        },
        "metrics": {
            "permanent_portfolio": port_metrics,
            "sp500": bm_spy_metrics,
            "portfolio_6040": bm_6040_metrics
        },
        "chart": {
            "dates": chart_dates,
            "port_val": chart_port_val,
            "spy_val": chart_spy_val,
            "f6040_val": chart_6040_val,
            "invested": chart_invested,
            "port_dd": chart_port_dd,
            "spy_dd": chart_spy_dd,
            "f6040_dd": chart_6040_dd
        },
        "crisis_analysis": crisis_results
    }

# ── 올웨더 포트폴리오 (Ray Dalio All Weather Portfolio) 백테스트 엔진 ──
def _run_allweather_portfolio_backtest(
    w_spy: float = 0.30,
    w_tlt: float = 0.40,
    w_ief: float = 0.15,
    w_gld: float = 0.075,
    w_dbc: float = 0.075,
    init_cap: float = 50000000,
    monthly_add: float = 500000,
    rebal_months: int = 12,
    season_months: list[int] = None,
    start_date: str = None,
    end_date: str = None,
    fee_rate: float = 0.001
):
    if _data is None:
        raise ValueError("데이터셋이 아직 준비되지 않았습니다.")

    if season_months is None:
        season_months = list(range(1, 13))
    else:
        season_months = [int(m) for m in season_months]

    req_tickers = ['SPY', 'TLT', 'IEF', 'GLD', 'DBC', 'BIL']
    for t in req_tickers:
        if t not in _data.columns:
            raise ValueError(f"올웨더 포트폴리오 필수 티커 {t} 가 데이터셋에 없습니다.")

    sub_df = _data[req_tickers].dropna().copy()
    if len(sub_df) < 20:
        raise ValueError("분석에 필요한 충분한 데이터가 없습니다.")

    avail_min = sub_df.index[0]
    avail_max = sub_df.index[-1]

    # 시작일 필터링 (1970-01-01부터)
    if start_date:
        s_ts = pd.Timestamp(start_date)
        if s_ts > avail_max:
            raise ValueError(f"시작일({start_date})이 데이터 마지막 날({avail_max.strftime('%Y-%m-%d')})보다 늦습니다.")
        if s_ts < avail_min:
            s_ts = avail_min
        sub_df = sub_df[sub_df.index >= s_ts]

    # 종료일 필터링
    if end_date:
        e_ts = pd.Timestamp(end_date)
        if e_ts < sub_df.index[0]:
            raise ValueError(f"종료일({end_date})이 시작일({sub_df.index[0].strftime('%Y-%m-%d')})보다 빠릅니다.")
        sub_df = sub_df[sub_df.index <= e_ts]

    n = len(sub_df)
    if n < 15:
        raise ValueError(f"선택한 기간 내 거래일이 너무 적습니다 (최소 15 거래일 필요, 현재 {n}일).")

    dates = sub_df.index
    months = dates.month

    # 비중 정규화
    total_w = w_spy + w_tlt + w_ief + w_gld + w_dbc
    if total_w <= 0:
        w_spy, w_tlt, w_ief, w_gld, w_dbc = 0.30, 0.40, 0.15, 0.075, 0.075
        total_w = 1.0
    w_spy /= total_w
    w_tlt /= total_w
    w_ief /= total_w
    w_gld /= total_w
    w_dbc /= total_w

    p_spy = sub_df['SPY'].values
    p_tlt = sub_df['TLT'].values
    p_ief = sub_df['IEF'].values
    p_gld = sub_df['GLD'].values
    p_dbc = sub_df['DBC'].values
    p_bil = sub_df['BIL'].values

    r_spy = np.zeros(n)
    r_tlt = np.zeros(n)
    r_ief = np.zeros(n)
    r_gld = np.zeros(n)
    r_dbc = np.zeros(n)
    r_bil = np.zeros(n)

    r_spy[1:] = (p_spy[1:] / p_spy[:-1]) - 1.0
    r_tlt[1:] = (p_tlt[1:] / p_tlt[:-1]) - 1.0
    r_ief[1:] = (p_ief[1:] / p_ief[:-1]) - 1.0
    r_gld[1:] = (p_gld[1:] / p_gld[:-1]) - 1.0
    r_dbc[1:] = (p_dbc[1:] / p_dbc[:-1]) - 1.0
    r_bil[1:] = (p_bil[1:] / p_bil[:-1]) - 1.0

    # 포트폴리오 가치 추적 (계절성 스위칭 반영)
    is_init_bull = (months[0] in season_months)
    if is_init_bull:
        v_spy = init_cap * w_spy
        v_tlt = init_cap * w_tlt
        v_ief = init_cap * w_ief
        v_gld = init_cap * w_gld
        v_dbc = init_cap * w_dbc
        v_safe = 0.0
        prev_mode = "BULL"
    else:
        v_spy, v_tlt, v_ief, v_gld, v_dbc = 0.0, 0.0, 0.0, 0.0, 0.0
        v_safe = init_cap
        prev_mode = "SAFE"

    v_bm_spy = init_cap
    v_6040_spy = init_cap * 0.6
    v_6040_tlt = init_cap * 0.4

    port_val = np.zeros(n)
    bm_spy_val = np.zeros(n)
    bm_6040_val = np.zeros(n)
    invested = np.zeros(n)

    port_daily_r = np.zeros(n)
    bm_spy_daily_r = np.zeros(n)
    bm_6040_daily_r = np.zeros(n)

    curr_inv = init_cap
    port_val[0] = v_spy + v_tlt + v_ief + v_gld + v_dbc + v_safe
    bm_spy_val[0] = v_bm_spy
    bm_6040_val[0] = v_6040_spy + v_6040_tlt
    invested[0] = curr_inv

    curr_month = months[0]
    months_elapsed_all = 0
    months_elapsed_6040 = 0
    total_rebalances_all = 0

    for i in range(1, n):
        m = months[i]

        if m != curr_month:
            curr_month = m
            curr_inv += monthly_add

            v_bm_spy += monthly_add
            v_6040_spy += monthly_add * 0.6
            v_6040_tlt += monthly_add * 0.4

            months_elapsed_6040 += 1
            if months_elapsed_6040 >= rebal_months:
                tot_6040 = v_6040_spy + v_6040_tlt
                turnover_6040 = abs(v_6040_spy - tot_6040 * 0.6)
                tot_6040_after = tot_6040 - turnover_6040 * fee_rate
                v_6040_spy = tot_6040_after * 0.6
                v_6040_tlt = tot_6040_after * 0.4
                months_elapsed_6040 = 0

            # 올웨더 계절성 판별
            is_bull_m = (m in season_months)
            next_mode = "BULL" if is_bull_m else "SAFE"

            if next_mode == "BULL":
                if prev_mode == "SAFE":
                    tot_prev = (v_safe + monthly_add) * (1.0 - fee_rate)
                    v_spy = tot_prev * w_spy
                    v_tlt = tot_prev * w_tlt
                    v_ief = tot_prev * w_ief
                    v_gld = tot_prev * w_gld
                    v_dbc = tot_prev * w_dbc
                    v_safe = 0.0
                    prev_mode = "BULL"
                    months_elapsed_all = 0
                else:
                    v_spy += monthly_add * w_spy
                    v_tlt += monthly_add * w_tlt
                    v_ief += monthly_add * w_ief
                    v_gld += monthly_add * w_gld
                    v_dbc += monthly_add * w_dbc
                    months_elapsed_all += 1

                    if months_elapsed_all >= rebal_months:
                        tot_a = v_spy + v_tlt + v_ief + v_gld + v_dbc
                        target_spy = tot_a * w_spy
                        target_tlt = tot_a * w_tlt
                        target_ief = tot_a * w_ief
                        target_gld = tot_a * w_gld
                        target_dbc = tot_a * w_dbc

                        turnover = (abs(v_spy - target_spy) + abs(v_tlt - target_tlt) + abs(v_ief - target_ief) + abs(v_gld - target_gld) + abs(v_dbc - target_dbc)) / 2.0
                        fee = turnover * fee_rate
                        tot_a_after = tot_a - fee

                        v_spy = tot_a_after * w_spy
                        v_tlt = tot_a_after * w_tlt
                        v_ief = tot_a_after * w_ief
                        v_gld = tot_a_after * w_gld
                        v_dbc = tot_a_after * w_dbc

                        months_elapsed_all = 0
                        total_rebalances_all += 1
            else:
                if prev_mode == "BULL":
                    tot_prev = (v_spy + v_tlt + v_ief + v_gld + v_dbc) * (1.0 - fee_rate) + monthly_add
                    v_safe = tot_prev
                    v_spy, v_tlt, v_ief, v_gld, v_dbc = 0.0, 0.0, 0.0, 0.0, 0.0
                    prev_mode = "SAFE"
                    months_elapsed_all = 0
                else:
                    v_safe += monthly_add

        # 일일 가격 변동 반영
        prev_p = v_spy + v_tlt + v_ief + v_gld + v_dbc + v_safe
        if prev_mode == "BULL":
            v_spy *= (1.0 + r_spy[i])
            v_tlt *= (1.0 + r_tlt[i])
            v_ief *= (1.0 + r_ief[i])
            v_gld *= (1.0 + r_gld[i])
            v_dbc *= (1.0 + r_dbc[i])
        else:
            v_safe *= (1.0 + r_bil[i])
        curr_p = v_spy + v_tlt + v_ief + v_gld + v_dbc + v_safe

        port_val[i] = curr_p
        port_daily_r[i] = (curr_p / prev_p - 1.0) if prev_p > 0 else 0.0

        prev_bm = v_bm_spy
        v_bm_spy *= (1.0 + r_spy[i])
        bm_spy_val[i] = v_bm_spy
        bm_spy_daily_r[i] = (v_bm_spy / prev_bm - 1.0) if prev_bm > 0 else 0.0

        prev_6040 = v_6040_spy + v_6040_tlt
        v_6040_spy *= (1.0 + r_spy[i])
        v_6040_tlt *= (1.0 + r_tlt[i])
        curr_6040 = v_6040_spy + v_6040_tlt
        bm_6040_val[i] = curr_6040
        bm_6040_daily_r[i] = (curr_6040 / prev_6040 - 1.0) if prev_6040 > 0 else 0.0

        invested[i] = curr_inv

    # 성과 지표 산출
    port_metrics = _calc_perf_metrics(port_val, invested, dates, port_daily_r[1:])
    bm_spy_metrics = _calc_perf_metrics(bm_spy_val, invested, dates, bm_spy_daily_r[1:])
    bm_6040_metrics = _calc_perf_metrics(bm_6040_val, invested, dates, bm_6040_daily_r[1:])

    p_peaks = np.maximum.accumulate(port_val)
    port_dd = ((port_val - p_peaks) / p_peaks) * 100.0

    spy_peaks = np.maximum.accumulate(bm_spy_val)
    spy_dd = ((bm_spy_val - spy_peaks) / spy_peaks) * 100.0

    f6040_peaks = np.maximum.accumulate(bm_6040_val)
    f6040_dd = ((bm_6040_val - f6040_peaks) / f6040_peaks) * 100.0

    # 6대 위기 구간 방어력 분석
    crisis_defs = [
        {"name": "1973 1차 오일쇼크", "desc": "스태그플레이션 & 주식 폭락", "start": "1973-10-01", "end": "1974-12-31"},
        {"name": "1987 블랙먼데이", "desc": "사상 최대 일일 주가 폭락", "start": "1987-10-01", "end": "1987-11-30"},
        {"name": "2000 닷컴 버블 붕괴", "desc": "나스닥 -80% 대폭락", "start": "2000-03-24", "end": "2002-10-09"},
        {"name": "2008 글로벌 금융위기", "desc": "서브프라임 & 리먼 파산", "start": "2007-10-09", "end": "2009-03-09"},
        {"name": "2020 코로나 쇼크", "desc": "팬데믹 단기 패닉셀", "start": "2020-02-19", "end": "2020-03-23"},
        {"name": "2022 긴축 약세장", "desc": "주식·채권 동반 하락", "start": "2022-01-03", "end": "2022-10-13"}
    ]

    df_series = pd.DataFrame({
        'port': port_val,
        'spy': bm_spy_val,
        'f6040': bm_6040_val
    }, index=dates)

    crisis_results = []
    for c in crisis_defs:
        s_d = pd.Timestamp(c['start'])
        e_d = pd.Timestamp(c['end'])
        if s_d >= dates[0] and e_d <= dates[-1]:
            c_sub = df_series.loc[(df_series.index >= s_d) & (df_series.index <= e_d)]
            if len(c_sub) > 1:
                p_ret = (c_sub['port'].iloc[-1] / c_sub['port'].iloc[0] - 1.0) * 100.0
                spy_ret = (c_sub['spy'].iloc[-1] / c_sub['spy'].iloc[0] - 1.0) * 100.0
                f6040_ret = (c_sub['f6040'].iloc[-1] / c_sub['f6040'].iloc[0] - 1.0) * 100.0

                p_pk = np.maximum.accumulate(c_sub['port'].values)
                p_mdd = float(np.min((c_sub['port'].values - p_pk) / p_pk)) * 100.0

                s_pk = np.maximum.accumulate(c_sub['spy'].values)
                s_mdd = float(np.min((c_sub['spy'].values - s_pk) / s_pk)) * 100.0

                f_pk = np.maximum.accumulate(c_sub['f6040'].values)
                f_mdd = float(np.min((c_sub['f6040'].values - f_pk) / f_pk)) * 100.0

                crisis_results.append({
                    "name": c['name'],
                    "desc": c['desc'],
                    "start": c['start'],
                    "end": c['end'],
                    "port_ret_pct": round(p_ret, 2),
                    "spy_ret_pct": round(spy_ret, 2),
                    "f6040_ret_pct": round(f6040_ret, 2),
                    "port_mdd_pct": round(p_mdd, 2),
                    "spy_mdd_pct": round(s_mdd, 2),
                    "f6040_mdd_pct": round(f_mdd, 2),
                    "defense_alpha": round(p_ret - spy_ret, 2)
                })

    step = max(1, n // 800)
    chart_indices = list(range(0, n, step))
    if chart_indices[-1] != n - 1:
        chart_indices.append(n - 1)

    chart_dates = [dates[idx].strftime('%Y-%m-%d') for idx in chart_indices]
    chart_port_val = [round(port_val[idx]) for idx in chart_indices]
    chart_spy_val = [round(bm_spy_val[idx]) for idx in chart_indices]
    chart_6040_val = [round(bm_6040_val[idx]) for idx in chart_indices]
    chart_invested = [round(invested[idx]) for idx in chart_indices]

    chart_port_dd = [round(float(port_dd[idx]), 2) for idx in chart_indices]
    chart_spy_dd = [round(float(spy_dd[idx]), 2) for idx in chart_indices]
    chart_6040_dd = [round(float(f6040_dd[idx]), 2) for idx in chart_indices]

    return {
        "status": "success",
        "info": {
            "w_spy": round(w_spy * 100, 1),
            "w_tlt": round(w_tlt * 100, 1),
            "w_ief": round(w_ief * 100, 1),
            "w_gld": round(w_gld * 100, 1),
            "w_dbc": round(w_dbc * 100, 1),
            "season_months": sorted(season_months),
            "rebal_months": rebal_months,
            "total_rebalances": total_rebalances_all,
            "start_date": dates[0].strftime('%Y-%m-%d'),
            "end_date": dates[-1].strftime('%Y-%m-%d'),
            "trading_days": n,
            "fee_rate_pct": round(fee_rate * 100, 2),
            "has_synthetic": True,
            "synthetic_notice": "⚠️ 1970~2000년대 데이터는 S&P 500(^GSPC), 30년 국채금리(^TYX), 10년 국채금리(^TNX), 금 선물(GC=F), 블룸버그/GSCI 원자재 지수를 활용해 역산 합성된 가상 데이터(Synthetic Data)입니다."
        },
        "metrics": {
            "allweather_portfolio": port_metrics,
            "sp500": bm_spy_metrics,
            "portfolio_6040": bm_6040_metrics
        },
        "chart": {
            "dates": chart_dates,
            "port_val": chart_port_val,
            "spy_val": chart_spy_val,
            "f6040_val": chart_6040_val,
            "invested": chart_invested,
            "port_dd": chart_port_dd,
            "spy_dd": chart_spy_dd,
            "f6040_dd": chart_6040_dd
        },
        "crisis_analysis": crisis_results
    }


# ── 동적 자산 배분 (Dynamic Asset Allocation) 라이브 시그널 산출 ──
def _get_dynamic_live_signal(strategy_id="BAA", target_date=None):
    if _data is None:
        raise ValueError("데이터셋이 아직 준비되지 않았습니다.")
    
    # 월말 종가 시계열 구성 + 최신 거래일 포함
    m_ends = _data.resample('ME').last()
    latest_dt = _data.index[-1]
    if latest_dt > m_ends.index[-1]:
        m_ends.loc[latest_dt] = _data.iloc[-1]
    
    idx = len(m_ends) - 1
    as_of_str = latest_dt.strftime('%Y-%m-%d')

    def r_k(t, k):
        return float(m_ends[t].iloc[idx] / m_ends[t].iloc[max(0, idx - k)] - 1.0)

    def score_13612w(t):
        p0 = m_ends[t].iloc[idx]
        return float(
            12.0 * (p0 / m_ends[t].iloc[max(0, idx - 1)] - 1.0) +
            4.0 * (p0 / m_ends[t].iloc[max(0, idx - 3)] - 1.0) +
            2.0 * (p0 / m_ends[t].iloc[max(0, idx - 6)] - 1.0) +
            1.0 * (p0 / m_ends[t].iloc[max(0, idx - 12)] - 1.0)
        )

    def score_haa(t):
        p0 = m_ends[t].iloc[idx]
        return float(
            (p0 / m_ends[t].iloc[max(0, idx - 1)] - 1.0) +
            (p0 / m_ends[t].iloc[max(0, idx - 3)] - 1.0) +
            (p0 / m_ends[t].iloc[max(0, idx - 6)] - 1.0) +
            (p0 / m_ends[t].iloc[max(0, idx - 12)] - 1.0)
        ) / 4.0

    def sma_rel(t, w=12):
        p0 = m_ends[t].iloc[idx]
        sma = float(m_ends[t].iloc[max(0, idx - w + 1) : idx + 1].mean())
        return float(p0 / sma - 1.0) if sma > 0 else 0.0

    strat_info = {
        "BAA": {"name": "Bold Asset Allocation (BAA)", "author": "Wouter Keller", "type": "카나리아 4종 모멘텀 공방 전환"},
        "HAA": {"name": "Hybrid Asset Allocation (HAA)", "author": "Wouter Keller", "type": "TIP 카나리아 하이브리드 동적 배분"},
        "LAA": {"name": "Lethargic Asset Allocation (LAA)", "author": "Wouter Keller", "type": "영구 75% + SPY 200일선 25%"},
        "RAA": {"name": "Robust Asset Allocation (RAA)", "author": "Wesley Gray", "type": "절대 모멘텀 & 12M 추세 필터"},
        "GTAA": {"name": "Global Tactical Asset Allocation (GTAA-5)", "author": "Meb Faber", "type": "5대 자산군 10M 이평 추세 추종"},
        "GEM": {"name": "Dual Momentum (GEM)", "author": "Gary Antonacci", "type": "절대 모멘텀(vs BIL) & 상대 모멘텀"}
    }

    info = strat_info.get(strategy_id, strat_info["BAA"])
    canaries = []
    regime = "RISK_ON"
    regime_badge = "🟢 공격 모드 (Risk-On)"
    rationale = ""
    portfolio = []
    target_weights = {}

    if strategy_id == "BAA":
        canary_tickers = ["SPY", "VEA", "VWO", "BND"]
        c_scores = {}
        for c in canary_tickers:
            sc = score_13612w(c)
            c_scores[c] = sc
            passed = (sc > 0)
            canaries.append({
                "ticker": c,
                "name_kr": TICKER_INFO.get(c, {}).get("name_kr", c),
                "score": round(sc, 3),
                "score_str": f"{sc:+.1%}" if abs(sc) < 10 else f"{sc:+.2f}",
                "status": "PASS" if passed else "FAIL"
            })
        
        is_risk_on = all(s > 0 for s in c_scores.values())
        if is_risk_on:
            regime = "RISK_ON"
            regime_badge = "🟢 공격 모드 (Risk-On)"
            rationale = "4대 카나리아 자산(SPY, VEA, VWO, BND)의 13612W 모멘텀이 모두 양수(> 0)이므로 공격 모드를 유지합니다."
            universe = ["QQQ", "EFA", "EEM", "AGG"]
            moms = [(t, sma_rel(t, 12)) for t in universe]
            top2 = sorted(moms, key=lambda x: x[1], reverse=True)[:2]
            target_weights = {top2[0][0]: 0.5, top2[1][0]: 0.5}
            for t, m in top2:
                portfolio.append({
                    "ticker": t,
                    "name_kr": TICKER_INFO.get(t, {}).get("name_kr", t),
                    "weight_pct": 50.0,
                    "current_price": round(float(_data[t].iloc[-1]), 2),
                    "momentum_score": f"{m:+.2%}",
                    "momentum_label": "12M 상대 모멘텀",
                    "role": "공격 자산",
                    "color": TICKER_INFO.get(t, {}).get("color", "#3b82f6")
                })
        else:
            regime = "RISK_OFF"
            regime_badge = "🛡️ 방어 모드 (Risk-Off)"
            failed_canaries = [c for c, sc in c_scores.items() if sc <= 0]
            rationale = f"카나리아 자산 중 {', '.join(failed_canaries)}의 13612W 스코어가 0 이하로 하락하여 방어 모드가 발동되었습니다."
            universe = ["TIP", "DBC", "BIL", "IEF", "TLT", "LQD", "AGG"]
            moms = [(t, sma_rel(t, 12)) for t in universe]
            bil_m = next(m for t, m in moms if t == "BIL")
            top3 = sorted(moms, key=lambda x: x[1], reverse=True)[:3]
            for t, m in top3:
                chosen = t if m >= bil_m else "BIL"
                target_weights[chosen] = target_weights.get(chosen, 0.0) + (1.0 / 3.0)
            for t, w in sorted(target_weights.items(), key=lambda x: x[1], reverse=True):
                m_val = next((m for tt, m in moms if tt == t), 0.0)
                portfolio.append({
                    "ticker": t,
                    "name_kr": TICKER_INFO.get(t, {}).get("name_kr", t),
                    "weight_pct": round(w * 100.0, 1),
                    "current_price": round(float(_data[t].iloc[-1]), 2),
                    "momentum_score": f"{m_val:+.2%}",
                    "momentum_label": "12M 상대 모멘텀",
                    "role": "방어 자산" if t != "BIL" else "현금 파킹",
                    "color": TICKER_INFO.get(t, {}).get("color", "#14b8a6")
                })

    elif strategy_id == "HAA":
        tip_s = score_haa("TIP")
        canaries.append({
            "ticker": "TIP",
            "name_kr": TICKER_INFO.get("TIP", {}).get("name_kr", "TIP"),
            "score": round(tip_s, 4),
            "score_str": f"{tip_s:+.2%}",
            "status": "PASS" if tip_s > 0 else "FAIL"
        })
        is_risk_on = (tip_s > 0)
        if is_risk_on:
            regime = "RISK_ON"
            regime_badge = "🟢 공격 모드 (Risk-On)"
            rationale = f"카나리아 TIP의 모멘텀 스코어({tip_s:+.2%})가 양수이므로 시장을 낙관적으로 판정하여 공격 자산에 투자합니다."
            universe = ["SPY", "IWM", "EFA", "EEM", "VNQ", "DBC", "IEF", "TLT"]
            scores = [(t, score_haa(t)) for t in universe]
            bil_s = score_haa("BIL")
            top4 = sorted(scores, key=lambda x: x[1], reverse=True)[:4]
            for t, s in top4:
                chosen = t if s >= bil_s else "BIL"
                target_weights[chosen] = target_weights.get(chosen, 0.0) + 0.25
            for t, w in sorted(target_weights.items(), key=lambda x: x[1], reverse=True):
                s_val = next((s for tt, s in scores if tt == t), bil_s)
                portfolio.append({
                    "ticker": t,
                    "name_kr": TICKER_INFO.get(t, {}).get("name_kr", t),
                    "weight_pct": round(w * 100.0, 1),
                    "current_price": round(float(_data[t].iloc[-1]), 2),
                    "momentum_score": f"{s_val:+.2%}",
                    "momentum_label": "HAA 1-12M 스코어",
                    "role": "공격 자산" if t != "BIL" else "현금 파킹",
                    "color": TICKER_INFO.get(t, {}).get("color", "#3b82f6")
                })
        else:
            regime = "RISK_OFF"
            regime_badge = "🛡️ 방어 모드 (Risk-Off)"
            rationale = f"카나리아 TIP의 모멘텀 스코어({tip_s:+.2%})가 0 이하로 인플레이션/실질금리 압박 신호가 감지되어 방어 모드로 전환했습니다."
            ief_s = score_haa("IEF")
            bil_s = score_haa("BIL")
            chosen = "IEF" if ief_s >= bil_s else "BIL"
            target_weights = {chosen: 1.0}
            c_score = ief_s if chosen == "IEF" else bil_s
            portfolio.append({
                "ticker": chosen,
                "name_kr": TICKER_INFO.get(chosen, {}).get("name_kr", chosen),
                "weight_pct": 100.0,
                "current_price": round(float(_data[chosen].iloc[-1]), 2),
                "momentum_score": f"{c_score:+.2%}",
                "momentum_label": "HAA 모멘텀 스코어",
                "role": "방어 채권" if chosen == "IEF" else "초단기 현금",
                "color": TICKER_INFO.get(chosen, {}).get("color", "#14b8a6")
            })

    elif strategy_id == "LAA":
        spy_curr = float(_data["SPY"].iloc[-1])
        spy_sma200 = float(_data["SPY"].iloc[-200:].mean())
        is_above = (spy_curr > spy_sma200)
        timing_pick = "QQQ" if is_above else "SHY"
        regime = "RISK_ON" if is_above else "RISK_OFF"
        regime_badge = "🟢 성장 가속 (QQQ)" if is_above else "🛡️ 방어 모드 (SHY)"
        diff_pct = (spy_curr / spy_sma200 - 1.0) * 100.0
        rationale = f"SPY 종가(${spy_curr:.2f})가 200일 이동평균선(${spy_sma200:.2f}, {diff_pct:+.2f}%) 위에 있어 타이밍 자산으로 QQQ(25%)를 보유합니다." if is_above else f"SPY 종가(${spy_curr:.2f})가 200일 이동평균선(${spy_sma200:.2f}, {diff_pct:+.2f}%) 아래로 하락하여 타이밍 자산으로 SHY(25%)를 보유합니다."
        target_weights = {"SPY": 0.25, "GLD": 0.25, "IEF": 0.25, timing_pick: 0.25}
        for t, w in target_weights.items():
            role_str = "타이밍 자산" if t == timing_pick else "핵심 영구 자산"
            portfolio.append({
                "ticker": t,
                "name_kr": TICKER_INFO.get(t, {}).get("name_kr", t),
                "weight_pct": 25.0,
                "current_price": round(float(_data[t].iloc[-1]), 2),
                "momentum_score": f"{r_k(t, 12):+.2%}",
                "momentum_label": "12M 수익률",
                "role": role_str,
                "color": TICKER_INFO.get(t, {}).get("color", "#3b82f6")
            })

    elif strategy_id == "RAA":
        universe = ["SPY", "EFA", "EEM", "VNQ", "DBC", "IEF", "TLT"]
        bil_12 = r_k("BIL", 12)
        target_weights = {}
        bil_alloc = 0.0
        base_w = 1.0 / 7.0
        half_w = base_w * 0.5
        pass_counts = 0
        for t in universe:
            r12 = r_k(t, 12)
            sma12 = float(m_ends[t].iloc[max(0, idx - 11) : idx + 1].mean())
            p0 = float(m_ends[t].iloc[idx])
            pass_abs = (r12 > bil_12)
            pass_trend = (p0 > sma12)
            w = (half_w if pass_abs else 0.0) + (half_w if pass_trend else 0.0)
            if w > 0:
                target_weights[t] = w
                pass_counts += 1
            bil_alloc += (base_w - w)
        if bil_alloc > 0:
            target_weights["BIL"] = target_weights.get("BIL", 0.0) + bil_alloc

        regime = "RISK_ON" if pass_counts >= 4 else "RISK_OFF"
        regime_badge = "⚖️ 다중 필터 분산" if pass_counts >= 4 else "🛡️ 방어적 분산"
        rationale = f"7개 자산군 중 {pass_counts}개 자산이 절대 모멘텀(vs BIL) 및 12개월 추세 필터를 통과하여 자금을 분산 배분하고, 미달 비중({bil_alloc*100:.1f}%)은 현금(BIL)에 파킹합니다."
        for t, w in sorted(target_weights.items(), key=lambda x: x[1], reverse=True):
            portfolio.append({
                "ticker": t,
                "name_kr": TICKER_INFO.get(t, {}).get("name_kr", t),
                "weight_pct": round(w * 100.0, 1),
                "current_price": round(float(_data[t].iloc[-1]), 2),
                "momentum_score": f"{r_k(t, 12):+.2%}" if t != "BIL" else f"{bil_12:+.2%}",
                "momentum_label": "12M 수익률",
                "role": "추세 자산" if t != "BIL" else "현금 파킹",
                "color": TICKER_INFO.get(t, {}).get("color", "#3b82f6")
            })

    elif strategy_id == "GTAA":
        universe = ["SPY", "EFA", "IEF", "DBC", "VNQ"]
        target_weights = {}
        bil_w = 0.0
        pass_assets = []
        for t in universe:
            sma10 = float(m_ends[t].iloc[max(0, idx - 9) : idx + 1].mean())
            p0 = float(m_ends[t].iloc[idx])
            if p0 > sma10:
                target_weights[t] = 0.2
                pass_assets.append(t)
            else:
                bil_w += 0.2
        if bil_w > 0:
            target_weights["BIL"] = bil_w

        regime = "RISK_ON" if len(pass_assets) >= 3 else "RISK_OFF"
        regime_badge = "📈 10M 추세 추종" if len(pass_assets) >= 3 else "🛡️ 추세 하회 방어"
        rationale = f"5대 글로벌 자산군 중 {len(pass_assets)}개 자산({', '.join(pass_assets) if pass_assets else '없음'})이 10개월 이동평균선을 상회하여 20%씩 보유하고, 하회 자산 비중({bil_w*100:.0f}%)은 현금(BIL)에 안전 보관합니다."
        for t, w in sorted(target_weights.items(), key=lambda x: x[1], reverse=True):
            portfolio.append({
                "ticker": t,
                "name_kr": TICKER_INFO.get(t, {}).get("name_kr", t),
                "weight_pct": round(w * 100.0, 1),
                "current_price": round(float(_data[t].iloc[-1]), 2),
                "momentum_score": f"{r_k(t, 10):+.2%}" if t != "BIL" else f"{r_k('BIL', 12):+.2%}",
                "momentum_label": "10M 모멘텀",
                "role": "추세 자산" if t != "BIL" else "현금 파킹",
                "color": TICKER_INFO.get(t, {}).get("color", "#3b82f6")
            })

    elif strategy_id == "GEM":
        spy_12 = r_k("SPY", 12)
        bil_12 = r_k("BIL", 12)
        efa_12 = r_k("EFA", 12)
        if spy_12 > bil_12:
            is_risk_on = True
            chosen = "SPY" if spy_12 >= efa_12 else "EFA"
            regime = "RISK_ON"
            regime_badge = "🟢 주식 집중 (Risk-On)"
            winner = "미국 대형주(SPY)" if chosen == "SPY" else "선진국 주식(EFA)"
            rationale = f"SPY 12개월 수익률({spy_12:+.2%})이 무위험 금리 BIL({bil_12:+.2%})을 초과하여 절대 모멘텀을 통과했으며, 상대 모멘텀 우위인 {winner}에 100% 집중 투자합니다."
            target_weights = {chosen: 1.0}
            c_score = spy_12 if chosen == "SPY" else efa_12
            portfolio.append({
                "ticker": chosen,
                "name_kr": TICKER_INFO.get(chosen, {}).get("name_kr", chosen),
                "weight_pct": 100.0,
                "current_price": round(float(_data[chosen].iloc[-1]), 2),
                "momentum_score": f"{c_score:+.2%}",
                "momentum_label": "12M 상대 모멘텀",
                "role": "주식 1위 자산",
                "color": TICKER_INFO.get(chosen, {}).get("color", "#3b82f6")
            })
        else:
            is_risk_on = False
            regime = "RISK_OFF"
            regime_badge = "🛡️ 안전채권 대피 (Risk-Off)"
            rationale = f"SPY 12개월 수익률({spy_12:+.2%})이 무위험 금리 BIL({bil_12:+.2%}) 이하로 주식시장 하락 신호가 발생하여 안전자산 AGG(100%)로 대피합니다."
            target_weights = {"AGG": 1.0}
            agg_12 = r_k("AGG", 12)
            portfolio.append({
                "ticker": "AGG",
                "name_kr": TICKER_INFO.get("AGG", {}).get("name_kr", "AGG"),
                "weight_pct": 100.0,
                "current_price": round(float(_data["AGG"].iloc[-1]), 2),
                "momentum_score": f"{agg_12:+.2%}",
                "momentum_label": "12M 수익률",
                "role": "안전자산 채권",
                "color": TICKER_INFO.get("AGG", {}).get("color", "#6366f1")
            })

    donut_labels = [p["ticker"] for p in portfolio]
    donut_weights = [p["weight_pct"] for p in portfolio]
    donut_colors = [p["color"] for p in portfolio]

    return {
        "as_of_date": as_of_str,
        "strategy_id": strategy_id,
        "strategy_name": info["name"],
        "strategy_author": info["author"],
        "strategy_type": info["type"],
        "regime": regime,
        "regime_badge": regime_badge,
        "regime_rationale": rationale,
        "canaries": canaries,
        "portfolio": portfolio,
        "donut_data": {
            "labels": donut_labels,
            "weights": donut_weights,
            "colors": donut_colors
        }
    }


# ── 동적 자산 배분 (Dynamic Asset Allocation) 백테스트 엔진 ───────
def _run_dynamic_allocation_backtest(
    strategy_id: str = "BAA",
    benchmark_id: str = "SPY",
    init_cap: float = 50000000,
    monthly_add: float = 500000,
    start_date: str = "1970-01-01",
    end_date: str = None,
    fee_rate: float = 0.001
):
    if _data is None:
        raise ValueError("데이터셋이 아직 준비되지 않았습니다.")

    sub_df = _data.copy()
    avail_min = sub_df.index[0]
    avail_max = sub_df.index[-1]

    s_ts = pd.Timestamp(start_date) if start_date else avail_min
    if s_ts < avail_min:
        s_ts = avail_min
    if s_ts > avail_max:
        raise ValueError("시작일이 데이터 마지막 날보다 늦습니다.")

    e_ts = pd.Timestamp(end_date) if end_date else avail_max
    if e_ts > avail_max:
        e_ts = avail_max

    sub_df = sub_df[(sub_df.index >= s_ts) & (sub_df.index <= e_ts)]
    if len(sub_df) < 20:
        raise ValueError("분석에 필요한 충분한 데이터가 없습니다.")

    dates = sub_df.index
    n = len(dates)
    months = dates.month

    # 전체 데이터셋 기준 월말 종가 시계열 (12개월 이전 룩백 보장)
    m_ends_all = _data.resample('ME').last()

    def r_k(t, idx, k):
        return float(m_ends_all[t].iloc[idx] / m_ends_all[t].iloc[max(0, idx - k)] - 1.0)
    
    def score_13612w(t, idx):
        p0 = m_ends_all[t].iloc[idx]
        return float(
            12.0 * (p0 / m_ends_all[t].iloc[max(0, idx - 1)] - 1.0) +
            4.0 * (p0 / m_ends_all[t].iloc[max(0, idx - 3)] - 1.0) +
            2.0 * (p0 / m_ends_all[t].iloc[max(0, idx - 6)] - 1.0) +
            1.0 * (p0 / m_ends_all[t].iloc[max(0, idx - 12)] - 1.0)
        )
        
    def score_haa(t, idx):
        p0 = m_ends_all[t].iloc[idx]
        return float(
            (p0 / m_ends_all[t].iloc[max(0, idx - 1)] - 1.0) +
            (p0 / m_ends_all[t].iloc[max(0, idx - 3)] - 1.0) +
            (p0 / m_ends_all[t].iloc[max(0, idx - 6)] - 1.0) +
            (p0 / m_ends_all[t].iloc[max(0, idx - 12)] - 1.0)
        ) / 4.0

    def sma_rel(t, idx, w=12):
        p0 = m_ends_all[t].iloc[idx]
        sma = float(m_ends_all[t].iloc[max(0, idx - w + 1) : idx + 1].mean())
        return float(p0 / sma - 1.0) if sma > 0 else 0.0

    # 시뮬레이션 배열
    strat_val = np.zeros(n)
    bench_val = np.zeros(n)
    invested = np.zeros(n)
    strat_daily_r = np.zeros(n)
    bench_daily_r = np.zeros(n)

    curr_strat = init_cap
    curr_bench = init_cap
    curr_inv = init_cap

    strat_val[0] = curr_strat
    bench_val[0] = curr_bench
    invested[0] = curr_inv

    # 벤치마크 초기 포지션
    is_bm_6040 = (benchmark_id == "6040")
    if is_bm_6040:
        bm_v_spy = init_cap * 0.6
        bm_v_ief = init_cap * 0.4
    else:
        bm_v_spy = init_cap
        bm_v_ief = 0.0

    curr_weights = {"BIL": 1.0}
    weights_history_records = []
    total_rebalances = 0

    curr_m = dates[0].month

    for i in range(1, n):
        d = dates[i]
        m = months[i]

        # 월 첫 거래일 처리: 리밸런싱 판별 & 적립금 투입
        if m != curr_m:
            curr_m = m
            curr_inv += monthly_add
            curr_strat += monthly_add
            curr_bench += monthly_add

            if is_bm_6040:
                bm_v_spy += monthly_add * 0.6
                bm_v_ief += monthly_add * 0.4
            else:
                bm_v_spy += monthly_add

            # 전월 말 시점의 m_ends_all 인덱스 찾기
            m_idx = m_ends_all.index.searchsorted(d) - 1
            target_w = {}

            if m_idx >= 12:
                if strategy_id == "BAA":
                    canaries = ["SPY", "VEA", "VWO", "BND"]
                    c_scores = [score_13612w(c, m_idx) for c in canaries]
                    if all(s > 0 for s in c_scores):
                        universe = ["QQQ", "EFA", "EEM", "AGG"]
                        moms = [(t, sma_rel(t, m_idx, 12)) for t in universe]
                        top2 = sorted(moms, key=lambda x: x[1], reverse=True)[:2]
                        target_w = {top2[0][0]: 0.5, top2[1][0]: 0.5}
                    else:
                        universe = ["TIP", "DBC", "BIL", "IEF", "TLT", "LQD", "AGG"]
                        moms = [(t, sma_rel(t, m_idx, 12)) for t in universe]
                        bil_m = next(mm for tt, mm in moms if tt == "BIL")
                        top3 = sorted(moms, key=lambda x: x[1], reverse=True)[:3]
                        for t, mm in top3:
                            chosen = t if mm >= bil_m else "BIL"
                            target_w[chosen] = target_w.get(chosen, 0.0) + (1.0 / 3.0)

                elif strategy_id == "HAA":
                    tip_s = score_haa("TIP", m_idx)
                    if tip_s > 0:
                        universe = ["SPY", "IWM", "EFA", "EEM", "VNQ", "DBC", "IEF", "TLT"]
                        scores = [(t, score_haa(t, m_idx)) for t in universe]
                        bil_s = score_haa("BIL", m_idx)
                        top4 = sorted(scores, key=lambda x: x[1], reverse=True)[:4]
                        for t, s in top4:
                            chosen = t if s >= bil_s else "BIL"
                            target_w[chosen] = target_w.get(chosen, 0.0) + 0.25
                    else:
                        ief_s = score_haa("IEF", m_idx)
                        bil_s = score_haa("BIL", m_idx)
                        target_w = {"IEF": 1.0} if ief_s >= bil_s else {"BIL": 1.0}

                elif strategy_id == "LAA":
                    spy_curr = float(_data["SPY"].iloc[_data.index.get_loc(dates[i - 1])])
                    loc_d = _data.index.get_loc(dates[i - 1])
                    spy_sma200 = float(_data["SPY"].iloc[max(0, loc_d - 200) : loc_d].mean())
                    timing = "QQQ" if spy_curr > spy_sma200 else "SHY"
                    target_w = {"SPY": 0.25, "GLD": 0.25, "IEF": 0.25, timing: 0.25}

                elif strategy_id == "RAA":
                    univ = ["SPY", "EFA", "EEM", "VNQ", "DBC", "IEF", "TLT"]
                    bil_12 = r_k("BIL", m_idx, 12)
                    bil_alloc = 0.0
                    base_w = 1.0 / 7.0
                    half_w = base_w * 0.5
                    for t in univ:
                        pass_abs = (r_k(t, m_idx, 12) > bil_12)
                        pass_sma = (m_ends_all[t].iloc[m_idx] > m_ends_all[t].iloc[max(0, m_idx - 11) : m_idx + 1].mean())
                        w = (half_w if pass_abs else 0.0) + (half_w if pass_sma else 0.0)
                        if w > 0:
                            target_w[t] = w
                        bil_alloc += (base_w - w)
                    if bil_alloc > 0:
                        target_w["BIL"] = target_w.get("BIL", 0.0) + bil_alloc

                elif strategy_id == "GTAA":
                    univ = ["SPY", "EFA", "IEF", "DBC", "VNQ"]
                    bil_w = 0.0
                    for t in univ:
                        sma10 = float(m_ends_all[t].iloc[max(0, m_idx - 9) : m_idx + 1].mean())
                        if m_ends_all[t].iloc[m_idx] > sma10:
                            target_w[t] = 0.2
                        else:
                            bil_w += 0.2
                    if bil_w > 0:
                        target_w["BIL"] = bil_w

                elif strategy_id == "GEM":
                    spy_12 = r_k("SPY", m_idx, 12)
                    bil_12 = r_k("BIL", m_idx, 12)
                    efa_12 = r_k("EFA", m_idx, 12)
                    if spy_12 > bil_12:
                        best = "SPY" if spy_12 >= efa_12 else "EFA"
                        target_w = {best: 1.0}
                    else:
                        target_w = {"AGG": 1.0}
            else:
                target_w = {"BIL": 1.0}

            # 비중 정규화
            sum_tw = sum(target_w.values())
            if sum_tw > 0:
                target_w = {k: v / sum_tw for k, v in target_w.items()}
            else:
                target_w = {"BIL": 1.0}

            # 회전율(Turnover) 계산 및 1회 수수료 차감
            all_t = set(curr_weights.keys()).union(target_w.keys())
            turnover = 0.5 * sum(abs(target_w.get(t, 0.0) - curr_weights.get(t, 0.0)) for t in all_t)
            fee = curr_strat * turnover * fee_rate
            curr_strat -= fee
            curr_weights = target_w
            total_rebalances += 1

            # 월간 비중 히스토리 기록
            weights_history_records.append({
                "date": d.strftime('%Y-%m'),
                "weights": {k: round(v * 100.0, 1) for k, v in curr_weights.items()}
            })

        # 일일 가격 변동 반영
        st_prev = curr_strat
        port_r = sum(curr_weights.get(t, 0.0) * (sub_df[t].iloc[i] / sub_df[t].iloc[i - 1] - 1.0) for t in curr_weights)
        curr_strat *= (1.0 + port_r)
        strat_val[i] = curr_strat
        strat_daily_r[i] = (curr_strat / st_prev - 1.0) if st_prev > 0 else 0.0

        # 벤치마크 일일 변동 반영
        bm_prev = curr_bench
        r_spy_d = sub_df["SPY"].iloc[i] / sub_df["SPY"].iloc[i - 1] - 1.0
        r_ief_d = sub_df["IEF"].iloc[i] / sub_df["IEF"].iloc[i - 1] - 1.0
        if is_bm_6040:
            bm_v_spy *= (1.0 + r_spy_d)
            bm_v_ief *= (1.0 + r_ief_d)
            curr_bench = bm_v_spy + bm_v_ief
        else:
            bm_v_spy *= (1.0 + r_spy_d)
            curr_bench = bm_v_spy

        bench_val[i] = curr_bench
        bench_daily_r[i] = (curr_bench / bm_prev - 1.0) if bm_prev > 0 else 0.0
        invested[i] = curr_inv

    # 핵심 성과 지표 산출
    strat_metrics = _calc_perf_metrics(strat_val, invested, dates, strat_daily_r[1:])
    bench_metrics = _calc_perf_metrics(bench_val, invested, dates, bench_daily_r[1:])

    # MDD 시계열
    st_peaks = np.maximum.accumulate(strat_val)
    st_dd = ((strat_val - st_peaks) / st_peaks) * 100.0
    bm_peaks = np.maximum.accumulate(bench_val)
    bm_dd = ((bench_val - bm_peaks) / bm_peaks) * 100.0

    # 차트 포인트 다운샘플링 (~500개)
    step = max(1, n // 500)
    c_indices = list(range(0, n, step))
    if (n - 1) not in c_indices:
        c_indices.append(n - 1)

    chart_dates = [dates[k].strftime('%Y-%m-%d') for k in c_indices]
    chart_strat_val = [round(strat_val[k]) for k in c_indices]
    chart_bench_val = [round(bench_val[k]) for k in c_indices]
    chart_invested = [round(invested[k]) for k in c_indices]
    chart_strat_dd = [round(st_dd[k], 2) for k in c_indices]
    chart_bench_dd = [round(bm_dd[k], 2) for k in c_indices]

    # 비중 히스토리 스택드 에어리어 차트 데이터 포맷팅
    unique_tickers = sorted(list({t for rec in weights_history_records for t in rec["weights"].keys()}))
    wh_dates = [rec["date"] for rec in weights_history_records]
    wh_series = []
    for t in unique_tickers:
        wh_series.append({
            "ticker": t,
            "name_kr": TICKER_INFO.get(t, {}).get("name_kr", t),
            "color": TICKER_INFO.get(t, {}).get("color", "#3b82f6"),
            "data": [rec["weights"].get(t, 0.0) for rec in weights_history_records]
        })

    # 역사적 위기 구간 방어력 분석
    crisis_periods = [
        {"name": "1973년 1차 오일쇼크", "start": "1973-10-01", "end": "1974-12-31", "desc": "스태그플레이션 & 주식 급락"},
        {"name": "1987년 블랙 먼데이", "start": "1987-10-01", "end": "1987-11-30", "desc": "사상 최대 일일 낙폭"},
        {"name": "2000년 닷컴 버블 붕괴", "start": "2000-03-24", "end": "2002-10-09", "desc": "기술주 대폭락 (-80%)"},
        {"name": "2008년 글로벌 금융위기", "start": "2007-10-09", "end": "2009-03-09", "desc": "리만 파산 & S&P -55%"},
        {"name": "2020년 코로나 팬데믹", "start": "2020-02-19", "end": "2020-03-23", "desc": "최단기 급락 충격"},
        {"name": "2022년 금리인상 약세장", "start": "2022-01-03", "end": "2022-10-13", "desc": "주식-채권 동반 폭락"}
    ]

    crisis_results = []
    for cp in crisis_periods:
        c_start = pd.Timestamp(cp["start"])
        c_end = pd.Timestamp(cp["end"])
        mask = (dates >= c_start) & (dates <= c_end)
        if mask.sum() >= 5:
            c_strat = strat_val[mask]
            c_bench = bench_val[mask]
            strat_ret = (c_strat[-1] / c_strat[0] - 1.0) * 100.0
            bench_ret = (c_bench[-1] / c_bench[0] - 1.0) * 100.0
            st_p = np.maximum.accumulate(c_strat)
            st_m = float(np.min((c_strat - st_p) / st_p)) * 100.0
            bm_p = np.maximum.accumulate(c_bench)
            bm_m = float(np.min((c_bench - bm_p) / bm_p)) * 100.0
            alpha = strat_ret - bench_ret
            crisis_results.append({
                "name": cp["name"],
                "period": f"{cp['start']} ~ {cp['end']}",
                "desc": cp["desc"],
                "strat_ret": round(strat_ret, 2),
                "bench_ret": round(bench_ret, 2),
                "strat_mdd": round(st_m, 2),
                "bench_mdd": round(bm_m, 2),
                "alpha": round(alpha, 2)
            })

    live_sig = _get_dynamic_live_signal(strategy_id)

    return {
        "status": "success",
        "info": {
            "strategy_id": strategy_id,
            "strategy_name": live_sig["strategy_name"],
            "strategy_author": live_sig["strategy_author"],
            "strategy_type": live_sig["strategy_type"],
            "benchmark_id": benchmark_id,
            "benchmark_name": "S&P 500 (SPY 100%)" if not is_bm_6040 else "전통 60/40 (SPY 60% + IEF 40%)",
            "start_date": dates[0].strftime('%Y-%m-%d'),
            "end_date": dates[-1].strftime('%Y-%m-%d'),
            "trading_days": n,
            "total_rebalances": total_rebalances,
            "fee_rate_pct": round(fee_rate * 100, 2),
            "as_of_date": live_sig["as_of_date"]
        },
        "live_signal": live_sig,
        "metrics": {
            "strategy": strat_metrics,
            "benchmark": bench_metrics
        },
        "chart": {
            "dates": chart_dates,
            "strat_val": chart_strat_val,
            "bench_val": chart_bench_val,
            "invested": chart_invested,
            "strat_dd": chart_strat_dd,
            "bench_dd": chart_bench_dd
        },
        "weights_history": {
            "dates": wh_dates,
            "tickers": unique_tickers,
            "series": wh_series
        },
        "crisis_analysis": crisis_results
    }


# ── 백테스트 시뮬레이션 엔진 ────────────────────────────────
def _run_seasonality_backtest(
    etf1: str = "SOXL",
    etf2: str = "TQQQ",
    etf1_ratio: float = 0.5, # 0.0 ~ 1.0 (예: 0.5)
    init_cap: float = 50000000.0,
    monthly_add: float = 500000.0,
    season_months: list[int] = None,
    rebal_months: int = 1,   # 리밸런싱 주기 (1 ~ 360개월)
    start_date: str = None,
    end_date: str = None,
    fee_rate: float = 0.001, # 기본 0.1% 거래비용/슬리피지
    assets: list[dict] = None
):
    if _data is None:
        raise ValueError("Yahoo Finance 데이터가 아직 로드되지 않았습니다.")

    if season_months is None:
        season_months = [1, 2, 3, 4, 11, 12]

    rebal_months = max(1, min(360, int(rebal_months)))
    safe_ticker = SAFE_PROXY

    if assets and isinstance(assets, list) and len(assets) > 0:
        raw_assets = []
        for item in assets:
            t = str(item.get("ticker", "")).strip().upper()
            w = float(item.get("weight", 0))
            if t and w > 0:
                raw_assets.append({"ticker": t, "weight": w})
        if not raw_assets:
            raise ValueError("유효한 종목과 비중이 필요합니다.")
        total_w = sum(a["weight"] for a in raw_assets)
        asset_list = [{"ticker": a["ticker"], "weight": a["weight"] / total_w} for a in raw_assets]
    else:
        etf2_ratio = 1.0 - etf1_ratio
        asset_list = [
            {"ticker": etf1, "weight": etf1_ratio},
            {"ticker": etf2, "weight": etf2_ratio}
        ]

    tickers = [a["ticker"] for a in asset_list]
    weights = np.array([a["weight"] for a in asset_list], dtype=float)
    k = len(asset_list)

    etf1 = asset_list[0]["ticker"]
    etf2 = asset_list[1]["ticker"] if k > 1 else asset_list[0]["ticker"]
    etf1_ratio = float(weights[0])
    etf2_ratio = float(weights[1]) if k > 1 else 0.0

    req_tickers = list(dict.fromkeys(tickers + [safe_ticker]))
    for t in req_tickers:
        if t not in _data.columns:
            raise ValueError(f"티커 {t} 가 데이터셋에 없습니다.")

    # 모든 선택 자산이 존재하는 공통 기간 추출
    sub_df = _data[req_tickers].dropna().copy()
    if len(sub_df) < 20:
        raise ValueError("분석에 필요한 충분한 데이터가 없습니다.")

    avail_min = sub_df.index[0]
    avail_max = sub_df.index[-1]

    # 시작일 필터링 (사용자 지정 날짜 우선, 미지정 시 가용 최소 시작일)
    if start_date:
        s_ts = pd.Timestamp(start_date)
        if s_ts > avail_max:
            raise ValueError(f"시작일({start_date})이 데이터 마지막 날({avail_max.strftime('%Y-%m-%d')})보다 늦습니다.")
        if s_ts < avail_min:
            s_ts = avail_min
        sub_df = sub_df[sub_df.index >= s_ts]

    # 종료일 필터링
    if end_date:
        e_ts = pd.Timestamp(end_date)
        if e_ts < sub_df.index[0]:
            raise ValueError(f"종료일({end_date})이 시작일({sub_df.index[0].strftime('%Y-%m-%d')})보다 빠릅니다.")
        sub_df = sub_df[sub_df.index <= e_ts]

    n = len(sub_df)
    if n < 15:
        raise ValueError(f"선택한 기간 내 거래일이 너무 적습니다 (최소 15 거래일 필요, 현재 {n}일).")
    dates = sub_df.index
    months = dates.month

    # 2010년 이전 데이터 포함 여부 (기초 지수 ^NDX, ^SOX 기반 가상 합성 데이터 사용 여부 판별)
    has_synthetic = (dates[0] < pd.Timestamp("2010-01-01"))
    synthetic_notice = (
        "⚠️ 2010년 이전 데이터는 기초 지수(^NDX, ^SOX)를 바탕으로 레버리지 배수를 곱해 합성된 가상 데이터(Synthetic Data)입니다. 롤오버 비용이 제외되어 실제보다 낙관적일 수 있습니다."
        if has_synthetic else None
    )

    prices_mat = np.vstack([sub_df[t].values for t in tickers])  # shape (k, n)
    ps = sub_df[safe_ticker].values

    asset_rets = np.zeros((k, n), dtype=float)
    asset_rets[:, 1:] = (prices_mat[:, 1:] / prices_mat[:, :-1]) - 1.0
    rs = np.zeros(n)
    rs[1:] = (ps[1:] / ps[:-1]) - 1.0

    strat_val = np.zeros(n)
    bh_val = np.zeros(n)
    invested = np.zeros(n)
    strat_daily_r = np.zeros(n)
    bh_daily_r = np.zeros(n)
    is_bull_arr = np.zeros(n, dtype=bool)

    # ── 포트폴리오 자산별 금액 추적 모델 (N종 동적 지원) ──
    bh_vals = init_cap * weights

    is_init_bull = (months[0] in season_months)
    if is_init_bull:
        strat_vals = init_cap * weights
        strat_v_safe = 0.0
        prev_mode = "BULL"
    else:
        strat_vals = np.zeros(k, dtype=float)
        strat_v_safe = init_cap
        prev_mode = "SAFE"

    curr_inv = init_cap
    strat_val[0] = float(strat_vals.sum()) + strat_v_safe
    bh_val[0] = float(bh_vals.sum())
    invested[0] = curr_inv
    is_bull_arr[0] = is_init_bull

    curr_month = months[0]
    bh_months_count = 0
    strat_bull_months_count = 0
    total_rebalances_strat = 0
    total_rebalances_bh = 0

    for i in range(1, n):
        m = months[i]

        # ── 월 첫 거래일 처리 (적립금 투입 + 리밸런싱 / 스위칭 판별) ──
        if m != curr_month:
            curr_month = m
            curr_inv += monthly_add

            # 1. Buy & Hold: 월 적립금 목표 비중 투입 및 N개월 주기 리밸런싱
            bh_vals += monthly_add * weights
            bh_months_count += 1

            if bh_months_count >= rebal_months:
                bh_total = float(bh_vals.sum())
                target_bh = bh_total * weights
                trade_amt = 0.5 * float(np.sum(np.abs(bh_vals - target_bh)))
                rebal_fee = trade_amt * fee_rate
                bh_vals = (bh_total - rebal_fee) * weights
                bh_months_count = 0
                total_rebalances_bh += 1

            # 2. 계절성 스위칭: 월 계절성 판별
            is_bull_month = (m in season_months)
            next_mode = "BULL" if is_bull_month else "SAFE"

            if next_mode == "BULL":
                if prev_mode == "SAFE":
                    total_strat_prev = (strat_v_safe + monthly_add) * (1.0 - fee_rate)
                    strat_vals = total_strat_prev * weights
                    strat_v_safe = 0.0
                    prev_mode = "BULL"
                    strat_bull_months_count = 0
                else:
                    strat_vals += monthly_add * weights
                    strat_bull_months_count += 1

                    if strat_bull_months_count >= rebal_months:
                        st_total = float(strat_vals.sum())
                        target_st = st_total * weights
                        trade_amt_st = 0.5 * float(np.sum(np.abs(strat_vals - target_st)))
                        rebal_fee_st = trade_amt_st * fee_rate
                        strat_vals = (st_total - rebal_fee_st) * weights
                        strat_bull_months_count = 0
                        total_rebalances_strat += 1
            else:
                if prev_mode == "BULL":
                    total_strat_prev = float(strat_vals.sum()) * (1.0 - fee_rate) + monthly_add
                    strat_v_safe = total_strat_prev
                    strat_vals = np.zeros(k, dtype=float)
                    prev_mode = "SAFE"
                    strat_bull_months_count = 0
                else:
                    strat_v_safe += monthly_add

        is_bull_arr[i] = (prev_mode == "BULL")

        # ── 일일 가격 변동 반영 ──
        bh_prev_day = float(bh_vals.sum())
        bh_vals *= (1.0 + asset_rets[:, i])
        bh_curr_day = float(bh_vals.sum())
        bh_val[i] = bh_curr_day
        bh_daily_r[i] = (bh_curr_day / bh_prev_day - 1.0) if bh_prev_day > 0 else 0.0

        strat_prev_day = float(strat_vals.sum()) + strat_v_safe
        if prev_mode == "BULL":
            strat_vals *= (1.0 + asset_rets[:, i])
        else:
            strat_v_safe *= (1.0 + rs[i])

        strat_curr_day = float(strat_vals.sum()) + strat_v_safe
        strat_val[i] = strat_curr_day
        strat_daily_r[i] = (strat_curr_day / strat_prev_day - 1.0) if strat_prev_day > 0 else 0.0

        invested[i] = curr_inv

    # 지표 산출
    strat_metrics = _calc_perf_metrics(strat_val, invested, dates, strat_daily_r[1:])
    bh_metrics = _calc_perf_metrics(bh_val, invested, dates, bh_daily_r[1:])

    # MDD 시계열
    strat_peaks = np.maximum.accumulate(strat_val)
    strat_dd = ((strat_val - strat_peaks) / strat_peaks) * 100.0

    bh_peaks = np.maximum.accumulate(bh_val)
    bh_dd = ((bh_val - bh_peaks) / bh_peaks) * 100.0

    # 월간 집계
    df_perf = pd.DataFrame({
        'Date': dates,
        'Year': dates.year,
        'Month': dates.month,
        'Strat_Val': strat_val,
        'BH_Val': bh_val,
        'Invested': invested
    })
    df_perf.set_index('Date', inplace=True)

    m_ends = df_perf.resample('ME').last()
    m_ends['Strat_Month_Ret'] = m_ends['Strat_Val'].pct_change() * 100.0
    m_ends['BH_Month_Ret'] = m_ends['BH_Val'].pct_change() * 100.0
    if len(m_ends) > 0 and len(df_perf) > 0:
        m_ends.iloc[0, m_ends.columns.get_loc('Strat_Month_Ret')] = (m_ends.iloc[0]['Strat_Val'] / init_cap - 1.0) * 100.0
        m_ends.iloc[0, m_ends.columns.get_loc('BH_Month_Ret')] = (m_ends.iloc[0]['BH_Val'] / init_cap - 1.0) * 100.0

    strat_win_months = int((m_ends['Strat_Month_Ret'] > 0).sum())
    bh_win_months = int((m_ends['BH_Month_Ret'] > 0).sum())
    total_months = max(len(m_ends), 1)

    strat_metrics["win_rate_pct"] = round((strat_win_months / total_months) * 100.0, 1)
    bh_metrics["win_rate_pct"] = round((bh_win_months / total_months) * 100.0, 1)
    strat_metrics["best_month_pct"] = round(float(m_ends['Strat_Month_Ret'].max()), 2) if len(m_ends) else 0.0
    strat_metrics["worst_month_pct"] = round(float(m_ends['Strat_Month_Ret'].min()), 2) if len(m_ends) else 0.0
    bh_metrics["best_month_pct"] = round(float(m_ends['BH_Month_Ret'].max()), 2) if len(m_ends) else 0.0
    bh_metrics["worst_month_pct"] = round(float(m_ends['BH_Month_Ret'].min()), 2) if len(m_ends) else 0.0

    safe_months_count = int(np.sum(~is_bull_arr))
    safe_time_pct = round((safe_months_count / max(n, 1)) * 100.0, 1)
    strat_metrics["safe_time_pct"] = safe_time_pct
    bh_metrics["safe_time_pct"] = 0.0

    # 연도별 수익률 집계
    y_ends = df_perf.resample('YE').last()
    annual_results = []

    for yr, row in y_ends.iterrows():
        year_int = yr.year
        s_val = row['Strat_Val']
        b_val = row['BH_Val']
        inv_val = row['Invested']

        yr_sub = df_perf[df_perf['Year'] == year_int]
        if len(yr_sub) > 1:
            y_s_ret = (yr_sub['Strat_Val'].iloc[-1] / yr_sub['Strat_Val'].iloc[0] - 1.0) * 100.0
            y_b_ret = (yr_sub['BH_Val'].iloc[-1] / yr_sub['BH_Val'].iloc[0] - 1.0) * 100.0
        else:
            y_s_ret = 0.0
            y_b_ret = 0.0

        s_yr_mdd = strat_metrics.get("yearly_mdds", {}).get(year_int, 0.0)
        b_yr_mdd = bh_metrics.get("yearly_mdds", {}).get(year_int, 0.0)

        annual_results.append({
            "year": int(year_int),
            "strat_ret_pct": round(float(y_s_ret), 2),
            "bh_ret_pct": round(float(y_b_ret), 2),
            "strat_mdd_pct": s_yr_mdd,
            "bh_mdd_pct": b_yr_mdd,
            "strat_final_val": round(float(s_val)),
            "bh_final_val": round(float(b_val)),
            "invested": round(float(inv_val))
        })

    # 다운샘플링 (차트용 데이터 생성)
    step = max(1, n // 700)
    chart_indices = list(range(0, n, step))
    if chart_indices[-1] != n - 1:
        chart_indices.append(n - 1)

    chart_dates = [dates[idx].strftime('%Y-%m-%d') for idx in chart_indices]
    chart_strat_val = [round(strat_val[idx]) for idx in chart_indices]
    chart_bh_val = [round(bh_val[idx]) for idx in chart_indices]
    chart_invested = [round(invested[idx]) for idx in chart_indices]
    chart_strat_dd = [round(float(strat_dd[idx]), 2) for idx in chart_indices]
    chart_bh_dd = [round(float(bh_dd[idx]), 2) for idx in chart_indices]
    chart_is_bull = [bool(is_bull_arr[idx]) for idx in chart_indices]

    # 1월~12월 계절성 통계
    sub_df['Month'] = sub_df.index.month
    monthly_stats = []
    for m in range(1, 13):
        m_rows = sub_df[sub_df['Month'] == m]
        m_rets = [(m_rows[t].pct_change().fillna(0).mean() * 21) * 100.0 for t in tickers]
        m_r1 = m_rets[0]
        m_r2 = m_rets[1] if k > 1 else 0.0
        port_m_ret = sum(weights[j] * m_rets[j] for j in range(k))
        is_selected = (m in season_months)
        monthly_stats.append({
            "month": m,
            "etf1_avg_ret": round(float(m_r1), 2),
            "etf2_avg_ret": round(float(m_r2), 2),
            "port_avg_ret": round(float(port_m_ret), 2),
            "is_selected": is_selected
        })

    # ── 백테스트 결과 자동 요약 (Executive Summary) 생성 ──────────
    portfolio_label = " + ".join(f"{a['ticker']}({round(a['weight'] * 100, 1):g}%)" for a in asset_list)
    alpha_final = strat_metrics["final_value"] - bh_metrics["final_value"]
    mdd_defense = bh_metrics["mdd_pct"] - strat_metrics["mdd_pct"]

    rebal_text = (
        f"리밸런싱 주기: {rebal_months}개월 단위로 정기 비중 재조정(계절성 전략 {total_rebalances_strat}회, Buy & Hold {total_rebalances_bh}회 리밸런싱 실행)을 거쳤으며, 자산 쏠림 방지 및 변동성 제어 효과를 거두었습니다."
    )

    summary_bullets = [
        f"수익성 (TR & CAGR): [{portfolio_label}] 계절성 스위칭 전략은 총 수익률(TR) {strat_metrics['tr_pct']:+,.2f}%, 연평균 CAGR {strat_metrics['cagr_pct']:+.2f}%를 기록하여 Buy & Hold 대비 {strat_metrics['cagr_pct'] - bh_metrics['cagr_pct']:+.2f}%p의 연복리 성과를 보였습니다. 최종 자산은 약 {abs(alpha_final):,d}원 {'초과 달성' if alpha_final >= 0 else '부족'}하였습니다.",
        f"리스크 방어 (전체 MDD): 전체 기간 최대 낙폭(MDD)은 Buy & Hold {bh_metrics['mdd_pct']:.2f}% 대비 {strat_metrics['mdd_pct']:.2f}%로, 하방 리스크를 {abs(mdd_defense):.1f}%p {'대폭 완화' if mdd_defense > 0 else '유지'}했습니다.",
        f"최악의 해 방어력: Buy & Hold 기준 가장 가혹했던 해({bh_metrics['worst_year']}년 MDD {bh_metrics['worst_year_mdd_pct']:.2f}%)와 대비하여, 계절성 전략의 최악의 해는 {strat_metrics['worst_year']}년(MDD {strat_metrics['worst_year_mdd_pct']:.2f}%)으로 약세장 방어 효과를 입증했습니다.",
        f"자본 효율성 (MAR): 감수한 최대 낙폭 대비 복리 수익을 나타내는 MAR 비율은 계절성 전략이 {strat_metrics['mar_ratio']}로 Buy & Hold({bh_metrics['mar_ratio']}) 대비 {'우수한' if strat_metrics['mar_ratio'] >= bh_metrics['mar_ratio'] else '유사한'} 자본 효율성을 기록했습니다.",
        rebal_text,
        f"계절성 자산배분: 전체 투자의 {strat_metrics['safe_time_pct']}% 기간 동안 안전자산(초단기채)에 파킹하여 위험 노출을 억제하면서도 {strat_metrics['win_rate_pct']}%의 월간 승률을 달성했습니다."
    ]

    return {
        "status": "success",
        "info": {
            "portfolio_label": portfolio_label,
            "assets": [{"ticker": a["ticker"], "weight": round(a["weight"] * 100, 1)} for a in asset_list],
            "etf1": etf1,
            "etf2": etf2,
            "etf1_ratio": round(etf1_ratio * 100, 1),
            "etf2_ratio": round(etf2_ratio * 100, 1),
            "safe_asset": safe_ticker,
            "rebal_months": rebal_months,
            "total_rebalances_strat": total_rebalances_strat,
            "total_rebalances_bh": total_rebalances_bh,
            "fee_rate_pct": round(fee_rate * 100, 2),
            "start_date": dates[0].strftime('%Y-%m-%d'),
            "end_date": dates[-1].strftime('%Y-%m-%d'),
            "trading_days": n,
            "season_months": sorted(season_months),
            "has_synthetic": has_synthetic,
            "synthetic_notice": synthetic_notice,
            "source": _data_status.get("source", "Yahoo Finance (Synthetic & Auto Adjusted)")
        },
        "metrics": {
            "strategy": strat_metrics,
            "buy_and_hold": bh_metrics
        },
        "summary": {
            "alpha_final": alpha_final,
            "mdd_defense": round(mdd_defense, 2),
            "bullets": summary_bullets
        },
        "chart": {
            "dates": chart_dates,
            "strat_val": chart_strat_val,
            "bh_val": chart_bh_val,
            "invested": chart_invested,
            "strat_dd": chart_strat_dd,
            "bh_dd": chart_bh_dd,
            "is_bull": chart_is_bull
        },
        "annual_results": annual_results,
        "monthly_seasonality": monthly_stats
    }


# ── API 엔드포인트 ──────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/search_ticker', methods=['GET'])
def search_ticker():
    query = request.args.get('q', '').strip()
    if not query:
        # 검색어가 없을 때는 기본 추천 목록 반환
        popular = []
        for sym, d in TICKER_INFO.items():
            if sym not in ['BIL', 'SGOV']:
                popular.append({
                    "symbol": sym,
                    "name": d.get("name_kr", sym),
                    "category": d.get("category", "ETF"),
                    "type": "ETF" if "ETF" in d.get("category", "") else "EQUITY"
                })
        return jsonify({"status": "success", "results": popular})

    q_lower = query.lower()
    results = []
    seen = set()

    # 1. 내장 TICKER_INFO 사전 매칭 (한글명 및 티커 우선)
    for sym, d in TICKER_INFO.items():
        if sym in ['BIL', 'SGOV']:
            continue
        name_kr = d.get("name_kr", "")
        if q_lower in sym.lower() or q_lower in name_kr.lower():
            results.append({
                "symbol": sym,
                "name": name_kr,
                "category": d.get("category", "ETF"),
                "type": "ETF" if "ETF" in d.get("category", "") else "EQUITY"
            })
            seen.add(sym)

    # 2. Yahoo Finance Search API를 통한 동적 종목/ETF 검색
    try:
        # yf.Search에 타임아웃 방지 및 안전 예외처리
        yf_search = yf.Search(query, max_results=8)
        quotes = getattr(yf_search, 'quotes', []) or []
        for item in quotes:
            sym = item.get('symbol', '').upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            short_name = item.get('shortname') or item.get('longname') or sym
            quote_type = item.get('quoteType', 'ETF')
            exch = item.get('exchDisp') or item.get('exchange') or ''
            results.append({
                "symbol": sym,
                "name": f"{short_name} ({exch})",
                "category": quote_type,
                "type": quote_type
            })
    except Exception as e:
        pass

    # 만약 직접 티커를 입력한 경우(예: 직접 알파벳 입력) 결과 최상단 보장
    query_sym = query.upper()
    if query_sym not in seen and len(query_sym) <= 10:
        results.insert(0, {
            "symbol": query_sym,
            "name": f"직접 입력 티커: {query_sym}",
            "category": "직접입력",
            "type": "CUSTOM"
        })

    return jsonify({"status": "success", "results": results[:12]})


@app.route('/api/status', methods=['GET'])
def get_status():
    _ensure_data_ready()
    with _lock:
        st = dict(_data_status)
    return jsonify(st)


@app.route('/api/tickers', methods=['GET'])
def get_tickers():
    return jsonify({
        "tickers": ALL_TICKERS,
        "details": TICKER_INFO,
        "default_etf1": "SOXL",
        "default_etf2": "TQQQ",
        "default_etf1_ratio": 50,
        "default_etf2_ratio": 50,
        "default_season_months": [1, 2, 3, 4, 11, 12]
    })


@app.route('/api/refresh_data', methods=['POST'])
def refresh_data():
    t = threading.Thread(target=_load_or_fetch_data, kwargs={"force_download": True})
    t.daemon = True
    t.start()
    return jsonify({"message": "Yahoo Finance로부터 최신 데이터 다운로드를 시작했습니다."})


@app.route('/api/date_range', methods=['GET'])
def get_date_range():
    if not _ensure_data_ready():
        return jsonify({"status": "error", "message": "데이터 준비 중"}), 400

    etf1 = request.args.get('etf1', 'SOXL').strip().upper()
    etf2 = request.args.get('etf2', 'TQQQ').strip().upper()

    # 필요 시 동적 다운로드
    _ensure_tickers_loaded([etf1, etf2])

    req = list({etf1, etf2, SAFE_PROXY})

    with _lock:
        for t in req:
            if t not in _data.columns:
                return jsonify({"status": "error", "message": f"{t} 티커 없음"}), 400

        sub = _data[req].dropna()
        if len(sub) == 0:
            return jsonify({"status": "error", "message": "공통 데이터 없음"}), 400

        min_d = sub.index[0].strftime('%Y-%m-%d')
        max_d = sub.index[-1].strftime('%Y-%m-%d')
    # 시작 날짜는 1970-01-01부터 선택 가능, 기본 시작일은 2001-01-01 또는 가용 시작일
    def_s = max(min_d, "2001-01-01") if min_d <= "2001-01-01" else min_d

    return jsonify({
        "status": "success",
        "min_date": "1970-01-01",
        "data_min_date": min_d,
        "max_date": max_d,
        "default_start": def_s,
        "default_end": max_d
    })


@app.route('/api/permanent_portfolio', methods=['POST'])
def permanent_portfolio():
    if not _ensure_data_ready():
        return jsonify({
            "status": "error",
            "message": "데이터가 아직 준비되지 않았습니다. 잠시 후 다시 시도해주세요."
        }), 400
    
    data = request.get_json() or {}
    w_spy = float(data.get('w_spy', 25)) / 100.0
    w_tlt = float(data.get('w_tlt', 25)) / 100.0
    w_gld = float(data.get('w_gld', 25)) / 100.0
    w_bil = float(data.get('w_bil', 25)) / 100.0

    init_cap = float(data.get('init_cap', 50000000))
    monthly_add = float(data.get('monthly_add', 500000))
    rebal_months = int(data.get('rebal_months', 12))
    season_months = data.get('season_months', list(range(1, 13)))
    start_date = data.get('start_date', '1970-01-01')
    end_date = data.get('end_date')
    raw_fee = float(data.get('fee_rate', 0.1))
    fee_rate = raw_fee / 100.0 if raw_fee > 0.01 else raw_fee

    try:
        result = _run_permanent_portfolio_backtest(
            w_spy=w_spy,
            w_tlt=w_tlt,
            w_gld=w_gld,
            w_bil=w_bil,
            init_cap=init_cap,
            monthly_add=monthly_add,
            rebal_months=rebal_months,
            season_months=season_months,
            start_date=start_date,
            end_date=end_date,
            fee_rate=fee_rate
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400

@app.route('/api/allweather_portfolio', methods=['POST'])
def allweather_portfolio():
    if not _ensure_data_ready():
        return jsonify({
            "status": "error",
            "message": "데이터가 아직 준비되지 않았습니다. 잠시 후 다시 시도해주세요."
        }), 400

    data = request.get_json() or {}
    w_spy = float(data.get('w_spy', 30)) / 100.0
    w_tlt = float(data.get('w_tlt', 40)) / 100.0
    w_ief = float(data.get('w_ief', 15)) / 100.0
    w_gld = float(data.get('w_gld', 7.5)) / 100.0
    w_dbc = float(data.get('w_dbc', 7.5)) / 100.0

    init_cap = float(data.get('init_cap', 50000000))
    monthly_add = float(data.get('monthly_add', 500000))
    rebal_months = int(data.get('rebal_months', 12))
    season_months = data.get('season_months', list(range(1, 13)))
    start_date = data.get('start_date', '1970-01-01')
    end_date = data.get('end_date')
    raw_fee = float(data.get('fee_rate', 0.1))
    fee_rate = raw_fee / 100.0 if raw_fee > 0.01 else raw_fee

    try:
        result = _run_allweather_portfolio_backtest(
            w_spy=w_spy,
            w_tlt=w_tlt,
            w_ief=w_ief,
            w_gld=w_gld,
            w_dbc=w_dbc,
            init_cap=init_cap,
            monthly_add=monthly_add,
            rebal_months=rebal_months,
            season_months=season_months,
            start_date=start_date,
            end_date=end_date,
            fee_rate=fee_rate
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400

@app.route('/api/backtest', methods=['POST'])
def backtest():
    if not _ensure_data_ready():
        return jsonify({
            "status": "error",
            "message": "데이터가 아직 준비되지 않았습니다. Yahoo Finance 수집 완료 후 다시 시도해주세요."
        }), 400
        
    data = request.get_json() or {}
    raw_assets = data.get('assets')
    parsed_assets = None

    if isinstance(raw_assets, list) and len(raw_assets) > 0:
        parsed_assets = []
        for a in raw_assets:
            if not isinstance(a, dict):
                continue
            t = str(a.get('ticker', '')).strip().upper()
            w = float(a.get('weight', 0))
            if t and w >= 0:
                parsed_assets.append({'ticker': t, 'weight': w})
        if parsed_assets:
            _ensure_tickers_loaded([a['ticker'] for a in parsed_assets])
        else:
            parsed_assets = None

    etf1 = str(data.get('etf1') or data.get('ticker1') or 'SOXL').strip().upper()
    etf2 = str(data.get('etf2') or data.get('ticker2') or 'TQQQ').strip().upper()

    if not parsed_assets:
        _ensure_tickers_loaded([etf1, etf2])

    # ETF 1과 ETF 2의 비중 처리 (하위 호환)
    etf1_ratio_pct = float(data.get('etf1_ratio', data.get('weight1', 50)))
    if ('etf2_ratio' in data or 'weight2' in data) and ('etf1_ratio' not in data and 'weight1' not in data):
        etf1_ratio_pct = 100.0 - float(data.get('etf2_ratio', data.get('weight2', 50)))

    init_cap = float(data.get('init_cap', 50000000))
    monthly_add = float(data.get('monthly_add', 500000))
    season_months = data.get('season_months', [1, 2, 3, 4, 11, 12])
    rebal_months = int(data.get('rebal_months', 1))
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    raw_fee = float(data.get('fee_rate', 0.1))
    fee_rate = raw_fee / 100.0 if raw_fee > 0.01 else raw_fee

    try:
        etf1_ratio = max(0.0, min(1.0, etf1_ratio_pct / 100.0))
        result = _run_seasonality_backtest(
            etf1=etf1,
            etf2=etf2,
            etf1_ratio=etf1_ratio,
            init_cap=init_cap,
            monthly_add=monthly_add,
            season_months=[int(m) for m in season_months],
            rebal_months=rebal_months,
            start_date=start_date,
            end_date=end_date,
            fee_rate=fee_rate,
            assets=parsed_assets
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400

@app.route('/api/dynamic_live_signal', methods=['GET'])
def dynamic_live_signal():
    if not _ensure_data_ready():
        return jsonify({
            "status": "error",
            "message": "데이터가 아직 준비되지 않았습니다. 잠시 후 다시 시도해주세요."
        }), 400

    strategy_id = request.args.get('strategy', 'BAA').strip().upper()
    try:
        sig = _get_dynamic_live_signal(strategy_id)
        return jsonify({
            "status": "success",
            "live_signal": sig
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400


@app.route('/api/dynamic_allocation', methods=['POST'])
def dynamic_allocation():
    if not _ensure_data_ready():
        return jsonify({
            "status": "error",
            "message": "데이터가 아직 준비되지 않았습니다. 잠시 후 다시 시도해주세요."
        }), 400

    data = request.get_json() or {}
    strategy_id = str(data.get('strategy_id', 'BAA')).strip().upper()
    benchmark_id = str(data.get('benchmark_id', 'SPY')).strip().upper()

    init_cap = float(data.get('init_cap', 50000000))
    monthly_add = float(data.get('monthly_add', 500000))
    start_date = data.get('start_date', '1970-01-01')
    end_date = data.get('end_date')
    raw_fee = float(data.get('fee_rate', 0.1))
    fee_rate = raw_fee / 100.0 if raw_fee > 0.01 else raw_fee

    try:
        result = _run_dynamic_allocation_backtest(
            strategy_id=strategy_id,
            benchmark_id=benchmark_id,
            init_cap=init_cap,
            monthly_add=monthly_add,
            start_date=start_date,
            end_date=end_date,
            fee_rate=fee_rate
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400

def _fetch_cnn_fear_greed() -> dict:
    """CNN Fear & Greed Index 공식 JSON API 호출"""
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://edition.cnn.com/markets/fear-and-greed"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        fg = data.get("fear_and_greed", {}) or {}
        hist_raw = (data.get("fear_and_greed_historical") or {}).get("data") or []

        history_90d = []
        for pt in hist_raw[-90:]:
            x_ms = pt.get("x")
            y_val = pt.get("y")
            if x_ms is not None and y_val is not None:
                dt_str = datetime.datetime.utcfromtimestamp(float(x_ms) / 1000.0).strftime("%Y-%m-%d")
                history_90d.append({"date": dt_str, "score": round(float(y_val), 1)})

        def _r(v):
            return round(float(v), 1) if v is not None else None

        return {
            "available": True,
            "score": _r(fg.get("score")),
            "rating": fg.get("rating") or "N/A",
            "previous_close": _r(fg.get("previous_close")),
            "previous_1_week": _r(fg.get("previous_1_week")),
            "previous_1_month": _r(fg.get("previous_1_month")),
            "previous_1_year": _r(fg.get("previous_1_year")),
            "history_90d": history_90d
        }
    except Exception as e:
        return {
            "available": False,
            "score": None,
            "rating": "Unavailable",
            "previous_close": None,
            "previous_1_week": None,
            "previous_1_month": None,
            "previous_1_year": None,
            "history_90d": [],
            "error": str(e)
        }


def _extract_close_series(df: pd.DataFrame, ticker: str) -> pd.Series:
    """yf.download 결과에서 특정 티커의 Close 시계열을 안전하게 추출"""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    if isinstance(df.columns, pd.MultiIndex):
        if ticker in df.columns.get_level_values(0):
            sub = df[ticker]
            col = "Close" if "Close" in sub.columns else sub.columns[0]
            return pd.to_numeric(sub[col], errors="coerce").dropna()
        if "Close" in df.columns.get_level_values(0) and ticker in df["Close"].columns:
            return pd.to_numeric(df["Close"][ticker], errors="coerce").dropna()
    else:
        col = "Close" if "Close" in df.columns else df.columns[0]
        return pd.to_numeric(df[col], errors="coerce").dropna()
    return pd.Series(dtype=float)


def _calc_rsi_series(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1.0 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1.0 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)

def _fetch_kr_pbr_metrics() -> tuple[float | None, float | None]:
    """KOSPI 지수 PBR 및 삼성전자(005930) 최신 PBR 조회 (네이버 증권 API 우선, pykrx 폴백)"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    kospi_pbr = None
    sec_pbr = None

    def _to_float(val):
        if val is None:
            return None
        s = str(val).replace(",", "").replace("배", "").strip()
        try:
            return float(s)
        except Exception:
            return None

    # 1-A) [변경] 네이버 모바일 지수 JSON API (삼성전자 PBR 조회와 동일한 해외 IP 허용 경로)
    try:
        for ep in ("basic", "integration"):
            r_m = requests.get(
                f"https://m.stock.naver.com/api/index/KOSPI/{ep}",
                headers={**headers, "Referer": "https://m.stock.naver.com/domestic/index/KOSPI/total"},
                timeout=3,
            )
            if r_m.status_code == 200:
                j = r_m.json()
                for item in j.get("totalInfos", []):
                    if str(item.get("code", "")).lower() == "pbr":
                        val = _to_float(item.get("value"))
                        if val is not None and 0.3 <= val <= 5.0:
                            kospi_pbr = round(val, 2)
                            break
                if kospi_pbr is None and j.get("pbr"):
                    val = _to_float(j.get("pbr"))
                    if val is not None and 0.3 <= val <= 5.0:
                        kospi_pbr = round(val, 2)
            if kospi_pbr is not None:
                break
    except Exception:
        pass

    # 1-B) [신규] KODEX 200(069500) 네이버 모바일 API PBR (KOSPI 대표 지수 추종 ETF)
    if kospi_pbr is None:
        try:
            r_etf = requests.get(
                "https://m.stock.naver.com/api/stock/069500/integration",
                headers={**headers, "Referer": "https://m.stock.naver.com/"},
                timeout=3,
            )
            if r_etf.status_code == 200:
                for item in r_etf.json().get("totalInfos", []):
                    if str(item.get("code", "")).lower() == "pbr":
                        val = _to_float(item.get("value"))
                        if val is not None and 0.3 <= val <= 5.0:
                            kospi_pbr = round(val, 2)
                            break
        except Exception:
            pass

    # 1-C) [수정] 국내 로컬 PC 실행용 KRX 공식 API (Vercel 환경에서는 건너뛰어 5초 지연 방지)
    if kospi_pbr is None and not os.environ.get("VERCEL"):
        try:
            today = datetime.datetime.now()
            strt_dd = (today - datetime.timedelta(days=14)).strftime("%Y%m%d")
            end_dd = today.strftime("%Y%m%d")
            krx_resp = requests.post(
                "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
                headers={
                    **headers,
                    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201010106",
                },
                data={
                    "bld": "dbms/MDC/STAT/standard/MDCSTAT00701",
                    "locale": "ko_KR",
                    "searchType": "A",
                    "idxIndMidclssCd": "01",
                    "indIdx": "1",
                    "indIdx2": "001",
                    "strtDd": strt_dd,
                    "endDd": end_dd,
                    "csvxls_isNo": "false",
                },
                timeout=3,
            )
            if krx_resp.status_code == 200:
                rows = krx_resp.json().get("output", [])
                for row in reversed(rows):
                    val = _to_float(row.get("WT_STKPRC_NETASST_RTO"))
                    if val is not None and val > 0:
                        kospi_pbr = round(val, 2)
                        break
        except Exception:
            pass

    # 1-D) [변경] 최종 안전망: KOSPI 대표 대형주(삼성전자·현대차·KB금융) 네이버 모바일 PBR 평균 근사
    if kospi_pbr is None:
        try:
            rep_pbrs = []
            for rep_code in ("005930", "005380", "105560"):
                r_rep = requests.get(
                    f"https://m.stock.naver.com/api/stock/{rep_code}/integration",
                    headers=headers,
                    timeout=2,
                )
                if r_rep.status_code == 200:
                    for item in r_rep.json().get("totalInfos", []):
                        if str(item.get("code", "")).lower() == "pbr":
                            v = _to_float(item.get("value"))
                            if v is not None and 0.2 <= v <= 5.0:
                                rep_pbrs.append(v)
                                break
            if rep_pbrs:
                kospi_pbr = round(sum(rep_pbrs) / len(rep_pbrs), 2)
        except Exception:
            pass

    # 2) 삼성전자(005930) PBR (네이버 모바일 종목 API -> 실패 시 pykrx -> yfinance)
    try:
        r_sec = requests.get(
            "https://m.stock.naver.com/api/stock/005930/integration",
            headers={**headers, "Referer": "https://finance.naver.com/item/main.naver?code=005930"},
            timeout=5
        )
        if r_sec.status_code == 200:
            for item in r_sec.json().get("totalInfos", []):
                if str(item.get("code", "")).lower() == "pbr":
                    sec_pbr = _to_float(item.get("value"))
                    break
    except Exception:
        pass

    if sec_pbr is None and HAS_PYKRX:
        try:
            today = datetime.datetime.now()
            s_str = (today - datetime.timedelta(days=14)).strftime("%Y%m%d")
            e_str = today.strftime("%Y%m%d")
            df_s = krx.get_market_fundamental(s_str, e_str, "005930")
            if not df_s.empty and "PBR" in df_s.columns:
                sec_pbr = round(float(df_s["PBR"].iloc[-1]), 2)
        except Exception:
            pass

    if sec_pbr is None:
        try:
            pb = (yf.Ticker("005930.KS").info or {}).get("priceToBook")
            if pb is not None:
                sec_pbr = round(float(pb), 2)
        except Exception:
            pass

    return kospi_pbr, sec_pbr

@app.route('/api/checklist_signals', methods=['GET'])
def api_checklist_signals():
    """CNN Fear & Greed + yfinance 기반 매수 6개 / 매도 5개 체크리스트 신호 산출"""
    target_ticker = str(request.args.get("ticker", "SOXL")).strip().upper()
    if target_ticker not in {"SOXL", "TQQQ", "QQQ", "SOXX", "^GSPC"}:
        target_ticker = "SOXL"

    fg_data = _fetch_cnn_fear_greed()
    fg_score = fg_data.get("score")
    kospi_pbr, sec_pbr = _fetch_kr_pbr_metrics()

    tickers = ["^VIX", "^GSPC", "SOXX", "SOXL", "TQQQ", "QQQ"]
    try:
        raw_df = yf.download(
            tickers=tickers,
            period="5y",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True
        )
    except Exception as e:
        return jsonify({"status": "error", "message": f"Yahoo Finance 데이터 조회 실패: {e}"}), 500

    vix_s = _extract_close_series(raw_df, "^VIX")
    gspc_s = _extract_close_series(raw_df, "^GSPC")
    soxx_s = _extract_close_series(raw_df, "SOXX")
    target_s = _extract_close_series(raw_df, target_ticker)

    vix_90d = []
    vix_curr = None
    vix_cond_met = False
    vix_days_elapsed = None
    if not vix_s.empty:
        vix_curr = round(float(vix_s.iloc[-1]), 2)
        for dt, val in vix_s.tail(90).items():
            vix_90d.append({"date": dt.strftime("%Y-%m-%d"), "value": round(float(val), 2)})
        latest_vix_dt = vix_s.index[-1]
        recent_180 = vix_s[vix_s.index >= (latest_vix_dt - pd.Timedelta(days=180))]
        high_dates = recent_180[recent_180 >= 30.0].index
        if len(high_dates) > 0:
            last_spike_dt = high_dates[-1]
            vix_days_elapsed = int((latest_vix_dt - last_spike_dt).days)
            if vix_days_elapsed >= 28:
                vix_cond_met = True

    gspc_mdd_52w = None
    gspc_daily_ret = None
    if len(gspc_s) >= 2:
        gspc_curr = float(gspc_s.iloc[-1])
        gspc_high_52w = float(gspc_s.tail(252).max())
        if gspc_high_52w > 0:
            gspc_mdd_52w = round(((gspc_curr / gspc_high_52w) - 1.0) * 100.0, 2)
        gspc_prev = float(gspc_s.iloc[-2])
        if gspc_prev > 0:
            gspc_daily_ret = round(((gspc_curr / gspc_prev) - 1.0) * 100.0, 2)

    soxx_curr = None
    soxx_sma20 = None
    soxx_disparity = None
    soxx_cond_met = False
    if len(soxx_s) >= 20:
        soxx_curr = round(float(soxx_s.iloc[-1]), 2)
        soxx_sma20 = round(float(soxx_s.tail(20).mean()), 2)
        if soxx_sma20 > 0:
            soxx_disparity = round(((soxx_curr / soxx_sma20) - 1.0) * 100.0, 2)
            soxx_cond_met = soxx_curr <= (soxx_sma20 * 0.85)

    target_curr = None
    target_rsi = None
    target_rsi_5d_peak = None
    target_sma20 = None
    target_sma20_disp = None
    target_sma200d = None
    target_sma200w = None
    macd_curr = None
    macd_sig_curr = None
    macd_dead_cross = False

    if len(target_s) >= 30:
        target_curr = round(float(target_s.iloc[-1]), 2)
        rsi_s = _calc_rsi_series(target_s, 14)
        target_rsi = round(float(rsi_s.iloc[-1]), 2)
        if len(rsi_s) >= 6:
            target_rsi_5d_peak = round(float(rsi_s.iloc[-6:-1].max()), 2)

        target_sma20 = round(float(target_s.tail(20).mean()), 2)
        if target_sma20 > 0:
            target_sma20_disp = round(((target_curr / target_sma20) - 1.0) * 100.0, 2)

        if len(target_s) >= 200:
            target_sma200d = round(float(target_s.tail(200).mean()), 2)
        else:
            target_sma200d = round(float(target_s.mean()), 2)

        weekly_s = target_s.resample("W-FRI").last().dropna()
        if len(weekly_s) >= 200:
            target_sma200w = round(float(weekly_s.tail(200).mean()), 2)
        elif not weekly_s.empty:
            target_sma200w = round(float(weekly_s.mean()), 2)

        ema12 = target_s.ewm(span=12, adjust=False).mean()
        ema26 = target_s.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        sig_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_curr = round(float(macd_line.iloc[-1]), 3)
        macd_sig_curr = round(float(sig_line.iloc[-1]), 3)
        if len(macd_line) >= 2:
            macd_dead_cross = bool(
                (macd_line.iloc[-2] >= sig_line.iloc[-2]) and (macd_line.iloc[-1] < sig_line.iloc[-1])
            )

    buy_checklist = [
        {
            "id": "buy_fg",
            "title": "CNN Fear & Greed 극단적 공포",
            "rule": "Fear & Greed < 20",
            "current": f"{fg_score}" if fg_score is not None else "N/A",
            "met": bool(fg_score is not None and fg_score < 20.0)
        },
        {
            "id": "buy_vix_28d",
            "title": "VIX 30 돌파 후 1개월(28일) 경과",
            "rule": "VIX ≥ 30 이후 28일+",
            "current": f"현재 {vix_curr} / 경과 {vix_days_elapsed}일" if vix_days_elapsed is not None else f"현재 {vix_curr} (최근 180일 30↑ 없음)",
            "met": bool(vix_cond_met)
        },
        {
            "id": "buy_rsi",
            "title": f"{target_ticker} RSI(14) 과매도",
            "rule": "RSI(14) ≤ 30",
            "current": f"{target_rsi}" if target_rsi is not None else "N/A",
            "met": bool(target_rsi is not None and target_rsi <= 30.0)
        },
        {
            "id": "buy_sp500_mdd",
            "title": "S&P 500 52주 고점 대비 급락",
            "rule": "52주 MDD ≤ -14%",
            "current": f"{gspc_mdd_52w:+.2f}%" if gspc_mdd_52w is not None else "N/A",
            "met": bool(gspc_mdd_52w is not None and gspc_mdd_52w <= -14.0)
        },
        {
            "id": "buy_soxx_ma20",
            "title": "SOXX 20일 이평선 과도 하회",
            "rule": "종가 ≤ 20일선 × 0.85 (-15%)",
            "current": f"${soxx_curr} (이격 {soxx_disparity:+.2f}%)" if soxx_curr is not None and soxx_disparity is not None else "N/A",
            "met": bool(soxx_cond_met)
        },
        {
            "id": "buy_200dw",
            "title": f"{target_ticker} 200일선·200주선 동시 이탈",
            "rule": "종가 < 200일선 AND < 200주선",
            "current": f"${target_curr} (200D ${target_sma200d} / 200W ${target_sma200w})" if target_curr is not None else "N/A",
            "met": bool(
                target_curr is not None and target_sma200d is not None and target_sma200w is not None
                and target_curr < target_sma200d and target_curr < target_sma200w
            )
        },
        {
            "id": "buy_kospi_pbr",
            "title": "KOSPI PBR 저평가 진입",
            "rule": "KOSPI PBR ≤ 0.90배",
            "current": f"{kospi_pbr:.2f}배" if kospi_pbr is not None else "N/A",
            "met": bool(kospi_pbr is not None and kospi_pbr <= 0.90)
        },
        {
            "id": "buy_sec_pbr",
            "title": "삼성전자 PBR 1배 이하 저평가",
            "rule": "삼성전자 PBR ≤ 1.00배 (0.9~1.0배 권역)",
            "current": f"{sec_pbr:.2f}배" if sec_pbr is not None else "N/A",
            "met": bool(sec_pbr is not None and sec_pbr <= 1.00)
        }
    ]

    sell_checklist = [
        {
            "id": "sell_fg",
            "title": "CNN Fear & Greed 극단적 탐욕",
            "rule": "Fear & Greed ≥ 80",
            "current": f"{fg_score}" if fg_score is not None else "N/A",
            "met": bool(fg_score is not None and fg_score >= 80.0)
        },
        {
            "id": "sell_rsi_cross",
            "title": f"{target_ticker} RSI 70 돌파 후 하향 이탈",
            "rule": "최근 5일 > 70 후 현재 ≤ 70",
            "current": f"현재 {target_rsi} (5일 최고 {target_rsi_5d_peak})" if target_rsi is not None else "N/A",
            "met": bool(
                target_rsi is not None and target_rsi_5d_peak is not None
                and target_rsi_5d_peak > 70.0 and target_rsi <= 70.0
            )
        },
        {
            "id": "sell_ma20_over",
            "title": f"{target_ticker} 20일 이평선 과열 이격",
            "rule": "종가 ≥ 20일선 × 1.15 (+15%)",
            "current": f"${target_curr} (이격 {target_sma20_disp:+.2f}%)" if target_curr is not None and target_sma20_disp is not None else "N/A",
            "met": bool(
                target_curr is not None and target_sma20 is not None and target_curr >= (target_sma20 * 1.15)
            )
        },
        {
            "id": "sell_macd_dc",
            "title": f"{target_ticker} MACD(12,26,9) 데드크로스",
            "rule": "MACD < Signal 하향 교차",
            "current": f"MACD {macd_curr} / Sig {macd_sig_curr}" if macd_curr is not None else "N/A",
            "met": bool(macd_dead_cross)
        },
       {
            "id": "sell_sp500_drop",
            "title": "S&P 500 일간 급락 경보",
            "rule": "일간 수익률 ≤ -1.5%",
            "current": f"{gspc_daily_ret:+.2f}%" if gspc_daily_ret is not None else "N/A",
            "met": bool(gspc_daily_ret is not None and gspc_daily_ret <= -1.5)
        },
        {
            "id": "sell_sec_pbr",
            "title": "삼성전자 PBR 고평가 과열",
            "rule": "삼성전자 PBR ≥ 2.10배",
            "current": f"{sec_pbr:.2f}배" if sec_pbr is not None else "N/A",
            "met": bool(sec_pbr is not None and sec_pbr >= 2.10)
        }
    ]

    return jsonify({
        "status": "success",
        "target_ticker": target_ticker,
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fear_and_greed": fg_data,
        "vix": {
            "current": vix_curr,
            "history_90d": vix_90d
        },
        "buy_checklist": buy_checklist,
        "sell_checklist": sell_checklist,
        "buy_on_count": sum(1 for item in buy_checklist if item["met"]),
        "sell_on_count": sum(1 for item in sell_checklist if item["met"])
    })


def _sanitize_api_error(err) -> str:
    """에러 메시지에서 ?key=AIza... 등 민감한 API 키 쿼리 문자열을 완전히 제거"""
    msg = str(err or "")
    msg = re.sub(r"([?&]key=)[^&\s\"']+", r"\1***", msg, flags=re.IGNORECASE)
    msg = re.sub(r"AIza[0-9A-Za-z\-_]{20,}", "AIza***", msg)
    return msg


def _post_gemini_with_retry(url: str, payload: dict, timeout: int = 30, max_retries: int = 2, delay: float = 1.5):
    """Gemini API 호출 시 429/503 일시 과부하 발생 시 1.5초 대기 후 최대 2회 자동 재시도"""
    last_resp = None
    for attempt in range(max_retries + 1):
        last_resp = requests.post(url, json=payload, timeout=timeout)
        if last_resp.status_code not in (429, 503):
            return last_resp
        if attempt < max_retries:
            time.sleep(delay)
    return last_resp


@app.route('/api/ai_analyst_chat', methods=['POST', 'OPTIONS'])
def api_ai_analyst_chat():
    """Gemini / OpenAI / Anthropic REST API 기반 멀티 프로바이더 퀀트 애널리스트 챗봇"""
    if request.method == 'OPTIONS':
        return jsonify({"ok": True}), 200

    data = request.get_json(force=True, silent=True) or {}
    provider = str(data.get("provider") or "gemini").strip().lower()
    model = str(data.get("model") or "").strip()
    api_key = str(data.get("api_key") or "").strip()
    tab_name = str(data.get("tab_name") or "퀀트 대시보드").strip()
    context_summary = str(data.get("context_summary") or "현재 선택된 전략의 요약 데이터가 없습니다.").strip()
    raw_messages = data.get("messages") if isinstance(data.get("messages"), list) else []

    if not api_key:
        return jsonify({
            "ok": False,
            "error": "우측 상단 톱니바퀴(⚙️) 설정에서 AI API 키를 먼저 등록해 주세요."
        })

    clean_messages = []
    for m in raw_messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "user").strip().lower()
        if role not in ("user", "assistant"):
            role = "user"
        content = str(m.get("content") or "").strip()
        if content:
            clean_messages.append({"role": role, "content": content})

    if not clean_messages:
        clean_messages = [{"role": "user", "content": "현재 화면의 전략 데이터를 분석해 주세요."}]

    system_prompt = (
        f"너는 월스트리트 출신 퀀트 포트폴리오 애널리스트다. "
        f"현재 사용자가 보고 있는 [{tab_name}] 탭의 실제 백테스트 및 스크리닝 데이터는 다음과 같다:\n"
        f"{context_summary}\n"
        f"이 수치를 근거로 명확하고 실전적인 투자 인사이트를 한국어로 답변해 줘."
    )

    try:
        if "openai" in provider:
            target_model = model or "gpt-4o-mini"
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                json={
                    "model": target_model,
                    "messages": [{"role": "system", "content": system_prompt}] + clean_messages,
                    "temperature": 0.3
                },
                timeout=30
            )
            if resp.status_code in (401, 403):
                return jsonify({"ok": False, "error": "OpenAI API 키가 유효하지 않거나 권한이 없습니다. 키를 다시 확인해 주세요."})
            if resp.status_code == 429:
                return jsonify({"ok": False, "error": "OpenAI API 호출 한도(Rate Limit/Quota)를 초과했습니다. 잠시 후 다시 시도해 주세요."})
            resp.raise_for_status()
            reply = resp.json()["choices"][0]["message"]["content"].strip()

        elif "anthropic" in provider or "claude" in provider:
            target_model = model or "claude-3-5-sonnet-latest"
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": target_model,
                    "max_tokens": 1500,
                    "system": system_prompt,
                    "messages": clean_messages
                },
                timeout=30
            )
            if resp.status_code in (401, 403):
                return jsonify({"ok": False, "error": "Anthropic Claude API 키가 유효하지 않거나 권한이 없습니다. 키를 다시 확인해 주세요."})
            if resp.status_code == 429:
                return jsonify({"ok": False, "error": "Anthropic Claude API 호출 한도(Rate Limit)를 초과했습니다. 잠시 후 다시 시도해 주세요."})
            resp.raise_for_status()
            blocks = resp.json().get("content") or []
            reply = "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text").strip()

        else:
            # 기본값: Gemini
            target_model = model or "gemini-4-hydrogen"
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
            gemini_contents = [
                {
                    "role": "model" if m["role"] == "assistant" else "user",
                    "parts": [{"text": m["content"]}]
                }
                for m in clean_messages
            ]
            resp = _post_gemini_with_retry(
                gemini_url,
                {
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": gemini_contents,
                    "generationConfig": {"temperature": 0.3}
                },
                timeout=30,
                max_retries=2,
                delay=1.5
            )
            if resp.status_code in (400, 401, 403):
                err_msg = ""
                try:
                    err_msg = resp.json().get("error", {}).get("message", "")
                except Exception:
                    pass
                if "API_KEY_INVALID" in err_msg or resp.status_code in (401, 403):
                    return jsonify({"ok": False, "error": "Gemini API 키가 유효하지 않거나 권한이 없습니다. 키를 다시 확인해 주세요."})
                return jsonify({"ok": False, "error": f"Gemini 요청 오류: {_sanitize_api_error(err_msg) or resp.status_code}"})
            if resp.status_code == 429:
                return jsonify({"ok": False, "error": "Gemini API 호출 한도(429)를 초과했습니다. 잠시 후 다시 시도해 주세요."})
            if resp.status_code == 503:
                return jsonify({"ok": False, "error": "Google Gemini 서버가 일시적으로 과부하 상태입니다(503). 잠시 후 다시 시도해 주세요."})
            if not resp.ok:
                return jsonify({"ok": False, "error": f"Gemini 서버 응답 오류 (HTTP {resp.status_code}). 잠시 후 다시 시도해 주세요."})
            reply = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

        return jsonify({"ok": True, "reply": reply})

    except requests.Timeout:
        return jsonify({"ok": False, "error": "AI 서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."})
    except Exception as e:
        return jsonify({"ok": False, "error": f"AI 응답 생성 중 오류가 발생했습니다: {_sanitize_api_error(e)}"})


# Vercel 서버 시작 시 즉시 내장 캐시 데이터를 메모리에 적재
# if os.environ.get("VERCEL"):
# _load_or_fetch_data()

@app.route("/api/search_kr_stock", methods=["GET"])
def api_search_kr_stock():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"status": "success", "results": []})
    try:
        results = search_korean_stocks(query, limit=10)
        return jsonify({"status": "success", "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/stock/<query>", methods=["GET"])
def get_stock_info(query):
    force_refresh = request.args.get("refresh", "false").lower() == "true"

    try:
        # '005930', '005930.KS', '삼성전자', 'SK하이닉스' 모두 6자리 종목코드로 변환
        clean_ticker = resolve_korean_ticker(query)
        data = load_or_fetch_stock(
            ticker=clean_ticker,
            fetcher=fetch_all_stock_data,
            force_refresh=force_refresh,
        )
        return jsonify({"status": "success", **data})
    except Exception as e:
        return jsonify({
            "status": "error",
            "query": query,
            "message": f"종목 조회 실패: {str(e)}"
        }), 400


# ==============================================================================
# 1) 국내주식 펀더멘털 & 수급 분석 API: GET /api/stock_analysis/kr?q=005930
# ==============================================================================
@app.route("/api/stock_analysis/kr", methods=["GET"])
def api_stock_analysis_kr():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"status": "error", "message": "종목코드 또는 종목명을 입력해 주세요."}), 400

    ticker_code, stock_name = resolve_kr_ticker(query)
    if not re.fullmatch(r"\d{6}", ticker_code):
        return jsonify({"status": "error", "message": f"'{query}'에 해당하는 국내주식 종목코드를 찾지 못했습니다."}), 404

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": f"https://finance.naver.com/item/main.naver?code={ticker_code}"
    }

    try:
        # 1. 현재가 및 기본 재무 (yfinance .KS -> .KQ)
        yf_symbol = f"{ticker_code}.KS"
        tk = yf.Ticker(yf_symbol)
        hist = tk.history(period="5d")
        if hist.empty:
            yf_symbol = f"{ticker_code}.KQ"
            tk = yf.Ticker(yf_symbol)
            hist = tk.history(period="5d")

        if hist.empty:
            return jsonify({"status": "error", "message": f"'{stock_name}({ticker_code})' 시세 데이터를 찾을 수 없습니다."}), 404

        info = tk.info or {}
        close_price = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else close_price
        change_pct = round(((close_price - prev_close) / prev_close) * 100, 2) if prev_close else 0.0

        # 2. 네이버 증권 모바일 JSON API로 PER, PBR, 배당수익률, ROE, 영업이익률 조회
        nv_per = nv_pbr = nv_div = nv_roe = nv_opm = None
        try:
            integ_url = f"https://m.stock.naver.com/api/stock/{ticker_code}/integration"
            res_int = requests.get(integ_url, headers=headers, timeout=6)
            if res_int.status_code == 200:
                j_data = res_int.json()
                if j_data.get("stockName"):
                    stock_name = j_data["stockName"]

                def _parse_val(v):
                    if v is None:
                        return None
                    s = str(v).replace(",", "").replace("배", "").replace("%", "").replace("원", "").strip()
                    try:
                        return float(s)
                    except Exception:
                        return None

                for item in j_data.get("totalInfos", []):
                    code_k = item.get("code", "")
                    val_v = _parse_val(item.get("value"))
                    if code_k == "per" and val_v is not None:
                        nv_per = val_v
                    elif code_k == "pbr" and val_v is not None:
                        nv_pbr = val_v
                    elif code_k == "dividendYieldRatio" and val_v is not None:
                        nv_div = val_v
        except Exception:
            pass

        per = nv_per if nv_per is not None else info.get("trailingPE")
        pbr = nv_pbr if nv_pbr is not None else info.get("priceToBook")
        roe = (nv_roe / 100.0) if nv_roe is not None else info.get("returnOnEquity")
        op_margin = (nv_opm / 100.0) if nv_opm is not None else info.get("operatingMargins")
        div_yield = nv_div if nv_div is not None else (info.get("dividendYield") * 100 if info.get("dividendYield") else None)

        fundamentals = [
            {
                "metric": "PER (주가수익비율)",
                "value": f"{per:.2f}배" if per else "N/A",
                "comment": "저평가 구간" if (per and 0 < per < 12) else ("적정 수준" if (per and per < 25) else "성장 프리미엄 / 적자")
            },
            {
                "metric": "PBR (주가순자산비율)",
                "value": f"{pbr:.2f}배" if pbr else "N/A",
                "comment": "순자산 대비 저평가 (1배↓)" if (pbr and pbr < 1.0) else "자산가치 이상 평가"
            },
            {
                "metric": "ROE (자기자본이익률)",
                "value": f"{roe * 100:.1f}%" if roe is not None else "N/A",
                "comment": "자본효율 우수 (10%↑)" if (roe is not None and roe >= 0.10) else "수익성 개선 필요"
            },
            {
                "metric": "영업이익률 (OPM)",
                "value": f"{op_margin * 100:.1f}%" if op_margin is not None else "N/A",
                "comment": "양호한 마진 구조 (10%↑)" if (op_margin is not None and op_margin >= 0.10) else "보통 / 원가 부담"
            },
            {
                "metric": "배당수익률",
                "value": f"{div_yield:.2f}%" if div_yield else "0.00%",
                "comment": "고배당 매력 (3%↑)" if (div_yield and div_yield >= 3.0) else "일반 배당"
            },
        ]

        if per and 0 < per < 15 and roe is not None and roe >= 0.10:
            fund_grade = {"label": "펀더멘털 우수", "tier": "tier-2"}
        elif per and per > 0:
            fund_grade = {"label": "펀더멘털 양호", "tier": "tier-1"}
        else:
            fund_grade = {"label": "실적 점검 필요", "tier": "tier-0"}

        # 3. 네이버 모바일 증권 투자자별 매매동향 JSON API로 외국인·기관·개인 순매수(주) 조회
        supply_flows = []
        supply_grade = {"label": "수급 중립", "tier": "tier-1"}
        try:
            trend_url = f"https://m.stock.naver.com/api/stock/{ticker_code}/trend?pageSize=20&page=1"
            res_tr = requests.get(trend_url, headers=headers, timeout=6)
            if res_tr.status_code == 200:
                tr_list = res_tr.json()
                if isinstance(tr_list, list) and len(tr_list) > 0:
                    def _to_int(val):
                        if val is None:
                            return 0
                        s = str(val).replace(",", "").replace("+", "").strip()
                        try:
                            return int(float(s))
                        except Exception:
                            return 0

                    def _agg_json(n, label):
                        sub = tr_list[:n]
                        f_sum = sum(_to_int(x.get("foreignerPureBuyQuant")) for x in sub)
                        i_sum = sum(_to_int(x.get("organPureBuyQuant")) for x in sub)
                        # 개인 순매수 필드가 있으면 직접 쓰고, 없으면 -(외국인+기관)으로 계산
                        if "individualPureBuyQuant" in sub[0]:
                            r_sum = sum(_to_int(x.get("individualPureBuyQuant")) for x in sub)
                        else:
                            r_sum = -(f_sum + i_sum)
                        return {
                            "period": label,
                            "foreign": f_sum,
                            "institution": i_sum,
                            "retail": r_sum
                        }

                    supply_flows = [
                        _agg_json(1, "최근 1거래일 (주)"),
                        _agg_json(5, "최근 5거래일 (주)"),
                        _agg_json(20, "최근 20거래일 (주)")
                    ]

                    f_5d = supply_flows[1]["foreign"]
                    i_5d = supply_flows[1]["institution"]
                    if f_5d > 0 and i_5d > 0:
                        supply_grade = {"label": "외인·기관 쌍끌이 매수", "tier": "tier-2"}
                    elif f_5d > 0 or i_5d > 0:
                        supply_grade = {"label": "메이저 부분 유입", "tier": "tier-1"}
                    else:
                        supply_grade = {"label": "외인·기관 동반 매도", "tier": "tier-0"}
        except Exception:
            pass

        if not supply_flows:
            supply_flows = [
                {"period": "최근 1거래일", "foreign": 0, "institution": 0, "retail": 0},
                {"period": "최근 5거래일", "foreign": 0, "institution": 0, "retail": 0},
                {"period": "최근 20거래일", "foreign": 0, "institution": 0, "retail": 0},
            ]
            supply_grade = {"label": "수급 데이터 없음", "tier": "tier-0"}

        return jsonify({
            "status": "ok",
            "ticker": ticker_code,
            "name": stock_name,
            "price": round(close_price, 0),
            "change_pct": change_pct,
            "updated_at": now_str,
            "fundamental_grade": fund_grade,
            "fundamentals": fundamentals,
            "supply_grade": supply_grade,
            "supply_flows": supply_flows,
        })

    except Exception as e:
        return jsonify({"status": "error", "message": f"국내주식 분석 오류: {str(e)}"}), 500


# ==============================================================================
# 2) 해외주식 펀더멘털 & 수급 분석 API: GET /api/stock_analysis/us?ticker=NVDA
# ==============================================================================
@app.route("/api/stock_analysis/us", methods=["GET"])
def api_stock_analysis_us():
    ticker = request.args.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"status": "error", "message": "미국주식 티커를 입력해 주세요."}), 400

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="1y")
        if hist.empty:
            return jsonify({"status": "error", "message": f"'{ticker}' 티커 데이터를 찾을 수 없습니다."}), 404

        info = tk.info or {}
        stock_name = info.get("shortName") or info.get("longName") or ticker

        close_price = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else close_price
        change_pct = round(((close_price - prev_close) / prev_close) * 100, 2) if prev_close else 0.0

        trailing_pe = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        peg_ratio = info.get("pegRatio")
        rev_growth = info.get("revenueGrowth")
        roe = info.get("returnOnEquity")
        target_price = info.get("targetMeanPrice")
        upside = ((target_price - close_price) / close_price * 100) if (target_price and close_price) else None

        fundamentals = [
            {
                "metric": "Trailing / Forward PER",
                "value": f"{trailing_pe:.1f}x / {forward_pe:.1f}x" if (trailing_pe and forward_pe) else (f"{forward_pe:.1f}x" if forward_pe else "N/A"),
                "comment": "실적 성장으로 밸류 부담 완화" if (trailing_pe and forward_pe and forward_pe < trailing_pe) else "멀티플 수준 점검"
            },
            {
                "metric": "PEG 비율",
                "value": f"{peg_ratio:.2f}" if peg_ratio else "N/A",
                "comment": "성장 대비 저평가 (1.5↓)" if (peg_ratio and peg_ratio < 1.5) else "성장 프리미엄 반영"
            },
            {
                "metric": "매출 성장률 (YoY)",
                "value": f"{rev_growth * 100:+.1f}%" if rev_growth is not None else "N/A",
                "comment": "고성장 지속 (15%↑)" if (rev_growth and rev_growth >= 0.15) else "안정적 외형 성장"
            },
            {
                "metric": "ROE (자기자본이익률)",
                "value": f"{roe * 100:.1f}%" if roe else "N/A",
                "comment": "우량 수익성 (15%↑)" if (roe and roe >= 0.15) else "보통 수준"
            },
            {
                "metric": "월가 평균 목표가 (괴리율)",
                "value": f"${target_price:.2f} ({upside:+.1f}%)" if target_price else "N/A",
                "comment": "상승 여력 보유" if (upside and upside > 10) else "목표가 근접"
            },
        ]

        if (rev_growth and rev_growth >= 0.15) and (roe and roe >= 0.15):
            fund_grade = {"label": "고성장·우량 펀더멘털", "tier": "tier-2"}
        elif forward_pe and forward_pe > 0:
            fund_grade = {"label": "펀더멘털 양호", "tier": "tier-1"}
        else:
            fund_grade = {"label": "밸류에이션 점검", "tier": "tier-0"}

        inst_pct = info.get("heldPercentInstitutions")
        short_pct = info.get("shortPercentOfFloat")
        vol_today = float(hist["Volume"].iloc[-1])
        vol_20d_avg = float(hist["Volume"].tail(20).mean())
        rvol = (vol_today / vol_20d_avg) if vol_20d_avg > 0 else 1.0

        ma50 = float(hist["Close"].tail(50).mean())
        ma200 = float(hist["Close"].tail(200).mean()) if len(hist) >= 200 else ma50
        above_ma50 = close_price > ma50
        above_ma200 = close_price > ma200

        supply_metrics = [
            {
                "metric": "기관 보유 비중",
                "value": f"{inst_pct * 100:.1f}%" if inst_pct else "N/A",
                "comment": "기관 메이저 수급 탄탄 (60%↑)" if (inst_pct and inst_pct >= 0.60) else "개인·기관 혼재"
            },
            {
                "metric": "유동주식 공매도 비율",
                "value": f"{short_pct * 100:.2f}%" if short_pct else "N/A",
                "comment": "공매도 압력 낮음 (5%↓)" if (short_pct and short_pct < 0.05) else "숏스퀴즈 또는 하방 압력 주의"
            },
            {
                "metric": "상대 거래량 (RVOL 20일)",
                "value": f"{rvol:.2f}배",
                "comment": "거래량 동반 수급 유입" if rvol >= 1.2 else "평균 수준 거래량"
            },
            {
                "metric": "추세 수급 (50일 / 200일선)",
                "value": f"{'상회' if above_ma50 else '하회'} / {'상회' if above_ma200 else '하회'}",
                "comment": "중장기 정배열 매수 우위" if (above_ma50 and above_ma200) else "이동평균선 저항/조정 구간"
            },
        ]

        if above_ma50 and above_ma200 and (inst_pct and inst_pct >= 0.5):
            supply_grade = {"label": "기관·추세 수급 강세", "tier": "tier-2"}
        elif above_ma200:
            supply_grade = {"label": "중기 수급 양호", "tier": "tier-1"}
        else:
            supply_grade = {"label": "수급 이탈 / 관망", "tier": "tier-0"}

        return jsonify({
            "status": "ok",
            "ticker": ticker,
            "name": stock_name,
            "price": round(close_price, 2),
            "change_pct": change_pct,
            "updated_at": now_str,
            "fundamental_grade": fund_grade,
            "fundamentals": fundamentals,
            "supply_grade": supply_grade,
            "supply_metrics": supply_metrics,
        })

    except Exception as e:
        return jsonify({"status": "error", "message": f"해외주식 분석 오류: {str(e)}"}), 500

# PWA 필수 파일들을 루트(/) 경로에서도 서빙하도록 연결 (Vercel과 경로 통일)
@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")

@app.route("/sw.js")
def serve_sw():
    return send_from_directory("static", "sw.js", mimetype="application/javascript")

@app.route("/icon-192.png")
def serve_icon_192():
    return send_from_directory("static", "icon-192.png", mimetype="image/png")

@app.route("/icon-512.png")
def serve_icon_512():
    return send_from_directory("static", "icon-512.png", mimetype="image/png")

if __name__ == '__main__':
    loader_thread = threading.Thread(target=_load_or_fetch_data)
    loader_thread.daemon = True
    loader_thread.start()

    print("=" * 60)
    print(" [ETF 계절성 스위칭 백테스트 터미널 (Yahoo Finance)]")
    print(" 로컬 웹 서버 주소: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)
