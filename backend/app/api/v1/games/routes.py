"""API v1 routes for platform games, bets, rounds, and outcomes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import ForbiddenException
from app.core.exceptions import BadRequestException
from app.core.redis import get_redis_client
from app.games.aviator.schemas import (
    AviatorActionRequest,
    AviatorBetRequest,
    AviatorBetResponse,
    AviatorCashoutRequest,
    AviatorCashoutResponse,
)
from app.games.aviator.service import AviatorService
from app.games.color.schemas import ColorActionRequest, ColorBetRequest, ColorBetResponse
from app.games.color.service import ColorService
from app.games.wingo.rules import MODES as WINGO_MODES
from app.games.wingo.service import WingoBetRequest, WingoBetResponse, WingoService
from app.games.teen_patti.service import TeenPattiBetRequest, TeenPattiBetResponse, TeenPattiService
from app.games.cricket.schemas import CricketPredictionRequest
from app.games.cricket.market_service import CricketMarketService, get_cricket_provider
from app.games.mines.schemas import (
    MinesActionRequest,
    MinesCashoutRequest,
    MinesRevealRequest,
    MinesSessionResponse,
    MinesStartRequest,
)
from app.games.mines.service import MinesService
from app.models.user import User
from app.services.game_service import GameService
from app.services.responsible_play_service import ResponsiblePlayService
from app.utils.idempotency import check_idempotency, store_idempotency_result

router = APIRouter(prefix="/games", tags=["Games"])


async def _check_self_exclusion(db: AsyncSession, user_id: str, role: Optional[str] = None) -> None:
    """Ensure betting is allowed: platform not in maintenance, user not self-excluded."""
    from app.services.platform_settings import ensure_betting_open

    await ensure_betting_open(db, role)
    resp_svc = ResponsiblePlayService(db)
    exclusion = await resp_svc.get_active_exclusion(user_id)
    if exclusion:
        raise ForbiddenException(
            f"Wagering blocked: Active self-exclusion until {exclusion.ends_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )


# ==========================================
# Game Catalog & History (Public)
# ==========================================


@router.get("", response_model=List[Dict[str, Any]])
async def list_games(db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """List all available games on the platform with limits and house edge."""
    svc = GameService(db)
    games = await svc.list_games()
    return [
        {
            "id": g.id,
            "name": g.name,
            "type": g.type,
            "description": g.description,
            "is_active": g.is_active,
            "min_bet": g.settings.min_bet if g.settings else 100,
            "max_bet": g.settings.max_bet if g.settings else 100000,
            "house_edge_percent": (g.settings.house_edge_percent / 100.0) if g.settings else 3.0,
        }
        for g in games
    ]


@router.get("/live/players")
async def live_players(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Real players active in each lobby game over the last few minutes (bots and staff excluded)."""
    from app.services.live_players import live_player_counts

    return await live_player_counts(db)


@router.get("/{game_id}")
async def get_game_details(
    game_id: str, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Fetch details and configuration for a specific game."""
    svc = GameService(db)
    g = await svc.get_game(game_id)
    return {
        "id": g.id,
        "name": g.name,
        "type": g.type,
        "description": g.description,
        "is_active": g.is_active,
        "min_bet": g.settings.min_bet if g.settings else 100,
        "max_bet": g.settings.max_bet if g.settings else 100000,
        "house_edge_percent": (g.settings.house_edge_percent / 100.0) if g.settings else 3.0,
    }


@router.get("/{game_id}/round")
async def get_current_round(
    game_id: str, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Fetch the active or scheduled round for a game (including public server_seed_hash)."""
    svc = GameService(db)
    round_obj = await svc.get_current_round(game_id)
    if not round_obj:
        return {"active": False, "message": "No round currently active"}

    return {
        "active": True,
        "round_id": round_obj.id,
        "round_no": round_obj.round_no,
        "status": round_obj.status,
        "server_seed_hash": round_obj.server_seed_hash,
        "started_at": round_obj.started_at.isoformat() if round_obj.started_at else None,
    }


@router.get("/{game_id}/rounds")
async def list_game_rounds(
    game_id: str,
    status: Optional[str] = Query(None, description="Optional round status filter"),
    from_date: Optional[datetime] = Query(None, description="Filter rounds from ISO timestamp"),
    to_date: Optional[datetime] = Query(None, description="Filter rounds up to ISO timestamp"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Fetch paginated game rounds with optional date and status filters."""
    svc = GameService(db)
    offset = (page - 1) * page_size
    rounds, total = await svc.list_game_rounds(
        game_id=game_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
        limit=page_size,
        offset=offset,
    )
    items = [
        {
            "id": r.id,
            "round_no": r.round_no,
            "game_id": r.game_id,
            "status": r.status,
            "server_seed_hash": r.server_seed_hash,
            "server_seed": r.server_seed if r.status in ("COMPLETED", "HISTORY") else None,
            "result": r.result,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in rounds
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/{game_id}/history")
async def get_game_round_history(
    game_id: str,
    status: Optional[str] = Query(None, description="Status filter (defaults to COMPLETED)"),
    from_date: Optional[datetime] = Query(None, description="Filter from ISO timestamp"),
    to_date: Optional[datetime] = Query(None, description="Filter to ISO timestamp"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    limit: Optional[int] = Query(None, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Fetch completed rounds with revealed seeds and outcomes (filter by date/status, paginated)."""
    svc = GameService(db)
    if limit is not None and status is None and from_date is None and to_date is None:
        return await svc.get_recent_history(game_id, limit=limit)

    offset = (page - 1) * page_size
    items, total = await svc.get_game_history_paginated(
        game_id=game_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
        limit=page_size,
        offset=offset,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


# ==========================================
# Aviator Endpoints
# ==========================================


@router.post(
    "/aviator/action",
    response_model=Union[AviatorBetResponse, AviatorCashoutResponse],
)
async def aviator_action(
    payload: AviatorActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
) -> Union[AviatorBetResponse, AviatorCashoutResponse]:
    """Place a wager or cash out using the required idempotency key."""
    service = AviatorService(db, redis=get_redis_client())
    if payload.action == "bet":
        if payload.amount is None:
            raise BadRequestException("amount is required for a bet action")
        await _check_self_exclusion(db, current_user.id, getattr(current_user, "role", None))
        result = await service.place_bet(
            user_id=current_user.id,
            round_id=payload.round_id,
            amount=payload.amount,
            auto_cashout=payload.auto_cashout,
            idempotency_key=idempotency_key,
        )
    else:
        if not payload.entry_id:
            raise BadRequestException("entry_id is required for a cashout action")
        result = await service.cashout(
            user_id=current_user.id,
            round_id=payload.round_id,
            entry_id=payload.entry_id,
            idempotency_key=idempotency_key,
        )
    return result


@router.post("/aviator/bet", response_model=AviatorBetResponse)
async def place_aviator_bet(
    payload: AviatorBetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
) -> AviatorBetResponse:
    """Place a wager on the active Aviator round."""
    await _check_self_exclusion(db, current_user.id, getattr(current_user, "role", None))
    svc = AviatorService(db, redis=get_redis_client())
    key = idempotency_key
    res = await svc.place_bet(
        user_id=current_user.id,
        round_id=payload.round_id,
        amount=payload.amount,
        auto_cashout=payload.auto_cashout,
        idempotency_key=key,
    )
    await db.commit()
    return res


@router.post("/aviator/cashout", response_model=AviatorCashoutResponse)
async def cashout_aviator_bet(
    payload: AviatorCashoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
) -> AviatorCashoutResponse:
    """Cash out using the server's current round time and multiplier."""
    svc = AviatorService(db, redis=get_redis_client())
    res = await svc.cashout(
        user_id=current_user.id,
        round_id=payload.round_id,
        entry_id=payload.entry_id,
        idempotency_key=idempotency_key,
    )
    await db.commit()
    return res


# ==========================================
# Color Prediction Endpoints
# ==========================================


@router.get("/wingo/modes")
async def list_wingo_modes() -> List[Dict[str, Any]]:
    """WinGo modes with their period length and betting lock window."""
    return [
        {"game_id": game_id, "label": label, "duration": duration, "lock_seconds": lock}
        for game_id, (duration, lock, label, _code) in WINGO_MODES.items()
    ]


@router.post("/wingo/action", response_model=WingoBetResponse)
async def wingo_action(
    payload: WingoBetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=100),
) -> WingoBetResponse:
    """Place a WinGo bet on a colour, a number (0-9) or Big/Small."""
    await _check_self_exclusion(db, current_user.id, getattr(current_user, "role", None))
    return await WingoService(db, redis=get_redis_client()).place_bet(
        current_user.id, payload, idempotency_key
    )


@router.post("/teen-patti/action", response_model=TeenPattiBetResponse)
async def teen_patti_action(
    payload: TeenPattiBetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=100),
) -> TeenPattiBetResponse:
    """Place a Teen Patti bet on Player A or Player B."""
    await _check_self_exclusion(db, current_user.id, getattr(current_user, "role", None))
    return await TeenPattiService(db, redis=get_redis_client()).place_bet(
        current_user.id, payload, idempotency_key
    )


@router.post("/color/action", response_model=ColorBetResponse)
async def color_action(
    payload: ColorActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
) -> ColorBetResponse:
    """Place a color prediction bet using the required idempotency key."""
    await _check_self_exclusion(db, current_user.id, getattr(current_user, "role", None))
    service = ColorService(db, redis=get_redis_client())
    result = await service.place_bet(
        user_id=current_user.id,
        round_id=payload.round_id,
        amount=payload.amount,
        colour=payload.colour,
        idempotency_key=idempotency_key,
    )
    return result


@router.post("/color/bet", response_model=ColorBetResponse)
async def place_color_bet(
    payload: ColorBetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
) -> ColorBetResponse:
    """Place a wager on the upcoming Color Prediction wheel spin."""
    await _check_self_exclusion(db, current_user.id, getattr(current_user, "role", None))
    svc = ColorService(db, redis=get_redis_client())
    key = idempotency_key
    res = await svc.place_bet(
        user_id=current_user.id,
        round_id=payload.round_id,
        amount=payload.amount,
        colour=payload.colour,
        idempotency_key=key,
    )
    await db.commit()
    return res


# ==========================================
# Mines (Solo Game) Endpoints
# ==========================================

@router.get("/mines/active", response_model=Optional[MinesSessionResponse])
async def get_active_mines_game(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[MinesSessionResponse]:
    """Return the player's in-progress Mines game (to resume after a reload), or null."""
    service = MinesService(db, redis=get_redis_client())
    entry = await service.get_active_session(current_user.id)
    if entry is None:
        return None
    return await service._response_for_entry(entry)


@router.post("/mines/action", response_model=MinesSessionResponse)
async def mines_action(
    payload: MinesActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
) -> MinesSessionResponse:
    """Run one server-validated Mines action with an idempotency key."""
    service = MinesService(db, redis=get_redis_client())
    if payload.action == "start":
        if payload.bet_amount is None or payload.mine_count is None:
            raise BadRequestException("bet_amount and mine_count are required to start")
        await _check_self_exclusion(db, current_user.id, getattr(current_user, "role", None))
        response = await service.start_game(
            user_id=current_user.id,
            bet_amount=payload.bet_amount,
            mine_count=payload.mine_count,
            client_seed=payload.client_seed,
            idempotency_key=idempotency_key,
        )
        await db.commit()
        return response

    action_payload = payload.model_dump(exclude_none=True)
    cache_key = f"mines-action:{current_user.id}:{idempotency_key}"
    cached = await check_idempotency(cache_key, action_payload)
    if cached is not None:
        return MinesSessionResponse(**cached)

    if payload.action == "reveal":
        if payload.tile_index is None:
            raise BadRequestException("tile_index is required to reveal")
        response = await service.reveal_tile(current_user.id, payload.tile_index)
    else:
        response = await service.cashout(current_user.id)
    await db.commit()
    await store_idempotency_result(cache_key, action_payload, response.model_dump())
    return response


@router.post("/mines/start", response_model=MinesSessionResponse)
async def start_mines_game(
    payload: MinesStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
) -> MinesSessionResponse:
    """Start a new solo Mines game session with provably fair commitment."""
    return await mines_action(
        MinesActionRequest(
            action="start",
            bet_amount=payload.bet_amount,
            mine_count=payload.mine_count,
            client_seed=payload.client_seed,
        ),
        current_user,
        db,
        idempotency_key,
    )


@router.post("/mines/reveal", response_model=MinesSessionResponse)
async def reveal_mines_tile(
    payload: MinesRevealRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
) -> MinesSessionResponse:
    """Reveal a tile in the player's active Mines game."""
    return await mines_action(
        MinesActionRequest(action="reveal", tile_index=payload.tile_index),
        current_user,
        db,
        idempotency_key,
    )


@router.post("/mines/cashout", response_model=MinesSessionResponse)
async def cashout_mines_game(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
) -> MinesSessionResponse:
    """Cash out accumulated winnings from the active Mines game."""
    return await mines_action(
        MinesActionRequest(action="cashout"),
        current_user,
        db,
        idempotency_key,
    )


def _cricket_market_service(db: AsyncSession) -> CricketMarketService:
    return CricketMarketService(
        db,
        provider=get_cricket_provider(),
        redis=get_redis_client(),
    )


def _cricket_match_payload(match, odds: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    return {
        "odds": {side: value / 100 for side, value in (odds or {}).items()},
        "match_id": match.id,
        "home_team": match.home_team,
        "away_team": match.away_team,
        "status": match.status,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "winner": match.winner,
        "abandoned": match.abandoned,
        "metadata": match.metadata_json,
    }


@router.get("/cricket/matches")
async def list_cricket_matches(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    service = _cricket_market_service(db)
    matches = await service.list_matches()
    from app.core.config import get_settings as _settings

    return {
        "source": "cricapi" if _settings().CRICAPI_KEY else "simulated",
        "items": [
            _cricket_match_payload(match, await service.winner_odds(match.home_team, match.away_team))
            for match in matches
        ]
    }


@router.get("/cricket/predictions/me")
async def list_my_cricket_predictions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """The player's most recent winner predictions with their match outcome."""
    rows = await _cricket_market_service(db).list_user_predictions(current_user.id)
    return {
        "items": [
            {
                "prediction_id": prediction.id,
                "match_id": prediction.match_id,
                "selection": prediction.selection,
                "team": match.home_team if prediction.selection == "HOME" else match.away_team,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "stake": prediction.stake,
                "odds": prediction.odds_bp / 100,
                "payout": prediction.payout,
                "status": prediction.status,
                "match_status": match.status,
                "winner": match.winner,
                "created_at": prediction.created_at.isoformat() if prediction.created_at else None,
            }
            for prediction, match in rows
        ]
    }


@router.get("/cricket/matches/{match_id}")
async def get_cricket_match(
    match_id: str, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    service = _cricket_market_service(db)
    match = await service.get_match(match_id)
    return _cricket_match_payload(match, await service.winner_odds(match.home_team, match.away_team))


@router.get("/cricket/matches/{match_id}/live-score")
async def get_cricket_live_score(
    match_id: str, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    match = await _cricket_market_service(db).get_match(match_id)
    return {
        "match_id": match.id,
        "status": match.status,
        "home_team": match.home_team,
        "home_score": match.home_score,
        "away_team": match.away_team,
        "away_score": match.away_score,
    }


@router.post("/cricket/predictions")
async def place_cricket_winner_prediction(
    payload: CricketPredictionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
) -> Dict[str, Any]:
    await _check_self_exclusion(db, current_user.id, getattr(current_user, "role", None))
    prediction = await _cricket_market_service(db).place_prediction(
        user_id=current_user.id,
        match_id=payload.match_id,
        selection=payload.selection,
        stake=payload.stake,
        idempotency_key=idempotency_key,
    )
    return {
        "prediction_id": prediction.id,
        "match_id": prediction.match_id,
        "selection": prediction.selection,
        "stake": prediction.stake,
        "odds_bp": prediction.odds_bp,
        "status": prediction.status,
    }
