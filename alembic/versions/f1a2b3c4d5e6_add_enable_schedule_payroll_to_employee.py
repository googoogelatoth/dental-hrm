"""add enable_schedule and enable_payroll to employee

Revision ID: f1a2b3c4d5e6
Revises: eca1c4622abc
Create Date: 2026-03-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'b7a1c9f4d2e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {col['name'] for col in inspector.get_columns('employees')}

    with op.batch_alter_table('employees', schema=None) as batch_op:
        if 'enable_schedule' not in existing_cols:
            batch_op.add_column(sa.Column('enable_schedule', sa.Boolean(), nullable=False, server_default=sa.true()))
        if 'enable_payroll' not in existing_cols:
            batch_op.add_column(sa.Column('enable_payroll', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.drop_column('enable_payroll')
        batch_op.drop_column('enable_schedule')
