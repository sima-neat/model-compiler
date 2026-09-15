# 私有上游變更紀錄

元件掃描器會將解析後的資訊清單，與工作流程啟動時擷取的精確 `develop` SHA 比較。`component-updates.*.*.upstream` 將套件名稱對應到 Jenkins 工作與 Bitbucket 儲存庫。若版本轉換相同，兩種架構共用報告。指定其他來源的試跑則以該來源 SHA 為基準。

已完成的 Jenkins 建置、來源修訂及去除重複的提交，保存在 `model-compiler/build-records/records/`。比較結果以基準 SHA 和解析後資訊清單的 SHA-256 為索引，保存在 `model-compiler/build-records/comparisons/`。不快取執行中的建置。報告會明確標示遺失的歷史與修訂、跨分支比較及未確認的 SCM 歸屬。共用 Jenkins 程式庫的提交不會被列為元件變更；歸屬不明的項目會在私有附件中分開列出。

詳細 Markdown 報告只會以 Slack 附件傳送，訊息包含簡短摘要。這是候選版本解析結果，不代表建置成功。既有建置結果通知保持獨立。變更紀錄不會上傳為 GitHub 成果物、加入工作摘要或 PR、提交至 Git，或透過 Vulcan 公開發布。即使步驟失敗，也會刪除暫存檔。試跑不會上傳歷史或傳送 Slack 訊息。

## 部署

設定儲存庫機密 `JENKINS_USERNAME`、`JENKINS_API_TOKEN`、`SLACK_BOT_TOKEN`。Slack 機器人需要 `files:write` 和 `SLACK_VULCAN_EVENT_CHANNEL_ID` 頻道的存取權。由內部 macOS 掃描器查詢 Jenkins。

先套用配套的 Vulcan 變更，在 CloudFront 與 S3 政策中封鎖 `model-compiler/build-records` 的公開讀取，再設定 `UPSTREAM_CHANGELOG_ENABLED=true`。沿用 Vulcan 設定取得儲存桶、角色、區域及 KMS 金鑰。角色必須能檢查儲存桶政策與公開存取封鎖、讀寫私有路徑並使用 KMS。若無法確認所有 S3 公開存取封鎖及無條件 CloudFront 拒絕規則，便中止儲存。上傳使用 KMS 加密，且不更新公開索引。

停用保存時仍可傳送 Slack，但只能使用 Jenkins 尚未刪除的紀錄。Jenkins 故障會標示為證據不完整。Slack 傳送或已設定的儲存服務失敗會使掃描失敗。單元測試不會實際傳送訊息或部署基礎設施。

部署工作流程時，也必須將 `id-token: write` 權限變更套用至預設分支的 `update-components.yml`。可重複使用的工作流程無法提升呼叫端權限。
