"""PR tools (materials, QR codes), FAQ, blog, contacts and partner manager details."""

from __future__ import annotations

import base64
import io
import re
import unicodedata
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate.common import Actor, audit, notify
from app.affiliate.constants import ContactStatus
from app.affiliate.partners import link_urls
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.affiliate import AffBlogPost, AffContact, AffPartner, AffQrCode, AffTrackingLink
from app.models.user import User

MAX_DATA_URL = 3_000_000  # ~2.2 MB image as a data URL (S3 replaces this later)


def qr_data_url(text: str) -> str:
    """QR code as a PNG data URL (SVG when Pillow is not installed)."""
    import qrcode

    try:
        import PIL  # noqa: F401

        image = qrcode.make(text, box_size=8, border=2)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    except ImportError:
        from qrcode.image.svg import SvgPathImage

        buffer = io.BytesIO()
        qrcode.make(text, image_factory=SvgPathImage, box_size=10, border=2).save(buffer)
        return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode()


async def create_qr(db: AsyncSession, actor: Actor, partner: AffPartner, link_id: int, name: Optional[str]) -> AffQrCode:
    link = await db.get(AffTrackingLink, link_id)
    if link is None or link.partner_id != partner.id:
        raise NotFoundException("Tracking link not found")
    url = (await link_urls(db, link.link_code))["query"]
    row = AffQrCode(partner_id=partner.id, tracking_link_id=link.id, name=(name or link.name)[:80], image_url=qr_data_url(url))
    db.add(row)
    await db.flush()
    await audit(db, actor, "AFF_QR_CREATED", "aff_qr_code", row.id, link=link.link_code)
    return row


def slugify(text: str) -> str:
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value[:180] or "post"


async def unique_slug(db: AsyncSession, title: str, exclude_id: Optional[int] = None) -> str:
    base = slugify(title)
    slug, n = base, 2
    while True:
        row = (await db.execute(select(AffBlogPost.id).where(AffBlogPost.slug == slug))).scalar_one_or_none()
        if row is None or row == exclude_id:
            return slug
        slug = f"{base}-{n}"
        n += 1


def check_media(value: Optional[str]) -> Optional[str]:
    """Accept https URLs or small image data URLs (png / jpeg / webp / gif)."""
    if not value:
        return None
    value = value.strip()
    if value.startswith("https://") or value.startswith("http://"):
        return value[:2000]
    if re.match(r"^data:image/(png|jpeg|webp|gif);base64,", value) and len(value) <= MAX_DATA_URL:
        return value
    raise BadRequestException("Use an https:// link or a PNG/JPEG/WebP/GIF image under 2 MB")


async def manager_contact(db: AsyncSession, partner: AffPartner) -> Optional[Dict[str, Any]]:
    if not partner.manager_id:
        return None
    manager = await db.get(User, partner.manager_id)
    if manager is None:
        return None
    return {"name": manager.full_name or manager.username, "email": manager.email}


async def create_contact(db: AsyncSession, actor: Actor, partner: Optional[AffPartner], data: Dict[str, Any]) -> AffContact:
    row = AffContact(partner_id=partner.id if partner else None, name=data["name"][:120], email=str(data["email"])[:255],
                     subject=data["subject"][:200], message=data["message"][:5000], assigned_to=partner.manager_id if partner else None)
    db.add(row)
    await db.flush()
    if partner and partner.manager_id:
        await notify(db, partner.manager_id, "New partner message", f"{partner.partner_code}: {row.subject}")
    return row


async def reply_contact(db: AsyncSession, actor: Actor, contact_id: int, reply: Optional[str], status: Optional[str],
                        assigned_to: Optional[str]) -> AffContact:
    row = await db.get(AffContact, contact_id)
    if row is None:
        raise NotFoundException("Message not found")
    if reply:
        row.reply = reply[:5000]
        if row.partner_id:
            partner = await db.get(AffPartner, row.partner_id)
            if partner:
                await notify(db, partner.user_id, f"Reply: {row.subject}", reply[:1000])
        if not status:
            row.status = ContactStatus.IN_PROGRESS
    if status:
        row.status = ContactStatus(status)
    if assigned_to is not None:
        row.assigned_to = assigned_to or None
    await db.flush()
    await audit(db, actor, "AFF_CONTACT_UPDATED", "aff_contact", row.id, new={"status": row.status.value, "replied": bool(reply)})
    return row
