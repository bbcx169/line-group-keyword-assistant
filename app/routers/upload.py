from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models import KeywordRule, ReplyType
from app.schemas import UploadResponse
from app.services.cloudinary_service import upload_file_to_cloudinary

router = APIRouter(prefix="/api/upload", tags=["Media Upload (Cloudinary)"])


@router.post("", response_model=UploadResponse, summary="上傳圖片或 PDF 至 Cloudinary")
async def upload_media(
    file: UploadFile = File(..., description="要上傳的圖片 (JPG/PNG/WEBP/GIF) 或 PDF 檔案"),
    keyword_id: Optional[int] = Form(None, description="選填：直接將回傳 URL 綁定更新至指定的關鍵字 ID"),
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """
    在後台上傳圖片或 PDF：
    1. 後端自動將檔案推播至 Cloudinary
    2. 若有提供 `keyword_id`，自動將回傳的 URL 與對應類型 (image/pdf) 寫入資料庫該筆關鍵字中
    3. 回傳公開 URL 與預覽縮圖 URL 供前端表單使用
    """
    result = await upload_file_to_cloudinary(file)

    updated_id = None
    if keyword_id is not None:
        rule = db.query(KeywordRule).filter(KeywordRule.id == keyword_id).first()
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"找不到 ID 為 {keyword_id} 的關鍵字規則",
            )
        rule.reply_content = result["url"]
        rule.reply_type = ReplyType.pdf if result["resource_type"] == "pdf" else ReplyType.image
        db.commit()
        db.refresh(rule)
        updated_id = rule.id

    return UploadResponse(
        url=result["url"],
        preview_url=result["preview_url"],
        resource_type=result["resource_type"],
        format=result.get("format"),
        public_id=result["public_id"],
        keyword_updated=updated_id,
    )
