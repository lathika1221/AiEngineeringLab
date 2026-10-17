"""Add persistent conversations and link chats."""

from alembic import op
import sqlalchemy as sa

revision = "d82a61f4b903"
down_revision = "c30d77670cf2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="New Chat"),
        sa.Column("category", sa.String(length=50), nullable=False, server_default="general"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_conversations_id", "conversations", ["id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])

    op.add_column(
        "chats",
        sa.Column("conversation_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_chats_conversation_id_conversations",
        "chats",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_chats_conversation_id", "chats", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_chats_conversation_id", table_name="chats")
    op.drop_constraint("fk_chats_conversation_id_conversations", "chats", type_="foreignkey")
    op.drop_column("chats", "conversation_id")

    op.drop_index("ix_conversations_project_id", table_name="conversations")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index("ix_conversations_id", table_name="conversations")
    op.drop_table("conversations")
