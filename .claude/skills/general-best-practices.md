---
name: general-best-practices
description: >-
  Next.js/TypeScriptプロジェクト全般に適用できるベストプラクティス集。
  UX・型安全・セキュリティ・状態管理・進捗トラッキング・アナリティクス・通知の 実装パターンを網羅する汎用ガイドライン。
category: other
sourceSkillIds:
  - 4c20b5c7
  - b6bf62e3
  - af5835a8
  - b65d7e1f
  - 5c2b73a0
  - b32c6c80
  - 833f68c8
  - 68c72247
  - c0d09ec0
  - 4537f343
  - 9b072ef4
  - 350b3fe4
  - 6d68ad95
  - 3acf4ab3
  - 11134f28
  - 9db6a344
  - b2127f6a
  - a6958a08
  - 0707f500
  - 8215d63c
generatedAt: '2026-05-11'
---

# General Best Practices — Next.js / TypeScript

複数プロジェクトの実装パターンを統合した汎用ガイドライン。
新機能追加・バグ修正・リファクタリング問わず、常にこのドキュメントを参照すること。

---

## 目次

1. [破壊的操作の UX](#1-破壊的操作の-ux)
2. [セキュリティ — オープンリダイレクト対策](#2-セキュリティ--オープンリダイレクト対策)
3. [進捗トラッキング（TodoWrite）](#3-進捗トラッキングtodowrite)
4. [管理者アラート・通知パターン](#4-管理者アラート通知パターン)
5. [表示条件・ステータス管理](#5-表示条件ステータス管理)
6. [キーボードナビゲーションのデバッグ](#6-キーボードナビゲーションのデバッグ)
7. [Git スナップショット運用](#7-git-スナップショット運用)
8. [開発サーバー起動](#8-開発サーバー起動)

---

## 1. 破壊的操作の UX

### 原則

| # | 原則 | 理由 |
|---|------|------|
| 1 | **取消不能であることを明示** | 「削除します」だけでなく「この操作は取り消せません」を入れる |
| 2 | **件数を必ず表示** | `${count} 件のデータを削除します`。0 件・1 件でも崩れない文言に |
| 3 | **進行中はボタン無効化 + 表示変更** | 再クリックによる二重実行を防ぐ |
| 4 | **成功後はサーバーから再取得** | 楽観的削除は整合性ズレが devtools でしか見えなくなる |
| 5 | **失敗時は理由を alert に出す** | `alert(\`削除に失敗しました: ${json.error ?? res.status}\`)` |

### 最小テンプレート

```typescript
const [deleting, setDeleting] = useState(false);

async function handleDelete(ids: string[]) {
  if (ids.length === 0) return;
  const confirmed = window.confirm(
    `${ids.length} 件のデータを削除します。\nこの操作は取り消せません。`
  );
  if (!confirmed) return;

  setDeleting(true);
  try {
    const res = await fetch("/api/resource", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    const json = await res.json();
    if (!res.ok) {
      alert(`削除に失敗しました: ${json.error ?? res.status}`);
      return;
    }
    await refetch(); // サーバーから再取得
  } finally {
    setDeleting(false);
  }
}

// JSX
<button
  onClick={() => handleDelete(selectedIds)}
  disabled={deleting || selectedIds.length === 0}
>
  {deleting ? "削除中…" : `${selectedIds.length} 件を削除`}
</button>
```

---

## 2. セキュリティ — オープンリダイレクト対策

### 問題

認証成功後の `?next=...` による元ページ復帰は標準 UX だが、
**無検証の `res.redirect(302, next)` はオープンリダイレクト脆弱性**。
フィッシング補助として悪用される。

### 対策：`sanitizeNext()` で相対パスのみ許可

```typescript
// lib/auth/redirect.ts
export function sanitizeNext(raw: unknown, fallback = "/"): string {
  if (typeof raw !== "string" || raw.length === 0) return fallback;
  // 相対パスのみ許可（// や http:// で始まる外部 URL を弾く）
  if (!raw.startsWith("/") || raw.startsWith("//")) return fallback;
  // 制御文字・改行を排除
  if (/[\r\n]/.test(raw)) return fallback;
  return raw;
}
```

```typescript
// 使用例: pages/api/auth/callback.ts（Pages Router）
import { sanitizeNext } from "@/lib/auth/redirect";

export default function handler(req, res) {
  // ... 認証処理 ...
  const next = sanitizeNext(req.query.next, "/dashboard");
  res.redirect(302, next);
}
```

### チェックリスト

- [ ] `next` パラメータは必ず `sanitizeNext()` を通す
- [ ] 外部 URL（`http://`, `https://`, `//`）は全てデフォルトパスへフォールバック
- [ ] 改行文字（`%0a`, `%0d`）インジェクションを防ぐ

---

## 3. 進捗トラッキング（TodoWrite）

### 使うべき条件

| 条件 | 使う | 使わない |
|------|------|----------|
| ステップ数 | 3 以上 | 1〜2（ノイズになる） |
| 並列に見える作業の順序付け | ✅ | — |
| ユーザーが複数依頼を同時に出した | ✅ | — |
| セッション中に新タスクが発見された | ✅ | — |

### 書き方の規約

```
content:    "Add DELETE endpoint to /api/admin/resource for bulk delete"
activeForm: "Adding DELETE endpoint for bulk delete"
status:     pending | in_progress | completed
```

- `content` は **命令形**（何をするか）
- `activeForm` は **進行形 / 現在分詞**（今やっていること）
- ステータスは必ず `pending → in_progress → completed` の順に遷移
- 着手前に全タスクを `pending` で書き出し、着手時に `in_progress` へ更新
- 完了したら即 `completed` へ更新し、未着手タスクを可視化し続ける

---

## 4. 管理者アラート・通知パターン

### アーキテクチャ

```
server/services/admin-alerts.ts   ← 集計・閾値判定ロジック
server/jobs/alert-scheduler.ts    ← cron / スケジューラ登録
lib/notify/email.ts               ← メール送信アダプタ
lib/notify/slack.ts               ← Slack Webhook アダプタ
```

### 統一インターフェース

```typescript
//
