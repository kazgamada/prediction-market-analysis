---
name: make-webhook-integration
description: Make.com の Webhook と Next.js / Supabase を連携させる実装を行うときに使う。Next.js API Route（App Router の Route Handler）または Supabase Edge Function 側で Make.com からの Webhook ペイロードを受信する、または逆に Make.com へ Webhook を送信する実装パターンを提供する。署名検証、リトライ戦略、べき等性、エラー時の Make.com への通知、「X/Twitter → LINE → Google Sheets → Make.com」のようなパイプライン組み込み全般。ユーザーが「Make と連携」「Webhook を受ける」「Make.com に送る」「外部サービス連携」と言及したときにトリガー。
---

# Make.com Webhook 連携パターン集

## 概要

Kaz の既存ツール群では Make.com を自動化のハブとして多用している。この Skill は、Next.js / Supabase と Make.com をつなぐ際の再利用可能なパターンをまとめる。

## 使用タイミング

- Next.js API Route で Make.com からの Webhook を受ける実装
- Supabase Edge Function / DB Trigger から Make.com の Webhook へ送信する実装
- 「X → LINE → Google Sheets → Make.com」などの既存パイプラインの一部を変更するとき
- Make.com のシナリオ結果を Supabase に書き戻すとき

## 手順

TODO: 追記予定

想定する構成:

### A. Make.com から受信（Webhook In）

1. Next.js の Route Handler（`app/api/webhooks/make/route.ts`）を作成
2. Make.com 側で Custom Webhook URL を発行し、ペイロードを送信
3. 共有シークレット（ヘッダ `X-Webhook-Secret`）で認証
4. ペイロードを Zod でバリデーション
5. Supabase に永続化、必要なら Supabase Realtime でクライアントへ通知

### B. Make.com へ送信（Webhook Out）

1. Supabase の `postgres_changes` または Edge Function でトリガ
2. `fetch` で Make.com の Webhook URL に POST
3. 失敗時はリトライキュー（`public.webhook_outbox` テーブル）に積む
4. Cron（Supabase Scheduled Function or Vercel Cron）で再送

### C. べき等性

- Make.com は同じイベントを2回送る可能性がある
- ペイロードに一意な ID（`event_id` 等）を含めてもらう
- 受信側で `event_id` を primary key / unique 制約にして upsert

## 補助ファイル

TODO: `examples/route-handler-template.ts`, `examples/outbox-migration.sql` を追加予定

## 備考

- Webhook URL は環境変数で管理（`MAKE_WEBHOOK_URL`）
- シークレットは `MAKE_WEBHOOK_SECRET`（サーバーサイドのみ）
- Make.com 側のシナリオ ID もコード側にコメントで書き残す（運用中の特定が楽になる）
