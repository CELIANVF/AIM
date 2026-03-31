"""inscription_event_registration: départ par archer (index)

Revision ID: a1b2c3d4e5f6
Revises: f8e9d0c1b2a4
Create Date: 2026-03-30

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'f8e9d0c1b2a4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'inscription_event_registration',
        sa.Column('depart_index', sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column('inscription_event_registration', 'depart_index')
