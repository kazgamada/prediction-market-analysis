---
name: nextjs-supabase-init
description: 新規の Next.js 14 (App Router) + TypeScript + Tailwind CSS + Supabase プロジェクトをゼロから立ち上げるときに使う。`create-next-app` からの初期化、Supabase クライアント設定（server / client / middleware の3種）、認証（Magic Link / OAuth）、RLS ポリシーの雛形、`src/types/database.ts` への型生成までを一括でセットアップする。新規ツールのリポジトリ作成直後、または既存リポジトリに Supabase を後付け導入するとき、「新しいツールを作りたい」「Supabase を入れて」と言われたときにトリガー。
---

# Next.js + Supabase 初期セットアップ

## 概要

Kaz の標準スタック（Next.js 14 App Router / TypeScript strict / Tailwind CSS / Supabase）で新規プロジェクトを立ち上げる際の決まった手順をテンプレ化する Skill。毎回同じコマンドと同じディレクトリ構造を再現する。

## 使用タイミング

- 新しいツールリポジトリを作成した直後
- 既存プロジェクトに Supabase を導入する場合
- ユーザーが「新しいツールを作る」「プロジェクトを初期化して」と指示した場合

## 手順

TODO: 追記予定

想定する手順（概要）:

1. `pnpm create next-app@latest` で App Router + TypeScript + Tailwind 構成を生成
2. `@supabase/supabase-js` と `@supabase/ssr` をインストール
3. `src/lib/supabase/` に `client.ts`, `server.ts`, `middleware.ts` を配置
4. `middleware.ts`（ルート直下）でセッション Cookie を同期
5. `.env.local.example` を配置（`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`）
6. 認証ページ（`/login`, `/auth/callback`）の雛形
7. 初期 migration（`users_profiles` テーブル + RLS）
8. `supabase gen types typescript` で `src/types/database.ts` を生成

## 補助ファイル

- `templates/.env.example` - 環境変数テンプレート（作成予定）

## 備考

- Supabase プロジェクトは事前に Dashboard で作成しておくこと（この Skill では自動化しない）
- `service_role` キーは **絶対にクライアント側で使わない**
