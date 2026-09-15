# 非公開の上流変更履歴

コンポーネントスキャナーは、解決済みマニフェストをワークフロー開始時に取得した `develop` の正確な SHA と比較します。`component-updates.*.*.upstream` はパッケージ名を Jenkins ジョブと Bitbucket リポジトリに対応付けます。バージョン遷移が同じ場合、両アーキテクチャはレポートを共有します。別のソースを指定したドライランでは、そのソース SHA を基準にします。

完了した Jenkins ビルド、ソースリビジョン、重複を除いたコミットを `model-compiler/build-records/records/` に保存します。比較結果は基準 SHA と解決済みマニフェストの SHA-256 をキーとして `model-compiler/build-records/comparisons/` に保存します。実行中のビルドは保存しません。欠落した履歴、リビジョン、ブランチ間比較、未確認の SCM 帰属を明示します。共有 Jenkins ライブラリのコミットをコンポーネントの変更として表示せず、帰属が不明な項目は添付ファイル内で区別します。

詳細は短い抜粋と Markdown ファイルとして Slack のみに送信します。これは候補の解決結果であり、ビルド成功通知ではありません。既存のビルド結果通知は別途送信されます。変更履歴を GitHub アーティファクト、ジョブ概要、PR、Git、Vulcan の公開成果物に掲載しません。一時ファイルは失敗時も削除します。ドライランでは履歴のアップロードや Slack 送信を行いません。

## 導入

`JENKINS_USERNAME`、`JENKINS_API_TOKEN`、`SLACK_BOT_TOKEN` をリポジトリのシークレットに設定します。Slack ボットには `files:write` と `SLACK_VULCAN_EVENT_CHANNEL_ID` のチャンネルへのアクセスが必要です。Jenkins への問い合わせは社内 macOS スキャナーで実行します。

関連する Vulcan 変更を適用し、CloudFront と S3 ポリシーで `model-compiler/build-records` の公開読み取りを拒否してから `UPSTREAM_CHANGELOG_ENABLED=true` を設定します。既存の Vulcan 設定からバケット、ロール、リージョン、KMS キーを取得します。ロールにはバケットポリシーと公開アクセスブロックの確認、非公開プレフィックスの読み書き、KMS 利用権限が必要です。公開アクセスブロックと無条件の CloudFront 拒否を確認できない場合、保存を中止します。公開インデックスは更新しません。

保存が無効でも Slack 通知は利用できますが、Jenkins に残る履歴のみ参照できます。Jenkins 障害は証拠不足として報告します。Slack 送信や設定済みストレージの失敗はスキャンを失敗させます。単体テストは実際の送信やインフラのデプロイを行いません。

ワーカーの導入時には、既定ブランチの `update-components.yml` にも `id-token: write` の変更を反映してください。再利用可能なワークフローは呼び出し元の権限を昇格できません。
