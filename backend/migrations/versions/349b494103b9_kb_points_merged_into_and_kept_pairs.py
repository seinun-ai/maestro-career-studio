"""kb_points.merged_into_point_id and kb_point_kept_pairs

The pointer Combine writes from a folded claim to the one it was folded into, and the pairs
the user marked "Not the same" so groom stops proposing them. Impl types only (sa.Uuid /
sa.DateTime), like the baseline: a revision never imports app code.

Adding a foreign key makes batch mode recreate kb_points (SQLite's move-and-copy).
migrations/env.py runs with foreign_keys OFF on purpose, so dropping the old table fires no
CASCADE into kb_port_log. Never run this chain through app.db.make_engine.

Revision ID: 349b494103b9
Revises: e5a1c2d77b04
"""
from alembic import op
import sqlalchemy as sa

revision = "349b494103b9"
down_revision = "e5a1c2d77b04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("kb_points", schema=None) as batch_op:
        batch_op.add_column(sa.Column("merged_into_point_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_kb_points_merged_into_point_id",
            "kb_points",
            ["merged_into_point_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_kb_points_merged_into_point_id", ["merged_into_point_id"], unique=False
        )
    op.create_table(
        "kb_point_kept_pairs",
        sa.Column("point_a_id", sa.Uuid(), nullable=False),
        sa.Column("point_b_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(["point_a_id"], ["kb_points.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["point_b_id"], ["kb_points.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("point_a_id", "point_b_id"),
    )


def downgrade() -> None:
    op.drop_table("kb_point_kept_pairs")
    with op.batch_alter_table("kb_points", schema=None) as batch_op:
        batch_op.drop_index("ix_kb_points_merged_into_point_id")
        batch_op.drop_constraint("fk_kb_points_merged_into_point_id", type_="foreignkey")
        batch_op.drop_column("merged_into_point_id")
