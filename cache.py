from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Callable

CACHE_DIR = Path("/tmp/.quant_cache") if os.environ.get("VERCEL") else Path(".quant_cache")


def get_cache_path(ticker: str, date_str: str | None = None) -> Path:
    # 예: .quant_cache/005930_2026-11-28.json
    day = date_str or datetime.now().strftime("%Y-%m-%d")
    safe_ticker = ticker.strip().upper()
    return CACHE_DIR / f"{safe_ticker}_{day}.json"


def load_or_fetch_stock(
    ticker: str,
    fetcher: Callable[[str], dict[str, Any]],
    force_refresh: bool = False,
) -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = get_cache_path(ticker)

    # 1. 강제 갱신이 아니고 캐시 파일이 있으면 즉시 반환
    if not force_refresh and cache_path.exists():
        try:
            with cache_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # 2. 캐시 미스 시 실제 네이버 조회 수행
    data = fetcher(ticker)

    # 3. 빈 데이터나 에러 응답이 아닐 때만 캐시 저장
    if data:
        tmp_path = cache_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(cache_path)

    return data