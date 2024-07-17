"""Add dataset, program, and region fields to Document

Revision ID: 7662da4b37fc
Revises: 73f4cdb40d2b
Create Date: 2024-07-16 19:35:45.465826

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7662da4b37fc"
down_revision = "73f4cdb40d2b"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic ###
    op.add_column(
        "document",
        sa.Column(
            "dataset", sa.Text(), nullable=True, comment="dataset in which the document belongs"
        ),
    )
    op.add_column(
        "document", sa.Column("program", sa.Text(), nullable=True, comment="benefit program")
    )
    op.add_column(
        "document",
        sa.Column(
            "region", sa.Text(), nullable=True, comment="geographical region of the benefit program"
        ),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("document", "region")
    op.drop_column("document", "program")
    op.drop_column("document", "dataset")
    # ### end Alembic commands ###
