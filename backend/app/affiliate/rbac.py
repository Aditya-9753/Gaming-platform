"""Affiliate permission metadata (names shown in the Roles / Permissions admin pages)."""

from __future__ import annotations

from typing import Dict, Tuple

from app.core.constants import PermissionCode

AFF_PERMISSIONS_META: Dict[str, Tuple[str, str]] = {
    PermissionCode.AFF_PORTAL.value: ("Partner Portal", "Use the partner portal for one's own partner account"),
    PermissionCode.AFF_PARTNER_READ.value: ("View Partners", "Look up partners, their links and statistics (read-only)"),
    PermissionCode.AFF_PARTNER_MANAGE.value: ("Manage Partners", "Create, approve, suspend partners and assign managers"),
    PermissionCode.AFF_IMPERSONATE.value: ("Impersonate Partner", "Open a partner's portal read-only for support"),
    PermissionCode.AFF_TRACKING_MANAGE.value: ("Manage Tracking", "Sources, campaigns, tracking links and promo codes of any partner"),
    PermissionCode.AFF_DOMAIN_MANAGE.value: ("Manage Tracking Domains", "Primary and mirror tracking domains"),
    PermissionCode.AFF_DEAL_MANAGE.value: ("Manage Deals", "Commission plans and partner deals / rates"),
    PermissionCode.AFF_SETTLEMENT_MANAGE.value: ("Manage Settlement", "Close settlement periods"),
    PermissionCode.AFF_WITHDRAWAL_MANAGE.value: ("Manage Partner Withdrawals", "Approve, reject and mark partner payouts paid"),
    PermissionCode.AFF_ADJUST.value: ("Partner Wallet Adjustments", "Request or approve maker-checker wallet adjustments"),
    PermissionCode.AFF_FINANCE_READ.value: ("View Partner Finance", "Partner wallets, ledger and period balances"),
    PermissionCode.AFF_STATS_READ.value: ("View Affiliate Statistics", "Platform-wide affiliate statistics"),
    PermissionCode.AFF_CONTENT_MANAGE.value: ("Manage Partner Content", "PR materials and blog posts"),
    PermissionCode.AFF_SUPPORT_MANAGE.value: ("Manage Partner Support", "Partner contact requests and FAQ"),
    PermissionCode.AFF_RISK_MANAGE.value: ("Manage Affiliate Risk", "Risk events, payout freezes, fraud marking"),
    PermissionCode.AFF_INGEST_MANAGE.value: ("Ingest Monitor", "Inspect and retry operator S2S events"),
    PermissionCode.AFF_SETTINGS_MANAGE.value: ("Affiliate Settings", "Global affiliate settings"),
}
