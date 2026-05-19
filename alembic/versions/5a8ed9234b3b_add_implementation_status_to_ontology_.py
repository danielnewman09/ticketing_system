"""add_implementation_status_to_ontology_nodes

Revision ID: 5a8ed9234b3b
Revises: 57e489149179
Create Date: 2026-04-28 18:30:44.920081

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a8ed9234b3b'
down_revision: Union[str, Sequence[str], None] = '57e489149179'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('ontology_nodes', sa.Column('implementation_status', sa.String(length=20), server_default='designed', nullable=False))
    op.add_column('ontology_nodes', sa.Column('source_file', sa.String(length=500), server_default='', nullable=False))
    op.add_column('ontology_nodes', sa.Column('test_file', sa.String(length=500), server_default='', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ontology_nodes', 'test_file')
    op.drop_column('ontology_nodes', 'source_file')
    op.drop_column('ontology_nodes', 'implementation_status')
