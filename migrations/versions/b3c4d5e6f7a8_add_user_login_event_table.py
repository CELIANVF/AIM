"""add user_login_event table for connection audit

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-04-01

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3c4d5e6f7a8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_login_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('attempted_username', sa.String(length=80), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_user_login_event_user_id_created_at',
        'user_login_event',
        ['user_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_user_login_event_ip_address_created_at',
        'user_login_event',
        ['ip_address', 'created_at'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_user_login_event_ip_address_created_at', table_name='user_login_event')
    op.drop_index('ix_user_login_event_user_id_created_at', table_name='user_login_event')
    op.drop_table('user_login_event')
