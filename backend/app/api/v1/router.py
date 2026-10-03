"""Central API v1 router definition mounting all platform modules."""

from fastapi import APIRouter

from app.api.v1.admin.routes import router as admin_router
from app.api.v1.admin.superadmin import public_router as system_router
from app.api.v1.admin.superadmin import router as superadmin_router
from app.api.v1.auth.routes import router as auth_router
from app.api.v1.fairness.router import router as fairness_router
from app.api.v1.games.routes import router as games_router
from app.api.v1.health import router as health_router
from app.api.v1.history.routes import router as history_router
from app.api.v1.leaderboard.router import router as leaderboard_router
from app.api.v1.notifications.router import router as notifications_router
from app.api.v1.payments.admin import router as admin_payments_router
from app.api.v1.payments.router import router as payments_router
from app.api.v1.responsible_play.router import router as responsible_play_router
from app.api.v1.risk.router import router as risk_router
from app.api.v1.support.routes import router as support_router
from app.api.v1.users.routes import router as users_router
from app.api.v1.wallet.router import router as wallet_router

api_router = APIRouter()

# Health checks
api_router.include_router(health_router, prefix="", tags=["Health"])

# Authentication & session management
api_router.include_router(auth_router)

# Virtual credit wallet & ledger
api_router.include_router(wallet_router)

# Deposits, withdrawals, payout accounts, provider webhook
api_router.include_router(payments_router)
api_router.include_router(admin_payments_router)

# Provably Fair verification
api_router.include_router(fairness_router)

# Games & betting
api_router.include_router(games_router)

# User profile
api_router.include_router(users_router)

# Responsible gaming
api_router.include_router(responsible_play_router)

# In-app notifications
api_router.include_router(notifications_router)

# Leaderboards
api_router.include_router(leaderboard_router)

# Gameplay & wager history
api_router.include_router(history_router)

# Customer support
api_router.include_router(support_router)

# Administration & auditing
api_router.include_router(admin_router)
api_router.include_router(superadmin_router)
api_router.include_router(system_router)

# Risk exposure controls & yield backtesting (super admin only)
api_router.include_router(risk_router)
