from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.permissions import require_permission
from app.services.currency import BASE_CURRENCY, convert_amount, currency_for_country, geolocate_ip, get_usd_rates, rates_for

router = APIRouter(prefix="/currency", tags=["Currency"])


@router.get("/rates")
def currency_rates(base: str = Query(default=BASE_CURRENCY)):
    return {"status": "success", "data": rates_for(base)}


@router.get("/admin/rates")
def admin_currency_rates(_=Depends(require_permission("view-settings"))):
    return {"status": "success", "data": get_usd_rates()}


@router.post("/admin/refresh")
def admin_refresh_currency_rates(_=Depends(require_permission("update-settings"))):
    return {"status": "success", "message": "Exchange rates refreshed", "data": get_usd_rates(force=True)}


@router.get("/convert")
def currency_convert(
    amount: Decimal = Query(...),
    from_currency: str = Query(default=BASE_CURRENCY, alias="from"),
    to_currency: str = Query(..., alias="to"),
):
    try:
        converted, rate, payload = convert_amount(amount, from_currency, to_currency)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "status": "success",
        "data": {
            "amount": str(amount),
            "from": from_currency.upper(),
            "to": to_currency.upper(),
            "rate": str(rate),
            "converted_amount": str(converted),
            "rate_date": payload.get("rate_date"),
            "source": payload.get("source"),
            "is_stale": payload.get("is_stale", False),
        },
    }


@router.get("/context")
def currency_context(request: Request, country: str = Query(default=""), db: Session = Depends(get_db)):
    requested_country = country.strip().upper()
    cloudflare_country = request.headers.get("cf-ipcountry", "").strip().upper()
    vercel_country = request.headers.get("x-vercel-ip-country", "").strip().upper()
    detected_country = requested_country or cloudflare_country or vercel_country
    country_source = "requested" if requested_country else ("cdn" if cloudflare_country or vercel_country else "unknown")
    if not detected_country:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (request.client.host if request.client else "")
        # geolocate_ip is best-effort and always returns "" on any failure
        # (timeout, non-200, bad body, rate limit) rather than raising, so
        # this can never block/fail the request - it just falls through to
        # the configured default currency below.
        try:
            detected_country = geolocate_ip(client_ip)
            if detected_country:
                country_source = "ip"
        except Exception:
            detected_country = ""
    # A local display currency is only valid when its country is in the
    # active public catalogue. Visitors from any other detected country see
    # USD rather than inheriting an unrelated site-default currency.
    active_country_currency = currency_for_country(db, detected_country)
    return {
        "status": "success",
        "data": {
            "base_currency": BASE_CURRENCY,
            "country_code": detected_country or None,
            # This coarse source lets the UI explain the result without ever
            # exposing the visitor IP address to the browser.
            "country_source": country_source,
            "currency": active_country_currency or BASE_CURRENCY,
        },
    }

