import enum
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, Text
from app.database import Base


class MatchType(str, enum.Enum):
    """關鍵字比對模式"""

    exact = "exact"        # 完全比對
    contains = "contains"  # 包含比對（模糊比對）


class ReplyType(str, enum.Enum):
    """回覆格式類型"""

    text = "text"    # 純文字
    image = "image"  # 圖片 (Cloudinary URL)
    pdf = "pdf"      # PDF / 檔案連結 (Cloudinary URL)


class KeywordRule(Base):
    """關鍵字規則資料表 (keywords)"""

    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    keyword = Column(String(255), unique=True, index=True, nullable=False, comment="觸發關鍵字")
    match_type = Column(
        Enum(MatchType, name="match_type_enum"),
        nullable=False,
        default=MatchType.exact,
        comment="比對模式: exact 或 contains",
    )
    reply_type = Column(
        Enum(ReplyType, name="reply_type_enum"),
        nullable=False,
        default=ReplyType.text,
        comment="回覆類型: text, image, pdf",
    )
    reply_content = Column(Text, nullable=False, comment="回覆的文字內容或 Cloudinary URL")
    is_active = Column(Boolean, nullable=False, default=True, comment="是否啟用該規則")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="建立時間",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="最後更新時間",
    )
