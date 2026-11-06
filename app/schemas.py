from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models import MatchType, ReplyType


class KeywordBase(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=255, description="觸發關鍵字")
    match_type: MatchType = Field(default=MatchType.exact, description="比對模式: exact 或 contains")
    reply_type: ReplyType = Field(default=ReplyType.text, description="回覆類型: text, image, pdf")
    reply_content: str = Field(..., min_length=1, description="回覆文字或 Cloudinary URL")
    is_active: bool = Field(default=True, description="是否啟用")

    @field_validator("keyword")
    @classmethod
    def strip_keyword(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("關鍵字不可為空白")
        return cleaned

    @field_validator("reply_content")
    @classmethod
    def validate_reply_content(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("回覆內容不可為空白")
        return cleaned


class KeywordCreate(KeywordBase):
    pass


class KeywordUpdate(BaseModel):
    keyword: Optional[str] = Field(None, min_length=1, max_length=255)
    match_type: Optional[MatchType] = None
    reply_type: Optional[ReplyType] = None
    reply_content: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None

    @field_validator("keyword")
    @classmethod
    def strip_keyword(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("關鍵字不可為空白")
            return cleaned
        return v


class KeywordResponse(KeywordBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class UploadResponse(BaseModel):
    url: str
    preview_url: str
    resource_type: str
    format: Optional[str] = None
    public_id: str
    keyword_updated: Optional[int] = None


class CSVImportErrorItem(BaseModel):
    row: int
    keyword: Optional[str] = None
    error: str


class CSVImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: List[CSVImportErrorItem]
