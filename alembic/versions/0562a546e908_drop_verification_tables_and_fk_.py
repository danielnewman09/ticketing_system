"""Drop verification tables and FK constraints.

Revision ID: 0562a546e908
Revises: 9a25f7d000a3
Create Date: 2026-05-23 14:18:56.851220

Phase 3: VerificationMethod, VerificationCondition, VerificationAction
models deleted — data lives in Neo4j as :VerificationMethod/:Condition/:Action
nodes. TaskVerification.verification_method_id becomes a plain integer
referencing a Neo4j node (no FK constraint).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = "0562a546e908"
down_revision: Union[str, Sequence[str], None] = "9a25f7d000a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop FK on task_verifications — verification_method_id is now a plain int.
    # SQLite doesn't support DROP CONSTRAINT directly, use batch mode.
    # Guard against the constraint already being dropped (idempotent).
    conn = op.get_bind()
    insp = sa.inspect(conn)
    fks = [fk["name"] for fk in insp.get_foreign_keys("task_verifications")]
    if "fk_task_verifications_verification_method_id_verification_methods" in fks:
        with op.batch_alter_table("task_verifications") as batch_op:
            batch_op.drop_constraint(
                "fk_task_verifications_verification_method_id_verification_methods",
                type_="foreignkey",
            )

    # Drop verification tables (order matters — conditions/actions reference methods)
    op.drop_table("verification_actions")
    op.drop_table("verification_conditions")
    op.drop_table("verification_methods")


def downgrade() -> None:
    # Recreate verification_methods
    op.create_table(
        "verification_methods",
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column("low_level_requirement_id", sa.INTEGER(), nullable=False),
        sa.Column("method", sa.VARCHAR(length=20), nullable=False),
        sa.Column("test_name", sa.VARCHAR(length=300), server_default="", nullable=True),
        sa.Column("description", sa.TEXT(), server_default="", nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_methods")),
    )

    # Recreate verification_conditions
    op.create_table(
        "verification_conditions",
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column("verification_id", sa.INTEGER(), nullable=False),
        sa.Column("phase", sa.VARCHAR(length=4), nullable=False),
        sa.Column("order", sa.INTEGER(), server_default="0", nullable=True),
        sa.Column("ontology_node_id", sa.INTEGER(), nullable=True),
        sa.Column("ontology_node_qualified_name", sa.VARCHAR(length=500), server_default="", nullable=True),
        sa.Column("member_qualified_name", sa.VARCHAR(length=500), nullable=False),
        sa.Column("operator", sa.VARCHAR(length=20), server_default="==", nullable=True),
        sa.Column("expected_value", sa.VARCHAR(length=500), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_conditions")),
        sa.ForeignKeyConstraint(
            ["verification_id"], ["verification_methods.id"],
            name=op.f("fk_verification_conditions_verification_id_verification_methods"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ontology_node_id"], ["ontology_nodes.id"],
            name=op.f("fk_verification_conditions_ontology_node_id_ontology_nodes"),
            ondelete="SET NULL",
        ),
    )

    # Recreate verification_actions
    op.create_table(
        "verification_actions",
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column("verification_id", sa.INTEGER(), nullable=False),
        sa.Column("order", sa.INTEGER(), server_default="0", nullable=True),
        sa.Column("description", sa.TEXT(), nullable=False),
        sa.Column("ontology_node_id", sa.INTEGER(), nullable=True),
        sa.Column("ontology_node_qualified_name", sa.VARCHAR(length=500), server_default="", nullable=True),
        sa.Column("member_qualified_name", sa.VARCHAR(length=500), server_default="", nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_actions")),
        sa.ForeignKeyConstraint(
            ["verification_id"], ["verification_methods.id"],
            name=op.f("fk_verification_actions_verification_id_verification_methods"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ontology_node_id"], ["ontology_nodes.id"],
            name=op.f("fk_verification_actions_ontology_node_id_ontology_nodes"),
            ondelete="SET NULL",
        ),
    )

    # Recreate FK on task_verifications
    with op.batch_alter_table("task_verifications") as batch_op:
        batch_op.create_foreign_key(
            op.f("fk_task_verifications_verification_method_id_verification_methods"),
            "verification_methods",
            ["verification_method_id"],
            ["id"],
            ondelete="CASCADE",
        )
