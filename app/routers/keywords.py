import csv
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models import KeywordRule, MatchType, ReplyType
from app.schemas import (
    CSVImportErrorItem,
    CSVImportResult,
    KeywordCreate,
    KeywordResponse,
    KeywordUpdate,
)

router = APIRouter(prefix="/api/keywords", tags=["Keywords Admin"])


@router.get("", response_model=List[KeywordResponse], summary="取得關鍵字規則列表")
def list_keywords(
    search: Optional[str] = Query(None, description="搜尋關鍵字或回覆內容"),
    match_type: Optional[MatchType] = Query(None, description="篩選比對方式"),
    reply_type: Optional[ReplyType] = Query(None, description="篩選回覆類型"),
    is_active: Optional[bool] = Query(None, description="篩選啟用狀態"),
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    query = db.query(KeywordRule)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            (KeywordRule.keyword.ilike(pattern)) | (KeywordRule.reply_content.ilike(pattern))
        )
    if match_type is not None:
        query = query.filter(KeywordRule.match_type == match_type)
    if reply_type is not None:
        query = query.filter(KeywordRule.reply_type == reply_type)
    if is_active is not None:
        query = query.filter(KeywordRule.is_active == is_active)

    return query.order_by(KeywordRule.id.desc()).all()


@router.post("", response_model=KeywordResponse, status_code=status.HTTP_201_CREATED, summary="新增關鍵字規則")
def create_keyword(
    payload: KeywordCreate,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    existing = db.query(KeywordRule).filter(KeywordRule.keyword == payload.keyword).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"關鍵字「{payload.keyword}」已存在，請直接編輯或使用其他名稱",
        )

    rule = KeywordRule(
        keyword=payload.keyword,
        match_type=payload.match_type,
        reply_type=payload.reply_type,
        reply_content=payload.reply_content,
        is_active=payload.is_active,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/export/csv", summary="匯出全部關鍵字為 CSV 檔案")
def export_keywords_csv(
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """將現有的關鍵字資料表下載為 UTF-8 BOM CSV 檔案，方便 Excel 檢視或備份"""
    rules = db.query(KeywordRule).order_by(KeywordRule.id.asc()).all()

    output = io.StringIO()
    # 寫入 UTF-8 BOM 讓 Microsoft Excel 正確識別中文編碼
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["keyword", "match_type", "reply_type", "reply_content", "is_active"])

    for r in rules:
        writer.writerow([
            r.keyword,
            r.match_type.value if isinstance(r.match_type, MatchType) else r.match_type,
            r.reply_type.value if isinstance(r.reply_type, ReplyType) else r.reply_type,
            r.reply_content,
            "true" if r.is_active else "false",
        ])

    output.seek(0)
    headers = {
        "Content-Disposition": 'attachment; filename="keywords_export.csv"',
    }
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


@router.post("/import/csv", response_model=CSVImportResult, summary="批次匯入 CSV 關鍵字規則")
async def import_keywords_csv(
    file: UploadFile = File(..., description="CSV 檔案 (需包含 keyword, match_type, reply_type, reply_content, is_active)"),
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """
    上傳 CSV 檔批次新增或更新關鍵字規則（具備防呆驗證與錯誤列號回報）：
    - 若關鍵字已存在：自動更新該筆規則 (Upsert)
    - 若關鍵字不存在：自動新增規則
    - 若某列格式錯誤（如無效的 match_type / reply_type 或空內容）：記錄於 errors 清單並繼續處理其餘有效列
    """
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="上傳的 CSV 檔案為空",
        )

    # 支援 UTF-8 (含 BOM) 與 Big5/CP950 (常見台灣 Excel 匯出編碼)
    decoded_text = None
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            decoded_text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if decoded_text is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無法解析 CSV 檔案編碼，請使用 UTF-8 或標準 CSV 格式儲存",
        )

    reader = csv.DictReader(io.StringIO(decoded_text))
    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV 檔案缺少標題列 (Header)",
        )

    normalized_headers = [h.strip().lower() for h in reader.fieldnames if h]
    required_columns = {"keyword", "reply_content"}
    missing_cols = required_columns - set(normalized_headers)
    if missing_cols:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV 標題列缺少必要欄位: {', '.join(sorted(missing_cols))}（必須包含 keyword, reply_content）",
        )

    created_count = 0
    updated_count = 0
    skipped_count = 0
    errors: List[CSVImportErrorItem] = []

    for row_idx, row in enumerate(reader, start=2):  # 第 1 列為 Header，資料從第 2 列開始
        # 將 key 正規化為小寫並去除空白
        clean_row = {(k.strip().lower() if k else ""): (v.strip() if v is not None else "") for k, v in row.items()}

        # 若整列皆為空白則略過
        if not any(clean_row.values()):
            continue

        kw = clean_row.get("keyword", "")
        reply_content = clean_row.get("reply_content", "")
        match_type_str = clean_row.get("match_type", "exact").lower() or "exact"
        reply_type_str = clean_row.get("reply_type", "text").lower() or "text"
        is_active_str = clean_row.get("is_active", "true").lower() or "true"

        if not kw:
            skipped_count += 1
            errors.append(CSVImportErrorItem(row=row_idx, keyword="", error="關鍵字 (keyword) 不可為空"))
            continue

        if not reply_content:
            skipped_count += 1
            errors.append(CSVImportErrorItem(row=row_idx, keyword=kw, error="回覆內容 (reply_content) 不可為空"))
            continue

        try:
            match_type_enum = MatchType(match_type_str)
        except ValueError:
            skipped_count += 1
            errors.append(
                CSVImportErrorItem(
                    row=row_idx,
                    keyword=kw,
                    error=f"無效的 match_type「{match_type_str}」，僅支援 exact 或 contains",
                )
            )
            continue

        try:
            reply_type_enum = ReplyType(reply_type_str)
        except ValueError:
            skipped_count += 1
            errors.append(
                CSVImportErrorItem(
                    row=row_idx,
                    keyword=kw,
                    error=f"無效的 reply_type「{reply_type_str}」，僅支援 text, image 或 pdf",
                )
            )
            continue

        if is_active_str in ("true", "1", "yes", "y", "啟用", "是"):
            is_active_val = True
        elif is_active_str in ("false", "0", "no", "n", "停用", "否"):
            is_active_val = False
        else:
            skipped_count += 1
            errors.append(
                CSVImportErrorItem(
                    row=row_idx,
                    keyword=kw,
                    error=f"無效的 is_active「{is_active_str}」，請填寫 true 或 false",
                )
            )
            continue

        existing_rule = db.query(KeywordRule).filter(KeywordRule.keyword == kw).first()
        if existing_rule:
            existing_rule.match_type = match_type_enum
            existing_rule.reply_type = reply_type_enum
            existing_rule.reply_content = reply_content
            existing_rule.is_active = is_active_val
            updated_count += 1
        else:
            new_rule = KeywordRule(
                keyword=kw,
                match_type=match_type_enum,
                reply_type=reply_type_enum,
                reply_content=reply_content,
                is_active=is_active_val,
            )
            db.add(new_rule)
            created_count += 1

    db.commit()
    return CSVImportResult(
        created=created_count,
        updated=updated_count,
        skipped=skipped_count,
        errors=errors,
    )


@router.get("/{keyword_id}", response_model=KeywordResponse, summary="查詢單筆關鍵字規則")
def get_keyword(
    keyword_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    rule = db.query(KeywordRule).filter(KeywordRule.id == keyword_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該筆關鍵字規則")
    return rule


@router.put("/{keyword_id}", response_model=KeywordResponse, summary="更新關鍵字規則")
def update_keyword(
    keyword_id: int,
    payload: KeywordUpdate,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    rule = db.query(KeywordRule).filter(KeywordRule.id == keyword_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該筆關鍵字規則")

    if payload.keyword is not None and payload.keyword != rule.keyword:
        conflict = db.query(KeywordRule).filter(KeywordRule.keyword == payload.keyword).first()
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"關鍵字「{payload.keyword}」已被其他規則使用",
            )
        rule.keyword = payload.keyword

    if payload.match_type is not None:
        rule.match_type = payload.match_type
    if payload.reply_type is not None:
        rule.reply_type = payload.reply_type
    if payload.reply_content is not None:
        rule.reply_content = payload.reply_content.strip()
    if payload.is_active is not None:
        rule.is_active = payload.is_active

    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{keyword_id}/toggle", response_model=KeywordResponse, summary="快速切換關鍵字啟用/停用狀態")
def toggle_keyword_status(
    keyword_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    rule = db.query(KeywordRule).filter(KeywordRule.id == keyword_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該筆關鍵字規則")

    rule.is_active = not rule.is_active
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT, summary="刪除關鍵字規則")
def delete_keyword(
    keyword_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    rule = db.query(KeywordRule).filter(KeywordRule.id == keyword_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該筆關鍵字規則")

    db.delete(rule)
    db.commit()
    return None
