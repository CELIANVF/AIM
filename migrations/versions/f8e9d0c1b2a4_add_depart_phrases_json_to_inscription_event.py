"""inscription_event: plusieurs phrases de départ (JSON)

Revision ID: f8e9d0c1b2a4
Revises: e2b3c4d5e6f7
Create Date: 2026-03-30

"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = 'f8e9d0c1b2a4'
down_revision = 'e2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'inscription_event',
        sa.Column('depart_phrases_json', sa.Text(), nullable=True),
    )
    conn = op.get_bind()
    rows = conn.execute(text('SELECT id, depart_phrase FROM inscription_event')).fetchall()
    for rid, phrase in rows:
        if phrase and str(phrase).strip():
            payload = json.dumps([str(phrase).strip()], ensure_ascii=False)
            conn.execute(
                text('UPDATE inscription_event SET depart_phrases_json = :j WHERE id = :id'),
                {'j': payload, 'id': rid},
            )


def downgrade():
    op.drop_column('inscription_event', 'depart_phrases_json')
