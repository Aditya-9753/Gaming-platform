"""Single place deciding what round secrets may leave the server, and when.

Provably-fair contract: a round's serverSeed is generated and its SHA-256 hash
published *before* betting opens; the outcome is HMAC-SHA256(serverSeed,
"clientSeed:nonce"). Until the round is finished nobody — player, admin or
super admin — may read the seed (it would reveal the outcome) and no endpoint
can change it. Every API that returns round or bet data must go through these
helpers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.constants import GameRoundLifecycle, RoundStatus

# Statuses after which the outcome is final and the seed may be revealed
FINISHED_STATUSES = frozenset({
    RoundStatus.COMPLETED.value,
    RoundStatus.CANCELLED.value,
    GameRoundLifecycle.HISTORY.value,
    GameRoundLifecycle.SETTLED.value,
})

# Selection keys holding hidden game state (e.g. Mines layout) or internal ids
_SECRET_SELECTION_KEYS = frozenset({"mines", "cashout_idempotency_key"})


def is_finished(status: Optional[str]) -> bool:
    return (status or "") in FINISHED_STATUSES


def revealable_seed(round_obj: Any) -> Optional[str]:
    """The server seed, but only once the round can no longer change."""
    return round_obj.server_seed if is_finished(getattr(round_obj, "status", None)) else None


def public_selection(selection: Optional[Dict[str, Any]], entry_status: Optional[str]) -> Optional[Dict[str, Any]]:
    """Strip hidden state from a bet's selection while that bet is still in play."""
    if not selection:
        return selection
    hidden = _SECRET_SELECTION_KEYS if entry_status == "PLACED" else {"cashout_idempotency_key"}
    return {k: v for k, v in selection.items() if k not in hidden}
