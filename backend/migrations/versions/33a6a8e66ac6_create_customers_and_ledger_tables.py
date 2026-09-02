"""create customers and ledger tables

Revision ID: 33a6a8e66ac6
Revises: 6e51de8ca5de
Create Date: 2026-09-02 05:22:43.957842

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '33a6a8e66ac6'
down_revision = '6e51de8ca5de'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.alter_column(
            'id',
            existing_type=sa.INTEGER(),
            type_=sa.String(length=64),
            existing_nullable=False,
            postgresql_using='CAST(id AS VARCHAR(64))',
        )
        batch_op.add_column(sa.Column('merchant_id', sa.String(length=64), nullable=False, server_default='merchant-001'))
        batch_op.add_column(sa.Column('email', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('address', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('status', sa.String(length=20), nullable=False, server_default='active'))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))

    op.execute("UPDATE customers SET id = 'customer-' || id WHERE id !~ '^customer-'")
    op.execute("UPDATE customers SET merchant_id = 'merchant-001' WHERE merchant_id IS NULL OR merchant_id = ''")
    op.execute("UPDATE customers SET status = 'active' WHERE status IS NULL OR status = ''")

    op.create_table('ledger_entries',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('merchant_id', sa.String(length=64), nullable=False, server_default='merchant-001'),
    sa.Column('customer_id', sa.String(length=64), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=10), nullable=False, server_default='INR'),
    sa.Column('description', sa.String(length=255), nullable=False, server_default=''),
    sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.CheckConstraint("type IN ('credit', 'payment', 'adjustment')", name='ledger_type_valid'),
    sa.CheckConstraint('amount > 0', name='ledger_amount_positive'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.drop_column('updated_at')
        batch_op.drop_column('status')
        batch_op.drop_column('address')
        batch_op.drop_column('email')
        batch_op.drop_column('merchant_id')
        batch_op.alter_column(
            'id',
            existing_type=sa.String(length=64),
            type_=sa.INTEGER(),
            existing_nullable=False,
            postgresql_using='CAST(id AS INTEGER)',
        )

    op.drop_table('ledger_entries')
