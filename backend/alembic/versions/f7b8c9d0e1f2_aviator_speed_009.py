"""Aviator: faster again (default growth 0.06/s -> 0.09/s)

Revision ID: f7b8c9d0e1f2
Revises: e6a7b8c9d0e1
Create Date: 2026-10-09

Stored values equal to an earlier default (0.045 or 0.06) move to 0.09; a rate an admin
chose on purpose is kept. Rounds already published keep their own rate.
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7b8c9d0e1f2"
down_revision: Union[str, None] = "e6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _set(old_values: tuple, new: float) -> None:
    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT config FROM game_settings WHERE game_id = 'aviator'")).first()
    if row is None:
        return
    config = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
    if float(config.get("exp_growth_rate", old_values[0])) not in old_values:
        return  # chosen by an admin: leave it
    config["exp_growth_rate"] = new
    value = "CAST(:c AS JSON)" if bind.dialect.name == "postgresql" else ":c"
    bind.execute(sa.text(f"UPDATE game_settings SET config = {value} WHERE game_id = 'aviator'"), {"c": json.dumps(config)})


def upgrade() -> None:
    _set((0.06, 0.045), 0.09)


def downgrade() -> None:
    _set((0.09,), 0.06)
