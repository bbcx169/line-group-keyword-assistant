import logging
from typing import Optional
from sqlalchemy.orm import Session
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    ImageMessage,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from app.config import get_settings
from app.models import KeywordRule, MatchType, ReplyType
from app.services.cloudinary_service import (
    build_attachment_download_url,
    build_preview_image_url,
)

logger = logging.getLogger(__name__)


def split_keywords(keyword_str: str) -> list[str]:
    """將關鍵字欄位支援逗號、頓號、斜線、換行拆分成多個同義關鍵字"""
    if not keyword_str:
        return []
    # 支援逗號(半形/全形)、頓號、斜線、直線或換行分隔
    normalized = (
        keyword_str.replace("，", ",")
        .replace("、", ",")
        .replace("/", ",")
        .replace("|", ",")
        .replace("\n", ",")
    )
    tokens = [k.strip() for k in normalized.split(",") if k.strip()]
    return tokens if tokens else [keyword_str.strip()]


def find_matching_rule(db: Session, message_text: str) -> Optional[KeywordRule]:
    """
    比對關鍵字規則：
    1. 只搜尋 is_active == True 的規則
    2. 支援「多關鍵字/別名」：欄位若填寫「裁處基準、罰鍰、裁罰基準」，自動拆分逐一比對
    3. 優先比對 exact（完全比對，輸入文字完全等於其中任一關鍵字）
    4. 若無命中 exact，再比對 contains（包含比對，輸入文字中包含其中任一關鍵字，字數長者優先）
    """
    if not message_text:
        return None

    cleaned_text = message_text.strip()
    if not cleaned_text:
        return None

    active_rules = db.query(KeywordRule).filter(KeywordRule.is_active.is_(True)).all()
    if not active_rules:
        return None

    # 1. 完全比對 (exact)
    for rule in active_rules:
        if rule.match_type == MatchType.exact:
            aliases = split_keywords(rule.keyword)
            if cleaned_text in aliases:
                return rule

    # 2. 包含比對 (contains) - 依各關鍵字長度由長至短排序，避免短詞誤攔截長詞
    contains_candidates = []
    for rule in active_rules:
        if rule.match_type == MatchType.contains:
            aliases = split_keywords(rule.keyword)
            for alias in aliases:
                contains_candidates.append((alias, rule))

    contains_candidates.sort(key=lambda item: len(item[0]), reverse=True)

    for alias, rule in contains_candidates:
        if alias in cleaned_text:
            return rule

    return None


def build_line_reply_messages(rule: KeywordRule):
    """
    依據 KeywordRule 的 reply_type 組裝 LINE Messaging API 訊息物件列表（最多 5 則）：
    - text: 純文字訊息 (TextMessage)
    - image: 圖片訊息 (ImageMessage)，支援單行或多行 URL（換行或逗號分隔，最多 5 張圖片）
    - pdf: 文字訊息附上 Cloudinary PDF 檔案下載/預覽連結（支援多個連結）
    """
    lines = [line.strip() for line in rule.reply_content.replace(",", "\n").splitlines() if line.strip()]

    if rule.reply_type == ReplyType.image:
        image_messages = []
        for img_url in lines[:5]:
            preview_url = build_preview_image_url(img_url)
            image_messages.append(
                ImageMessage(
                    original_content_url=img_url,
                    preview_image_url=preview_url,
                )
            )
        if image_messages:
            return image_messages
        # 防呆：若無解析到有效網址，退回文字訊息
        return [TextMessage(text=rule.reply_content)]

    if rule.reply_type == ReplyType.pdf:
        pdf_urls = [build_attachment_download_url(u) for u in lines]
        pdf_links_text = "\n".join(pdf_urls)
        text_body = f"📄 【{rule.keyword}】檔案下載連結：\n{pdf_links_text}"
        return [TextMessage(text=text_body)]

    # 預設純文字
    return [TextMessage(text=rule.reply_content)]


def send_line_reply(reply_token: str, rule: KeywordRule) -> None:
    """發送 LINE Reply Message（單次最多發送 5 則訊息氣泡）"""
    settings = get_settings()
    if not settings.line_channel_access_token:
        logger.warning("尚未設定 LINE_CHANNEL_ACCESS_TOKEN，略過實際發送 Reply Message")
        return

    messages = build_line_reply_messages(rule)
    configuration = Configuration(access_token=settings.line_channel_access_token)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=messages,
            )
        )
