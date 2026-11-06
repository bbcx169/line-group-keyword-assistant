import re
from typing import Any, Dict
import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile, status
from app.config import get_settings


def configure_cloudinary() -> None:
    """初始化 Cloudinary SDK 設定"""
    settings = get_settings()
    if settings.cloudinary_url:
        # 若有 CLOUDINARY_URL (cloudinary://api_key:api_secret@cloud_name)，解析並設定
        match = re.match(r"cloudinary://([^:]+):([^@]+)@(.+)", settings.cloudinary_url.strip())
        if match:
            api_key, api_secret, cloud_name = match.groups()
            cloudinary.config(
                cloud_name=cloud_name,
                api_key=api_key,
                api_secret=api_secret,
                secure=True,
            )
            return

    if settings.cloudinary_cloud_name and settings.cloudinary_api_key and settings.cloudinary_api_secret:
        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True,
        )


def build_preview_image_url(original_url: str) -> str:
    """
    根據 Cloudinary 原始圖片網址產生 LINE ImageMessage 所需的縮圖預覽網址 (preview_image_url)。
    若為一般非 Cloudinary 網址，則直接回傳原網址。
    """
    if "res.cloudinary.com" in original_url and "/image/upload/" in original_url:
        return original_url.replace(
            "/image/upload/",
            "/image/upload/c_limit,w_800,q_auto,f_auto/",
            1,
        )
    return original_url


async def upload_file_to_cloudinary(file: UploadFile) -> Dict[str, Any]:
    """
    上傳圖片或 PDF 檔案至 Cloudinary 並回傳公開安全網址與縮圖網址
    """
    settings = get_settings()
    configure_cloudinary()

    cfg = cloudinary.config()
    if not (cfg.cloud_name and cfg.api_key and cfg.api_secret):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="尚未設定 Cloudinary 憑證 (CLOUDINARY_URL 或 CLOUDINARY_CLOUD_NAME / API_KEY / API_SECRET)",
        )

    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()

    allowed_image_exts = (".jpg", ".jpeg", ".png", ".webp", ".gif")
    is_pdf = filename.endswith(".pdf") or content_type == "application/pdf"
    is_image = filename.endswith(allowed_image_exts) or content_type.startswith("image/")

    if not (is_image or is_pdf):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="僅支援上傳圖片 (JPG, PNG, WEBP, GIF) 或 PDF 檔案",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="上傳的檔案內容為空",
        )

    try:
        # 對於 PDF 與圖片，使用 auto 讓 Cloudinary 自動處理並提供公開預覽/下載 URL
        upload_result = cloudinary.uploader.upload(
            file_bytes,
            folder=settings.cloudinary_folder,
            resource_type="auto",
            use_filename=True,
            unique_filename=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cloudinary 上傳失敗: {exc}",
        ) from exc

    secure_url = upload_result.get("secure_url", "")
    preview_url = build_preview_image_url(secure_url) if is_image else secure_url

    return {
        "url": secure_url,
        "preview_url": preview_url,
        "resource_type": "pdf" if is_pdf else "image",
        "format": upload_result.get("format"),
        "public_id": upload_result.get("public_id", ""),
    }
