"""add federal tub shipping method

Revision ID: 0aeeae57adb4
Revises: b21034d4ccfa
Create Date: 2026-05-28 19:16:23.636382

"""

# revision identifiers, used by Alembic.
revision = '0aeeae57adb4'
down_revision = 'b21034d4ccfa'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    with op.batch_alter_table("units") as batch:
        batch.drop_constraint("shipping_enum", type_="check")
        batch.alter_column(
            "shipping_method",
            existing_type=sa.String(length=10),
            type_=sa.String(length=11),
            existing_nullable=True,
        )
        batch.create_check_constraint(
            "shipping_enum",
            "shipping_method IN ('Box', 'Individual', 'Federal Tub')",
        )


def downgrade():
    bind = op.get_bind()
    count = bind.execute(
        sa.text("SELECT COUNT(*) FROM units WHERE shipping_method = :v"),
        {"v": "Federal Tub"},
    ).scalar()
    if count:
        raise RuntimeError(
            f"Cannot downgrade: {count} unit(s) still use 'Federal Tub'."
        )

    with op.batch_alter_table("units") as batch:
        batch.drop_constraint("shipping_enum", type_="check")
        batch.alter_column(
            "shipping_method",
            existing_type=sa.String(length=11),
            type_=sa.String(length=10),
            existing_nullable=True,
        )
        batch.create_check_constraint(
            "shipping_enum",
            "shipping_method IN ('Box', 'Individual')",
        )
