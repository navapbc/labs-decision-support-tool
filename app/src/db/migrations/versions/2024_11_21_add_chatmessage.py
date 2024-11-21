"""Add ChatMessage

Revision ID: ca317bb046ba
Revises: 305e919583ad
Create Date: 2024-11-21 19:19:01.646653

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "ca317bb046ba"
down_revision = "305e919583ad"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "chat_message",
        sa.Column(
            "session_id",
            sa.Text(),
            nullable=False,
            comment="Session ID that this message is associated with",
        ),
        sa.Column("role", sa.Text(), nullable=False, comment="Role of the message speaker"),
        sa.Column("content", sa.Text(), nullable=False, comment="Content of the message"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("chat_message_pkey")),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("chat_message")
    # ### end Alembic commands ###