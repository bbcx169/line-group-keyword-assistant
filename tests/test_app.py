import base64
import hashlib
import hmac
import io
import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 設定測試環境變數
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LINE_CHANNEL_SECRET"] = "test_channel_secret_12345"
os.environ["LINE_CHANNEL_ACCESS_TOKEN"] = "test_channel_access_token_67890"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "secretpass"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_at_least_32_bytes_long_2026"

from app.config import get_settings

get_settings.cache_clear()

from app.database import Base, get_db
from app.main import app

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "secretpass"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def sign_line_body(body_str: str, secret: str = "test_channel_secret_12345") -> str:
    hash_bytes = hmac.new(
        secret.encode("utf-8"),
        body_str.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(hash_bytes).decode("utf-8")


def test_health_and_admin_ui(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"

    ui_res = client.get("/admin")
    assert ui_res.status_code == 200
    assert "LINE 群組關鍵字助手" in ui_res.text


def test_auth_protection(client):
    # 未帶 Token 存取後台 API 應回傳 401
    res = client.get("/api/keywords")
    assert res.status_code == 401

    # 錯誤帳密登入應回傳 401
    bad_login = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad_login.status_code == 401

    # HTTP Basic Auth 亦可通行
    basic_res = client.get("/api/keywords", auth=("admin", "secretpass"))
    assert basic_res.status_code == 200


def test_keyword_crud_and_toggle(client, auth_headers):
    # 1. 新增關鍵字
    create_res = client.post(
        "/api/keywords",
        headers=auth_headers,
        json={
            "keyword": "菜單",
            "match_type": "exact",
            "reply_type": "image",
            "reply_content": "https://res.cloudinary.com/demo/image/upload/v1/menu.jpg",
            "is_active": True,
        },
    )
    assert create_res.status_code == 201
    created = create_res.json()
    rule_id = created["id"]
    assert created["keyword"] == "菜單"

    # 重複關鍵字應回傳 409
    dup_res = client.post(
        "/api/keywords",
        headers=auth_headers,
        json={
            "keyword": "菜單",
            "match_type": "exact",
            "reply_type": "text",
            "reply_content": "重複測試",
        },
    )
    assert dup_res.status_code == 409

    # 2. 編輯關鍵字
    update_res = client.put(
        f"/api/keywords/{rule_id}",
        headers=auth_headers,
        json={"reply_content": "https://res.cloudinary.com/demo/image/upload/v2/menu_new.jpg"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["reply_content"].endswith("menu_new.jpg")

    # 3. 切換啟用/停用
    toggle_res = client.patch(f"/api/keywords/{rule_id}/toggle", headers=auth_headers)
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_active"] is False

    # 4. 刪除關鍵字
    del_res = client.delete(f"/api/keywords/{rule_id}", headers=auth_headers)
    assert del_res.status_code == 204


def test_csv_import_and_export(client, auth_headers):
    csv_content = (
        "keyword,match_type,reply_type,reply_content,is_active\n"
        "營業時間,contains,text,每日 09:00 - 21:00,true\n"
        "價目表,exact,pdf,https://res.cloudinary.com/demo/image/upload/price.pdf,true\n"
        "錯誤類型測試,invalid_match,text,內容,true\n"
        ",exact,text,缺少關鍵字,true\n"
    )

    files = {"file": ("keywords.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    import_res = client.post("/api/keywords/import/csv", headers=auth_headers, files=files)
    assert import_res.status_code == 200
    result = import_res.json()
    assert result["created"] == 2
    assert result["skipped"] == 2
    assert len(result["errors"]) == 2

    # 再次匯入更新「營業時間」(Upsert)
    csv_update = (
        "keyword,match_type,reply_type,reply_content,is_active\n"
        "營業時間,exact,text,更新後的營業時間 10:00 - 22:00,true\n"
    )
    files2 = {"file": ("update.csv", io.BytesIO(csv_update.encode("utf-8")), "text/csv")}
    import_res2 = client.post("/api/keywords/import/csv", headers=auth_headers, files=files2)
    assert import_res2.status_code == 200
    assert import_res2.json()["updated"] == 1

    # 測試匯出 CSV
    export_res = client.get("/api/keywords/export/csv", headers=auth_headers)
    assert export_res.status_code == 200
    assert "更新後的營業時間 10:00 - 22:00" in export_res.text
    assert "價目表" in export_res.text


@patch("app.routers.webhook.send_line_reply")
def test_line_webhook_signature_and_matching(mock_send_reply, client, auth_headers):
    # 建立測試規則：1. 完全比對 (菜單 -> 圖片)、2. 包含比對 (營業 -> 文字)、3. 停用規則 (隱藏版)
    client.post(
        "/api/keywords",
        headers=auth_headers,
        json={
            "keyword": "菜單",
            "match_type": "exact",
            "reply_type": "image",
            "reply_content": "https://res.cloudinary.com/demo/image/upload/v1/menu.jpg",
            "is_active": True,
        },
    )
    client.post(
        "/api/keywords",
        headers=auth_headers,
        json={
            "keyword": "營業時間",
            "match_type": "contains",
            "reply_type": "text",
            "reply_content": "我們營業時間是 10:00-22:00",
            "is_active": True,
        },
    )
    client.post(
        "/api/keywords",
        headers=auth_headers,
        json={
            "keyword": "停用詞",
            "match_type": "exact",
            "reply_type": "text",
            "reply_content": "不應該觸發",
            "is_active": False,
        },
    )

    # 1. 簽章錯誤應回傳 400
    bad_res = client.post(
        "/webhook",
        headers={"X-Line-Signature": "invalid_sig"},
        content="{}",
    )
    assert bad_res.status_code == 400

    # 2. 群組文字訊息觸發「包含比對」與忽略貼圖訊息
    webhook_payload = {
        "destination": "Uxxxxxxxx",
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "100001",
                    "quoteToken": "qtoken_1",
                    "text": "請問你們今天的營業時間是幾點？",
                },
                "timestamp": 1700000000000,
                "source": {"type": "group", "groupId": "Ca56f94637c...", "userId": "U4af4980629..."},
                "replyToken": "reply_token_group_1",
                "mode": "active",
                "webhookEventId": "01H8X000000000000000000001",
                "deliveryContext": {"isRedelivery": False},
            },
            {
                "type": "message",
                "message": {
                    "type": "sticker",
                    "id": "100002",
                    "quoteToken": "qtoken_2",
                    "packageId": "1",
                    "stickerId": "1",
                    "stickerResourceType": "STATIC",
                },
                "timestamp": 1700000001000,
                "source": {"type": "group", "groupId": "Ca56f94637c..."},
                "replyToken": "reply_token_sticker",
                "mode": "active",
                "webhookEventId": "01H8X000000000000000000002",
                "deliveryContext": {"isRedelivery": False},
            },
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "100003",
                    "quoteToken": "qtoken_3",
                    "text": "停用詞",
                },
                "timestamp": 1700000002000,
                "source": {"type": "group", "groupId": "Ca56f94637c..."},
                "replyToken": "reply_token_inactive",
                "mode": "active",
                "webhookEventId": "01H8X000000000000000000003",
                "deliveryContext": {"isRedelivery": False},
            },
        ],
    }
    body_str = json.dumps(webhook_payload, ensure_ascii=False)
    sig = sign_line_body(body_str)

    ok_res = client.post(
        "/webhook",
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
        content=body_str.encode("utf-8"),
    )
    assert ok_res.status_code == 200
    assert ok_res.json()["replied"] == 1
    assert mock_send_reply.call_count == 1
    called_token, called_rule = mock_send_reply.call_args[0]
    assert called_token == "reply_token_group_1"
    assert called_rule.keyword == "營業時間"


@patch("app.services.cloudinary_service.cloudinary.uploader.upload")
@patch("app.services.cloudinary_service.cloudinary.config")
def test_cloudinary_upload_and_bind_keyword(mock_config, mock_upload, client, auth_headers):
    class DummyCfg:
        cloud_name = "demo_cloud"
        api_key = "12345"
        api_secret = "abcde"

    mock_config.return_value = DummyCfg()
    mock_upload.return_value = {
        "secure_url": "https://res.cloudinary.com/demo_cloud/image/upload/v123/line_keyword_bot/sample.pdf",
        "format": "pdf",
        "public_id": "line_keyword_bot/sample",
    }

    # 先建立一筆關鍵字規則
    kw_res = client.post(
        "/api/keywords",
        headers=auth_headers,
        json={
            "keyword": "型錄",
            "match_type": "exact",
            "reply_type": "text",
            "reply_content": "暫定文字",
            "is_active": True,
        },
    )
    kw_id = kw_res.json()["id"]

    # 上傳 PDF 並同時指定 keyword_id 綁定更新
    files = {"file": ("catalog.pdf", io.BytesIO(b"%PDF-1.4 dummy pdf content"), "application/pdf")}
    up_res = client.post(
        "/api/upload",
        headers=auth_headers,
        files=files,
        data={"keyword_id": str(kw_id)},
    )
    assert up_res.status_code == 200
    up_data = up_res.json()
    assert up_data["resource_type"] == "pdf"
    assert up_data["keyword_updated"] == kw_id

    # 驗證資料庫中的關鍵字回覆類型與內容已自動更新為該 Cloudinary URL
    check_res = client.get(f"/api/keywords/{kw_id}", headers=auth_headers)
    assert check_res.json()["reply_type"] == "pdf"
    assert check_res.json()["reply_content"] == up_data["url"]
