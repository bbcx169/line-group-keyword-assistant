"""initial keywords table

Revision ID: 0001_initial_keywords
Revises:
Create Date: 2026-11-06 16:20:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_keywords"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "keywords" in inspector.get_table_names():
        return

    op.create_table(
        "keywords",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False, comment="觸發關鍵字"),
        sa.Column(
            "match_type",
            sa.Enum("exact", "contains", name="match_type_enum"),
            nullable=False,
            comment="比對模式: exact 或 contains",
        ),
        sa.Column(
            "reply_type",
            sa.Enum("text", "image", "pdf", name="reply_type_enum"),
            nullable=False,
            comment="回覆類型: text, image, pdf",
        ),
        sa.Column("reply_content", sa.Text(), nullable=False, comment="回覆的文字內容或 Cloudinary URL"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"), comment="是否啟用該規則"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="建立時間"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="最後更新時間"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_keywords_id"), "keywords", ["id"], unique=False)
    op.create_index(op.f("ix_keywords_keyword"), "keywords", ["keyword"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_keywords_keyword"), table_name="keywords")
    op.drop_index(op.f("ix_keywords_id"), table_name="keywords")
    op.drop_table("keywords")
