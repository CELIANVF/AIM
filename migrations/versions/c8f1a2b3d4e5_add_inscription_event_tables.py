"""Add inscription_event and inscription_event_registration tables

Revision ID: c8f1a2b3d4e5
Revises: bd57850f2f9a
Create Date: 2026-03-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c8f1a2b3d4e5'
down_revision = 'bd57850f2f9a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'inscription_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('recipient_name', sa.String(length=120), nullable=True),
        sa.Column('depart_phrase', sa.String(length=500), nullable=True),
        sa.Column('lieu', sa.String(length=200), nullable=True),
        sa.Column('blasons_line', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'inscription_event_registration',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('archer_id', sa.Integer(), nullable=False),
        sa.Column('weapon_choice', sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(['archer_id'], ['archer.id']),
        sa.ForeignKeyConstraint(['event_id'], ['inscription_event.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'archer_id', name='uq_inscription_event_archer'),
    )


def downgrade():
    op.drop_table('inscription_event_registration')
    op.drop_table('inscription_event')
