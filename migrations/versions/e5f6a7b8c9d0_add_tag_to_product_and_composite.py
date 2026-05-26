"""Add tag (numéro d'identification) to Product and CompositeProduct.

Revision ID: e5f6a7b8c9d0
Revises: d0e1f2a3b4c5
Create Date: 2026-05-26

Ce changement ajoute un code court (« P-001 », « A-001 »…) imprimable sur
chaque étiquette physique pour faciliter l'inventaire du matériel.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c9d0'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def _pad(n, width=3):
    s = str(int(n))
    return s if len(s) >= width else s.rjust(width, '0')


def upgrade():
    # 1) Ajout des colonnes (nullable + uniques)
    with op.batch_alter_table('product', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tag', sa.String(length=32), nullable=True))
        batch_op.create_index('ix_product_tag', ['tag'], unique=True)

    with op.batch_alter_table('composite_product', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tag', sa.String(length=32), nullable=True))
        batch_op.create_index('ix_composite_product_tag', ['tag'], unique=True)

    conn = op.get_bind()

    # 2) Backfill : chaque produit reçoit « P-001 », « P-002 », … (tri par id).
    rows = conn.execute(sa.text('SELECT id FROM product ORDER BY id')).fetchall()
    width = max(3, len(str(len(rows))))
    for idx, row in enumerate(rows, start=1):
        conn.execute(
            sa.text('UPDATE product SET tag = :tag WHERE id = :id'),
            {'tag': f'P-{_pad(idx, width)}', 'id': row[0]},
        )

    rows = conn.execute(sa.text('SELECT id FROM composite_product ORDER BY id')).fetchall()
    width = max(3, len(str(len(rows))))
    for idx, row in enumerate(rows, start=1):
        conn.execute(
            sa.text('UPDATE composite_product SET tag = :tag WHERE id = :id'),
            {'tag': f'A-{_pad(idx, width)}', 'id': row[0]},
        )


def downgrade():
    with op.batch_alter_table('composite_product', schema=None) as batch_op:
        batch_op.drop_index('ix_composite_product_tag')
        batch_op.drop_column('tag')

    with op.batch_alter_table('product', schema=None) as batch_op:
        batch_op.drop_index('ix_product_tag')
        batch_op.drop_column('tag')
