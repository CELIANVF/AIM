"""inscription_event: disciplines autorisées par concours

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-04-02

"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d0e1f2a3b4'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('inscription_event', schema=None) as batch_op:
        batch_op.add_column(sa.Column('allowed_disciplines_json', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('inscription_event', schema=None) as batch_op:
        batch_op.drop_column('allowed_disciplines_json')
