"""add welfare defaults and payroll adjustments

Revision ID: b7a1c9f4d2e8
Revises: eca1c4622abc
Create Date: 2026-03-24 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7a1c9f4d2e8'
down_revision = 'eca1c4622abc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if 'benefits' in table_names:
        benefit_cols = {col['name'] for col in inspector.get_columns('benefits')}
        with op.batch_alter_table('benefits', schema=None) as batch_op:
            if 'description' not in benefit_cols:
                batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
            if 'budget_amount' not in benefit_cols:
                batch_op.add_column(sa.Column('budget_amount', sa.Float(), nullable=True, server_default='0'))
            if 'start_date' not in benefit_cols:
                batch_op.add_column(sa.Column('start_date', sa.Date(), nullable=True))
            if 'end_date' not in benefit_cols:
                batch_op.add_column(sa.Column('end_date', sa.Date(), nullable=True))
            if 'is_employee_specific' not in benefit_cols:
                batch_op.add_column(sa.Column('is_employee_specific', sa.Boolean(), nullable=True, server_default=sa.false()))
            if 'is_active' not in benefit_cols:
                batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.true()))

    if 'payroll_adjustment_types' not in table_names:
        op.create_table(
            'payroll_adjustment_types',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('adjustment_kind', sa.String(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('default_amount', sa.Float(), nullable=True),
            sa.Column('start_date', sa.Date(), nullable=True),
            sa.Column('end_date', sa.Date(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name')
        )
        with op.batch_alter_table('payroll_adjustment_types', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_payroll_adjustment_types_id'), ['id'], unique=False)

    if 'employee_payroll_adjustments' not in table_names:
        op.create_table(
            'employee_payroll_adjustments',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('employee_id', sa.Integer(), nullable=False),
            sa.Column('adjustment_type_id', sa.Integer(), nullable=False),
            sa.Column('amount', sa.Float(), nullable=True),
            sa.Column('start_date', sa.Date(), nullable=True),
            sa.Column('end_date', sa.Date(), nullable=True),
            sa.Column('note', sa.String(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.ForeignKeyConstraint(['adjustment_type_id'], ['payroll_adjustment_types.id']),
            sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
            sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('employee_payroll_adjustments', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_employee_payroll_adjustments_id'), ['id'], unique=False)

    if 'payroll_line_items' not in table_names:
        op.create_table(
            'payroll_line_items',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('payroll_detail_id', sa.Integer(), nullable=False),
            sa.Column('item_type', sa.String(), nullable=False),
            sa.Column('source_type', sa.String(), nullable=False),
            sa.Column('code', sa.String(), nullable=True),
            sa.Column('label', sa.String(), nullable=False),
            sa.Column('amount', sa.Float(), nullable=True),
            sa.Column('sort_order', sa.Integer(), nullable=True),
            sa.Column('benefit_transaction_id', sa.Integer(), nullable=True),
            sa.Column('employee_adjustment_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['benefit_transaction_id'], ['benefit_transactions.id']),
            sa.ForeignKeyConstraint(['employee_adjustment_id'], ['employee_payroll_adjustments.id']),
            sa.ForeignKeyConstraint(['payroll_detail_id'], ['payroll_details.id']),
            sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('payroll_line_items', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_payroll_line_items_id'), ['id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if 'payroll_line_items' in table_names:
        with op.batch_alter_table('payroll_line_items', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_payroll_line_items_id'))
        op.drop_table('payroll_line_items')

    if 'employee_payroll_adjustments' in table_names:
        with op.batch_alter_table('employee_payroll_adjustments', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_employee_payroll_adjustments_id'))
        op.drop_table('employee_payroll_adjustments')

    if 'payroll_adjustment_types' in table_names:
        with op.batch_alter_table('payroll_adjustment_types', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_payroll_adjustment_types_id'))
        op.drop_table('payroll_adjustment_types')

    if 'benefits' in table_names:
        benefit_cols = {col['name'] for col in inspector.get_columns('benefits')}
        with op.batch_alter_table('benefits', schema=None) as batch_op:
            if 'is_active' in benefit_cols:
                batch_op.drop_column('is_active')
            if 'is_employee_specific' in benefit_cols:
                batch_op.drop_column('is_employee_specific')
            if 'end_date' in benefit_cols:
                batch_op.drop_column('end_date')
            if 'start_date' in benefit_cols:
                batch_op.drop_column('start_date')
            if 'budget_amount' in benefit_cols:
                batch_op.drop_column('budget_amount')
            if 'description' in benefit_cols:
                batch_op.drop_column('description')