"""Aviator: faster default growth curve (0.045/s -> 0.06/s)

Revision ID: e6a7b8c9d0e1
Revises: d5f6a7b8c9d0
Create Date: 2026-10-09

Only a stored value equal to the old default is changed; a rate an admin chose on purpose
is kept. Running and past rounds keep the rate they were published with.
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6a7b8c9d0e1"
down_revision: Union[str, None] = "d5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD, NEW = 0.045, 0.06


def _set(rate_from: float, rate_to: float) -> None:
    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT config FROM game_settings WHERE game_id = 'aviator'")).first()
    if row is None:
        return
    config = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
    if float(config.get("exp_growth_rate", rate_from)) != rate_from:
        return  # chosen by an admin: leave it
    config["exp_growth_rate"] = rate_to
    value = "CAST(:c AS JSON)" if bind.dialect.name == "postgresql" else ":c"
    bind.execute(sa.text(f"UPDATE game_settings SET config = {value} WHERE game_id = 'aviator'"),
                 {"c": json.dumps(config)})


def upgrade() -> None:
    _set(OLD, NEW)


def downgrade() -> None:
    _set(NEW, OLD)
