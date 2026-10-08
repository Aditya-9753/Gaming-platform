"""Partner portal API (/api/v1/aff/...). Every query is scoped to the partner from the token."""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate import content as content_service
from app.affiliate import ledger, postbacks, serialize, settlement, stats, withdrawals
from app.affiliate import partners as partner_service
from app.affiliate import security as sec
from app.affiliate import settings as aff_settings
from app.affiliate.constants import (
    ContentStatus,
    ExportStatus,
    PostbackEvent,
    RecordStatus,
)
from app.affiliate.util import utcnow
from app.api.v1.affiliate.deps import PartnerCtx, active_partner, partner_ctx
from app.core.database import get_db
from app.core.exceptions import BadRequestException, NotFoundException
from app.middleware.rate_limit import rate_limit_dependency
from app.models.affiliate import (
    AffBlogPost,
    AffCampaign,
    AffContact,
    AffExportJob,
    AffFaq,
    AffPartnerPostback,
    AffPartnerPostbackLog,
    AffPartnerProfile,
    AffPrMaterial,
    AffPromoCode,
    AffQrCode,
    AffSource,
    AffWalletTransaction,
    AffWithdrawal,
    AffWithdrawalMethod,
)
from app.models.notification import Notification
from app.schemas.affiliate import (
    AutoWithdrawalIn,
    CampaignIn,
    CampaignUpdateIn,
    ContactIn,
    EmailChangeIn,
    ExportIn,
    LinkIn,
    LinkUpdateIn,
    MeUpdateIn,
    MethodIn,
    MethodUpdateIn,
    PasswordChangeIn,
    PostbackIn,
    PostbackUpdateIn,
    PromoIn,
    QrIn,
    SourceIn,
    SourceUpdateIn,
    TermsAcceptIn,
    WithdrawalIn,
)

router = APIRouter(prefix="/aff", tags=["Partner portal"])


def _ids(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        return [int(x) for x in raw.split(",") if x.strip()]
    except ValueError as exc:
        raise BadRequestException("Filters must be comma-separated ids") from exc


def _countries(raw: Optional[str]) -> List[str]:
    return [c.strip().upper() for c in (raw or "").split(",") if len(c.strip()) == 2]


# ===================================================================== me


@router.get("/me")
async def me(ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    p = ctx.partner
    profile = (await db.execute(select(AffPartnerProfile).where(AffPartnerProfile.partner_id == p.id))).scalar_one_or_none()
    wallet = await ledger.get_wallet(db, p.id)
    deal = await partner_service.current_deal(db, p.id)
    terms = await sec.needs_terms(db, ctx.user.id)
    unread = (await db.execute(select(func.count()).select_from(Notification).where(
        Notification.user_id == ctx.user.id, Notification.is_read.is_(False)))).scalar_one()
    config = await aff_settings.get_all(db)
    return {
        "partner": serialize.partner(p, ctx.user.email),
        "profile": serialize.profile(profile),
        "name": ctx.user.full_name or (ctx.user.email or "").split("@")[0],
        "email_verified": ctx.user.is_verified,
        "wallet": serialize.wallet(wallet),
        "deal": serialize.deal(deal),
        "terms_required": serialize.terms(terms),
        "unread_notifications": unread,
        "impersonated_by": ctx.impersonated_by,
        "is_subpartner": p.parent_partner_id is not None,
        "subpartners_enabled": int(config["subpartner_depth"]) >= 1 and p.parent_partner_id is None,
        "config": {k: config[k] for k in aff_settings.PUBLIC_KEYS},
    }


@router.patch("/me")
async def update_me(body: MeUpdateIn, ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    if body.timezone:
        stats.tz_of(body.timezone)  # validates
        ctx.partner.timezone = body.timezone
    if body.locale:
        langs = await aff_settings.get(db, "languages")
        if body.locale not in langs:
            raise BadRequestException(f"Language must be one of {', '.join(langs)}")
        ctx.partner.locale = body.locale
    if body.profile is not None:
        profile = (await db.execute(select(AffPartnerProfile).where(AffPartnerProfile.partner_id == ctx.partner.id))).scalar_one()
        for key, value in body.profile.model_dump(exclude_unset=True).items():
            setattr(profile, key, value)
        names = [profile.first_name, profile.last_name]
        ctx.user.full_name = " ".join(n for n in names if n) or ctx.user.full_name
    await db.commit()
    return {"ok": True}


@router.post("/terms/accept")
async def accept_terms(body: TermsAcceptIn, ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    latest = await sec.latest_terms(db)
    if latest is None or latest.id != body.version_id:
        raise BadRequestException("Accept the latest terms version")
    await sec.accept_terms(db, ctx.user.id, latest.id, ctx.ip)
    await db.commit()
    return {"accepted": latest.version}


@router.post("/auth/resend-verification", dependencies=[Depends(rate_limit_dependency("aff:resend", 3, 600))])
async def resend_verification(ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    if ctx.user.is_verified:
        return {"sent": False, "already_verified": True}
    await sec.send_verification(db, ctx.user)
    await db.commit()
    return {"sent": True}


@router.get("/me/deal")
async def my_deal(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    from app.models.affiliate import AffPartnerDeal

    rows = (await db.execute(select(AffPartnerDeal).where(AffPartnerDeal.partner_id == ctx.partner.id)
                             .order_by(AffPartnerDeal.effective_from.desc()))).scalars().all()
    current = await partner_service.current_deal(db, ctx.partner.id)
    return {"current": serialize.deal(current), "history": [serialize.deal(d) for d in rows]}


@router.get("/me/invite-link")
async def invite_link(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    if ctx.partner.parent_partner_id is not None or int(await aff_settings.get(db, "subpartner_depth")) < 1:
        raise BadRequestException("Subpartner invites are not available for this account")
    return {"url": await partner_service.invite_link(db, ctx.partner), "rate": str(ctx.partner.subpartner_rate)}


# ===================================================================== 2FA / account


@router.post("/account/password", dependencies=[Depends(rate_limit_dependency("aff:pwd", 5, 600))])
async def change_password(body: PasswordChangeIn, ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    await sec.change_password(db, ctx.user, body.current_password, body.new_password, ctx.ip)
    return {"ok": True}


@router.post("/account/email", dependencies=[Depends(rate_limit_dependency("aff:email", 5, 600))])
async def change_email(body: EmailChangeIn, ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    await sec.change_email(db, ctx.user, body.password, str(body.new_email), ctx.ip)
    return {"ok": True, "verification_sent": True}


# ===================================================================== dashboard


@router.get("/dashboard/summary")
async def dashboard_summary(
    period: str = "all", date_from: Optional[date] = None, date_to: Optional[date] = None,
    source_ids: Optional[str] = None, link_ids: Optional[str] = None, countries: Optional[str] = None,
    ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db),
) -> dict:
    return await stats.summary(db, ctx.partner, period, date_from, date_to, _ids(source_ids), _ids(link_ids), _countries(countries))


@router.get("/dashboard/timeseries")
async def dashboard_timeseries(
    period: str = "30d", date_from: Optional[date] = None, date_to: Optional[date] = None,
    source_ids: Optional[str] = None, link_ids: Optional[str] = None, countries: Optional[str] = None,
    ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db),
) -> dict:
    series = await stats.timeseries(db, [ctx.partner.id], ctx.partner.timezone, period, date_from, date_to,
                                    _ids(source_ids), _ids(link_ids), _countries(countries))
    return {"timezone": ctx.partner.timezone, "series": series}


@router.get("/dashboard/filters")
async def dashboard_filters(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    return await stats.filter_options(db, ctx.partner.id)


@router.get("/dashboard/top-sources")
async def top_sources(period: str = "30d", ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    rows = await stats.grouped(db, [ctx.partner.id], ctx.partner.timezone, period, "source")
    return {"items": rows[:5]}


# ===================================================================== statistics


@router.get("/statistics/common")
async def statistics_common(
    group_by: str = "day", period: str = "30d", date_from: Optional[date] = None, date_to: Optional[date] = None,
    source_ids: Optional[str] = None, link_ids: Optional[str] = None, countries: Optional[str] = None,
    ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db),
) -> dict:
    if group_by == "partner":
        raise BadRequestException("group_by=partner is for admins")
    rows = await stats.grouped(db, [ctx.partner.id], ctx.partner.timezone, period, group_by, date_from, date_to,
                               _ids(source_ids), _ids(link_ids), _countries(countries))
    return {"group_by": group_by, "items": rows}


@router.get("/statistics/subpartners")
async def statistics_subpartners(
    period: str = "all", date_from: Optional[date] = None, date_to: Optional[date] = None,
    ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db),
) -> dict:
    return {"items": await stats.subpartner_stats(db, ctx.partner, period, date_from, date_to)}


async def _run_export(job_id: int) -> None:
    from app.core.database import get_session_factory

    async with get_session_factory()() as db:
        await run_export(db, job_id)


async def run_export(db: AsyncSession, job_id: int) -> None:
    from app.affiliate.partners import get_partner

    job = await db.get(AffExportJob, job_id)
    if job is None or job.status != ExportStatus.PENDING:
        return
    try:
        params = job.params
        partner = await get_partner(db, int(params["partner_id"]))
        start = date.fromisoformat(params["date_from"]) if params.get("date_from") else None
        end = date.fromisoformat(params["date_to"]) if params.get("date_to") else None
        if params["kind"] == "subpartners":
            rows = await stats.subpartner_stats(db, partner, params["period"], start, end)
        else:
            rows = await stats.grouped(db, [partner.id], partner.timezone, params["period"], params["group_by"], start, end)
        job.file_content = stats.to_csv(rows)
        job.row_count = len(rows)
        job.status = ExportStatus.DONE
        job.expires_at = utcnow() + timedelta(days=7)
    except Exception as exc:
        job.status = ExportStatus.FAILED
        job.error = str(getattr(exc, "message", exc))[:255]
    await db.commit()


@router.post("/statistics/export", status_code=202)
async def statistics_export(body: ExportIn, background: BackgroundTasks, ctx: PartnerCtx = Depends(active_partner),
                            db: AsyncSession = Depends(get_db)) -> dict:
    stats.period_range(body.period, ctx.partner.timezone, body.date_from, body.date_to)  # validates
    job = AffExportJob(user_id=ctx.user.id, type=f"statistics_{body.kind}", status=ExportStatus.PENDING,
                       params={"partner_id": ctx.partner.id, "kind": body.kind, "group_by": body.group_by, "period": body.period,
                               "date_from": body.date_from.isoformat() if body.date_from else None,
                               "date_to": body.date_to.isoformat() if body.date_to else None})
    db.add(job)
    await db.commit()
    background.add_task(_run_export, job.id)
    return serialize.export_job(job)


@router.get("/exports")
async def list_exports(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffExportJob).where(AffExportJob.user_id == ctx.user.id)
                             .order_by(AffExportJob.id.desc()).limit(20))).scalars().all()
    return {"items": [serialize.export_job(j) for j in rows]}


@router.get("/exports/{job_id}/download")
async def download_export(job_id: int, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> Response:
    job = await db.get(AffExportJob, job_id)
    if job is None or job.user_id != ctx.user.id:
        raise NotFoundException("Export not found")
    if job.status != ExportStatus.DONE:
        raise BadRequestException("The export is not ready yet")
    return Response(content=job.file_content or "", media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="statistics-{job.id}.csv"'})


# ===================================================================== sources / campaigns / links


@router.get("/sources")
async def list_sources(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffSource).where(AffSource.partner_id == ctx.partner.id).order_by(AffSource.is_default.desc(), AffSource.id))).scalars().all()
    return {"items": [serialize.source(s) for s in rows]}


@router.post("/sources", status_code=201)
async def create_source(body: SourceIn, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.create_source(db, ctx.actor, ctx.partner.id, body.model_dump())
    await db.commit()
    return serialize.source(row)


@router.patch("/sources/{source_id}")
async def update_source(source_id: int, body: SourceUpdateIn, ctx: PartnerCtx = Depends(active_partner),
                        db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.update_source(db, ctx.actor, ctx.partner.id, source_id, body.model_dump(exclude_unset=True))
    await db.commit()
    return serialize.source(row)


@router.get("/campaigns")
async def list_campaigns(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffCampaign).where(AffCampaign.partner_id == ctx.partner.id).order_by(AffCampaign.id.desc()))).scalars().all()
    return {"items": [serialize.campaign(c) for c in rows]}


@router.post("/campaigns", status_code=201)
async def create_campaign(body: CampaignIn, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.create_campaign(db, ctx.actor, ctx.partner.id, body.model_dump())
    await db.commit()
    return serialize.campaign(row)


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: int, body: CampaignUpdateIn, ctx: PartnerCtx = Depends(active_partner),
                          db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.update_campaign(db, ctx.actor, ctx.partner.id, campaign_id, body.model_dump(exclude_unset=True))
    await db.commit()
    return serialize.campaign(row)


@router.get("/tracking-links")
async def list_links(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    base = await partner_service.link_base(db)
    rows = await partner_service.list_links(db, [ctx.partner.id])
    mirrors = [d.domain for d in await partner_service.active_domains(db)][1:]
    return {"items": [serialize.link(l, await partner_service.link_urls(db, l.link_code, base)) for l in rows],
            "base_url": base, "mirrors": mirrors}


@router.post("/tracking-links", status_code=201)
async def create_link(body: LinkIn, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.create_link(db, ctx.actor, ctx.partner.id, body.model_dump())
    await db.commit()
    return serialize.link(row, await partner_service.link_urls(db, row.link_code))


@router.patch("/tracking-links/{link_id}")
async def update_link(link_id: int, body: LinkUpdateIn, ctx: PartnerCtx = Depends(active_partner),
                      db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.update_link(db, ctx.actor, ctx.partner.id, link_id, body.model_dump(exclude_unset=True))
    await db.commit()
    return serialize.link(row, await partner_service.link_urls(db, row.link_code))


@router.get("/promo-codes")
async def list_promos(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffPromoCode).where(AffPromoCode.partner_id == ctx.partner.id).order_by(AffPromoCode.id.desc()))).scalars().all()
    return {"items": [serialize.promo(p) for p in rows]}


@router.post("/promo-codes", status_code=201)
async def create_promo(body: PromoIn, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.create_promo(db, ctx.actor, ctx.partner.id, body.tracking_link_id, body.code)
    await db.commit()
    return serialize.promo(row)


@router.patch("/promo-codes/{promo_id}")
async def archive_promo(promo_id: int, status: str = Query(...), ctx: PartnerCtx = Depends(active_partner),
                        db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(AffPromoCode, promo_id)
    if row is None or row.partner_id != ctx.partner.id:
        raise NotFoundException("Promo code not found")
    row.status = RecordStatus(status)
    await db.commit()
    return serialize.promo(row)


# ===================================================================== PR tools


@router.get("/pr-materials")
async def pr_materials(type: Optional[str] = None, language: Optional[str] = None, ctx: PartnerCtx = Depends(active_partner),
                       db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffPrMaterial).where(AffPrMaterial.status == ContentStatus.PUBLISHED,
                                        (AffPrMaterial.partner_id.is_(None)) | (AffPrMaterial.partner_id == ctx.partner.id))
    if type:
        query = query.where(AffPrMaterial.type == type.upper())
    if language:
        query = query.where(AffPrMaterial.language == language)
    rows = (await db.execute(query.order_by(AffPrMaterial.id.desc()))).scalars().all()
    return {"items": [serialize.material(x) for x in rows]}


@router.get("/qr-codes")
async def list_qr(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffQrCode).where(AffQrCode.partner_id == ctx.partner.id).order_by(AffQrCode.id.desc()))).scalars().all()
    return {"items": [serialize.qr(q) for q in rows]}


@router.post("/qr-codes", status_code=201)
async def create_qr(body: QrIn, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await content_service.create_qr(db, ctx.actor, ctx.partner, body.tracking_link_id, body.name)
    await db.commit()
    return serialize.qr(row)


# ===================================================================== wallet & withdrawals


@router.get("/wallet")
async def wallet(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    w = await ledger.get_wallet(db, ctx.partner.id)
    deal = await partner_service.current_deal(db, ctx.partner.id)
    open_wd = (await db.execute(select(AffWithdrawal).where(AffWithdrawal.partner_id == ctx.partner.id,
                                                            AffWithdrawal.status.in_(["PENDING", "UNDER_REVIEW", "APPROVED", "PROCESSING"])))).scalars().first()
    minimum = await aff_settings.get_decimal(db, "min_payout")
    available = w.available_balance
    reason = None
    if ctx.partner.payout_frozen:
        reason = "Payouts are frozen on this account"
    elif open_wd is not None:
        reason = "A withdrawal is already in progress"
    elif available < minimum:
        reason = "Negative balance: it is covered by future earnings first" if available < 0 else f"Minimum payout is {minimum:.2f} $"
    return {**serialize.wallet(w), "deal": serialize.deal(deal), "min_payout": f"{minimum:.2f}",
            "can_withdraw": reason is None, "withdraw_blocked_reason": reason}


@router.get("/wallet/transactions")
async def wallet_transactions(cursor: Optional[int] = None, limit: int = Query(30, ge=1, le=100), bucket: Optional[str] = None,
                              ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    w = await ledger.get_wallet(db, ctx.partner.id)
    query = select(AffWalletTransaction).where(AffWalletTransaction.wallet_id == w.id)
    if bucket:
        query = query.where(AffWalletTransaction.bucket == bucket.upper())
    if cursor:
        query = query.where(AffWalletTransaction.id < cursor)
    rows = (await db.execute(query.order_by(AffWalletTransaction.id.desc()).limit(limit + 1))).scalars().all()
    return {"items": [serialize.ledger_entry(t) for t in rows[:limit]], "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


@router.get("/wallet/statements")
async def wallet_statements(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    rows = await settlement.statements(db, ctx.partner.id)
    return {"items": [{**serialize.period_balance(r["balance"]), "period": serialize.period(r["period"])} for r in rows]}


@router.get("/withdrawal-methods")
async def list_methods(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffWithdrawalMethod).where(AffWithdrawalMethod.partner_id == ctx.partner.id,
                                                               AffWithdrawalMethod.status == RecordStatus.ACTIVE)
                             .order_by(AffWithdrawalMethod.is_default.desc(), AffWithdrawalMethod.id))).scalars().all()
    return {"items": [serialize.method(x) for x in rows], "types": ["EWALLET_EMAIL", "USDT_TRC20", "BANK", "UPI", "OTHER"]}


@router.post("/withdrawal-methods", status_code=201, dependencies=[Depends(rate_limit_dependency("aff:method", 10, 3600))])
async def add_method(body: MethodIn, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await withdrawals.add_method(db, ctx.actor, ctx.partner, body.model_dump())
    await db.commit()
    return serialize.method(row)


@router.patch("/withdrawal-methods/{method_id}")
async def update_method(method_id: int, body: MethodUpdateIn, ctx: PartnerCtx = Depends(active_partner),
                        db: AsyncSession = Depends(get_db)) -> dict:
    data = body.model_dump(exclude_unset=True)
    row = await withdrawals.update_method(db, ctx.actor, ctx.partner, method_id, data)
    await db.commit()
    return serialize.method(row)


@router.get("/withdrawals")
async def list_withdrawals(cursor: Optional[int] = None, limit: int = Query(20, ge=1, le=100),
                           ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffWithdrawal).where(AffWithdrawal.partner_id == ctx.partner.id)
    if cursor:
        query = query.where(AffWithdrawal.id < cursor)
    rows = (await db.execute(query.order_by(AffWithdrawal.id.desc()).limit(limit + 1))).scalars().all()
    return {"items": [serialize.withdrawal(w) for w in rows[:limit]], "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


@router.post("/withdrawals", status_code=201, dependencies=[Depends(rate_limit_dependency("aff:withdraw", 10, 3600))])
async def request_withdrawal(body: WithdrawalIn, idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
                             ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await withdrawals.request_withdrawal(db, ctx.actor, ctx.partner, amount=body.amount, method_id=body.method_id,
                                               idempotency_key=idempotency_key)
    await db.commit()
    return serialize.withdrawal(row)


@router.get("/withdrawals/{withdrawal_id}")
async def get_withdrawal(withdrawal_id: int, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(AffWithdrawal, withdrawal_id)
    if row is None or row.partner_id != ctx.partner.id:
        raise NotFoundException("Withdrawal not found")
    return {**serialize.withdrawal(row), "history": [serialize.status_history(h) for h in await withdrawals.history(db, row.id)]}


@router.post("/withdrawals/{withdrawal_id}/cancel")
async def cancel_withdrawal(withdrawal_id: int, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await withdrawals.cancel(db, ctx.actor, ctx.partner, withdrawal_id)
    await db.commit()
    return serialize.withdrawal(row)


@router.get("/withdrawals-auto")
async def get_auto(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await withdrawals.get_auto(db, ctx.partner.id)
    return {"enabled": row.enabled, "method_id": row.withdrawal_method_id, "min_amount": f"{row.min_amount:.2f}"}


@router.put("/withdrawals-auto")
async def put_auto(body: AutoWithdrawalIn, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await withdrawals.set_auto(db, ctx.actor, ctx.partner, body.enabled, body.method_id, body.min_amount)
    await db.commit()
    return {"enabled": row.enabled, "method_id": row.withdrawal_method_id, "min_amount": f"{row.min_amount:.2f}"}


# ===================================================================== subpartners


@router.get("/subpartners")
async def subpartners(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    url = None
    if ctx.partner.parent_partner_id is None and int(await aff_settings.get(db, "subpartner_depth")) >= 1:
        url = await partner_service.invite_link(db, ctx.partner)
    return {"invite_link": url, "rate": str(ctx.partner.subpartner_rate),
            "items": await stats.subpartner_stats(db, ctx.partner, "all")}


# ===================================================================== postbacks


@router.get("/postbacks")
async def list_postbacks(ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffPartnerPostback).where(AffPartnerPostback.partner_id == ctx.partner.id)
                             .order_by(AffPartnerPostback.id))).scalars().all()
    logs = (await db.execute(select(AffPartnerPostbackLog).where(AffPartnerPostbackLog.partner_postback_id.in_([r.id for r in rows] or [0]))
                             .order_by(AffPartnerPostbackLog.id.desc()).limit(50))).scalars().all()
    return {"items": [serialize.postback(p) for p in rows], "logs": [serialize.postback_log(l) for l in logs],
            "macros": list(postbacks.MACROS)}


@router.post("/postbacks", status_code=201)
async def create_postback(body: PostbackIn, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = AffPartnerPostback(partner_id=ctx.partner.id, event_type=PostbackEvent(body.event_type.upper()),
                             url_template=postbacks.validate_template(body.url_template))
    db.add(row)
    await db.commit()
    return serialize.postback(row)


@router.patch("/postbacks/{postback_id}")
async def update_postback(postback_id: int, body: PostbackUpdateIn, ctx: PartnerCtx = Depends(active_partner),
                          db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(AffPartnerPostback, postback_id)
    if row is None or row.partner_id != ctx.partner.id:
        raise NotFoundException("Postback not found")
    if body.url_template:
        row.url_template = postbacks.validate_template(body.url_template)
    if body.status:
        row.status = RecordStatus(body.status)
    await db.commit()
    return serialize.postback(row)


@router.post("/postbacks/{postback_id}/test", dependencies=[Depends(rate_limit_dependency("aff:pbtest", 10, 600))])
async def test_postback(postback_id: int, ctx: PartnerCtx = Depends(active_partner), db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(AffPartnerPostback, postback_id)
    if row is None or row.partner_id != ctx.partner.id:
        raise NotFoundException("Postback not found")
    return await postbacks.test_fire(row.url_template)


# ===================================================================== content & support


@router.get("/faqs")
async def faqs(language: Optional[str] = None, ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffFaq).where(AffFaq.status == ContentStatus.PUBLISHED)
    if language:
        query = query.where(AffFaq.language == language)
    rows = (await db.execute(query.order_by(AffFaq.sort_order, AffFaq.id))).scalars().all()
    return {"items": [serialize.faq(f) for f in rows]}


@router.get("/blog-posts")
async def blog_posts(ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffBlogPost).where(AffBlogPost.status == ContentStatus.PUBLISHED)
                             .order_by(AffBlogPost.published_at.desc()).limit(50))).scalars().all()
    return {"items": [serialize.blog(b, full=False) for b in rows]}


@router.get("/blog-posts/{slug}")
async def blog_post(slug: str, ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    row = (await db.execute(select(AffBlogPost).where(AffBlogPost.slug == slug, AffBlogPost.status == ContentStatus.PUBLISHED))).scalar_one_or_none()
    if row is None:
        raise NotFoundException("Post not found")
    return serialize.blog(row)


@router.get("/contacts/manager")
async def manager(ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    return {"manager": await content_service.manager_contact(db, ctx.partner)}


@router.get("/contacts")
async def my_contacts(ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffContact).where(AffContact.partner_id == ctx.partner.id).order_by(AffContact.id.desc()).limit(50))).scalars().all()
    return {"items": [serialize.contact(c) for c in rows]}


@router.post("/contacts", status_code=201, dependencies=[Depends(rate_limit_dependency("aff:contact", 5, 3600))])
async def contact(body: ContactIn, ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    row = await content_service.create_contact(db, ctx.actor, ctx.partner, body.model_dump())
    await db.commit()
    return serialize.contact(row)


@router.get("/notifications")
async def notifications(cursor: Optional[str] = None, ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    query = select(Notification).where(Notification.user_id == ctx.user.id)
    rows = (await db.execute(query.order_by(Notification.created_at.desc()).limit(100))).scalars().all()
    return {"items": [{"id": n.id, "title": n.title, "message": n.message, "type": n.type, "is_read": n.is_read,
                       "created_at": serialize._v(n.created_at)} for n in rows]}


@router.post("/notifications/read")
async def read_notifications(ids: Optional[List[str]] = None, ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> dict:
    query = update(Notification).where(Notification.user_id == ctx.user.id, Notification.is_read.is_(False))
    if ids:
        query = query.where(Notification.id.in_(ids))
    result = await db.execute(query.values(is_read=True))
    await db.commit()
    return {"updated": result.rowcount}
