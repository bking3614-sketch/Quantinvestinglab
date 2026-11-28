import ast
from io import StringIO
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import quote

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/"
}


def get_company_overview_and_financials(ticker: str) -> dict:
    """
    기업 개요, 연간/분기 재무제표(컨센서스 포함), 현재 PER/PBR을 한 번의 요청으로 수집
    """
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "euc-kr"
    html_text = res.text
    soup = BeautifulSoup(html_text, "lxml")

    # 1. 종목명 및 기업 개요
    name_tag = soup.select_one(".wrap_company h2 a")
    stock_name = name_tag.text.strip() if name_tag else ticker
    summary_tags = soup.select("#summary_info p")
    overview = [p.text.strip() for p in summary_tags if p.text.strip()]

    # 2. 현재 투자지표 (PER, PBR, 배당수익률 등)
    metrics = {}
    for id_name, label in [("_per", "PER"), ("_pbr", "PBR"), ("_dvr", "배당수익률"), ("_cns_per", "추정PER")]:
        tag = soup.select_one(f"#{id_name}")
        metrics[label] = tag.text.strip() if tag else None

    # 3. 재무제표 및 컨센서스 (기업실적분석 테이블)
    try:
        tables = pd.read_html(StringIO(html_text))
    except ValueError:
        tables = []

    financial_df = None
    for df in tables:
        if isinstance(df.columns, pd.MultiIndex) and "주요재무정보" in str(df.columns[0]):
            financial_df = df
            break

    financial_records = []
    if financial_df is not None:
        flat_cols = ["항목"]
        for col in financial_df.columns[1:]:
            period_type = "연간" if "연간" in str(col[0]) else "분기"
            flat_cols.append(f"{period_type}_{col[1]}")
        financial_df.columns = flat_cols
        financial_df = financial_df.dropna(how="all")
        financial_records = financial_df.fillna("-").to_dict(orient="records")

    return {
        "ticker": ticker,
        "name": stock_name,
        "overview": overview,
        "valuation": metrics,
        "financials_and_consensus": financial_records
    }


def get_investor_trends(ticker: str, rows: int = 20) -> list:
    """
    투자자별 매매동향 (일별 종가, 기관/외국인 순매매량, 외국인 보유율) 수집
    """
    url = f"https://finance.naver.com/item/frgn.naver?code={ticker}"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "euc-kr"

    try:
        tables = pd.read_html(StringIO(res.text))
    except ValueError:
        return []

    trend_df = None
    for df in tables:
        if "날짜" in str(df.columns) and "기관" in str(df.columns) and "외국인" in str(df.columns):
            trend_df = df
            break

    if trend_df is None:
        return []

    if isinstance(trend_df.columns, pd.MultiIndex):
        trend_df.columns = [
            f"{c[0]}_{c[1]}" if c[0] != c[1] else str(c[0])
            for c in trend_df.columns
        ]

    trend_df = trend_df.dropna(subset=[trend_df.columns[0]]).head(rows)
    return trend_df.fillna("-").to_dict(orient="records")


def get_daily_ohlcv(ticker: str, start_date: str = "20240101", end_date: str = "20261231") -> list:
    """
    네이버 증권 일봉 차트 데이터 (날짜, 시가, 고가, 저가, 종가, 거래량, 외국인소진율) 수집
    """
    url = (
        f"https://api.finance.naver.com/siseJson.naver?"
        f"symbol={ticker}&requestType=1&startTime={start_date}&endTime={end_date}&timeframe=day"
    )
    res = requests.get(url, headers=HEADERS, timeout=10)
    raw_data = ast.literal_eval(res.text.strip())

    if not raw_data or len(raw_data) < 2:
        return []

    columns = [col.strip() for col in raw_data[0]]
    df = pd.DataFrame(raw_data[1:], columns=columns)
    return df.to_dict(orient="records")


def fetch_all_stock_data(ticker: str) -> dict:
    """
    단일 종목의 모든 핵심 정보를 통합 반환
    """
    base_info = get_company_overview_and_financials(ticker)
    time.sleep(0.3)
    investors = get_investor_trends(ticker, rows=15)
    time.sleep(0.3)
    ohlcv = get_daily_ohlcv(ticker)

    return {
        **base_info,
        "investor_trends": investors,
        "daily_chart": ohlcv
    }

import os
from pathlib import Path
import re
from urllib.parse import quote


def _load_krx_stock_list() -> list[dict]:
    """
    한국거래소(KRX) 공식 상장법인 목록을 로컬에 캐싱해 두고 반환 (외부 검색 API 장애 대비용)
    """
    cache_dir = Path("/tmp/.quant_cache") if os.environ.get("VERCEL") else Path(".quant_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    krx_cache = cache_dir / "krx_listed_stocks.json"

    # 캐시가 존재하면 즉시 로드 (7일간 유효)
    if krx_cache.exists():
        try:
            age_days = (time.time() - krx_cache.stat().st_mtime) / 86400
            if age_days < 7:
                import json
                with krx_cache.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data:
                        return data
        except Exception:
            pass

    # KRX 공식 상장법인 엑셀(HTML 테이블) 다운로드
    try:
        krx_url = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
        res = requests.get(krx_url, headers=HEADERS, timeout=10)
        res.encoding = "euc-kr"
        tables = pd.read_html(StringIO(res.text))
        if tables:
            df = tables[0]
            stocks = []
            for _, row in df.iterrows():
                name = str(row.get("회사명", "")).strip()
                code = str(row.get("종목코드", "")).strip().zfill(6)
                if name and code.isdigit() and len(code) == 6:
                    stocks.append({"ticker": code, "name": name, "market": "KRX"})
            if stocks:
                import json
                with krx_cache.open("w", encoding="utf-8") as f:
                    json.dump(stocks, f, ensure_ascii=False)
                return stocks
    except Exception:
        pass

    return []


def search_korean_stocks(query: str, limit: int = 10) -> list[dict]:
    """
    한글 종목명 또는 종목코드로 국내 상장 종목 검색
    """
    q = query.strip()
    if not q:
        return []

    results = []
    seen = set()

    # 1순위: 네이버 금융 통합검색 (단일 종목 리다이렉트 + 복수 목록 모두 대응)
    try:
        encoded_q = quote(q.encode("euc-kr"))
        web_url = f"https://finance.naver.com/search/searchList.naver?query={encoded_q}"
        res = requests.get(web_url, headers=HEADERS, timeout=10)
        res.encoding = "euc-kr"

        # 단일 종목 일치 시 네이버가 /item/main.naver?code=000660 으로 바로 리다이렉트함
        if "code=" in res.url:
            code_match = re.search(r"code=(\d{6})", res.url)
            if code_match:
                code = code_match.group(1)
                soup = BeautifulSoup(res.text, "lxml")
                name_tag = soup.select_one(".wrap_company h2 a")
                name = name_tag.text.strip() if name_tag else q
                return [{"ticker": code, "name": name, "market": "KRX"}]

        # 복수 검색 결과 목록 파싱
        soup = BeautifulSoup(res.text, "lxml")
        for a_tag in soup.select("a[href*='code=']"):
            href = a_tag.get("href", "")
            code_match = re.search(r"code=(\d{6})", href)
            name = a_tag.text.strip()
            if code_match and name:
                code = code_match.group(1)
                if code not in seen:
                    seen.add(code)
                    results.append({"ticker": code, "name": name, "market": "KRX"})
                    if len(results) >= limit:
                        return results
    except Exception:
        pass

    # 2순위: KRX 공식 상장종목 캐시에서 검색 (부분 일치 + 정확 일치 우선 정렬)
    q_upper = q.upper()
    krx_stocks = _load_krx_stock_list()
    exact_matches = [s for s in krx_stocks if s["name"].upper() == q_upper or s["ticker"] == q_upper]
    partial_matches = [
        s for s in krx_stocks
        if (q_upper in s["name"].upper() or q_upper in s["ticker"]) and s not in exact_matches
    ]

    for item in (exact_matches + partial_matches):
        if item["ticker"] not in seen:
            seen.add(item["ticker"])
            results.append(item)
            if len(results) >= limit:
                break

    return results


def resolve_korean_ticker(query: str) -> str:
    """
    입력값이 '005930' 또는 '005930.KS'면 6자리 코드로 정제하고,
    '삼성전자', 'SK하이닉스' 같은 한글/영문 종목명이면 네이버 검색을 통해 6자리 종목코드로 변환
    """
    cleaned = query.strip().upper().split(".")[0]
    if cleaned.isdigit() and len(cleaned) == 6:
        return cleaned

    matches = search_korean_stocks(query, limit=5)
    if not matches:
        raise ValueError(f"'{query}'에 해당하는 국내 상장 종목을 찾을 수 없습니다.")

    # 정확히 일치하는 종목명이 있으면 우선 선택 (예: '삼성전자' 검색 시 '삼성전자우'보다 '삼성전자' 우선)
    exact = next((m for m in matches if m["name"].upper() == cleaned), None)
    return exact["ticker"] if exact else matches[0]["ticker"]