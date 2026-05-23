"""drop_hlr_llr_tables_and_fk_constraints

Revision ID: 9a25f7d000a3
Revises: ead4b30f9296
Create Date: 2026-05-22 23:26:37.858754

Phase 2: Drop HLR/LLR SQLAlchemy tables and FK constraints.
HLR/LLR data now lives in Neo4j. VerificationMethod.low_level_requirement_id
is kept as a plain integer column (no FK constraint).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '9a25f7d000a3'
down_revision: Union[str, Sequence[str], None] = 'ead4b30f9296'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop HLR/LLR tables and FK constraint on verification_methods.

    Order matters: tables with FKs to other dropped tables must go first.
    """
    # Drop FK constraint on verification_methods.low_level_requirement_id
    # (keep the column as a plain integer, just remove the FK)
    # SQLite doesn't support DROP CONSTRAINT, so we use batch mode.
    with op.batch_alter_table('verification_methods') as batch_op:
        batch_op.drop_constraint(
            'fk_verification_methods_low_level_requirement_id_low_level_requirements',
            type_='foreignkey',
        )

    # Drop M2M tables first (they reference both HLR/LLR and other tables)
    op.drop_table('ticket_requirements')
    op.drop_table('low_level_requirements_components')
    op.drop_table('low_level_requirements_nodes')
    op.drop_table('low_level_requirements_triples')
    op.drop_table('high_level_requirements_nodes')
    op.drop_table('high_level_requirements_triples')

    # Drop LLR before HLR (LLR has FK to HLR)
    op.drop_table('low_level_requirements')
    op.drop_table('high_level_requirements')


def downgrade() -> None:
    """Recreate HLR/LLR tables (for rollback)."""
    op.create_table('high_level_requirements',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('description', sa.TEXT(), nullable=False),
        sa.Column('component_id', sa.INTEGER(), nullable=True),
        sa.Column('dependency_context', sqlite.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['component_id'], ['components.id'], name=op.f('fk_high_level_requirements_component_id_components'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_high_level_requirements')),
    )
    op.create_table('low_level_requirements',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('high_level_requirement_id', sa.INTEGER(), nullable=True),
        sa.Column('description', sa.TEXT(), nullable=False),
        sa.ForeignKeyConstraint(['high_level_requirement_id'], ['high_level_requirements.id'], name=op.f('fk_low_level_requirements_high_level_requirement_id_high_level_requirements'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_low_level_requirements')),
    )
    op.create_table('high_level_requirements_triples',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('highlevelrequirement_id', sa.INTEGER(), nullable=False),
        sa.Column('ontologytriple_id', sa.INTEGER(), nullable=False),
        sa.ForeignKeyConstraint(['highlevelrequirement_id'], ['high_level_requirements.id'], name=op.f('fk_high_level_requirements_triples_highlevelrequirement_id_high_level_requirements'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ontologytriple_id'], ['ontology_triples.id'], name=op.f('fk_high_level_requirements_triples_ontologytriple_id_ontology_triples'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_high_level_requirements_triples')),
    )
    op.create_table('high_level_requirements_nodes',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('highlevelrequirement_id', sa.INTEGER(), nullable=False),
        sa.Column('ontologynode_id', sa.INTEGER(), nullable=False),
        sa.ForeignKeyConstraint(['highlevelrequirement_id'], ['high_level_requirements.id'], name=op.f('fk_high_level_requirements_nodes_highlevelrequirement_id_high_level_requirements'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ontologynode_id'], ['ontology_nodes.id'], name=op.f('fk_high_level_requirements_nodes_ontologynode_id_ontology_nodes'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_high_level_requirements_nodes')),
    )
    op.create_table('low_level_requirements_triples',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('lowlevelrequirement_id', sa.INTEGER(), nullable=False),
        sa.Column('ontologytriple_id', sa.INTEGER(), nullable=False),
        sa.ForeignKeyConstraint(['lowlevelrequirement_id'], ['low_level_requirements.id'], name=op.f('fk_low_level_requirements_triples_lowlevelrequirement_id_low_level_requirements'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ontologytriple_id'], ['ontology_triples.id'], name=op.f('fk_low_level_requirements_triples_ontologytriple_id_ontology_triples'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_low_level_requirements_triples')),
    )
    op.create_table('low_level_requirements_nodes',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('lowlevelrequirement_id', sa.INTEGER(), nullable=False),
        sa.Column('ontologynode_id', sa.INTEGER(), nullable=False),
        sa.ForeignKeyConstraint(['lowlevelrequirement_id'], ['low_level_requirements.id'], name=op.f('fk_low_level_requirements_nodes_lowlevelrequirement_id_low_level_requirements'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ontologynode_id'], ['ontology_nodes.id'], name=op.f('fk_low_level_requirements_nodes_ontologynode_id_ontology_nodes'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_low_level_requirements_nodes')),
    )
    op.create_table('low_level_requirements_components',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('lowlevelrequirement_id', sa.INTEGER(), nullable=False),
        sa.Column('component_id', sa.INTEGER(), nullable=False),
        sa.ForeignKeyConstraint(['component_id'], ['components.id'], name=op.f('fk_low_level_requirements_components_component_id_components'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lowlevelrequirement_id'], ['low_level_requirements.id'], name=op.f('fk_low_level_requirements_components_lowlevelrequirement_id_low_level_requirements'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_low_level_requirements_components')),
    )
    op.create_table('ticket_requirements',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('ticket_id', sa.INTEGER(), nullable=False),
        sa.Column('low_level_requirement_id', sa.INTEGER(), nullable=False),
        sa.ForeignKeyConstraint(['low_level_requirement_id'], ['low_level_requirements.id'], name=op.f('fk_ticket_requirements_low_level_requirement_id_low_level_requirements'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], name=op.f('fk_ticket_requirements_ticket_id_tickets'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ticket_requirements')),
        sa.UniqueConstraint('ticket_id', 'low_level_requirement_id', name=op.f('uq_ticket_requirements_ticket_llr')),
    )
    # Recreate FK on verification_methods
    op.create_foreign_key(
        op.f('fk_verification_methods_low_level_requirement_id_low_level_requirements'),
        'verification_methods',
        'low_level_requirements',
        ['low_level_requirement_id'],
        ['id'],
        ondelete='CASCADE',
    )