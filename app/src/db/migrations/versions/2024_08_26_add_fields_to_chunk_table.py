"""add fields to Chunk table

Revision ID: 39241f0cfb43
Revises: 7662da4b37fc
Create Date: 2024-08-26 22:57:02.836949

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "39241f0cfb43"
down_revision = "7662da4b37fc"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("chunk", sa.Column("page_number", sa.Integer(), nullable=False))
    op.add_column("chunk", sa.Column("headings", postgresql.ARRAY(sa.Text()), nullable=False))
    op.alter_column(
        "document",
        "dataset",
        existing_type=sa.TEXT(),
        nullable=False,
        comment=None,
        existing_comment="dataset in which the document belongs",
    )
    op.alter_column(
        "document",
        "program",
        existing_type=sa.TEXT(),
        nullable=False,
        comment=None,
        existing_comment="benefit program",
    )
    op.alter_column(
        "document",
        "region",
        existing_type=sa.TEXT(),
        nullable=False,
        comment=None,
        existing_comment="geographical region of the benefit program",
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column(
        "document",
        "region",
        existing_type=sa.TEXT(),
        nullable=True,
        comment="geographical region of the benefit program",
    )
    op.alter_column(
        "document", "program", existing_type=sa.TEXT(), nullable=True, comment="benefit program"
    )
    op.alter_column(
        "document",
        "dataset",
        existing_type=sa.TEXT(),
        nullable=True,
        comment="dataset in which the document belongs",
    )
    op.drop_column("chunk", "headings")
    op.drop_column("chunk", "page_number")
    # ### end Alembic commands ###
