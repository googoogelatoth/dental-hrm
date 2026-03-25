"""add benefit balance and transactions

Revision ID: 9b1c2d3e4f5
Revises: 75d6e309b4f5
Create Date: 2026-03-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '9b1c2d3e4f5'
down_revision = '75d6e309b4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_names = set(inspector.get_table_names())

    # Add columns to employee_benefits (only if missing)
    if 'employee_benefits' in table_names:
        existing_cols = {col['name'] for col in inspector.get_columns('employee_benefits')}
        with op.batch_alter_table('employee_benefits', schema=None) as batch_op:
            if 'start_date' not in existing_cols:
                batch_op.add_column(sa.Column('start_date', sa.Date(), nullable=True))
            if 'end_date' not in existing_cols:
                batch_op.add_column(sa.Column('end_date', sa.Date(), nullable=True))
            if 'initial_amount' not in existing_cols:
                batch_op.add_column(sa.Column('initial_amount', sa.Float(), nullable=True))
            if 'remaining_amount' not in existing_cols:
                batch_op.add_column(sa.Column('remaining_amount', sa.Float(), nullable=True))

    # benefit_transactions may already exist in some environments
    if 'benefit_transactions' not in table_names:
        op.create_table(
            'benefit_transactions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('employee_benefit_id', sa.Integer(), nullable=True),
            sa.Column('amount', sa.Float(), nullable=True),
            sa.Column('trans_date', sa.DateTime(), nullable=True),
            sa.Column('reason', sa.String(), nullable=True),
            sa.ForeignKeyConstraint(['employee_benefit_id'], ['employee_benefits.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    else:
        existing_cols = {col['name'] for col in inspector.get_columns('benefit_transactions')}
        with op.batch_alter_table('benefit_transactions', schema=None) as batch_op:
            if 'trans_date' not in existing_cols:
                batch_op.add_column(sa.Column('trans_date', sa.DateTime(), nullable=True))
            if 'reason' not in existing_cols:
                batch_op.add_column(sa.Column('reason', sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    # Drop table if it exists
    if 'benefit_transactions' in table_names:
        op.drop_table('benefit_transactions')

    # Drop added columns if they exist
    if 'employee_benefits' in table_names:
        existing_cols = {col['name'] for col in inspector.get_columns('employee_benefits')}
        with op.batch_alter_table('employee_benefits', schema=None) as batch_op:
            if 'remaining_amount' in existing_cols:
                batch_op.drop_column('remaining_amount')
            if 'initial_amount' in existing_cols:
                batch_op.drop_column('initial_amount')
            if 'end_date' in existing_cols:
                batch_op.drop_column('end_date')
            if 'start_date' in existing_cols:
                batch_op.drop_column('start_date')
