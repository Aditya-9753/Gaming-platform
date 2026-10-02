"""Live operations dashboard: real-time aggregates from the real tables.

Everything is read straight from users / game_entries / game_rounds / wallets
on each request (the page polls every few seconds). Simulated players
(``app.games.simulated_players.BOT_NAMES``) are excluded unless asked for, so
the numbers describe real people.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, case, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.games.simulated_players import BOT_NAMES
from app.models.game import Game, GameEntry, GameRound
from app.models.role import Role
from app.models.support import SupportTicket
from app.models.user import User
from app.models.wallet import Wallet

_IST = timezone(timedelta(hours=5, minutes=30))
SETTLED = ("WON", "LOST")


def _today_start_utc(now: datetime) -> datetime:
    local = now.astimezone(_IST)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _pick_label(game_id: str, selection: Optional[Dict[str, Any]]) -> str:
    s = selection or {}
    if s.get("type") and s.get("value") is not None:
        return f"#{s['value']}" if s["type"] == "NUMBER" else str(s["value"]).title()
    if "mine_count" in s:
        return f"{s['mine_count']} mines"
    if s.get("auto_cashout"):
        return f"auto {float(s['auto_cashout']):.2f}x"
    return "manual" if game_id == "aviator" else "—"


class LiveDashboard:
    def __init__(self, db: AsyncSession, include_bots: bool = False) -> None:
        self.db = db
        self.include_bots = include_bots

    def _real_users(self):
        """WHERE clause for 'real people' (players only, bots excluded unless requested)."""
        clauses = [Role.name == "USER"]
        if not self.include_bots:
            clauses.append(User.username.notin_(BOT_NAMES))
        return and_(*clauses)

    async def build(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        today = _today_start_utc(now)
        recent = now - timedelta(minutes=15)
        day_ago = now - timedelta(hours=24)
        player = self._real_users()

        users = (await self.db.execute(
            select(
                func.count(User.id),
                func.count(case((User.created_at >= today, 1))),
                func.count(case((User.is_active == False, 1))),  # noqa: E712
            ).join(Role, Role.id == User.role_id).where(player)
        )).one()

        def agg(since: datetime):
            return (
                select(
                    func.count(GameEntry.id),
                    func.count(distinct(GameEntry.user_id)),
                    func.coalesce(func.sum(GameEntry.bet_amount), 0),
                    func.coalesce(func.sum(case((GameEntry.status.in_(SETTLED), GameEntry.bet_amount), else_=0)), 0),
                    func.coalesce(func.sum(case((GameEntry.status == "WON", GameEntry.payout_amount), else_=0)), 0),
                )
                .select_from(GameEntry)
                .join(User, User.id == GameEntry.user_id)
                .join(Role, Role.id == User.role_id)
                .where(player, GameEntry.created_at >= since)
            )

        bets_today, players_today, wagered_today, settled_stake, paid_today = (await self.db.execute(agg(today))).one()
        active_15m = (await self.db.execute(
            select(func.count(distinct(User.id))).join(Role, Role.id == User.role_id).where(
                player,
                or_(
                    User.last_login_at >= recent,
                    User.id.in_(select(GameEntry.user_id).where(GameEntry.created_at >= recent)),
                ),
            )
        )).scalar_one()
        active_24h = (await self.db.execute(
            select(func.count(distinct(GameEntry.user_id)))
            .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
            .where(player, GameEntry.created_at >= day_ago)
        )).scalar_one()
        balances = (await self.db.execute(
            select(func.coalesce(func.sum(Wallet.balance), 0), func.coalesce(func.sum(Wallet.locked_balance), 0))
            .join(User, User.id == Wallet.user_id).join(Role, Role.id == User.role_id).where(player)
        )).one()
        open_tickets = (await self.db.execute(
            select(func.count(SupportTicket.id)).where(SupportTicket.status.in_(["OPEN", "IN_PROGRESS"]))
        )).scalar_one()

        house_today = int(settled_stake) - int(paid_today)

        # Per game (today)
        per_game_rows = (await self.db.execute(
            select(
                GameRound.game_id,
                func.count(GameEntry.id),
                func.count(distinct(GameEntry.user_id)),
                func.coalesce(func.sum(GameEntry.bet_amount), 0),
                func.coalesce(func.sum(case((GameEntry.status.in_(SETTLED), GameEntry.bet_amount), else_=0)), 0),
                func.coalesce(func.sum(case((GameEntry.status == "WON", GameEntry.payout_amount), else_=0)), 0),
                func.max(GameEntry.created_at),
            )
            .select_from(GameEntry)
            .join(GameRound, GameRound.id == GameEntry.round_id)
            .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
            .where(player, GameEntry.created_at >= today)
            .group_by(GameRound.game_id)
        )).all()
        per_game = {
            gid: {"bets": n, "players": p, "wagered": int(w), "paid": int(paid), "house_net": int(s) - int(paid),
                  "last_bet_at": last.isoformat() if last else None}
            for gid, n, p, w, s, paid, last in per_game_rows
        }
        games = []
        for game in (await self.db.execute(select(Game).order_by(Game.id))).scalars():
            last_round = (await self.db.execute(
                select(GameRound).where(GameRound.game_id == game.id).order_by(GameRound.round_no.desc()).limit(1)
            )).scalar_one_or_none()
            stats = per_game.get(game.id, {"bets": 0, "players": 0, "wagered": 0, "paid": 0, "house_net": 0, "last_bet_at": None})
            games.append({
                "game_id": game.id,
                "name": game.name,
                "is_active": game.is_active,
                "round_no": last_round.round_no if last_round else None,
                "round_status": last_round.status if last_round else None,
                **stats,
            })

        # Hourly series (last 24h): wagered vs paid
        series: List[Dict[str, Any]] = []
        hour_rows = (await self.db.execute(
            select(GameEntry.created_at, GameEntry.bet_amount, GameEntry.status, GameEntry.payout_amount)
            .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
            .where(player, GameEntry.created_at >= day_ago)
        )).all()
        buckets: Dict[int, Dict[str, int]] = {}
        for created, amount, status, payout in hour_rows:
            ts = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
            idx = int((now - ts).total_seconds() // 3600)
            b = buckets.setdefault(min(idx, 23), {"wagered": 0, "paid": 0, "bets": 0})
            b["wagered"] += amount
            b["bets"] += 1
            if status == "WON":
                b["paid"] += payout
        for i in range(23, -1, -1):
            hour = (now - timedelta(hours=i)).astimezone(_IST)
            b = buckets.get(i, {"wagered": 0, "paid": 0, "bets": 0})
            series.append({"hour": hour.strftime("%H:00"), **b})

        # Recent bets (real players)
        recent_rows = (await self.db.execute(
            select(GameEntry, User.username, GameRound.game_id)
            .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
            .join(GameRound, GameRound.id == GameEntry.round_id)
            .where(player)
            .order_by(GameEntry.created_at.desc())
            .limit(25)
        )).all()
        recent_bets = [
            {
                "username": username,
                "game_id": gid,
                "amount": e.bet_amount,
                "pick": _pick_label(gid, e.selection),
                "status": e.status,
                "payout": e.payout_amount,
                "multiplier": (e.multiplier / 100) if e.multiplier else None,
                "at": e.created_at.isoformat(),
            }
            for e, username, gid in recent_rows
        ]

        # Newest registrations
        signups = (await self.db.execute(
            select(User.username, User.created_at, User.last_login_at, Wallet.balance)
            .join(Role, Role.id == User.role_id).outerjoin(Wallet, Wallet.user_id == User.id)
            .where(player).order_by(User.created_at.desc()).limit(10)
        )).all()

        # Top players today by net result
        top_rows = (await self.db.execute(
            select(
                User.username,
                func.count(GameEntry.id),
                func.coalesce(func.sum(GameEntry.bet_amount), 0),
                func.coalesce(func.sum(case((GameEntry.status == "WON", GameEntry.payout_amount), else_=0)), 0),
            )
            .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
            .where(player, GameEntry.created_at >= today, GameEntry.status.in_(SETTLED))
            .group_by(User.username)
            .order_by((func.coalesce(func.sum(case((GameEntry.status == "WON", GameEntry.payout_amount), else_=0)), 0) - func.coalesce(func.sum(GameEntry.bet_amount), 0)).desc())
            .limit(8)
        )).all()

        return {
            "generated_at": now.isoformat(),
            "include_bots": self.include_bots,
            "kpis": {
                "players_total": users[0],
                "signups_today": users[1],
                "suspended": users[2],
                "active_15m": active_15m,
                "active_24h": active_24h,
                "players_today": players_today,
                "bets_today": bets_today,
                "wagered_today": int(wagered_today),
                "paid_today": int(paid_today),
                "house_today": house_today,
                "hold_pct_today": round(house_today / int(settled_stake) * 100, 2) if settled_stake else 0.0,
                "player_balances": int(balances[0]),
                "in_open_bets": int(balances[1]),
                "open_tickets": open_tickets,
            },
            "games": games,
            "hourly": series,
            "recent_bets": recent_bets,
            "signups": [
                {"username": u, "joined_at": c.isoformat() if c else None, "last_login_at": l.isoformat() if l else None, "balance": int(b or 0)}
                for u, c, l, b in signups
            ],
            "top_players": [
                {"username": u, "bets": n, "wagered": int(w), "won": int(p), "net": int(p) - int(w)} for u, n, w, p in top_rows
            ],
        }


__all__ = ["LiveDashboard"]
