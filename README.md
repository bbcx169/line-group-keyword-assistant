# LINE 群組關鍵字助手 (LINE Group Keyword Assistant)

本專案依據「LINE 群組關鍵字助手需求規格書」開發，結合 **Python + FastAPI + PostgreSQL + LINE Messaging API + Cloudinary**，提供群組訊息自動監聽、關鍵字完全/包含比對、多元格式（文字、圖片、PDF 連結）自動回覆，並內建完整的 **Web 後台管理介面** 與 **CSV 批次匯入/匯出**，可一鍵部署至 **Render** 雲端平台。

---

## 1. 功能特色

### LINE Bot 核心功能
- **Webhook 安全簽章驗證 (`POST /webhook` / `POST /callback`)**：嚴格驗證 `X-Line-Signature` 標頭。
- **群組與聊天室文字監聽**：自動處理群組、多人聊天室與個人對話中的文字訊息，並自動忽略貼圖、語音等非文字事件。
- **雙模式關鍵字比對**：
  - `exact`（完全比對）：訊息內容與關鍵字完全相符時觸發（最高優先權）。
  - `contains`（包含比對）：訊息中包含該關鍵字即觸發（依關鍵字長度由長至短優先比對）。
- **多元回覆格式**：
  - `text`：純文字訊息回覆。
  - `image`：圖片訊息 (`ImageMessage`)，自動結合 Cloudinary 動態縮圖轉換產生 `preview_image_url`。
  - `pdf`：以文字訊息附上 Cloudinary 的 PDF 預覽/下載連結。

### 後台管理系統 (`/admin` 或 `/`)
- **身分驗證保護**：支援 JWT Bearer Token（Web 登入）與 HTTP Basic Auth，保護所有後台 API。
- **關鍵字 CRUD 與即時開關**：支援新增、編輯、刪除、搜尋篩選，以及一鍵啟用/停用 (`is_active`)。
- **Cloudinary 媒體直傳 (`POST /api/upload`)**：於後台選擇圖片或 PDF 即可直接上傳至 Cloudinary，並自動將公開 URL 帶入或寫入資料庫對應的關鍵字規則。
- **CSV 批次匯出/匯入**：
  - **匯出 (`GET /api/keywords/export/csv`)**：含 UTF-8 BOM，Excel 直接開啟不亂碼。
  - **匯入 (`POST /api/keywords/import/csv`)**：支援批次新增與更新 (Upsert)，具備欄位防呆檢查與錯誤列號報告。

---

## 2. 本機開發與啟動步驟

### 2.1 安裝套件
```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

### 2.2 設定環境變數
複製 `.env.example` 為 `.env` 並填入您的設定：
```bash
cp .env.example .env
```

### 2.3 執行 Alembic 資料庫遷移
```bash
alembic upgrade head
```

### 2.4 啟動伺服器
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- **後台管理介面**：http://localhost:8000/admin
- **Swagger API 文件**：http://localhost:8000/docs
- **LINE Webhook URL**：`https://<您的網域>/webhook`

### 2.5 執行自動化測試
```bash
pytest -v
```

---

## 3. Render 雲端部署指南

1. **建立 GitHub 儲存庫**並將本專案程式碼推送至 `main` 分支。
2. **於 Render 建立部署**：
   - **方式 A (Blueprint 自動建立)**：於 Render Dashboard 點選 **New + -> Blueprint**，連結 GitHub 儲存庫，Render 會自動讀取 `render.yaml` 建立 PostgreSQL 實例與 Web Service。
   - **方式 B (手動建立)**：
     1. 先建立 **Render PostgreSQL**，複製 `Internal Database URL`。
     2. 建立 **Render Web Service**，設定：
        - **Build Command**: `pip install -r requirements.txt`
        - **Start Command**: `bash start.sh`
3. **設定 Render 環境變數 (Environment Variables)**：
   - `DATABASE_URL`：填入 Render PostgreSQL 的 Internal Database URL。
   - `LINE_CHANNEL_SECRET`：LINE Developers Console 取得的 Channel Secret。
   - `LINE_CHANNEL_ACCESS_TOKEN`：LINE Developers Console 取得的 Channel Access Token。
   - `CLOUDINARY_URL`：Cloudinary 控制台取得的 `cloudinary://api_key:api_secret@cloud_name`。
   - `ADMIN_USERNAME` / `ADMIN_PASSWORD`：後台登入帳號與密碼。
4. **LINE Developers Console 設定**：
   - 將 Webhook URL 設為 `https://<您的-render-服務名稱>.onrender.com/webhook` 並開啟 **Use webhook**。
   - 關閉官方預設的「自動回應訊息 (Auto-reply messages)」。
   - 開啟「加入群組或多人聊天室 (Allow bot to join group chats)」權限。
