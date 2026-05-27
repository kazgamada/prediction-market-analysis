---
name: debugging
description: >-
  バグ・不具合報告を受けたときに厳守すべき修正ワークフロー。 Next.js/TypeScript
  プロジェクト全般（API連携・DB・表示不具合など）に適用する。 「動かない」報告を受けたら必ずこのスキルを参照してからコードに触れること。
category: debugging
version: 3
effectiveTimestamp: '2026-05-26T00:00:00.000Z'
sourceSkillIds:
  - a50bbc64
  - f6371710
generatedAt: '2026-05-27'
---

# デバッグ修正ワークフロー（厳守）

> **このワークフローは省略不可。コードに触れる前に必ず全ステップを実行すること。**
>
> 適用範囲: Next.js/TypeScript プロジェクト全般  
> （REST/GraphQL API 連携・DB クエリ・表示不具合・外部サービス連携 等）

---

## STEP 0 — このスキルを開く（前提確認）

バグ・不具合報告を受けたら **最初にこのファイルを開き**、以下を確認する。

| 確認項目 | OK? |
|---|---|
| 再現手順を口頭またはテキストで説明できる | ☐ |
| 影響範囲（画面/API/DB）を1行で言える | ☐ |
| 「たぶんこれが原因」という仮説を一旦棚上げした | ☐ |

---

## STEP 1 — 事実の収集（仮説より先に証拠を集める）

### 1-1. エラーメッセージ・ログを取得する

```bash
# ブラウザコンソール / Node プロセスログをそのままコピー
# スタックトレースは末尾まで省略しない
```

確認すべき場所:

- ブラウザ DevTools → Console / Network タブ
- Next.js サーバーログ（`next dev` / `next start` の標準出力）
- 外部サービス管理画面のログ（Supabase Logs, Shopify Partners, Vercel Functions 等）
- DB クライアントのクエリログ・スロークエリログ

### 1-2. 再現条件を特定する

```
再現率: 常に / 特定操作後のみ / 稀に
環境:   local / staging / production
ユーザー: 全員 / 特定ロール / 特定ID
```

### 1-3. 「最後に動いていた状態」を確認する

```bash
git log --oneline -20        # 直近の変更履歴
git diff HEAD~1 HEAD -- <疑わしいファイル>
```

---

## STEP 2 — 仮説の列挙と優先付け

証拠が揃ったら初めて仮説を立てる。**3つ以上**挙げてから絞る。

| # | 仮説 | 根拠（ログ/コード行） | 確認コスト |
|---|---|---|---|
| 1 | | | 低/中/高 |
| 2 | | | 低/中/高 |
| 3 | | | 低/中/高 |

> **アンチパターン**: 最初に浮かんだ仮説だけを追いかけてコードを書き換える。
> 必ず複数仮説を並列検討してから手を動かす。

---

## STEP 3 — 最小再現と仮説検証

### 3-1. 最小再現ケースを作る

- 影響範囲を **1ファイル / 1エンドポイント / 1コンポーネント** まで絞る
- 外部依存（API・DB）を可能な限りモックして切り離す

```typescript
// 例: API 呼び出しを切り離して UI ロジックだけ確認
const mockData = { id: 1, status: "active" } satisfies Product;
```

### 3-2. 追加ログで仮説を検証する

```typescript
// 削除前提のデバッグログは TODO コメントで明示
// TODO: debug - remove before merge
console.log("[DEBUG] fetchProducts response:", JSON.stringify(res, null, 2));
```

### 3-3. よくある原因チェックリスト

#### API / ネットワーク

- [ ] レスポンスの HTTP ステータスを確認した（200 以外の扱い）
- [ ] ページネーション・レート制限に引っかかっていないか
- [ ] 環境変数（`NEXT_PUBLIC_*` / サーバーサイド専用）の混在がないか
- [ ] キャッシュ（fetch cache / CDN / ブラウザキャッシュ）が古い状態を返していないか

#### DB / クエリ

- [ ] フィルタ・JOIN 条件が意図どおりか（実際のクエリをログ出力して確認）
- [ ] NULL 値・空配列の扱いが意図どおりか
- [ ] トランザクション境界・楽観的ロックの競合がないか
- [ ] インデックスが効いているか（EXPLAIN / EXPLAIN ANALYZE）

#### TypeScript / 型

- [ ] `as` キャストや `!` 非 null アサーションで型エラーを隠していないか
- [ ] `unknown` / `any` の境界で実行時エラーが起きていないか
- [ ] Zod 等のランタイムバリデーションが期待どおり動いているか

#### Next.js 特有

- [ ] Server Component / Client Component の境界が正しいか（`"use client"` の有無）
- [ ] `getServerSideProps` / `getStaticProps` / Server Actions のデータが古くないか
- [ ] Route Handler の `dynamic = "force-dynamic"` / `revalidate` 設定が意図どおりか
- [ ] Middleware でリクエストが意図せず書き換えられていないか

---

## STEP 4 — 修正と影響範囲の確認

### 4-1. 修正方針を決める（コードを書く前に）

```
修正方針: <1〜2行で記述>
変更ファイル: <変更予定ファイルのリスト>
リグレッションリスク: 低 / 中（理由: ）/ 高（理由: ）
```

### 4-2. 修正を実装する

- **1つの仮説につき1つのコミット** を目安にする
- デバッグ用 `console.log` は必ず削除してからコミット
- 型を緩める方向（`any` 化・キャスト追加）の修正は **最終手段**

```typescript
// NG: 型エラーを隠す
const data = response as SomeType;

// OK: 実行時バ
