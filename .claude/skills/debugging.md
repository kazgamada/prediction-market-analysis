---
name: debugging
description: >-
  バグ・不具合報告を受けたときに厳守すべき修正ワークフロー。 Next.js/TypeScript
  プロジェクト全般（API連携・DB・表示不具合など）に適用する。 「動かない」報告を受けたら必ずこのスキルを参照してからコードに触れること。
category: debugging
version: 4
effectiveTimestamp: '2026-05-27T00:00:00.000Z'
sourceSkillIds:
  - a50bbc64
  - f6371710
generatedAt: '2026-06-17'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-25T00:00:00.000Z'
adoptedFromArchive:
  - archive/skills/troubleshoot-supabase-shopify.md
  - archive/skills/debugging.md
---

# デバッグ修正ワークフロー（厳守）

> **このワークフローは省略不可。コードに触れる前に必ず全ステップを実行すること。**
>
> 適用範囲: Next.js / TypeScript プロジェクト全般
> （API 連携・DB クエリ・外部サービス連携・表示不具合など）

---

## 統合方針メモ

- `aegis-market-os / debugging`（effectiveTimestamp: 2026-05-26）を主軸として採用
- `glabaffil / troubleshoot-supabase-shopify`（changedAt: 2026-05-25）の Supabase / Shopify 固有パターンを「よくある根本原因」セクションに吸収
- 両者の「ワークフロー主体」方針は一致しているため衝突なし
- Supabase / Shopify 固有の用語は「外部サービス連携」として抽象化し、汎用性を維持

---

## フェーズ 0 — 報告受領（コードに触れる前）

```
1. 症状を一行で言語化する
   例: "商品一覧が 0 件表示される"

2. 再現条件を確定する
   - 環境（local / staging / production）
   - 操作手順（URL / ボタン / API コール）
   - 発生頻度（常時 / 特定条件のみ）

3. 期待値と実際値を並べる
   期待: 商品 42 件表示
   実際: 0 件表示
```

> ⛔ この 3 点が揃う前にコードを変更してはならない。

---

## フェーズ 1 — 仮説を立てる（原因を絞る）

### 1-1. 症状レイヤーの特定

```
UI 表示崩れ
  └─ CSS / 条件分岐 / null 安全
データ件数の不一致
  └─ DB クエリ条件 / フィルタ / ページネーション
API エラー
  └─ 認証 / レート制限 / スキーマ不一致
型エラー / ランタイムエラー
  └─ TypeScript 型 / undefined アクセス / 非同期漏れ
```

### 1-2. よくある根本原因（パターン集）

**DB / ORM クエリ系**
```typescript
// ❌ フィルタ条件の抜け（Supabase例）
const { data } = await supabase.from('products').select('*')
// ↑ status = 'active' フィルタが抜けると全件または0件になる

// ✅ 条件を明示
const { data, error } = await supabase
  .from('products')
  .select('*')
  .eq('status', 'active')
  .order('created_at', { ascending: false })

// 確認コマンド（汎用）
// → DB クライアントで同じクエリを直接実行して件数を比較する
```

**外部 API 連携系**
```typescript
// ❌ エラーハンドリング漏れ（Shopify等のREST/GraphQL API）
const response = await fetch(apiUrl, { headers })
const data = await response.json() // エラーレスポンスを素通し

// ✅ ステータスコードを必ず確認
const response = await fetch(apiUrl, { headers })
if (!response.ok) {
  const errorBody = await response.text()
  throw new Error(`API ${response.status}: ${errorBody}`)
}
const data = await response.json()
```

**Next.js キャッシュ / revalidate 系**
```typescript
// ❌ fetch キャッシュが古いデータを返す
const res = await fetch(url) // デフォルトは force-cache

// ✅ 動的データは明示的に no-store
const res = await fetch(url, { cache: 'no-store' })

// または revalidate を設定
const res = await fetch(url, { next: { revalidate: 60 } })
```

**TypeScript / null 安全系**
```typescript
// ❌ undefined アクセス
const name = user.profile.name // profile が null の場合クラッシュ

// ✅ オプショナルチェーンでガード
const name = user?.profile?.name ?? '未設定'
```

**非同期処理系**
```typescript
// ❌ await 漏れ
const data = fetchData() // Promise のまま使用してしまう

// ✅ 必ず await
const data = await fetchData()
```

---

## フェーズ 2 — ログ収集（変更前）

```
確認順序（上から順に）:
1. ブラウザ DevTools → Console / Network タブ
2. サーバーログ（next dev の標準出力 / Vercel Functions ログ）
3. 外部サービスダッシュボード（API ログ・DB ログ等）
4. 型チェック: npx tsc --noEmit
5. Lint:      npx eslint . --ext .ts,.tsx
```

```typescript
// デバッグ用ログの挿入パターン
console.log('[DEBUG][コンポーネント名]', {
  入力値: input,
  クエリ結果件数: data?.length,
  エラー: error,
  timestamp: new Date().toISOString(),
})
```

> ✅ ログで「どこまでは正しいか」を確定してから次へ進む。

---

## フェーズ 3 — 最小再現を作る

```
目的: 関係ないコードを排除し、原因を一点に絞る

手順:
1. 疑わしい処理を単独で実行できるか確認
   - API ハンドラ → curl / Postman で直接叩く
   - DB クエリ   → クライアントツールで直接実行
   - コンポーネント → Storybook / 単体テスト

2. ダミーデータに差し替えて UI が正しく動くか確認
   → YES: データ取得層が原因
   → NO : 表示層が原因

3. 最小再現ができたらコメントに記録
   // 再現: products が [] のとき CardList が null を返す
```

---

## フェーズ 4 — 修正する

### 修正の原則

```
1. 一度に変更するファイルは 1〜2 ファイ
