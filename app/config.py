import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """系統環境變數設定"""

    # 資料庫設定（Render 有時提供 postgres:// 開頭，需轉換為 postgresql://）
    database_url: str = "sqlite:///./linebot.db"

    # LINE Messaging API
    line_channel_secret: str = ""
    line_channel_access_token: str = ""

    # Cloudinary 設定
    cloudinary_url: str = ""
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    cloudinary_folder: str = "line_keyword_bot"

    # 後台管理員與 JWT 設定
    admin_username: str = "admin"
    admin_password: str = "admin123"
    jwt_secret_key: str = "line-keyword-assistant-secret-key-2026-change-in-production"
    jwt_expire_minutes: int = 1440

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlalchemy_database_url(self) -> str:
        """將 postgres:// 轉為 SQLAlchemy 2.0 支援的 postgresql://"""
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
