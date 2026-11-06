import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from app.config import get_settings
from app.database import get_db
from app.services.line_service import find_matching_rule, send_line_reply

logger = logging.getLogger(__name__)

router = APIRouter(tags=["LINE Webhook"])


@router.post("/webhook", summary="LINE Messaging API Webhook 接收端點")
@router.post("/callback", summary="LINE Messaging API Webhook 備用端點")
async def line_webhook(
    request: Request,
    x_line_signature: Optional[str] = Header(None, alias="X-Line-Signature"),
    db: Session = Depends(get_db),
):
    """
    接收並驗證來自 LINE 伺服器的 Webhook 事件：
    1. 驗證 X-Line-Signature 確保請求來自 LINE 官方伺服器
    2. 監聽群組/聊天室/個人文字訊息，忽略貼圖、圖片、語音等非文字訊息
    3. 比對啟用中的關鍵字規則（exact 完全比對 / contains 包含比對）並自動回覆
    """
    settings = get_settings()
    if not settings.line_channel_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="尚未設定 LINE_CHANNEL_SECRET",
        )

    if not x_line_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 X-Line-Signature 標頭",
        )

    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")

    parser = WebhookParser(settings.line_channel_secret)
    try:
        events = parser.parse(body_text, x_line_signature)
    except InvalidSignatureError as exc:
        logger.warning("LINE Webhook 簽章驗證失敗")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Line-Signature",
        ) from exc

    replied_count = 0
    for event in events:
        # 僅處理文字訊息事件 (MessageEvent + TextMessageContent)，自動忽略非文字訊息
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessageContent):
            continue

        incoming_text = event.message.text
        matched_rule = find_matching_rule(db, incoming_text)
        if matched_rule:
            try:
                send_line_reply(event.reply_token, matched_rule)
                replied_count += 1
            except Exception as exc:
                logger.error("發送 LINE 回覆失敗 (keyword=%s): %s", matched_rule.keyword, exc)

    return {"status": "ok", "replied": replied_count}
