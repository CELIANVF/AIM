"""inscription_event: inscription en ligne archers

Revision ID: b7c8d9e0f1a2
Revises: 9dc9f66c218e
Create Date: 2026-04-02

"""
from alembic import op
import sqlalchemy as sa

revision = 'b7c8d9e0f1a2'
down_revision = '9dc9f66c218e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('inscription_event', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('open_for_archer_registration', sa.Boolean(), nullable=False, server_default='0')
        )
        batch_op.add_column(sa.Column('archer_registration_deadline', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('inscription_event', schema=None) as batch_op:
        batch_op.drop_column('archer_registration_deadline')
        batch_op.drop_column('open_for_archer_registration')
