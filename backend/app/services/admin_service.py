"""Administrative operations service with mandatory audit logging for every write."""

from __future__ import annotations

import csv
import io
import math
from app.games.fairness_guard import public_selection, revealable_seed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import UserRole
from app.core.exceptions import BadRequestException, ConflictException, IdempotencyException, NotFoundException
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.game import Game, GameEntry, GameRound, GameSetting
from app.models.notification import Notification
from app.models.role import Permission, Role, RolePermission
from app.models.support import SupportMessage, SupportTicket
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.audit_repo import AuditRepository
from app.repositories.game_repo import GameRepository
from app.repositories.user_repo import UserRepository
from app.services.notification_service import NotificationService
from app.services.wallet_service import WalletService
from app.websocket.manager import ws_manager
from app.utils.money import MAX_SINGLE_TRANSACTION_PAISE


class AdminService:
    """Service providing administration actions with mandatory audit logging for EVERY write."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit_repo = AuditRepository(session)
        self.game_repo = GameRepository(session)
        self.user_repo = UserRepository(session)
        self.wallet_svc = WalletService(session)

    # =========================================================================
    # Dashboard Statistics
    # =========================================================================

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Aggregate high-level platform health, user activity, and financial metrics."""
        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(days=1)

        # Total & active users
        total_users_res = await self.session.execute(select(func.count(User.id)))
        total_users = total_users_res.scalar_one() or 0

        active_users_res = await self.session.execute(
            select(func.count(User.id)).where(
                User.is_active == True,  # noqa: E712
                or_(User.last_login_at >= day_ago, User.created_at >= day_ago),
            )
        )
        active_users = active_users_res.scalar_one() or 0

        # Live games
        live_games_res = await self.session.execute(
            select(func.count(Game.id)).where(Game.is_active == True)  # noqa: E712
        )
        live_games = live_games_res.scalar_one() or 0

        # Active WS sessions from in-memory ConnectionManager
        active_ws_sessions = ws_manager.active_connection_count

        # Total rounds played
        rounds_played_res = await self.session.execute(select(func.count(GameRound.id)))
        rounds_played = rounds_played_res.scalar_one() or 0

        # Credit in vs out
        in_stmt = select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
            WalletTransaction.type.in_(["FAUCET", "BONUS"]),
            WalletTransaction.amount > 0,
        )
        credit_in_res = await self.session.execute(in_stmt)
        credit_in = credit_in_res.scalar_one() or 0

        out_stmt = select(func.coalesce(func.sum(GameEntry.bet_amount), 0)).where(
            GameEntry.status.notin_(["CANCELLED", "REFUNDED"])
        )
        credit_out_res = await self.session.execute(out_stmt)
        credit_out = credit_out_res.scalar_one() or 0

        # Open support tickets
        open_tickets_res = await self.session.execute(
            select(func.count(SupportTicket.id)).where(
                SupportTicket.status.in_(["OPEN", "IN_PROGRESS"])
            )
        )
        open_tickets = open_tickets_res.scalar_one() or 0

        # Chart series: 7-day daily activity
        chart_series = []
        for i in range(6, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            wagers_res = await self.session.execute(
                select(func.coalesce(func.sum(GameEntry.bet_amount), 0)).where(
                    GameEntry.created_at >= day_start,
                    GameEntry.created_at < day_end,
                )
            )
            daily_wager = wagers_res.scalar_one() or 0

            payouts_res = await self.session.execute(
                select(func.coalesce(func.sum(GameEntry.payout_amount), 0)).where(
                    GameEntry.created_at >= day_start,
                    GameEntry.created_at < day_end,
                    GameEntry.status == "WON",
                )
            )
            daily_payout = payouts_res.scalar_one() or 0

            signups_res = await self.session.execute(
                select(func.count(User.id)).where(
                    User.created_at >= day_start,
                    User.created_at < day_end,
                )
            )
            daily_signups = signups_res.scalar_one() or 0

            chart_series.append({
                "date": day_start.strftime("%Y-%m-%d"),
                "wagered": daily_wager,
                "payout": daily_payout,
                "new_users": daily_signups,
            })

        return {
            "users": total_users,
            "active_users": active_users,
            "live_games": live_games,
            "active_ws_sessions": active_ws_sessions,
            "rounds_played": rounds_played,
            "credit_in": credit_in,
            "credit_out": credit_out,
            "open_tickets": open_tickets,
            "chart_series": chart_series,
        }

    # =========================================================================
    # Users Management
    # =========================================================================

    async def search_users(
        self,
        q: Optional[str] = None,
        role_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[User], int]:
        """Search and filter users with pagination."""
        stmt = select(User).options(selectinload(User.role), selectinload(User.wallet))
        count_stmt = select(func.count(User.id))

        filters = []
        if q:
            term = f"%{q}%"
            filters.append(or_(User.username.ilike(term), User.email.ilike(term), User.id.ilike(term)))
        if role_id is not None:
            filters.append(User.role_id == role_id)
        if is_active is not None:
            filters.append(User.is_active == is_active)
        if from_date:
            filters.append(User.created_at >= from_date)
        if to_date:
            filters.append(User.created_at <= to_date)

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        stmt = stmt.order_by(desc(User.created_at)).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total

    async def get_user_details(self, user_id: str) -> Dict[str, Any]:
        """Fetch comprehensive details for an individual user."""
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.role).selectinload(Role.permissions),
                selectinload(User.wallet),
                selectinload(User.self_exclusion),
            )
        )
        res = await self.session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            raise NotFoundException("User not found")

        perms = [p.code for p in user.role.permissions] if user.role and user.role.permissions else []

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role_id": user.role_id,
            "role": user.role.name if user.role else "USER",
            "permissions": perms,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "totp_enabled": user.totp_enabled,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat(),
            "wallet": {
                "balance": user.wallet.balance if user.wallet else 0,
                "locked_balance": user.wallet.locked_balance if user.wallet else 0,
                "available_balance": (user.wallet.balance - user.wallet.locked_balance) if user.wallet else 0,
                "currency": user.wallet.currency if user.wallet else "VIRTUAL",
                "is_frozen": user.wallet.is_frozen if user.wallet else False,
            } if user.wallet else None,
            "self_exclusion": {
                "is_active": user.self_exclusion.is_active,
                "starts_at": user.self_exclusion.starts_at.isoformat(),
                "ends_at": user.self_exclusion.ends_at.isoformat(),
                "reason": user.self_exclusion.reason,
            } if user.self_exclusion and user.self_exclusion.is_active else None,
        }

    async def set_user_status(
        self,
        actor_id: str,
        target_user_id: str,
        is_active: bool,
        reason: str,
        ip_address: Optional[str] = None,
    ) -> User:
        """Activate or deactivate user account with audit trail."""
        user = await self.user_repo.get_by_id(target_user_id)
        if not user:
            raise NotFoundException("Target user not found")

        if not reason.strip():
            raise BadRequestException("Reason is required to change user status")

        before_status = user.is_active
        user.is_active = is_active
        await self.session.flush()

        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="SET_USER_STATUS",
            target_type="USER",
            target_id=target_user_id,
            details={
                "before": {"is_active": before_status},
                "after": {"is_active": is_active},
                "reason": reason,
            },
            ip_address=ip_address,
        )
        return user

    async def get_user_wallet(self, user_id: str) -> Dict[str, Any]:
        """Fetch wallet balances and details for a user."""
        stmt = select(Wallet).where(Wallet.user_id == user_id)
        res = await self.session.execute(stmt)
        wallet = res.scalar_one_or_none()
        if not wallet:
            raise NotFoundException("Wallet not found for this user")
        return {
            "id": wallet.id,
            "user_id": wallet.user_id,
            "balance": wallet.balance,
            "locked_balance": wallet.locked_balance,
            "available_balance": wallet.balance - wallet.locked_balance,
            "currency": wallet.currency,
            "is_frozen": wallet.is_frozen,
            "updated_at": wallet.updated_at.isoformat(),
        }

    async def get_user_history(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch user gameplay entry records."""
        from app.services.game_service import GameService
        svc = GameService(self.session)
        entries, total = await svc.get_user_entries(user_id=user_id, limit=limit, offset=offset)
        items = [
            {
                "entry_id": e.id,
                "round_id": e.round_id,
                "game_id": e.round.game_id if e.round else None,
                "round_no": e.round.round_no if e.round else None,
                "bet_amount": e.bet_amount,
                "payout_amount": e.payout_amount,
                "status": e.status,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ]
        return items, total

    async def get_user_transactions(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch user wallet ledger transaction rows."""
        stmt = (
            select(WalletTransaction)
            .join(Wallet, WalletTransaction.wallet_id == Wallet.id)
            .where(Wallet.user_id == user_id)
        )
        count_stmt = (
            select(func.count(WalletTransaction.id))
            .join(Wallet, WalletTransaction.wallet_id == Wallet.id)
            .where(Wallet.user_id == user_id)
        )
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        stmt = stmt.order_by(desc(WalletTransaction.created_at)).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        txs = res.scalars().all()
        items = [
            {
                "id": t.id,
                "wallet_id": t.wallet_id,
                "type": t.type,
                "amount": t.amount,
                "balance_before": t.balance_before,
                "balance_after": t.balance_after,
                "status": t.status,
                "reference": t.reference,
                "description": t.description,
                "idempotency_key": t.idempotency_key,
                "created_at": t.created_at.isoformat(),
            }
            for t in txs
        ]
        return items, total

    async def adjust_user_balance(
        self,
        actor_id: str,
        target_user_id: str,
        amount: int,
        reason: str,
        idempotency_key: str,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Manually adjust user wallet credits with reason and audit log."""
        if not reason or not reason.strip():
            raise BadRequestException("Reason is strictly required for manual balance adjustments")

        existing = (
            await self.session.execute(
                select(WalletTransaction).where(
                    WalletTransaction.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
        if existing:
            if (
                existing.amount != amount
                or existing.reference != f"ADMIN:{actor_id}"
                or existing.description != reason
            ):
                raise IdempotencyException(
                    "Idempotency key was already used for a different wallet adjustment"
                )
            wallet = (
                await self.session.execute(
                    select(Wallet).where(Wallet.id == existing.wallet_id)
                )
            ).scalar_one()
            if wallet.user_id != target_user_id:
                raise IdempotencyException(
                    "Idempotency key was already used for a different wallet adjustment"
                )
            return {
                "transaction_id": existing.id,
                "new_balance": existing.balance_after,
            }

        res = await self.wallet_svc.admin_adjust(
            actor_id=actor_id,
            target_user_id=target_user_id,
            amount_paise=amount,
            reason=reason,
            idempotency_key=idempotency_key,
            ip_address=ip_address,
        )

        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="ADJUST_USER_BALANCE",
            target_type="WALLET",
            target_id=target_user_id,
            details={
                "amount": amount,
                "reason": reason,
                "tx_id": res.id,
                "before": {"balance": res.balance_before},
                "after": {"balance": res.balance_after},
            },
            ip_address=ip_address,
        )
        return {"transaction_id": res.id, "new_balance": res.balance_after}


    # =========================================================================
    # Games Management
    # =========================================================================

    async def list_all_games(self) -> List[Dict[str, Any]]:
        """List all platform games with current settings and active state."""
        games = await self.game_repo.list_all()
        return [
            {
                "id": g.id,
                "name": g.name,
                "type": g.type,
                "description": g.description,
                "is_active": g.is_active,
                "min_bet": g.settings.min_bet if g.settings else 100,
                "max_bet": g.settings.max_bet if g.settings else 100000,
                "house_edge_percent": g.settings.house_edge_percent if g.settings else 300,
                "config": g.settings.config if g.settings else {},
            }
            for g in games
        ]

    async def set_game_status(
        self,
        actor_id: str,
        game_id: str,
        is_active: bool,
        ip_address: Optional[str] = None,
    ) -> Game:
        """Enable or disable a game with audit log."""
        game = await self.game_repo.get_by_id(game_id)
        if not game:
            raise NotFoundException(f"Game '{game_id}' not found")

        before_status = game.is_active
        game.is_active = is_active
        await self.session.flush()

        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="SET_GAME_STATUS",
            target_type="GAME",
            target_id=game_id,
            details={"before": {"is_active": before_status}, "after": {"is_active": is_active}},
            ip_address=ip_address,
        )
        return game

    async def get_game_settings(self, game_id: str) -> Dict[str, Any]:
        """Fetch game configuration and limits."""
        game = await self.game_repo.get_by_id(game_id)
        if not game:
            raise NotFoundException(f"Game '{game_id}' not found")
        settings = game.settings
        return {
            "game_id": game.id,
            "name": game.name,
            "is_active": game.is_active,
            "min_bet": settings.min_bet if settings else 100,
            "max_bet": settings.max_bet if settings else 100000,
            "house_edge_percent": settings.house_edge_percent if settings else 300,
            "config": settings.config if settings else {},
        }

    async def update_game_settings(
        self,
        actor_id: str,
        game_id: str,
        min_bet: Optional[int] = None,
        max_bet: Optional[int] = None,
        house_edge_percent: Optional[int] = None,
        config: Optional[dict] = None,
        is_active: Optional[bool] = None,
        ip_address: Optional[str] = None,
    ) -> GameSetting:
        """Update game settings with input validation and before/after audit log."""
        game = await self.game_repo.get_by_id(game_id)
        if not game:
            raise NotFoundException(f"Game '{game_id}' not found")

        current_settings = game.settings
        if not current_settings:
            raise NotFoundException(f"Settings for '{game_id}' not found")

        # Validation
        effective_min = min_bet if min_bet is not None else current_settings.min_bet
        effective_max = max_bet if max_bet is not None else current_settings.max_bet
        if effective_min <= 0:
            raise BadRequestException("Minimum bet must be greater than 0")
        if effective_max < effective_min:
            raise BadRequestException("Maximum bet cannot be less than minimum bet")
        if effective_max > MAX_SINGLE_TRANSACTION_PAISE:
            raise BadRequestException("Maximum bet exceeds the wallet transaction limit")
        if house_edge_percent is not None and not (0 <= house_edge_percent <= 5000):
            raise BadRequestException("House edge must be between 0 and 5000 basis points (0-50%)")
        effective_config = dict(current_settings.config or {})
        effective_config.update(config or {})
        try:
            if game_id == "aviator":
                duration = float(effective_config.get("betting_duration_sec", 6))
                rate = float(effective_config.get("growth_rate", 0.08))
                power = float(effective_config.get("growth_power", 1.3))
                from app.games.aviator.rules import DEFAULT_EXP_GROWTH_RATE

                exp_rate = float(effective_config.get("exp_growth_rate", DEFAULT_EXP_GROWTH_RATE))
                if effective_config.get("growth_model", "exponential") not in ("exponential", "power"):
                    raise ValueError("growth_model must be exponential or power")
                if not math.isfinite(exp_rate) or not 0 < exp_rate <= 10:
                    raise ValueError("exp_growth_rate must be between 0 and 10")
                if (
                    not all(map(math.isfinite, (duration, rate, power)))
                    or not 0 < duration <= 300
                    or not 0 < rate <= 10
                    or not 0 < power <= 10
                ):
                    raise ValueError("Aviator betting duration and growth settings are invalid")
            elif game_id == "color":
                from app.games.color.rules import (
                    ColourResult,
                    configured_payout_x100,
                    round_timing_seconds,
                )

                round_timing_seconds(effective_config)
                multipliers = effective_config.get("payout_multipliers", {})
                if not isinstance(multipliers, dict):
                    raise ValueError("Color payout_multipliers must be an object")
                if set(multipliers) - {colour.value for colour in ColourResult}:
                    raise ValueError("Color payout_multipliers has an unknown color")
                for colour in ColourResult:
                    configured_payout_x100(colour, multipliers)
            elif game_id == "teen_patti":
                from app.games.teen_patti.rules import payout_from_config

                payout_from_config(effective_config)
            elif game_id.startswith("wingo_"):
                from app.games.wingo.rules import payouts_from_config

                payouts_from_config(effective_config)
            elif game_id == "cricket":
                odds = effective_config.get("winner_odds_bp", {})
                if not isinstance(odds, dict):
                    raise ValueError("Cricket winner_odds_bp must be an object")
                values = list(odds.values()) + [
                    effective_config.get("home_odds_bp", 200),
                    effective_config.get("away_odds_bp", 200),
                ]
                if any(
                    not isinstance(value, int) or not 100 <= value <= 100_000
                    for value in values
                ):
                    raise ValueError("Cricket winner odds must be integer basis points in 100..100000")
        except (TypeError, ValueError, OverflowError) as exc:
            raise BadRequestException(str(exc)) from exc

        # Snapshot before state
        before_state = {
            "min_bet": current_settings.min_bet,
            "max_bet": current_settings.max_bet,
            "house_edge_percent": current_settings.house_edge_percent,
            "config": current_settings.config,
            "is_active": game.is_active,
        }

        # Apply updates
        if min_bet is not None:
            current_settings.min_bet = min_bet
        if max_bet is not None:
            current_settings.max_bet = max_bet
        if house_edge_percent is not None:
            current_settings.house_edge_percent = house_edge_percent
        if config is not None:
            # Merge or overwrite config
            merged_config = dict(current_settings.config or {})
            merged_config.update(config)
            current_settings.config = merged_config
        if is_active is not None:
            game.is_active = is_active

        await self.session.flush()

        # Snapshot after state
        after_state = {
            "min_bet": current_settings.min_bet,
            "max_bet": current_settings.max_bet,
            "house_edge_percent": current_settings.house_edge_percent,
            "config": current_settings.config,
            "is_active": game.is_active,
        }

        # Write audit log with before/after diff
        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="UPDATE_GAME_SETTINGS",
            target_type="GAME",
            target_id=game_id,
            details={"before": before_state, "after": after_state},
            ip_address=ip_address,
        )
        return current_settings

    # =========================================================================
    # Live Games & Rounds
    # =========================================================================

    async def get_live_rounds(self) -> List[Dict[str, Any]]:
        """List currently active game rounds across all games with player counts."""
        live_statuses = [
            "SCHEDULED",
            "BETTING",
            "BETTING_OPEN",
            "CREATED",
            "OPEN",
            "LOCKED",
            "RUNNING",
            "CRASHED",
            "SETTLING",
            "RESULT",
            "SETTLED",
            "WAITING",
        ]
        stmt = (
            select(GameRound)
            .where(GameRound.status.in_(live_statuses))
            .options(selectinload(GameRound.entries))
            .order_by(desc(GameRound.started_at))
        )
        res = await self.session.execute(stmt)
        rounds = res.scalars().all()

        return [
            {
                "round_id": r.id,
                "game_id": r.game_id,
                "round_no": r.round_no,
                "status": r.status,
                "server_seed_hash": r.server_seed_hash,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "total_entries": len(r.entries),
                "total_wagered": sum(e.bet_amount for e in r.entries),
            }
            for r in rounds
        ]

    async def get_round_details(self, round_id: str) -> Dict[str, Any]:
        """Fetch detailed round metadata, players, and placed wagers."""
        stmt = (
            select(GameRound)
            .where(GameRound.id == round_id)
            .options(
                selectinload(GameRound.entries).selectinload(GameEntry.user),
                selectinload(GameRound.game_result),
            )
        )
        res = await self.session.execute(stmt)
        round_obj = res.scalar_one_or_none()
        if not round_obj:
            raise NotFoundException("Game round not found")

        entries = [
            {
                "entry_id": e.id,
                "user_id": e.user_id,
                "username": e.user.username if e.user else None,
                "bet_amount": e.bet_amount,
                "payout_amount": e.payout_amount,
                "multiplier": (e.multiplier / 100.0) if e.multiplier else None,
                "status": e.status,
                "selection": public_selection(e.selection, e.status),
                "created_at": e.created_at.isoformat(),
            }
            for e in round_obj.entries
        ]

        return {
            "round_id": round_obj.id,
            "game_id": round_obj.game_id,
            "round_no": round_obj.round_no,
            "status": round_obj.status,
            "server_seed_hash": round_obj.server_seed_hash,
            # never before the round is finished (would reveal the outcome)
            "server_seed": revealable_seed(round_obj),
            "client_seed": round_obj.client_seed,
            "result": round_obj.result,
            "started_at": round_obj.started_at.isoformat() if round_obj.started_at else None,
            "ended_at": round_obj.ended_at.isoformat() if round_obj.ended_at else None,
            "entries": entries,
            "total_bets": len(entries),
            "total_wagered": sum(e["bet_amount"] for e in entries),
            "total_payout": sum(e["payout_amount"] for e in entries),
        }

    async def list_historical_rounds(
        self,
        game_id: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch historical rounds with filtering and pagination."""
        from app.repositories.round_repo import RoundRepository
        repo = RoundRepository(self.session)
        rounds, total = await repo.list_rounds(
            game_id=game_id,
            status=status,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
            newest_first=True,
        )
        from app.games.fairness_guard import is_finished
        from app.games.simulated_players import BOT_NAMES
        from app.services.live_dashboard import _outcome_label

        # Real-player money per round (simulated lobby players excluded)
        totals: Dict[str, Tuple[int, int, int]] = {}
        round_ids = [r.id for r in rounds]
        if round_ids:
            agg = await self.session.execute(
                select(
                    GameEntry.round_id,
                    func.count(GameEntry.id),
                    func.coalesce(func.sum(GameEntry.bet_amount), 0),
                    func.coalesce(func.sum(GameEntry.payout_amount), 0),
                )
                .join(User, User.id == GameEntry.user_id)
                .where(GameEntry.round_id.in_(round_ids), User.username.not_in(BOT_NAMES))
                .group_by(GameEntry.round_id)
            )
            totals = {rid: (int(n), int(bet), int(paid)) for rid, n, bet, paid in agg.all()}

        items = []
        for r in rounds:
            finished = is_finished(r.status) or r.status == "CRASHED"
            outcome = None
            if finished:
                outcome = _outcome_label(r.game_id, (r.game_result.outcome if r.game_result else None) or r.result)
            bets, wagered, paid = totals.get(r.id, (0, 0, 0))
            if outcome is None and finished and r.game_id == "mines" and bets:
                outcome = "Cashed out" if paid > 0 else "Hit a mine"
            items.append({
                "round_id": r.id,
                "game_id": r.game_id,
                "round_no": r.round_no,
                "period": (r.result or {}).get("period"),
                "status": r.status,
                "outcome": outcome,
                "server_seed_hash": r.server_seed_hash,
                "server_seed": revealable_seed(r),
                # raw result only once final (it can hold the outcome before it is public)
                "result": r.result if finished else None,
                "bets": bets,
                "wagered": wagered,
                "paid_out": paid,
                "house_net": wagered - paid,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return items, total

    # =========================================================================
    # Roles, Permissions & Admin Management (Super Admin)
    # =========================================================================

    async def list_roles(self) -> List[Dict[str, Any]]:
        """List all platform roles and assigned permissions."""
        stmt = select(Role).options(selectinload(Role.permissions))
        res = await self.session.execute(stmt)
        roles = res.scalars().all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "permissions": [p.code for p in r.permissions],
            }
            for r in roles
        ]

    async def list_permissions(self) -> List[Dict[str, Any]]:
        """List all available platform permissions."""
        stmt = select(Permission).order_by(Permission.code)
        res = await self.session.execute(stmt)
        perms = res.scalars().all()
        return [
            {"id": p.id, "code": p.code, "name": p.name, "description": p.description}
            for p in perms
        ]

    async def create_role(
        self,
        actor_id: str,
        name: str,
        description: str,
        permission_codes: List[str],
        ip_address: Optional[str] = None,
    ) -> Role:
        """Create a new role with associated permissions."""
        name_clean = name.upper().strip()
        existing = await self.session.execute(select(Role).where(Role.name == name_clean))
        if existing.scalar_one_or_none():
            raise BadRequestException(f"Role '{name_clean}' already exists")

        role = Role(name=name_clean, description=description)
        self.session.add(role)
        await self.session.flush()

        # Associate permissions
        if permission_codes:
            perms_res = await self.session.execute(
                select(Permission).where(Permission.code.in_(permission_codes))
            )
            for p in perms_res.scalars().all():
                rp = RolePermission(role_id=role.id, permission_id=p.id)
                self.session.add(rp)
            await self.session.flush()

        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="CREATE_ROLE",
            target_type="ROLE",
            target_id=str(role.id),
            details={"name": name_clean, "permissions": permission_codes},
            ip_address=ip_address,
        )
        return role

    async def update_role_permissions(
        self,
        actor_id: str,
        role_id: int,
        permission_codes: List[str],
        ip_address: Optional[str] = None,
    ) -> Role:
        """Update permission assignments for a role with before/after audit."""
        stmt = select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
        role = (await self.session.execute(stmt)).scalar_one_or_none()
        if not role:
            raise NotFoundException(f"Role {role_id} not found")

        before_perms = [p.code for p in role.permissions]

        # Clear existing role_permissions
        del_stmt = select(RolePermission).where(RolePermission.role_id == role_id)
        existing_rp = (await self.session.execute(del_stmt)).scalars().all()
        for rp in existing_rp:
            await self.session.delete(rp)
        await self.session.flush()

        # Add new permissions
        if permission_codes:
            perms_res = await self.session.execute(
                select(Permission).where(Permission.code.in_(permission_codes))
            )
            for p in perms_res.scalars().all():
                new_rp = RolePermission(role_id=role_id, permission_id=p.id)
                self.session.add(new_rp)
            await self.session.flush()

        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="UPDATE_ROLE_PERMISSIONS",
            target_type="ROLE",
            target_id=str(role_id),
            details={"before": before_perms, "after": permission_codes},
            ip_address=ip_address,
        )
        return role

    async def list_admin_users(self) -> List[Dict[str, Any]]:
        """List administrative staff and support users."""
        # Every non-player role, including custom roles from the Roles system
        stmt = (
            select(User)
            .join(Role, User.role_id == Role.id)
            .where(Role.name != UserRole.USER.value)
            .options(selectinload(User.role))
            .order_by(User.username)
        )
        res = await self.session.execute(stmt)
        users = res.scalars().all()
        return [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "email": u.email,
                "role_id": u.role_id,
                "role": u.role.name if u.role else None,
                "is_active": u.is_active,
                "totp_enabled": u.totp_enabled,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            }
            for u in users
        ]

    async def create_admin_user(
        self,
        actor_id: str,
        username: str,
        email: str,
        password: str,
        role_name: str,
        ip_address: Optional[str] = None,
        full_name: Optional[str] = None,
    ) -> User:
        """Create staff credentials with a zero-balance wallet and immutable audit record."""
        role_name = role_name.upper()
        if role_name in {UserRole.USER.value, UserRole.SUPERADMIN.value}:
            raise BadRequestException("Choose a staff role (players and super admins cannot be created here)")

        # Login ID and email are unique case-insensitively
        if (await self.session.execute(select(User.id).where(func.lower(User.username) == username.lower()).limit(1))).scalar_one_or_none():
            raise ConflictException("This login ID is already taken")
        if (await self.session.execute(select(User.id).where(func.lower(User.email) == email.lower()).limit(1))).scalar_one_or_none():
            raise ConflictException("This email is already registered")

        role_result = await self.session.execute(
            select(Role).where(func.upper(Role.name) == role_name)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise BadRequestException(f"Role {role_name} is not configured")

        user = User(
            username=username,
            full_name=(full_name or "").strip() or None,
            email=email.lower(),
            # Argon2id hash — the plaintext password is never stored
            password_hash=hash_password(password),
            role_id=role.id,
            role=role,
            is_active=True,
            is_verified=True,
            totp_enabled=False,
        )
        self.session.add(user)
        await self.session.flush()

        wallet = Wallet(
            user_id=user.id,
            balance=0,
            locked_balance=0,
            currency="VIRTUAL",
            is_frozen=False,
        )
        self.session.add(wallet)
        await self.session.flush()

        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="CREATE_ADMIN_USER",
            target_type="USER",
            target_id=user.id,
            details={"username": username, "full_name": user.full_name, "email": user.email, "role": role_name},
            ip_address=ip_address,
        )
        return user

    async def assign_user_role(
        self,
        actor_id: str,
        target_user_id: str,
        role_id: int,
        ip_address: Optional[str] = None,
    ) -> User:
        """Assign/promote user to a specific role with audit log."""
        user = await self.user_repo.get_by_id(target_user_id)
        if not user:
            raise NotFoundException("User not found")

        role = await self.session.get(Role, role_id)
        if not role:
            raise NotFoundException("Target role not found")
        from app.core.config import get_settings

        if (
            get_settings().admin_2fa_required
            and role.name.upper() in {"ADMIN", "SUPERADMIN"}
            and not user.totp_enabled
        ):
            raise BadRequestException(
                "Enable two-factor authentication before assigning an administrator role"
            )

        before_role_id = user.role_id
        user.role_id = role_id
        await self.session.flush()

        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="ASSIGN_USER_ROLE",
            target_type="USER",
            target_id=target_user_id,
            details={
                "before": {"role_id": before_role_id},
                "after": {"role_id": role_id, "role_name": role.name},
            },
            ip_address=ip_address,
        )
        return user

    # =========================================================================
    # Support Administration
    # =========================================================================

    async def list_support_tickets(
        self,
        status: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch all tickets for staff review with filtering."""
        stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.user), selectinload(SupportTicket.assigned_to))
        )
        count_stmt = select(func.count(SupportTicket.id))

        filters = []
        if status:
            filters.append(SupportTicket.status == status)
        if assigned_to_id:
            filters.append(SupportTicket.assigned_to_id == assigned_to_id)
        if priority:
            filters.append(SupportTicket.priority == priority)

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        stmt = stmt.order_by(desc(SupportTicket.created_at)).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        tickets = res.scalars().all()
        items = [
            {
                "id": t.id,
                "user_id": t.user_id,
                "username": t.user.username if t.user else None,
                "subject": t.subject,
                "status": t.status,
                "priority": t.priority,
                "assigned_to_id": t.assigned_to_id,
                "assigned_to_name": t.assigned_to.username if t.assigned_to else None,
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in tickets
        ]
        return items, total

    async def get_admin_ticket_details(self, ticket_id: str) -> Dict[str, Any]:
        """Fetch ticket with all messages including internal staff notes."""
        from app.services.support_service import SupportService
        svc = SupportService(self.session)
        ticket = await svc.get_ticket(ticket_id)
        return {
            "id": ticket.id,
            "user_id": ticket.user_id,
            "username": ticket.user.username if ticket.user else None,
            "subject": ticket.subject,
            "status": ticket.status,
            "priority": ticket.priority,
            "assigned_to_id": ticket.assigned_to_id,
            "assigned_to_name": ticket.assigned_to.username if ticket.assigned_to else None,
            "created_at": ticket.created_at.isoformat(),
            "messages": [
                {
                    "id": m.id,
                    "sender_id": m.sender_id,
                    "sender_name": m.sender.username if m.sender else "Staff",
                    "message": m.message,
                    "is_internal": m.is_internal,
                    "created_at": m.created_at.isoformat(),
                }
                for m in ticket.messages
            ],
        }

    async def admin_reply_ticket(
        self,
        actor_id: str,
        ticket_id: str,
        message: str,
        is_internal: bool = False,
        ip_address: Optional[str] = None,
    ) -> SupportMessage:
        """Staff reply to a ticket (optional internal note) with audit log."""
        from app.services.support_service import SupportService
        svc = SupportService(self.session)
        msg = await svc.reply_ticket(
            ticket_id=ticket_id,
            sender_id=actor_id,
            message=message,
            is_internal=is_internal,
        )
        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="REPLY_TICKET",
            target_type="TICKET",
            target_id=ticket_id,
            details={"is_internal": is_internal, "message_id": msg.id},
            ip_address=ip_address,
        )
        return msg

    async def assign_ticket(
        self,
        actor_id: str,
        ticket_id: str,
        assigned_to_id: Optional[str],
        ip_address: Optional[str] = None,
    ) -> SupportTicket:
        """Assign or reassign ticket to a staff member with audit log."""
        from app.services.support_service import SupportService
        svc = SupportService(self.session)
        ticket = await svc.get_ticket(ticket_id)
        before_assignee = ticket.assigned_to_id
        ticket.assigned_to_id = assigned_to_id
        await self.session.flush()

        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="ASSIGN_TICKET",
            target_type="TICKET",
            target_id=ticket_id,
            details={"before": before_assignee, "after": assigned_to_id},
            ip_address=ip_address,
        )
        return ticket

    async def update_ticket_status(
        self,
        actor_id: str,
        ticket_id: str,
        status: str,
        ip_address: Optional[str] = None,
    ) -> SupportTicket:
        """Update ticket resolution status with audit log."""
        from app.services.support_service import SupportService
        svc = SupportService(self.session)
        ticket = await svc.get_ticket(ticket_id)
        before_status = ticket.status
        ticket.status = status
        await self.session.flush()

        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="UPDATE_TICKET_STATUS",
            target_type="TICKET",
            target_id=ticket_id,
            details={"before": before_status, "after": status},
            ip_address=ip_address,
        )
        return ticket

    # =========================================================================
    # Notifications Broadcast & Reports
    # =========================================================================

    async def broadcast_notification(
        self,
        actor_id: str,
        title: str,
        message: str,
        notification_type: str = "SYSTEM",
        role_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> int:
        """Deliver system notification to users and record an audit entry."""
        stmt = select(User.id).where(User.is_active == True)  # noqa: E712
        if role_id is not None:
            stmt = stmt.where(User.role_id == role_id)
        res = await self.session.execute(stmt)
        user_ids = res.scalars().all()

        notif_svc = NotificationService(self.session)
        notifications = [
            Notification(
                user_id=uid,
                title=title,
                message=message,
                type=notification_type,
                is_read=False,
            )
            for uid in user_ids
        ]
        self.session.add_all(notifications)
        await self.session.flush()
        for notification in notifications:
            await notif_svc._push_ws_notification(notification.user_id, notification)
        count = len(notifications)

        await self.audit_repo.create_log(
            actor_id=actor_id,
            action="BROADCAST_NOTIFICATION",
            target_type="NOTIFICATION",
            target_id=None,
            details={"title": title, "count": count, "role_id": role_id},
            ip_address=ip_address,
        )
        return count

    async def export_report_csv(
        self,
        report_type: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> str:
        """Export platform records as CSV string."""
        if from_date and to_date and from_date > to_date:
            raise BadRequestException("from_date must be earlier than or equal to to_date")
        output = io.StringIO()
        writer = csv.writer(output)

        rep_clean = report_type.lower()
        if rep_clean not in {"transactions", "bets", "wagers", "users"}:
            raise BadRequestException("report_type must be transactions, bets, or users")
        if rep_clean == "transactions":
            writer.writerow(["id", "wallet_id", "type", "amount_paise", "balance_after", "status", "created_at"])
            stmt = select(WalletTransaction)
            if from_date:
                stmt = stmt.where(WalletTransaction.created_at >= from_date)
            if to_date:
                stmt = stmt.where(WalletTransaction.created_at <= to_date)
            stmt = stmt.order_by(desc(WalletTransaction.created_at)).limit(1000)
            res = await self.session.execute(stmt)
            for t in res.scalars().all():
                writer.writerow([t.id, t.wallet_id, t.type, t.amount, t.balance_after, t.status, t.created_at.isoformat()])

        elif rep_clean in ("bets", "wagers"):
            writer.writerow(["id", "user_id", "round_id", "bet_amount_paise", "payout_paise", "status", "created_at"])
            stmt = select(GameEntry)
            if from_date:
                stmt = stmt.where(GameEntry.created_at >= from_date)
            if to_date:
                stmt = stmt.where(GameEntry.created_at <= to_date)
            stmt = stmt.order_by(desc(GameEntry.created_at)).limit(1000)
            res = await self.session.execute(stmt)
            for e in res.scalars().all():
                writer.writerow([e.id, e.user_id, e.round_id, e.bet_amount, e.payout_amount, e.status, e.created_at.isoformat()])

        else:
            writer.writerow(["id", "username", "email", "role_id", "is_active", "created_at"])
            stmt = select(User)
            if from_date:
                stmt = stmt.where(User.created_at >= from_date)
            if to_date:
                stmt = stmt.where(User.created_at <= to_date)
            stmt = stmt.order_by(desc(User.created_at)).limit(1000)
            res = await self.session.execute(stmt)
            for u in res.scalars().all():
                writer.writerow([u.id, u.username, u.email, u.role_id, u.is_active, u.created_at.isoformat()])

        return output.getvalue()

    async def get_audit_logs(
        self,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        target_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Tuple[List[AuditLog], int]:
        """Query platform audit log trail (read-only)."""
        return await self.audit_repo.list_logs(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            limit=limit,
            offset=offset,
            search=search,
            from_date=from_date,
            to_date=to_date,
        )
