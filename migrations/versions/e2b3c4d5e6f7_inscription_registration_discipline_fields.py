"""Inscription registration: discipline, age, blason, distance, pique

Revision ID: e2b3c4d5e6f7
Revises: c8f1a2b3d4e5
Create Date: 2026-03-30

"""
from alembic import op
import sqlalchemy as sa


revision = 'e2b3c4d5e6f7'
down_revision = 'c8f1a2b3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('inscription_event_registration', schema=None) as batch_op:
        batch_op.add_column(sa.Column('discipline', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('age_category', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('blason', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('distance_label', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('pike_label', sa.String(length=60), nullable=True))


def downgrade():
    with op.batch_alter_table('inscription_event_registration', schema=None) as batch_op:
        batch_op.drop_column('pike_label')
        batch_op.drop_column('distance_label')
        batch_op.drop_column('blason')
        batch_op.drop_column('age_category')
        batch_op.drop_column('discipline')
