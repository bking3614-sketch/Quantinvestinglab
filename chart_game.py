# -*- coding: utf-8 -*-
"""
chart_game.py - 차트 랜덤 게임 (Chart Trading Game) 백엔드 모듈
Flask Blueprint: chart_game_bp, url_prefix='/api/chart_game'

기능:
1. 대표 종목(한국 30개 + 미국 20개) 목록 제공 및 사용자 지정 티커 지원
2. yfinance를 통한 과거 전체 일봉(OHLCV) 다운로드 (수정주가 반영)
3. 무작위 시점(start_idx >= 150) 추출 및 턴 수 자동 조율
4. 블라인드 게임 진행용 캔들 데이터 및 종료 후 공개용 메타데이터 제공
"""

import os
import io
import json
import random
import logging
import zipfile
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import email.utils
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import numpy as np
import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request

try:
    import scipy
    HAS_SCIPY = True
except (ImportError, Exception):
    HAS_SCIPY = False

try:
    import FinanceDataReader as fdr
    HAS_FDR = True
except (ImportError, Exception):
    fdr = None
    HAS_FDR = False

# Vercel 환경 임시 디렉토리 지원
CACHE_DIR = "/tmp/.chart_game_cache" if os.environ.get("VERCEL") else os.path.join(os.path.dirname(__file__), ".chart_game_cache")
try:
    os.makedirs(CACHE_DIR, exist_ok=True)
except Exception:
    pass

logger = logging.getLogger("chart_game")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

chart_game_bp = Blueprint("chart_game", __name__, url_prefix="/api/chart_game")

# ─────────────────────────────────────────────────────────────────────────────
# 1. 대표 종목 풀 (한국 30개, 미국 20개)
# ─────────────────────────────────────────────────────────────────────────────
KR_PRESET_STOCKS: List[Dict[str, str]] = [
    {"ticker": "005930.KS", "name": "삼성전자", "market": "KOSPI"},
    {"ticker": "000660.KS", "name": "SK하이닉스", "market": "KOSPI"},
    {"ticker": "373220.KS", "name": "LG에너지솔루션", "market": "KOSPI"},
    {"ticker": "207940.KS", "name": "삼성바이오로직스", "market": "KOSPI"},
    {"ticker": "005380.KS", "name": "현대차", "market": "KOSPI"},
    {"ticker": "000270.KS", "name": "기아", "market": "KOSPI"},
    {"ticker": "068270.KS", "name": "셀트리온", "market": "KOSPI"},
    {"ticker": "105560.KS", "name": "KB금융", "market": "KOSPI"},
    {"ticker": "035420.KS", "name": "NAVER", "market": "KOSPI"},
    {"ticker": "055550.KS", "name": "신한지주", "market": "KOSPI"},
    {"ticker": "005490.KS", "name": "POSCO홀딩스", "market": "KOSPI"},
    {"ticker": "006400.KS", "name": "삼성SDI", "market": "KOSPI"},
    {"ticker": "051910.KS", "name": "LG화학", "market": "KOSPI"},
    {"ticker": "035720.KS", "name": "카카오", "market": "KOSPI"},
    {"ticker": "010130.KS", "name": "고려아연", "market": "KOSPI"},
    {"ticker": "028260.KS", "name": "삼성물산", "market": "KOSPI"},
    {"ticker": "012330.KS", "name": "현대모비스", "market": "KOSPI"},
    {"ticker": "086790.KS", "name": "하나금융지주", "market": "KOSPI"},
    {"ticker": "138040.KS", "name": "메리츠금융지주", "market": "KOSPI"},
    {"ticker": "034020.KS", "name": "두산에너빌리티", "market": "KOSPI"},
    {"ticker": "011200.KS", "name": "HMM", "market": "KOSPI"},
    {"ticker": "003670.KS", "name": "포스코퓨처엠", "market": "KOSPI"},
    {"ticker": "096770.KS", "name": "SK이노베이션", "market": "KOSPI"},
    {"ticker": "036570.KS", "name": "엔씨소프트", "market": "KOSPI"},
    {"ticker": "259960.KS", "name": "크래프톤", "market": "KOSPI"},
    {"ticker": "377300.KS", "name": "카카오페이", "market": "KOSPI"},
    {"ticker": "247540.KQ", "name": "에코프로비엠", "market": "KOSDAQ"},
    {"ticker": "086520.KQ", "name": "에코프로", "market": "KOSDAQ"},
    {"ticker": "196170.KQ", "name": "알테오젠", "market": "KOSDAQ"},
    {"ticker": "028300.KQ", "name": "HLB", "market": "KOSDAQ"},
]

US_PRESET_STOCKS: List[Dict[str, str]] = [
    {"ticker": "AAPL", "name": "애플 (Apple)", "market": "NASDAQ"},
    {"ticker": "MSFT", "name": "마이크로소프트 (Microsoft)", "market": "NASDAQ"},
    {"ticker": "NVDA", "name": "엔비디아 (NVIDIA)", "market": "NASDAQ"},
    {"ticker": "TSLA", "name": "테슬라 (Tesla)", "market": "NASDAQ"},
    {"ticker": "AMZN", "name": "아마존 (Amazon)", "market": "NASDAQ"},
    {"ticker": "META", "name": "메타 (Meta Platforms)", "market": "NASDAQ"},
    {"ticker": "GOOGL", "name": "알파벳 A (Google)", "market": "NASDAQ"},
    {"ticker": "SPY", "name": "S&P 500 ETF (SPY)", "market": "NYSE ARCA"},
    {"ticker": "QQQ", "name": "나스닥 100 ETF (QQQ)", "market": "NASDAQ"},
    {"ticker": "BRK-B", "name": "버크셔 해서웨이 B", "market": "NYSE"},
    {"ticker": "AMD", "name": "AMD", "market": "NASDAQ"},
    {"ticker": "INTC", "name": "인텔 (Intel)", "market": "NASDAQ"},
    {"ticker": "NFLX", "name": "넷플릭스 (Netflix)", "market": "NASDAQ"},
    {"ticker": "PLTR", "name": "팔란티어 (Palantir)", "market": "NYSE"},
    {"ticker": "COIN", "name": "코인베이스 (Coinbase)", "market": "NASDAQ"},
    {"ticker": "AVGO", "name": "브로드컴 (Broadcom)", "market": "NASDAQ"},
    {"ticker": "TSM", "name": "TSMC", "market": "NYSE"},
    {"ticker": "JNJ", "name": "존슨앤존슨 (Johnson & Johnson)", "market": "NYSE"},
    {"ticker": "JPM", "name": "JP모건 체이스 (JPMorgan)", "market": "NYSE"},
    {"ticker": "V", "name": "비자 (Visa)", "market": "NYSE"},
]

# 티커별 빠른 이름 검색용 맵
PRESET_MAP = {s["ticker"].upper(): s for s in (KR_PRESET_STOCKS + US_PRESET_STOCKS)}


# ─────────────────────────────────────────────────────────────────────────────
# 2. 캔들 다운로드 및 전처리 헬퍼
# ─────────────────────────────────────────────────────────────────────────────
def _is_korean_ticker(ticker: str) -> bool:
    t = ticker.upper()
    return t.endswith(".KS") or t.endswith(".KQ") or (len(t) == 6 and t.isdigit())


def _get_ticker_candidates(raw_ticker: str) -> List[str]:
    """사용자 입력 티커를 바탕으로 시도할 후보 티커 목록 생성"""
    t = raw_ticker.strip().upper()
    if not t or t == "RANDOM":
        all_pool = KR_PRESET_STOCKS + US_PRESET_STOCKS
        chosen = random.choice(all_pool)
        return [chosen["ticker"]]

    # 6자리 숫자인 경우 프리셋 우선 확인 후 .KS, .KQ 시도
    if len(t) == 6 and t.isdigit():
        if f"{t}.KQ" in PRESET_MAP:
            return [f"{t}.KQ", f"{t}.KS"]
        elif f"{t}.KS" in PRESET_MAP:
            return [f"{t}.KS", f"{t}.KQ"]
        return [f"{t}.KS", f"{t}.KQ"]

    # 만약 소문자나 공백이 섞여있거나 대문자 티커인 경우
    # 예: "005930.ks" -> "005930.KS"
    return [t]


def fetch_historical_candles(raw_ticker: str) -> tuple:
    """
    yfinance로부터 최대 기간 수정주가 반영 일봉 데이터를 조회.
    후보 티커(.KS, .KQ 등)를 순차 시도하여 최초 유효 데이터 반환.
    반환: (df, resolved_ticker, stock_name, currency)
    """
    candidates = _get_ticker_candidates(raw_ticker)

    for cand in candidates:
        try:
            ticker_obj = yf.Ticker(cand)
            df = ticker_obj.history(period="max", interval="1d", auto_adjust=True)
        except Exception as e:
            logger.warning(f"Ticker.history failed for {cand}: {e}")
            df = pd.DataFrame()

        if df is None or df.empty:
            try:
                df = yf.download(tickers=cand, period="max", interval="1d", auto_adjust=True, progress=False)
            except Exception as e:
                logger.warning(f"yf.download failed for {cand}: {e}")
                df = pd.DataFrame()

        if df is None or df.empty:
            continue

        # MultiIndex 컬럼 평탄화
        if isinstance(df.columns, pd.MultiIndex):
            new_cols = {}
            for col_name in ["Open", "High", "Low", "Close", "Volume"]:
                for full_col in df.columns:
                    if full_col[0] == col_name or (len(full_col) > 1 and full_col[1] == col_name):
                        new_cols[col_name] = df[full_col]
                        break
            if new_cols:
                df = pd.DataFrame(new_cols, index=df.index)
            else:
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        required_cols = ["Open", "High", "Low", "Close", "Volume"]
        if not all(col in df.columns for col in required_cols):
            continue

        df = df[required_cols].dropna(subset=["Open", "High", "Low", "Close"])
        df = df[df["Close"] > 0]

        # 최소 170개(150 + 20) 일봉 이상이어야 게임 진행 가능
        if len(df) < 170:
            logger.warning(f"Insufficient candles for {cand}: {len(df)}")
            continue

        # 종목명 결정
        lookup = PRESET_MAP.get(cand.upper())
        if lookup:
            stock_name = lookup["name"]
        else:
            stock_name = cand
            try:
                t_info = ticker_obj.info
                stock_name = t_info.get("shortName") or t_info.get("longName") or cand
            except Exception:
                pass

        currency = "KRW" if _is_korean_ticker(cand) else "USD"
        return df, cand, stock_name, currency

    return pd.DataFrame(), "", "", "KRW"


# ─────────────────────────────────────────────────────────────────────────────
# 3. 라우트 엔드포인트
# ─────────────────────────────────────────────────────────────────────────────
@chart_game_bp.route("/tickers", methods=["GET"])
def get_tickers():
    """대표 한국/미국 주식 풀 반환"""
    return jsonify({
        "status": "success",
        "kr_stocks": KR_PRESET_STOCKS,
        "us_stocks": US_PRESET_STOCKS,
        "total_count": len(KR_PRESET_STOCKS) + len(US_PRESET_STOCKS)
    })


@chart_game_bp.route("/new_game", methods=["POST", "OPTIONS"])
def new_game():
    """
    새로운 차트 게임 생성:
    - 티커 결정 (지정 티커 또는 랜덤)
    - 일봉 다운로드 및 검증
    - 무작위 시작 인덱스 (start_idx >= 150) 결정
    - 캔들 및 종료 후 공개용 메타데이터 반환
    """
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    data = request.get_json(force=True, silent=True) or {}

    raw_ticker = str(data.get("ticker", "")).strip()
    try:
        max_turns = int(data.get("max_turns", 50))
    except (ValueError, TypeError):
        max_turns = 50
    # 최소 20, 최대 2000 클램핑
    max_turns = max(20, min(2000, max_turns))

    try:
        initial_capital = float(data.get("initial_capital", 10000000))
    except (ValueError, TypeError):
        initial_capital = 10000000.0

    # 주가 데이터 다운로드 (실제 yfinance 전용, 실패 시 400 반환)
    df, resolved_ticker, stock_name, currency = fetch_historical_candles(raw_ticker)
    if df.empty or len(df) < 170:
        return jsonify({
            "status": "error",
            "message": "Yahoo Finance에서 해당 티커 데이터를 찾을 수 없습니다"
        }), 400

    lookup = PRESET_MAP.get(resolved_ticker.upper())
    market_name = lookup["market"] if lookup else ("KOSPI/KOSDAQ" if currency == "KRW" else "US")

    total_len = len(df)
    min_initial_bars = 150

    # 데이터 길이가 부족한 경우 max_turns 자동 조정
    if total_len < min_initial_bars + max_turns:
        max_turns = max(20, total_len - min_initial_bars)

    # 액면분할 등으로 인한 극초기 동전주/뭉개짐 구간 회피:
    # 종가(Close)가 1.0 이상(한국 주식은 100원 이상)인 시점 이후부터 랜덤 시작점 선택
    min_price_threshold = 100.0 if currency == "KRW" else 1.0
    valid_indices = [i for i, c in enumerate(df["Close"]) if c >= min_price_threshold]

    max_start = total_len - max_turns
    min_start = min_initial_bars

    if valid_indices:
        first_valid_idx = valid_indices[0]
        # 해당 정상 주가 구간 이후에서 시작점을 잡을 수 있는 경우에만 보정
        if first_valid_idx <= max_start:
            min_start = max(min_initial_bars, first_valid_idx)

    if max_start <= min_start:
        start_idx = min_start
    else:
        start_idx = random.randint(min_start, max_start)

    # 필요한 범위 슬라이스 (0부터 start_idx + max_turns까지)
    end_idx = start_idx + max_turns
    sliced_df = df.iloc[:end_idx]

    candles: List[Dict[str, Any]] = []

    for idx, (dt, row) in enumerate(sliced_df.iterrows()):
        dt_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
        candles.append({
            "index": idx,
            "date": dt_str,
            "open": round(float(row["Open"]), 6),
            "high": round(float(row["High"]), 6),
            "low": round(float(row["Low"]), 6),
            "close": round(float(row["Close"]), 6),
            "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0
        })

    # 게임 시작일 및 종료일 메타데이터
    game_start_date = candles[start_idx]["date"]
    game_end_date = candles[-1]["date"]

    ticker_info = {
        "ticker": resolved_ticker,
        "resolved_ticker": resolved_ticker,
        "name": stock_name,
        "market": market_name,
        "currency": currency,
        "game_start_date": game_start_date,
        "game_end_date": game_end_date,
        "total_candles": len(candles),
        "start_idx": start_idx,
        "max_turns": max_turns,
        "is_simulated": False
    }

    return jsonify({
        "status": "success",
        "candles": candles,
        "start_idx": start_idx,
        "max_turns": max_turns,
        "initial_capital": initial_capital,
        "currency": currency,
        "ticker_info": ticker_info
    })


# ─────────────────────────────────────────────────────────────────────────────
# 4. 재무제표 API (미국 SEC EDGAR + 한국 OpenDART / yfinance 폴백)
# ─────────────────────────────────────────────────────────────────────────────
_FINANCIALS_RAW_CACHE: Dict[str, Any] = {}
_FINANCIALS_RESP_CACHE: Dict[str, Any] = {}
_SEC_CIK_CACHE: Optional[Dict[str, str]] = None
_DART_CORP_CODE_CACHE: Optional[Dict[str, str]] = None

SEC_HEADERS = {"User-Agent": "QuantInvestingLab research@quantlab.local"}


# 대표 미국 주식 기본 CIK 매핑 (네트워크 장애 대비 즉시 지원)
_POPULAR_US_CIKS = {
    "AAPL": "0000320193", "MSFT": "0000789019", "NVDA": "0001045810", "TSLA": "0001318605",
    "AMZN": "0001018724", "GOOGL": "0001652044", "GOOG": "0001652044", "META": "0001326801",
    "SPY": "0000884394", "QQQ": "0001067839", "AMD": "0000002488", "INTC": "0000050863",
    "NFLX": "0001065280", "PLTR": "0001321655", "COIN": "0001679788", "AVGO": "0001730168",
    "TSM": "0001046179", "JNJ": "0000200406", "JPM": "0000019617", "V": "0001403161"
}


def _get_sec_cik_map() -> Dict[str, str]:
    """SEC EDGAR Ticker -> 10자리 CIK 매핑 로드 및 캐시"""
    global _SEC_CIK_CACHE
    if _SEC_CIK_CACHE is not None and len(_SEC_CIK_CACHE) > 50:
        return _SEC_CIK_CACHE

    cik_map = dict(_POPULAR_US_CIKS)
    urls = [
        "https://www.sec.gov/files/company_tickers.json",
        "https://data.sec.gov/files/company_tickers.json"
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=SEC_HEADERS)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.values():
                    t = str(item.get("ticker", "")).upper()
                    cik = str(item.get("cik_str", "")).zfill(10)
                    if t and cik:
                        cik_map[t] = cik
                if len(cik_map) > 50:
                    _SEC_CIK_CACHE = cik_map
                    return cik_map
        except Exception as e:
            logger.debug(f"Failed to fetch SEC CIK map from {url}: {e}")

    _SEC_CIK_CACHE = cik_map
    return cik_map


def _fetch_sec_edgar_quarterly(ticker: str, target_date_str: str) -> Optional[List[Dict[str, Any]]]:
    """
    SEC EDGAR XBRL companyfacts API를 통해 filed <= target_date 인 분기 재무제표 추출
    - 미래 실적 누수(Look-Ahead Bias) 엄격 차단
    """
    clean_ticker = ticker.upper().split(".")[0]
    cik_map = _get_sec_cik_map()
    cik = cik_map.get(clean_ticker)
    if not cik:
        return None

    try:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        req = urllib.request.Request(url, headers=SEC_HEADERS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        us_gaap = data.get("facts", {}).get("us-gaap", {})
        if not us_gaap:
            return None

        # 3개월 분기 손익계산서 팩트 추출 헬퍼 (form == '10-Q' & filed <= target_date)
        def extract_duration_facts(concept_names: List[str]):
            results = {}
            for name in concept_names:
                node = us_gaap.get(name, {}).get("units", {}).get("USD", [])
                for entry in node:
                    form = entry.get("form", "")
                    filed = entry.get("filed", "")
                    end = entry.get("end", "")
                    val = entry.get("val")
                    start = entry.get("start", "")
                    if form == "10-Q" and filed and filed <= target_date_str and val is not None:
                        days = 90
                        if start and end:
                            try:
                                d_start = datetime.strptime(start, "%Y-%m-%d")
                                d_end = datetime.strptime(end, "%Y-%m-%d")
                                days = (d_end - d_start).days
                            except Exception:
                                pass
                        if 60 <= days <= 115 or entry.get("fp") in ("Q1", "Q2", "Q3"):
                            prev = results.get(end)
                            if not prev or filed >= prev["filed"]:
                                results[end] = {
                                    "val": float(val),
                                    "filed": filed,
                                    "fp": entry.get("fp", ""),
                                    "fy": entry.get("fy", "")
                                }
            return results

        # 대차대조표 특정 시점 팩트 추출 헬퍼
        def extract_instant_facts(concept_names: List[str]):
            results = {}
            for name in concept_names:
                node = us_gaap.get(name, {}).get("units", {}).get("USD", [])
                for entry in node:
                    form = entry.get("form", "")
                    filed = entry.get("filed", "")
                    end = entry.get("end", "")
                    val = entry.get("val")
                    if form in ("10-Q", "10-K") and filed and filed <= target_date_str and val is not None:
                        prev = results.get(end)
                        if not prev or filed >= prev["filed"]:
                            results[end] = {
                                "val": float(val),
                                "filed": filed
                            }
            return results

        rev_map = extract_duration_facts(["RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "Revenues"])
        op_map = extract_duration_facts(["OperatingIncomeLoss"])
        net_map = extract_duration_facts(["NetIncomeLoss"])
        ocf_map = extract_duration_facts(["NetCashProvidedByUsedInOperatingActivities"])

        assets_map = extract_instant_facts(["Assets"])
        liab_map = extract_instant_facts(["Liabilities"])
        eq_map = extract_instant_facts(["StockholdersEquity", "CommonStockEquity"])

        all_ends = sorted(list(set(list(rev_map.keys()) + list(op_map.keys()) + list(net_map.keys()))))
        if not all_ends:
            return None

        quarters = []
        for end_dt in all_ends:
            r = rev_map.get(end_dt)
            o = op_map.get(end_dt)
            n = net_map.get(end_dt)
            cf = ocf_map.get(end_dt)
            a = assets_map.get(end_dt)
            l = liab_map.get(end_dt)
            e = eq_map.get(end_dt)

            filing_date = max([x["filed"] for x in (r, o, n, cf, a, l, e) if x], default=end_dt)
            if filing_date > target_date_str:
                continue

            revenue = r["val"] if r else 0.0
            op_inc = o["val"] if o else 0.0
            net_inc = n["val"] if n else 0.0
            ocf = cf["val"] if cf else 0.0
            tot_assets = a["val"] if a else 0.0
            tot_liab = l["val"] if l else 0.0
            tot_equity = e["val"] if e else 0.0

            dt_obj = datetime.strptime(end_dt, "%Y-%m-%d")
            # Apple 등 9월 결산법인은 12월말 마감이 Q1, 3월말 Q2, 6월말 Q3, 9월말 Q4
            # fp 정보가 있으면 우선 적용하고, 없으면 달력 기준 계산
            fy = (r or o or n or {}).get("fy")
            fp = (r or o or n or {}).get("fp")
            if fp and fp.startswith("Q"):
                # end 날짜의 연도 또는 fy 매칭
                q_label = f"{fy or dt_obj.year} {fp[1]}Q"
            else:
                q_num = (dt_obj.month - 1) // 3 + 1
                q_label = f"{dt_obj.year} {q_num}Q"

            quarters.append({
                "quarter_label": q_label,
                "date": end_dt,
                "filing_date": filing_date,
                "revenue": revenue,
                "operating_income": op_inc,
                "net_income": net_inc,
                "op_margin": round((op_inc / revenue) * 100, 2) if revenue > 0 else 0.0,
                "net_margin": round((net_inc / revenue) * 100, 2) if revenue > 0 else 0.0,
                "total_assets": tot_assets,
                "total_liabilities": tot_liab,
                "total_equity": tot_equity,
                "debt_ratio": round((tot_liab / tot_equity) * 100, 1) if tot_equity > 0 else 0.0,
                "operating_cash_flow": ocf
            })

        quarters.sort(key=lambda x: x["date"])
        return quarters[-4:] if quarters else None
    except Exception as e:
        logger.debug(f"SEC EDGAR fetch failed for {ticker}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# OpenDART API 헬퍼 및 분기 실적 추출
# ─────────────────────────────────────────────────────────────────────────────
def _get_dart_corp_code(stock_code: str, dart_api_key: str) -> Optional[str]:
    """OpenDART corpCode.xml ZIP을 다운로드/캐시하여 6자리 종목코드 -> 8자리 DART 고유번호 매핑"""
    global _DART_CORP_CODE_CACHE
    if _DART_CORP_CODE_CACHE and stock_code in _DART_CORP_CODE_CACHE:
        return _DART_CORP_CODE_CACHE[stock_code]

    cache_file = os.path.join(CACHE_DIR, "dart_corp_code_map.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                _DART_CORP_CODE_CACHE = json.load(f)
                if stock_code in _DART_CORP_CODE_CACHE:
                    return _DART_CORP_CODE_CACHE[stock_code]
        except Exception:
            pass

    if not dart_api_key:
        return None

    try:
        url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={dart_api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "QuantInvestingLab"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            zip_bytes = resp.read()

        mapping = {}
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            xml_filename = [n for n in zf.namelist() if n.lower().endswith(".xml")][0]
            with zf.open(xml_filename) as xf:
                tree = ET.parse(xf)
                for item in tree.findall(".//list"):
                    sc = item.findtext("stock_code", "").strip()
                    cc = item.findtext("corp_code", "").strip()
                    if sc and cc and len(sc) == 6:
                        mapping[sc] = cc

        _DART_CORP_CODE_CACHE = mapping
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(mapping, f)
        except Exception:
            pass

        return mapping.get(stock_code)
    except Exception as e:
        logger.debug(f"OpenDART corpCode fetch failed: {e}")
        return None


def _fetch_opendart_quarterly(stock_code: str, target_date_str: str, dart_api_key: str) -> Optional[List[Dict[str, Any]]]:
    """
    OpenDART 단일회사 전체 재무제표 API(fnlttSinglAcntAll.json)를 호출해
    공시 접수일(rcept_dt <= target_date) 이전의 최근 4개 분기 실적 추출
    """
    clean_code = re.sub(r"[^0-9]", "", stock_code)
    if len(clean_code) != 6 or not dart_api_key:
        return None

    corp_code = _get_dart_corp_code(clean_code, dart_api_key)
    if not corp_code:
        return None

    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    target_date_num = target_date_str.replace("-", "")
    target_year = target_dt.year

    # 11013: 1분기(03-31), 11012: 반기(06-30), 11014: 3분기(09-30), 11011: 사업보고서(12-31)
    report_plans = []
    for y in [target_year - 2, target_year - 1, target_year]:
        report_plans.extend([
            (y, "11013", f"{y} 1Q", f"{y}-03-31"),
            (y, "11012", f"{y} 2Q", f"{y}-06-30"),
            (y, "11014", f"{y} 3Q", f"{y}-09-30"),
            (y, "11011", f"{y} 4Q", f"{y}-12-31"),
        ])

    quarters = []
    # 이전 분기 누적금액 캐시 (단독 분기치 환산용: year -> {1Q: rev, 2Q: rev, 3Q: rev})
    cum_cache = {}

    for (year, reprt_code, q_label, end_date) in report_plans:
        # 종료일 자체가 타겟 날짜보다 미래인 경우 스킵
        if end_date > target_date_str:
            continue

        raw_items = None
        # 연결(CFS) 우선 시도, 실패 시 개별(OFS) 시도
        for fs_div in ("CFS", "OFS"):
            cache_k = f"dart_{corp_code}_{year}_{reprt_code}_{fs_div}"
            if cache_k in _FINANCIALS_RAW_CACHE:
                raw_items = _FINANCIALS_RAW_CACHE[cache_k]
                break
            try:
                url = (
                    f"https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json?"
                    f"crtfc_key={dart_api_key}&corp_code={corp_code}&bsns_year={year}&reprt_code={reprt_code}&fs_div={fs_div}"
                )
                req = urllib.request.Request(url, headers={"User-Agent": "QuantInvestingLab"})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    if res_json.get("status") == "000" and res_json.get("list"):
                        raw_items = res_json["list"]
                        _FINANCIALS_RAW_CACHE[cache_k] = raw_items
                        break
            except Exception:
                pass

        if not raw_items:
            continue

        # 공시 접수일 확인: rcept_no[:8] <= target_date_num
        sample_rcept = raw_items[0].get("rcept_no", "")
        rcept_dt = sample_rcept[:8]
        if not rcept_dt or rcept_dt > target_date_num:
            continue  # 미래 공시 차단

        filing_date_str = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}"

        def parse_amt(item_dict, key="thstrm_amount"):
            val_s = str(item_dict.get(key, "")).replace(",", "").strip()
            try:
                return float(val_s)
            except Exception:
                return 0.0

        rev_cum = 0.0
        op_cum = 0.0
        net_cum = 0.0
        tot_assets = 0.0
        tot_liab = 0.0
        tot_equity = 0.0
        ocf = 0.0

        for it in raw_items:
            sj = it.get("sj_div", "")
            ac = str(it.get("account_nm", "")).strip()

            if sj in ("IS", "CIS"):
                if any(k in ac for k in ["매출액", "수익(매출액)", "영업수익"]) and rev_cum == 0:
                    rev_cum = parse_amt(it)
                elif any(k in ac for k in ["영업이익", "영업이익(손실)", "영업손익"]) and op_cum == 0:
                    op_cum = parse_amt(it)
                elif any(k in ac for k in ["당기순이익", "당기순이익(손실)", "분기순이익", "반기순이익"]) and net_cum == 0:
                    net_cum = parse_amt(it)
            elif sj == "BS":
                if "자산총계" in ac and tot_assets == 0:
                    tot_assets = parse_amt(it)
                elif "부채총계" in ac and tot_liab == 0:
                    tot_liab = parse_amt(it)
                elif "자본총계" in ac and tot_equity == 0:
                    tot_equity = parse_amt(it)
            elif sj == "CF":
                if "영업활동" in ac and ocf == 0:
                    ocf = parse_amt(it)

        if year not in cum_cache:
            cum_cache[year] = {}

        # 분기 단독 실적 환산
        q_code = reprt_code
        if q_code == "11013":
            rev = rev_cum
            op_inc = op_cum
            net_inc = net_cum
            cum_cache[year]["1Q"] = (rev_cum, op_cum, net_cum)
        elif q_code == "11012":
            prev = cum_cache.get(year, {}).get("1Q", (0, 0, 0))
            rev = rev_cum - prev[0] if rev_cum >= prev[0] else rev_cum
            op_inc = op_cum - prev[1]
            net_inc = net_cum - prev[2]
            cum_cache[year]["2Q"] = (rev_cum, op_cum, net_cum)
        elif q_code == "11014":
            prev = cum_cache.get(year, {}).get("2Q", (0, 0, 0))
            rev = rev_cum - prev[0] if rev_cum >= prev[0] else rev_cum
            op_inc = op_cum - prev[1]
            net_inc = net_cum - prev[2]
            cum_cache[year]["3Q"] = (rev_cum, op_cum, net_cum)
        else:  # 11011 (연간)
            prev = cum_cache.get(year, {}).get("3Q", (0, 0, 0))
            rev = rev_cum - prev[0] if rev_cum >= prev[0] else rev_cum
            op_inc = op_cum - prev[1]
            net_inc = net_cum - prev[2]

        quarters.append({
            "quarter_label": q_label,
            "date": end_date,
            "filing_date": filing_date_str,
            "revenue": rev,
            "operating_income": op_inc,
            "net_income": net_inc,
            "op_margin": round((op_inc / rev) * 100, 2) if rev > 0 else 0.0,
            "net_margin": round((net_inc / rev) * 100, 2) if rev > 0 else 0.0,
            "total_assets": tot_assets,
            "total_liabilities": tot_liab,
            "total_equity": tot_equity,
            "debt_ratio": round((tot_liab / tot_equity) * 100, 1) if tot_equity > 0 else 0.0,
            "operating_cash_flow": ocf
        })

    quarters.sort(key=lambda x: x["date"])
    return quarters[-4:] if quarters else None


def _get_val_from_df(df: Optional[pd.DataFrame], possible_keys: List[str], col: Any) -> float:
    """재무제표 데이터프레임에서 유효 수치 추출 헬퍼"""
    if df is None or df.empty or col not in df.columns:
        return 0.0
    lower_idx = {str(k).strip().lower(): k for k in df.index}
    for key in possible_keys:
        lk = key.strip().lower()
        if lk in lower_idx:
            val = df.loc[lower_idx[lk], col]
            if pd.notna(val):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
    return 0.0


def _fetch_yfinance_quarterly(ticker: str, target_date_str: str) -> List[Dict[str, Any]]:
    """yfinance를 통한 분기 재무제표 폴백 (Q1~Q3: +42일, Q4: +75일 Look-Ahead Bias 차단)"""
    global _FINANCIALS_RAW_CACHE
    if ticker not in _FINANCIALS_RAW_CACHE:
        try:
            ticker_obj = yf.Ticker(ticker)
            _FINANCIALS_RAW_CACHE[ticker] = {
                "income": ticker_obj.quarterly_income_stmt,
                "balance": ticker_obj.quarterly_balance_sheet,
                "cashflow": ticker_obj.quarterly_cashflow
            }
        except Exception as e:
            logger.warning(f"yfinance quarterly fetch error for {ticker}: {e}")
            _FINANCIALS_RAW_CACHE[ticker] = {"income": None, "balance": None, "cashflow": None}

    raw = _FINANCIALS_RAW_CACHE[ticker]
    inc = raw.get("income")
    bal = raw.get("balance")
    cf = raw.get("cashflow")

    cols = []
    if inc is not None and not inc.empty:
        cols.extend(list(inc.columns))
    if bal is not None and not bal.empty:
        cols.extend(list(bal.columns))
    if cf is not None and not cf.empty:
        cols.extend(list(cf.columns))

    if not cols:
        return []

    unique_dates = sorted(list(set(cols)))
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()

    quarters = []
    for col in unique_dates:
        col_dt = col.date() if hasattr(col, "date") else datetime.strptime(str(col)[:10], "%Y-%m-%d").date()
        is_q4 = col_dt.month in (12, 1, 2)
        offset_days = 75 if is_q4 else 42
        filing_dt = col_dt + timedelta(days=offset_days)

        if filing_dt > target_dt:
            continue  # 미래 실적 누수 방지

        rev = _get_val_from_df(inc, ["Total Revenue", "Operating Revenue", "Revenue"], col)
        op_inc = _get_val_from_df(inc, ["Operating Income", "Operating Profit", "Operating Gain Loss"], col)
        net_inc = _get_val_from_df(inc, ["Net Income Common Stockholders", "Net Income", "Net Income Continuous Operations"], col)
        tot_assets = _get_val_from_df(bal, ["Total Assets"], col)
        tot_liab = _get_val_from_df(bal, ["Total Liabilities Net Minority Interest", "Total Liabilities"], col)
        tot_equity = _get_val_from_df(bal, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"], col)
        ocf = _get_val_from_df(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], col)

        q_num = (col_dt.month - 1) // 3 + 1
        q_label = f"{col_dt.year} {q_num}Q"

        quarters.append({
            "quarter_label": q_label,
            "date": col_dt.strftime("%Y-%m-%d"),
            "filing_date": filing_dt.strftime("%Y-%m-%d"),
            "revenue": rev,
            "operating_income": op_inc,
            "net_income": net_inc,
            "op_margin": round((op_inc / rev) * 100, 2) if rev > 0 else 0.0,
            "net_margin": round((net_inc / rev) * 100, 2) if rev > 0 else 0.0,
            "total_assets": tot_assets,
            "total_liabilities": tot_liab,
            "total_equity": tot_equity,
            "debt_ratio": round((tot_liab / tot_equity) * 100, 1) if tot_equity > 0 else 0.0,
            "operating_cash_flow": ocf
        })

    quarters.sort(key=lambda x: x["date"])
    return quarters[-4:] if quarters else []


@chart_game_bp.route("/financials", methods=["GET", "POST"])
def get_chart_financials():
    """
    (A) 기준일(date) 시점에 공개된 최근 4분기 재무제표 조회 API
    - 미래 실적 차단 (Look-Ahead Bias 엄격 방지)
    - 미국 주식: SEC EDGAR API 직접 연동 -> yfinance 폴백
    - 한국 주식: OpenDART API 직접 연동 (인증키 등록 시) -> yfinance 폴백 (dart_required: true)
    """
    req_data = request.get_json(silent=True) or {} if request.method == "POST" else {}
    raw_ticker = str(req_data.get("ticker") or request.args.get("ticker", "")).strip().upper()
    target_date = str(req_data.get("date") or request.args.get("date", "")).strip()
    dart_api_key = str(req_data.get("dart_api_key") or request.args.get("dart_api_key") or os.environ.get("OPENDART_API_KEY", "")).strip()

    if not raw_ticker or not target_date:
        return jsonify({"status": "error", "message": "ticker and date are required"}), 400

    cache_key = f"{raw_ticker}_{target_date}_{bool(dart_api_key)}"
    if cache_key in _FINANCIALS_RESP_CACHE:
        return jsonify(_FINANCIALS_RESP_CACHE[cache_key])

    is_kr = _is_korean_ticker(raw_ticker)
    currency = "KRW" if is_kr else "USD"
    quarters: Optional[List[Dict[str, Any]]] = None
    source = "yfinance (추정치)"
    dart_required = False

    # 1) 미국 주식: SEC EDGAR 우선 조회
    if not is_kr:
        quarters = _fetch_sec_edgar_quarterly(raw_ticker, target_date)
        if quarters:
            source = "SEC EDGAR"

    # 2) 한국 주식: OpenDART API 우선 조회 (키 등록 시)
    if is_kr:
        if dart_api_key:
            quarters = _fetch_opendart_quarterly(raw_ticker, target_date, dart_api_key)
            if quarters:
                source = "OpenDART"
        else:
            dart_required = True

    # 3) 실패 시 yfinance 폴백
    if not quarters:
        quarters = _fetch_yfinance_quarterly(raw_ticker, target_date)
        if is_kr and not dart_api_key:
            dart_required = True

    resp_data = {
        "status": "success",
        "ticker": raw_ticker,
        "currency": currency,
        "as_of_date": target_date,
        "source": source,
        "dart_required": dart_required,
        "latest_quarter": quarters[-1]["quarter_label"] if quarters else None,
        "quarters": quarters or []
    }

    _FINANCIALS_RESP_CACHE[cache_key] = resp_data
    return jsonify(resp_data)



# ─────────────────────────────────────────────────────────────────────────────
# 5. 뉴스 수집 및 AI 시황 요약 API
# ─────────────────────────────────────────────────────────────────────────────
_NEWS_SUMMARY_CACHE: Dict[str, Any] = {}


def _clean_html_tags(text: str) -> str:
    """HTML 태그 및 특수 엔티티 정제"""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = clean.replace("&quot;", "\"").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
    return clean.strip()


def _fetch_google_news_rss(query: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Google News RSS 피드를 통해 end_date 이전의 뉴스 최대 15건 수집"""
    articles = []
    try:
        encoded_q = urllib.parse.quote(f"{query} after:{start_date} before:{end_date}")
        url = f"https://news.google.com/rss/search?q={encoded_q}&hl=ko&gl=KR&ceid=KR:ko"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

        for item in items[:25]:
            title = _clean_html_tags(item.findtext("title") or "")
            link = item.findtext("link") or ""
            pub_date_raw = item.findtext("pubDate") or ""

            pub_dt_str = end_date
            if pub_date_raw:
                try:
                    parsed_dt = email.utils.parsedate_to_datetime(pub_date_raw)
                    if parsed_dt.date() > end_dt:
                        continue  # 미래 뉴스 누수 방지
                    pub_dt_str = parsed_dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

            source = "Google News"
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0]
                source = parts[1]

            if title:
                articles.append({
                    "title": title,
                    "link": link,
                    "date": pub_dt_str,
                    "source": source
                })
            if len(articles) >= 15:
                break
    except Exception as e:
        logger.debug(f"Google News RSS fetch error: {e}")

    return articles


def _fetch_naver_news_api(query: str, start_date: str, end_date: str, client_id: str, client_secret: str) -> List[Dict[str, Any]]:
    """Naver 뉴스 검색 API를 통해 end_date 이전 뉴스 수집"""
    articles = []
    if not client_id or not client_secret:
        return articles
    try:
        encoded_q = urllib.parse.quote(query)
        url = f"https://openapi.naver.com/v1/search/news.json?query={encoded_q}&display=15&sort=date"
        req = urllib.request.Request(
            url,
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
                "User-Agent": "QuantInvestingLab"
            }
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

        for item in data.get("items", []):
            title = _clean_html_tags(item.get("title", ""))
            link = item.get("originallink") or item.get("link") or ""
            pub_raw = item.get("pubDate", "")
            pub_dt_str = end_date
            if pub_raw:
                try:
                    p_dt = email.utils.parsedate_to_datetime(pub_raw)
                    p_date = p_dt.date()
                    if p_date > end_dt or p_date < start_dt:
                        continue
                    pub_dt_str = p_date.strftime("%Y-%m-%d")
                except Exception:
                    pass

            if title:
                articles.append({
                    "title": title,
                    "link": link,
                    "date": pub_dt_str,
                    "source": "Naver 뉴스"
                })
    except Exception as e:
        logger.debug(f"Naver News API fetch error: {e}")

    return articles


def _generate_ai_news_summary(
    articles: List[Dict[str, Any]],
    current_date: str,
    company_name: str,
    ticker: str,
    provider: str,
    api_key: str
) -> Dict[str, Any]:
    """LLM REST API(Gemini / OpenAI)를 호출해 기준일 이전 뉴스 요약 생성"""
    if not articles or not api_key:
        return {
            "sentiment": "중립",
            "one_liner": f"{current_date} 기준 수집된 주요 뉴스 헤드라인입니다.",
            "bullets": [a["title"] for a in articles[:4]] or ["수집된 주요 뉴스가 없습니다."],
            "is_ai": False
        }

    news_text = "\n".join([f"- [{a['date']}] {a['title']} ({a['source']})" for a in articles[:12]])
    prompt = f"""당신은 금융 시장 전문 애널리스트입니다.
아래 제공된 뉴스는 모두 {current_date} 시점 이전에 보도된 과거 뉴스입니다.
반드시 {current_date} 시점 기준 수집된 뉴스 내용만을 바탕으로 요약하십시오.
{current_date} 이후의 미래 주가, 실적 또는 사건은 절대로 언급하거나 예측하지 마십시오. (Look-Ahead Bias 엄격 방지)

[대상 기업] {company_name} ({ticker})
[기준 일자] {current_date}
[수집된 뉴스 기사]
{news_text}

반드시 아래 JSON 형식으로만 응답하십시오 (마크다운 따옴표 없이 순수 JSON):
{{
  "sentiment": "호재" 또는 "중립" 또는 "악재",
  "one_liner": "한줄 시황 & 시장 심리 요약 (40자 이내)",
  "bullets": [
    "핵심 이슈 요약 1",
    "핵심 이슈 요약 2",
    "핵심 이슈 요약 3"
  ]
}}"""

    try:
        clean_provider = provider.lower().strip()
        if clean_provider == "gemini" or ("gemini" in clean_provider):
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
            }
            req = urllib.request.Request(
                gemini_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                text_out = res_json["candidates"][0]["content"]["parts"][0]["text"]
        else:
            # OpenAI API
            openai_url = "https://api.openai.com/v1/chat/completions"
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "response_format": {"type": "json_object"}
            }
            req = urllib.request.Request(
                openai_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                text_out = res_json["choices"][0]["message"]["content"]

        # JSON 파싱 시도
        match = re.search(r"\{[\s\S]*\}", text_out)
        if match:
            parsed = json.loads(match.group(0))
            return {
                "sentiment": parsed.get("sentiment", "중립"),
                "one_liner": parsed.get("one_liner", f"{current_date} 시황 요약"),
                "bullets": parsed.get("bullets", [a["title"] for a in articles[:3]]),
                "is_ai": True
            }
    except Exception as e:
        logger.warning(f"AI news summary error: {e}")

    # Fallback 기본 헤드라인 요약
    return {
        "sentiment": "중립",
        "one_liner": f"{current_date} 기준 주요 뉴스 헤드라인 목록입니다.",
        "bullets": [a["title"] for a in articles[:4]],
        "is_ai": False
    }


@chart_game_bp.route("/news_summary", methods=["POST", "OPTIONS"])
def get_chart_news_summary():
    """
    (B) 기준일(current_date) 이전 뉴스 수집 및 AI 시황 요약 API
    - Google News RSS 및 선택적 Naver 뉴스 API 연동
    - Gemini / OpenAI REST API를 통한 과거 시점 기준 AI 요약
    """
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    data = request.get_json(force=True, silent=True) or {}
    ticker = str(data.get("ticker", "")).strip().upper()
    company_name = str(data.get("company_name", "")).strip() or ticker
    current_date = str(data.get("current_date", "")).strip()

    try:
        days = int(data.get("days", 30))
    except (ValueError, TypeError):
        days = 30
    days = max(7, min(90, days))

    if not ticker or not current_date:
        return jsonify({"status": "error", "message": "ticker and current_date are required"}), 400

    cache_key = f"{ticker}_{current_date}_{days}"
    if cache_key in _NEWS_SUMMARY_CACHE:
        return jsonify(_NEWS_SUMMARY_CACHE[cache_key])

    try:
        cur_dt = datetime.strptime(current_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"status": "error", "message": "invalid current_date format (YYYY-MM-DD)"}), 400

    start_dt = cur_dt - timedelta(days=days)
    start_date_str = start_dt.strftime("%Y-%m-%d")

    # 검색 질의어 (회사명 우선, 한국어 주식이면 한글명 활용)
    search_query = company_name.split("(")[0].strip() or ticker

    # 1) Google News RSS 수집
    articles = _fetch_google_news_rss(search_query, start_date_str, current_date)

    # 2) Naver 뉴스 API (인증 정보 존재 시)
    naver_cid = str(data.get("naver_client_id") or os.environ.get("NAVER_CLIENT_ID", "")).strip()
    naver_sec = str(data.get("naver_client_secret") or os.environ.get("NAVER_CLIENT_SECRET", "")).strip()
    if naver_cid and naver_sec:
        naver_articles = _fetch_naver_news_api(search_query, start_date_str, current_date, naver_cid, naver_sec)
        # 중복 제목 제거 후 병합
        seen_titles = {a["title"][:20] for a in articles}
        for na in naver_articles:
            if na["title"][:20] not in seen_titles:
                articles.append(na)
                seen_titles.add(na["title"][:20])

    # 날짜 역순 정렬 (최신 뉴스 우선)
    articles.sort(key=lambda x: x.get("date", ""), reverse=True)
    articles = articles[:15]

    # 3) AI 요약 생성 (Gemini 또는 OpenAI)
    llm_provider = str(data.get("llm_provider", "gemini")).lower()
    llm_api_key = str(data.get("llm_api_key") or os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")).strip()

    summary_info = _generate_ai_news_summary(
        articles=articles,
        current_date=current_date,
        company_name=company_name,
        ticker=ticker,
        provider=llm_provider,
        api_key=llm_api_key
    )

    resp_data = {
        "status": "success",
        "ticker": ticker,
        "company_name": company_name,
        "current_date": current_date,
        "start_date": start_date_str,
        "days": days,
        "sentiment": summary_info.get("sentiment", "중립"),
        "one_liner": summary_info.get("one_liner", ""),
        "bullets": summary_info.get("bullets", []),
        "is_ai": summary_info.get("is_ai", False),
        "news_count": len(articles),
        "articles": articles
    }

    _NEWS_SUMMARY_CACHE[cache_key] = resp_data
    return jsonify(resp_data)

