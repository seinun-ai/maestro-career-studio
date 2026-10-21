"""jobs.salary_currency_assumed

True when a posting gave an amount but no currency of its own (a bare "$" included) and capture
took the job's country's currency, else the home currency (routers/jobs._salary_currency_for).
NOT NULL, default false.

Backfill: a job whose extraction carries no currency but whose row has one got it from the
fallback, so it is assumed. A currency the old symbol table read from a bare "$" (USD) cannot be
told apart from a stated one and stays unmarked. Downgrade drops the column.

Revision ID: ff9591f140f7
Revises: 2d3de2d60a4c
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ff9591f140f7"
down_revision: Union[str, Sequence[str], None] = "2d3de2d60a4c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("salary_currency_assumed", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    # `id` untyped: the stored text is matched back as it was read, whatever its shape.
    jobs = sa.table(
        "jobs",
        sa.column("id"),
        sa.column("extracted_json", sa.JSON()),
        sa.column("salary_currency", sa.Text()),
        sa.column("salary_min", sa.Numeric()),
        sa.column("salary_max", sa.Numeric()),
        sa.column("salary_currency_assumed", sa.Boolean()),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(jobs.c.id, jobs.c.extracted_json).where(
            jobs.c.salary_currency.is_not(None),
            sa.or_(jobs.c.salary_min.is_not(None), jobs.c.salary_max.is_not(None)),
        )
    ).all()
    for row in rows:
        stated = row.extracted_json.get("salary_currency") if isinstance(row.extracted_json, dict) else None
        if not stated:
            bind.execute(jobs.update().where(jobs.c.id == row.id).values(salary_currency_assumed=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("salary_currency_assumed")
