"""Daily FX reference rates (European Central Bank, via the Frankfurter API) into aff_fx_rates.

Rates are stored as "1 unit of currency = rate_to_usd USD" for the publication date. Ingest
uses the rate of the event's day or the latest one before it. Currencies the ECB does not
publish can be entered by finance in the admin panel (or as an override in
``fallback_fx_rates``).
"""

from __future__ import annotations

import time
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.affiliate import AffFxRate

logger = get_logger("aff_fx")

SOURCE_URL = "https://api.frankfurter.dev/v1/latest?from=USD"
_last_attempt = 0.0
_RETRY_SECONDS = 600


async def fetch_latest() -> tuple[date, Dict[str, Decimal]]:
    """Return (publication date, {currency: rate_to_usd}) from the ECB reference rates."""
    import httpx

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(SOURCE_URL)
        resp.raise_for_status()
        data = resp.json()
    published = date.fromisoformat(data["date"])
    rates: Dict[str, Decimal] = {}
    for currency, per_usd in (data.get("rates") or {}).items():
        try:
            units = Decimal(str(per_usd))
        except InvalidOperation:
            continue
        if units > 0 and len(currency) == 3:
            rates[currency.upper()] = (Decimal(1) / units).quantize(Decimal("0.00000001"))
    if not rates:
        raise ValueError("FX source returned no rates")
    return published, rates


async def sync_rates(db: AsyncSession) -> Dict[str, object]:
    """Fetch today's reference rates and upsert them. Commits."""
    global _last_attempt
    _last_attempt = time.monotonic()
    published, rates = await fetch_latest()
    for currency, value in rates.items():
        row = await db.get(AffFxRate, (published, currency))
        if row is None:
            db.add(AffFxRate(rate_date=published, currency=currency, rate_to_usd=value))
        else:
            row.rate_to_usd = value
    await db.commit()
    logger.info("FX rates stored", date=str(published), currencies=len(rates))
    return {"date": published.isoformat(), "currencies": len(rates)}


async def sync_if_due(db: AsyncSession) -> bool:
    """Used when a rate is missing: try one live fetch, at most every 10 minutes."""
    if time.monotonic() - _last_attempt < _RETRY_SECONDS and _last_attempt:
        return False
    try:
        await sync_rates(db)
        return True
    except Exception as exc:
        await db.rollback()
        logger.warning("FX fetch failed", error=str(exc))
        return False
