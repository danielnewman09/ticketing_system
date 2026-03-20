"""Enrich ontology_nodes with codebase fields

Revision ID: d2bda3c4ae65
Revises: 386b62adeef5
Create Date: 2026-03-16 19:38:02.415846

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2bda3c4ae65'
down_revision: Union[str, Sequence[str], None] = '386b62adeef5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # New columns on ontology_nodes
    op.add_column('ontology_nodes', sa.Column('refid', sa.String(length=200), server_default='', nullable=False))
    op.add_column('ontology_nodes', sa.Column('source_type', sa.String(length=20), server_default='', nullable=False))
    op.add_column('ontology_nodes', sa.Column('type_signature', sa.String(length=500), server_default='', nullable=False))
    op.add_column('ontology_nodes', sa.Column('argsstring', sa.String(length=500), server_default='', nullable=False))
    op.add_column('ontology_nodes', sa.Column('definition', sa.Text(), server_default='', nullable=False))
    op.add_column('ontology_nodes', sa.Column('file_path', sa.String(length=500), server_default='', nullable=False))
    op.add_column('ontology_nodes', sa.Column('line_number', sa.Integer(), nullable=True))
    op.add_column('ontology_nodes', sa.Column('is_static', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('ontology_nodes', sa.Column('is_const', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('ontology_nodes', sa.Column('is_virtual', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('ontology_nodes', sa.Column('is_abstract', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('ontology_nodes', sa.Column('is_final', sa.Boolean(), server_default='0', nullable=False))

    # Migrate compound_refid data into the new refid column
    op.execute("UPDATE ontology_nodes SET refid = compound_refid WHERE compound_refid != ''")
    op.execute("UPDATE ontology_nodes SET source_type = 'compound' WHERE compound_refid != ''")

    op.drop_column('ontology_nodes', 'compound_refid')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('ontology_nodes', sa.Column('compound_refid', sa.VARCHAR(length=200), server_default=sa.text("('')"), nullable=False))

    # Migrate refid data back to compound_refid
    op.execute("UPDATE ontology_nodes SET compound_refid = refid WHERE source_type = 'compound'")

    op.drop_column('ontology_nodes', 'is_final')
    op.drop_column('ontology_nodes', 'is_abstract')
    op.drop_column('ontology_nodes', 'is_virtual')
    op.drop_column('ontology_nodes', 'is_const')
    op.drop_column('ontology_nodes', 'is_static')
    op.drop_column('ontology_nodes', 'line_number')
    op.drop_column('ontology_nodes', 'file_path')
    op.drop_column('ontology_nodes', 'definition')
    op.drop_column('ontology_nodes', 'argsstring')
    op.drop_column('ontology_nodes', 'type_signature')
    op.drop_column('ontology_nodes', 'source_type')
    op.drop_column('ontology_nodes', 'refid')
