"""Ajoute la date de dernière vérification à CompositeProduct.

Revision ID: f0a1b2c3d4e5
Revises: e5f6a7b8c9d0
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa


revision = 'f0a1b2c3d4e5'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('composite_product', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_verification_date', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('composite_product', schema=None) as batch_op:
        batch_op.drop_column('last_verification_date')
