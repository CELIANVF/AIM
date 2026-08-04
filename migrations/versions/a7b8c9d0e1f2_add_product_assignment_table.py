"""Ajoute la table product_assignment (prêt direct d'un produit à un archer).

Revision ID: a7b8c9d0e1f2
Revises: f0a1b2c3d4e5
Create Date: 2026-08-04

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7b8c9d0e1f2'
down_revision = 'f0a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'product_assignment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('archer_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('date_assigned', sa.DateTime(), nullable=True),
        sa.Column('date_returned', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['archer_id'], ['archer.id']),
        sa.ForeignKeyConstraint(['product_id'], ['product.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('product_assignment')
