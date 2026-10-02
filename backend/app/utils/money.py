"""Virtual-credit money utilities.

All amounts are integers in **paise** (100 paise = 1 Credit).
No floats are ever used for financial arithmetic.

Rules enforced here:
- Amount must be a positive integer > 0.
- Wallet balance must never go negative.
- Locked balance must never exceed available balance.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import Union

# 100 paise == 1 virtual credit
PAISE_PER_CREDIT: int = 100

# Platform-wide single-transaction maximum (50,000 credits = 5,000,000 paise)
MAX_SINGLE_TRANSACTION_PAISE: int = 5_000_000

# Minimum bet amount (1 credit = 100 paise)
MIN_BET_PAISE: int = 100


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def credits_to_paise(credits: Union[int, float, Decimal, str]) -> int:
    """Convert credits to paise using Decimal to avoid floating-point drift.

    Always rounds DOWN (platform-favourable).

    >>> credits_to_paise(10)
    1000
    >>> credits_to_paise("5.5")
    550
    """
    d = Decimal(str(credits))
    return int((d * PAISE_PER_CREDIT).to_integral_value(rounding=ROUND_DOWN))


def paise_to_credits(paise: int) -> Decimal:
    """Convert paise integer to Decimal credits (exact, no float).

    >>> paise_to_credits(1050)
    Decimal('10.50')
    """
    return Decimal(paise) / Decimal(PAISE_PER_CREDIT)


def format_credits(paise: int) -> str:
    """Return a human-readable credit string: '10.50 Credits'.

    >>> format_credits(1050)
    '10.50 Credits'
    """
    return f"{paise_to_credits(paise):.2f} Credits"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_positive_paise(amount: int, label: str = "amount") -> None:
    """Raise ValueError if amount is not a positive integer."""
    if not isinstance(amount, int):
        raise TypeError(f"{label} must be an integer paise value, got {type(amount).__name__}")
    if amount <= 0:
        raise ValueError(f"{label} must be > 0 paise, got {amount}")


def validate_transaction_limit(amount: int, label: str = "amount") -> None:
    """Raise ValueError if amount exceeds the single-transaction cap."""
    validate_positive_paise(amount, label)
    if amount > MAX_SINGLE_TRANSACTION_PAISE:
        raise ValueError(
            f"{label} {amount} paise exceeds single-transaction maximum "
            f"of {MAX_SINGLE_TRANSACTION_PAISE} paise "
            f"({format_credits(MAX_SINGLE_TRANSACTION_PAISE)})"
        )


def validate_sufficient_balance(available: int, required: int) -> None:
    """Raise ValueError if available balance is less than required."""
    if available < required:
        from app.core.exceptions import InsufficientBalanceException

        raise InsufficientBalanceException(
            f"Insufficient virtual credits: need {format_credits(required)}, "
            f"have {format_credits(available)} available"
        )


def safe_add(a: int, b: int) -> int:
    """Add two paise integers with overflow guard."""
    result = a + b
    if result < 0:
        raise OverflowError(f"safe_add underflow: {a} + {b} = {result}")
    return result


def safe_subtract(a: int, b: int) -> int:
    """Subtract paise integers, never allowing negative results."""
    result = a - b
    if result < 0:
        raise ValueError(f"safe_subtract would produce negative balance: {a} - {b} = {result}")
    return result
