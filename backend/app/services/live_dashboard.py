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

from app.games.fairness_guard import is_finished, public_selection
from app.games.simulated_players import BOT_NAMES
from app.models.cricket import CricketMatchRecord, CricketPrediction
from app.models.game import Game, GameEntry, GameResult, GameRound
from app.models.role import Role
from app.models.support import SupportTicket
from app.models.user import User
from app.models.wallet import Wallet

_IST = timezone(timedelta(hours=5, minutes=30))
SETTLED = ("WON", "LOST")
# Round metadata that is safe to show while a round is still running (timing only, never the outcome)
_SAFE_LIVE_KEYS = ("period", "betting_closes_at", "result_at", "duration")


def _outcome_visible(status: Optional[str]) -> bool:
    """The outcome may be shown once the round can no longer change (crash already broadcast)."""
    return is_finished(status) or (status or "") == "CRASHED"


def _outcome_label(game_id: str, outcome: Optional[Dict[str, Any]]) -> Optional[str]:
    o = outcome or {}
    if "crash_point" in o:
        return f"{float(o['crash_point']):.2f}x"
    if "crash_point_x100" in o:
        return f"{int(o['crash_point_x100']) / 100:.2f}x"
    if o.get("number") is not None:
        colours = "/".join(str(c).title() for c in (o.get("colours") or []))
        return f"{o['number']} · {colours} · {str(o.get('size', '')).title()}".strip(" ·")
    return None


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


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
                "live": await self._live_round(game.id, last_round, now),
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
                "id": e.id,
                "user_id": e.user_id,
                "round_id": e.round_id,
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
            select(User.id, User.username, User.created_at, User.last_login_at, Wallet.balance)
            .join(Role, Role.id == User.role_id).outerjoin(Wallet, Wallet.user_id == User.id)
            .where(player).order_by(User.created_at.desc()).limit(10)
        )).all()

        # Top players today by net result
        top_rows = (await self.db.execute(
            select(
                User.id,
                User.username,
                func.count(GameEntry.id),
                func.coalesce(func.sum(GameEntry.bet_amount), 0),
                func.coalesce(func.sum(case((GameEntry.status == "WON", GameEntry.payout_amount), else_=0)), 0),
            )
            .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
            .where(player, GameEntry.created_at >= today, GameEntry.status.in_(SETTLED))
            .group_by(User.id, User.username)
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
                {"user_id": i, "username": u, "joined_at": c.isoformat() if c else None, "last_login_at": l.isoformat() if l else None, "balance": int(b or 0)}
                for i, u, c, l, b in signups
            ],
            "top_players": [
                {"user_id": i, "username": u, "bets": n, "wagered": int(w), "won": int(p), "net": int(p) - int(w)} for i, u, n, w, p in top_rows
            ],
        }

    # ------------------------------------------------------------------ live round
    async def _live_round(self, game_id: str, round_obj: Optional[GameRound], now: datetime) -> Dict[str, Any]:
        """What is happening right now in a game. Timing and stakes only; never an unrevealed outcome."""
        if game_id == "mines":
            n, staked = (await self.db.execute(
                select(func.count(GameEntry.id), func.coalesce(func.sum(GameEntry.bet_amount), 0))
                .join(GameRound, GameRound.id == GameEntry.round_id)
                .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
                .where(GameRound.game_id == "mines", GameEntry.status == "PLACED", self._real_users())
            )).one()
            return {"kind": "sessions", "open_bets": int(n), "open_stake": int(staked)}
        if game_id == "cricket":
            n, staked = (await self.db.execute(
                select(func.count(CricketPrediction.id), func.coalesce(func.sum(CricketPrediction.stake), 0))
                .join(User, User.id == CricketPrediction.user_id).join(Role, Role.id == User.role_id)
                .where(CricketPrediction.status == "PLACED", self._real_users())
            )).one()
            live_matches = (await self.db.execute(
                select(func.count(CricketMatchRecord.id))
                .where(func.upper(CricketMatchRecord.status).in_(["LIVE", "IN_PROGRESS", "INPROGRESS"]))
            )).scalar_one()
            return {"kind": "matches", "open_bets": int(n), "open_stake": int(staked), "live_matches": int(live_matches)}
        if round_obj is None:
            return {"kind": "round", "open_bets": 0, "open_stake": 0}
        n, staked = (await self.db.execute(
            select(func.count(GameEntry.id), func.coalesce(func.sum(GameEntry.bet_amount), 0))
            .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
            .where(GameEntry.round_id == round_obj.id, GameEntry.status == "PLACED", self._real_users())
        )).one()
        info: Dict[str, Any] = {
            "kind": "round",
            "round_id": round_obj.id,
            "status": round_obj.status,
            "open_bets": int(n),
            "open_stake": int(staked),
        }
        meta = round_obj.result or {}
        info.update({k: meta[k] for k in _SAFE_LIVE_KEYS if k in meta})
        if game_id == "aviator" and round_obj.status == "RUNNING" and round_obj.started_at and meta.get("growth_rate"):
            from app.games.aviator.rules import elapsed_since, multiplier_x100_at

            info["multiplier"] = round(multiplier_x100_at(
                elapsed_since(round_obj.started_at, now),
                float(meta["growth_rate"]), float(meta.get("growth_power", 1.0)), str(meta.get("growth_model", "power")),
            ) / 100, 2)
        if _outcome_visible(round_obj.status):
            info["outcome"] = await self._round_outcome_label(round_obj)
        return info

    async def _round_outcome_label(self, round_obj: GameRound) -> Optional[str]:
        if not _outcome_visible(round_obj.status):
            return None
        res = (await self.db.execute(
            select(GameResult.outcome).where(GameResult.round_id == round_obj.id)
        )).scalar_one_or_none()
        return _outcome_label(round_obj.game_id, res or round_obj.result)

    def _bet_row(self, e: GameEntry, username: str, game_id: str, round_no: Optional[int] = None) -> Dict[str, Any]:
        sel = public_selection(e.selection, e.status) or {}
        return {
            "id": e.id,
            "user_id": e.user_id,
            "username": username,
            "game_id": game_id,
            "round_id": e.round_id,
            "round_no": round_no,
            "amount": e.bet_amount,
            "pick": _pick_label(game_id, sel),
            "status": e.status,
            "payout": e.payout_amount,
            "multiplier": (e.multiplier / 100) if e.multiplier else None,
            "revealed": len(sel.get("revealed_tiles") or []) if game_id == "mines" else None,
            "at": _iso(e.created_at),
        }

    # ------------------------------------------------------------------ per game
    async def game_detail(self, game_id: str) -> Optional[Dict[str, Any]]:
        game = await self.db.get(Game, game_id)
        if game is None:
            return None
        now = datetime.now(timezone.utc)
        today = _today_start_utc(now)
        player = self._real_users()

        if game_id == "cricket":
            return await self._cricket_detail(game, now)

        current = (await self.db.execute(
            select(GameRound).where(GameRound.game_id == game_id).order_by(GameRound.round_no.desc()).limit(1)
        )).scalar_one_or_none()

        # Bets in play: the current round (round games) or every open session (Mines)
        live_rows: List[Any] = []
        if game_id == "mines" or current is not None:
            live_q = (
                select(GameEntry, User.username, GameRound.round_no)
                .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
                .join(GameRound, GameRound.id == GameEntry.round_id)
                .where(player)
            )
            if game_id == "mines":
                live_q = live_q.where(GameRound.game_id == "mines", GameEntry.status == "PLACED")
            else:
                live_q = live_q.where(GameEntry.round_id == current.id)
            live_rows = (await self.db.execute(live_q.order_by(GameEntry.bet_amount.desc()).limit(200))).all()

        # Recently finished rounds with their totals
        recent_rounds = (await self.db.execute(
            select(GameRound).where(
                GameRound.game_id == game_id,
                GameRound.status.in_(["COMPLETED", "SETTLED", "HISTORY", "CANCELLED", "CRASHED"]),
            ).order_by(GameRound.round_no.desc()).limit(20)
        )).scalars().all()
        round_ids = [r.id for r in recent_rounds]
        totals: Dict[str, tuple] = {}
        outcomes: Dict[str, Any] = {}
        if round_ids:
            for rid, n, w, paid in (await self.db.execute(
                select(
                    GameEntry.round_id, func.count(GameEntry.id), func.coalesce(func.sum(GameEntry.bet_amount), 0),
                    func.coalesce(func.sum(case((GameEntry.status == "WON", GameEntry.payout_amount), else_=0)), 0),
                )
                .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
                .where(GameEntry.round_id.in_(round_ids), player)
                .group_by(GameEntry.round_id)
            )).all():
                totals[rid] = (int(n), int(w), int(paid))
            outcomes = dict((await self.db.execute(
                select(GameResult.round_id, GameResult.outcome).where(GameResult.round_id.in_(round_ids))
            )).all())

        latest = (await self.db.execute(
            select(GameEntry, User.username, GameRound.round_no)
            .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
            .join(GameRound, GameRound.id == GameEntry.round_id)
            .where(player, GameRound.game_id == game_id, GameEntry.created_at >= today)
            .order_by(GameEntry.created_at.desc()).limit(50)
        )).all()

        def round_row(r: GameRound) -> Dict[str, Any]:
            n, w, paid = totals.get(r.id, (0, 0, 0))
            return {
                "round_id": r.id,
                "round_no": r.round_no,
                "status": r.status,
                "outcome": _outcome_label(game_id, outcomes.get(r.id) or r.result) if _outcome_visible(r.status) else None,
                "bets": n,
                "wagered": w,
                "paid": paid,
                "house_net": w - paid,
                "ended_at": _iso(r.ended_at),
            }

        current_info = None
        if current is not None:
            current_info = {"round_no": current.round_no, "started_at": _iso(current.started_at),
                            **(await self._live_round(game_id, current, now))}
        return {
            "generated_at": now.isoformat(),
            "game_id": game.id,
            "name": game.name,
            "is_active": game.is_active,
            "current": current_info,
            "live_bets": [self._bet_row(e, u, game_id, rn) for e, u, rn in live_rows],
            "recent_rounds": [round_row(r) for r in recent_rounds],
            "today_bets": [self._bet_row(e, u, game_id, rn) for e, u, rn in latest],
        }

    async def _cricket_detail(self, game: Game, now: datetime) -> Dict[str, Any]:
        player = self._real_users()
        matches = (await self.db.execute(
            select(CricketMatchRecord).order_by(CricketMatchRecord.updated_at.desc()).limit(30)
        )).scalars().all()
        per_match = {
            mid: (int(n), int(st), int(op))
            for mid, n, st, op in (await self.db.execute(
                select(
                    CricketPrediction.match_id, func.count(CricketPrediction.id),
                    func.coalesce(func.sum(CricketPrediction.stake), 0),
                    func.count(case((CricketPrediction.status == "PLACED", 1))),
                )
                .join(User, User.id == CricketPrediction.user_id).join(Role, Role.id == User.role_id)
                .where(player).group_by(CricketPrediction.match_id)
            )).all()
        }
        preds = (await self.db.execute(
            select(CricketPrediction, User.username, CricketMatchRecord.home_team, CricketMatchRecord.away_team)
            .join(User, User.id == CricketPrediction.user_id).join(Role, Role.id == User.role_id)
            .join(CricketMatchRecord, CricketMatchRecord.id == CricketPrediction.match_id)
            .where(player).order_by(CricketPrediction.created_at.desc()).limit(50)
        )).all()
        return {
            "generated_at": now.isoformat(),
            "game_id": game.id,
            "name": game.name,
            "is_active": game.is_active,
            "matches": [
                {
                    "match_id": m.id,
                    "teams": f"{m.home_team} vs {m.away_team}",
                    "status": m.status,
                    "score": " · ".join(x for x in (m.home_score, m.away_score) if x) or None,
                    "winner": m.winner,
                    "predictions": per_match.get(m.id, (0, 0, 0))[0],
                    "staked": per_match.get(m.id, (0, 0, 0))[1],
                    "open": per_match.get(m.id, (0, 0, 0))[2],
                }
                for m in matches
            ],
            "predictions": [
                {
                    "id": p.id, "user_id": p.user_id, "username": u, "match": f"{h} vs {a}",
                    "pick": p.selection, "amount": p.stake, "odds": p.odds_bp / 100 if p.odds_bp else None,
                    "status": p.status, "payout": p.payout, "at": _iso(p.created_at),
                }
                for p, u, h, a in preds
            ],
        }

    # ------------------------------------------------------------------ KPI drill-down
    DRILLDOWNS = {
        "players": "All players",
        "signups_today": "Signed up today",
        "suspended": "Suspended players",
        "active_15m": "Active in the last 15 minutes",
        "players_today": "Played today",
        "bets_today": "Bets placed today",
        "won_today": "Winning bets today",
        "balances": "Player balances",
        "open_bets": "Bets in play right now",
        "tickets": "Open support tickets",
        "hour": "Bets in this hour",
    }

    async def drilldown(self, kind: str, hour: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if kind not in self.DRILLDOWNS:
            return None
        now = datetime.now(timezone.utc)
        today = _today_start_utc(now)
        player = self._real_users()
        out: Dict[str, Any] = {"kind": kind, "title": self.DRILLDOWNS[kind], "generated_at": now.isoformat()}

        if kind == "tickets":
            rows = (await self.db.execute(
                select(SupportTicket, User.username).outerjoin(User, User.id == SupportTicket.user_id)
                .where(SupportTicket.status.in_(["OPEN", "IN_PROGRESS"]))
                .order_by(SupportTicket.created_at.desc()).limit(100)
            )).all()
            out.update(shape="tickets", rows=[
                {"id": t.id, "user_id": t.user_id, "username": u, "subject": t.subject, "status": t.status,
                 "priority": t.priority, "at": _iso(t.created_at)}
                for t, u in rows
            ])
            return out

        if kind in ("bets_today", "won_today", "open_bets", "hour"):
            q = (
                select(GameEntry, User.username, GameRound.game_id, GameRound.round_no)
                .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
                .join(GameRound, GameRound.id == GameEntry.round_id)
                .where(player)
            )
            if kind == "bets_today":
                q = q.where(GameEntry.created_at >= today).order_by(GameEntry.created_at.desc())
            elif kind == "won_today":
                q = q.where(GameEntry.created_at >= today, GameEntry.status == "WON").order_by(GameEntry.payout_amount.desc())
            elif kind == "open_bets":
                q = q.where(GameEntry.status == "PLACED").order_by(GameEntry.bet_amount.desc())
            else:
                # Same bucketing as the hourly chart: offset 0 = the last hour, 23 = 23-24 hours ago
                offset = max(0, min(23, int(hour or 0)))
                end = now - timedelta(hours=offset)
                start = end - timedelta(hours=1)
                q = q.where(GameEntry.created_at > start, GameEntry.created_at <= end).order_by(GameEntry.created_at.desc())
                out["title"] = f"Bets {start.astimezone(_IST):%H:%M} to {end.astimezone(_IST):%H:%M} IST"
            rows = (await self.db.execute(q.limit(200))).all()
            out.update(shape="bets", rows=[self._bet_row(e, u, gid, rn) for e, u, gid, rn in rows])
            return out

        # Player lists
        played = (
            select(GameEntry.user_id.label("uid"), func.count(GameEntry.id).label("n"),
                   func.coalesce(func.sum(GameEntry.bet_amount), 0).label("w"))
            .where(GameEntry.created_at >= today).group_by(GameEntry.user_id).subquery()
        )
        q = (
            select(User.id, User.username, User.is_active, User.created_at, User.last_login_at,
                   Wallet.balance, Wallet.locked_balance, played.c.n, played.c.w)
            .join(Role, Role.id == User.role_id)
            .outerjoin(Wallet, Wallet.user_id == User.id)
            .outerjoin(played, played.c.uid == User.id)
            .where(player)
        )
        if kind == "signups_today":
            q = q.where(User.created_at >= today).order_by(User.created_at.desc())
        elif kind == "suspended":
            q = q.where(User.is_active == False).order_by(User.created_at.desc())  # noqa: E712
        elif kind == "active_15m":
            recent = now - timedelta(minutes=15)
            q = q.where(or_(
                User.last_login_at >= recent,
                User.id.in_(select(GameEntry.user_id).where(GameEntry.created_at >= recent)),
            )).order_by(User.last_login_at.desc().nullslast())
        elif kind == "players_today":
            q = q.where(played.c.n > 0).order_by(played.c.w.desc())
        elif kind == "balances":
            q = q.order_by(Wallet.balance.desc().nullslast())
        else:
            q = q.order_by(User.created_at.desc())
        rows = (await self.db.execute(q.limit(200))).all()
        out.update(shape="players", rows=[
            {"user_id": i, "username": u, "is_active": act, "joined_at": _iso(c), "last_login_at": _iso(ll),
             "balance": int(b or 0), "locked": int(lk or 0), "bets_today": int(n or 0), "wagered_today": int(w or 0)}
            for i, u, act, c, ll, b, lk, n, w in rows
        ])
        return out

    # ------------------------------------------------------------------ one bet
    async def bet_detail(self, entry_id: str) -> Optional[Dict[str, Any]]:
        row = (await self.db.execute(
            select(GameEntry, User.username, GameRound)
            .join(User, User.id == GameEntry.user_id)
            .join(GameRound, GameRound.id == GameEntry.round_id)
            .where(GameEntry.id == entry_id)
        )).first()
        if row is None:
            return None
        e, username, r = row
        return {
            **self._bet_row(e, username, r.game_id, r.round_no),
            "selection": public_selection(e.selection, e.status) or {},
            "updated_at": _iso(e.updated_at),
            "round": {
                "round_id": r.id,
                "round_no": r.round_no,
                "status": r.status,
                "started_at": _iso(r.started_at),
                "ended_at": _iso(r.ended_at),
                "server_seed_hash": r.server_seed_hash,
                "client_seed": r.client_seed or r.id,
                "server_seed": r.server_seed if is_finished(r.status) else None,
                "outcome": await self._round_outcome_label(r),
            },
        }


__all__ = ["LiveDashboard"]
