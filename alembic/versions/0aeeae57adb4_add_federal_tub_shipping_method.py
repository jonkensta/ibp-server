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


# The metadata naming convention in ibp/base.py is
# `ck_%(table_name)s_%(constraint_name)s`, so the bare name "shipping_enum"
# below resolves to the live constraint name `ck_units_shipping_enum`.
# Passing the full name would double-prefix it.
OLD_ENUM = sa.Enum("Box", "Individual", name="shipping_enum")
NEW_ENUM = sa.Enum("Box", "Individual", "Federal Tub", name="shipping_enum")


def upgrade():
    with op.batch_alter_table("units") as batch:
        batch.drop_constraint("shipping_enum", type_="check")
        batch.alter_column(
            "shipping_method",
            existing_type=OLD_ENUM,
            type_=NEW_ENUM,
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
            existing_type=NEW_ENUM,
            type_=OLD_ENUM,
            existing_nullable=True,
        )
        batch.create_check_constraint(
            "shipping_enum",
            "shipping_method IN ('Box', 'Individual')",
        )
