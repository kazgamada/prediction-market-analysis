---
name: debugging
description: >-
  バグ・不具合報告を受けたときに厳守すべき修正ワークフロー。 Next.js/TypeScript
  プロジェクト全般（API連携・DB・表示不具合など）に適用する。 「動かない」報告を受けたら必ずこのスキルを参照してからコードに触れること。
category: debugging
version: 1
effectiveTimestamp: '2026-05-25T00:00:00.000Z'
sourceSkillIds:
  - f6371710
generatedAt: '2026-05-26'
---

# デバッグ修正ワークフロー（厳守）

> **このワークフローは省略不可。コードに触れる前に必ず全ステップを実行すること。**

---

## STEP 1 — 事実の収集（仮説より先に証拠を集める）

コードを読む前に、以下の情報を確認・収集する。

```
[ ] エラーメッセージの全文（スタックトレース含む）
[ ] 再現手順（どの操作・URLで発生するか）
[ ] 期待値 vs 実際の値（件数・レスポンス・表示など）
[ ] 最後に動作していたタイミング・直前の変更内容
[ ] 環境情報（本番/開発、ブラウザ、ログ出力）
```

**原則**: 「たぶん〇〇が原因」という推測でコードを変更しない。

---

## STEP 2 — 問題の切り分け（層ごとに分離する）

Next.js プロジェクトの典型的な層を上から順に確認する。

```
┌─────────────────────────────┐
│  UI / フロントエンド層       │  ← レンダリング・状態管理・表示ロジック
├─────────────────────────────┤
│  API Route / Server Action  │  ← リクエスト処理・バリデーション
├─────────────────────────────┤
│  ビジネスロジック層          │  ← データ変換・集計・フィルタリング
├─────────────────────────────┤
│  外部API / DB 層             │  ← クエリ・レスポンス・スキーマ整合性
└─────────────────────────────┘
```

**各層で確認すること**:

| 層 | 確認ポイント |
|---|---|
| UI | `console.log` で props/state の実値を確認。型と表示の不一致を疑う |
| API Route | レスポンスの shape を直接 curl/fetch で確認。ステータスコードを確認 |
| ビジネスロジック | 入力と出力を単体でログ出力。変換・フィルタのロジックを trace |
| 外部API / DB | クエリをそのまま実行して結果を確認。ページネーション・件数制限を確認 |

---

## STEP 3 — 根本原因の特定（修正前に言語化する）

コードを変更する前に、以下を自然言語で明示する。

```
【根本原因】
  どの層の、どのコードが、なぜ期待通りに動いていないか。

【証拠】
  STEP 1〜2 で得られた事実のうち、原因を裏付けるもの。

【影響範囲】
  修正によって影響を受ける可能性のある他の機能・エンドポイント。
```

根本原因を言語化できない場合は STEP 2 に戻る。

---

## STEP 4 — 修正（最小変更の原則）

```
[ ] 修正は1つの根本原因に対して1箇所を基本とする
[ ] 複数箇所を同時に変更しない（原因特定が困難になるため）
[ ] 型安全性を維持する（any の濫用・型アサーションの乱用をしない）
[ ] 既存のテスト・動作している機能を壊さない
```

### 典型的な修正パターン

#### データ件数の不一致

```typescript
// ❌ Bad: デフォルトの件数制限に気づかず使用
const { data } = await supabase.from('items').select('*')
// → Supabase はデフォルト 1000 件制限がある

// ✅ Good: 件数を明示的に指定 or ページネーション実装
const { data, count } = await supabase
  .from('items')
  .select('*', { count: 'exact' })
  .range(0, 99)
```

#### 外部API エラーハンドリング

```typescript
// ❌ Bad: エラーを握り潰して空配列を返す
async function fetchItems(): Promise<Item[]> {
  try {
    const res = await fetch('/api/items')
    return res.json()
  } catch {
    return []  // エラーが隠れて原因特定が困難
  }
}

// ✅ Good: エラーを上位に伝播させてログを残す
async function fetchItems(): Promise<Item[]> {
  const res = await fetch('/api/items')
  if (!res.ok) {
    const error = await res.text()
    console.error('[fetchItems] API error:', res.status, error)
    throw new Error(`API error: ${res.status}`)
  }
  return res.json()
}
```

#### 非同期処理の競合

```typescript
// ❌ Bad: await を忘れて未解決の Promise を使用
const data = fetchData()  // Promise<Data> が data に入る
console.log(data.items)   // undefined

// ✅ Good: 必ず await する
const data = await fetchData()
console.log(data.items)
```

#### 型ガードによる安全な絞り込み

```typescript
// ❌ Bad: 型アサーションで強制変換
const item = response.data as Item

// ✅ Good: 型ガードで検証してから使用
function isItem(v: unknown): v is Item {
  return typeof v === 'object' && v !== null && 'id' in v
}
if (isItem(response.data)) {
  console.log(response.data.id)
}
```

---

## STEP 5 — 検証（修正が根本原因を解消したか確認する）

```
[ ] 再現手順を再実行して問題が解消されたか確認
[ ] 修正前に確認した「期待値 vs 実際の値」が一致するか確認
[ ] 影響範囲として挙げた他機能が壊れていないか確認
[ ] デバッグ用の console.log・一時コードを削除
```

---

## STEP 6 — 再発防止（任意だが推奨）

修正内容に応じて以下を検討する。

```
[ ] エラーが握り潰されていた箇所に適切なエラーハンドリングを追加
[ ] 型定義を強化して同種のバグを型レベルで防ぐ
