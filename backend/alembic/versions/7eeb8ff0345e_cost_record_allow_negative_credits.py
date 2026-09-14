"""cost record allow negative credits

Revision ID: 7eeb8ff0345e
Revises: babdd53f5f24
Create Date: 2026-09-13 20:32:28.102702

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7eeb8ff0345e'
down_revision: Union[str, None] = 'babdd53f5f24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Individual AWS cost lines can be negative (credits/refunds/adjustments).
    op.drop_constraint("ck_cost_record_non_negative", "cost_records", type_="check")


def downgrade() -> None:
    op.create_check_constraint(
        "ck_cost_record_non_negative", "cost_records", "cost >= 0"
    )
