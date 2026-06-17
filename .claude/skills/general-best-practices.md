---
category: other
sourceSkillIds:
  - 544d5768
  - 4c20b5c7
  - b8b6e2c7
  - af1353e3
  - 9805f577
  - e679a935
  - a0cd9eec
  - 79dd4189
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
  - cd3cafd4
  - b6bf62e3
  - 3acf4ab3
  - 11134f28
  - 9db6a344
  - b2127f6a
  - a6958a08
  - 0707f500
generatedAt: '2026-06-17'
integrationStrategy: latest-first
adoptedFromArchive:
  - archive/skills/account-system.md
  - archive/skills/add-admin-alert.md
  - archive/skills/analytics-engine.md
  - archive/skills/csv-parser.md
  - archive/skills/google-drive-bridge.md
  - archive/skills/guest-mode.md
  - archive/skills/line-bot.md
  - archive/skills/ocr-receipt.md
  - archive/skills/08-destructive-action-ux.md
  - archive/skills/15-planning-with-todos.md
---
```markdown
---
name: general-best-practices
description: Next.js/TypeScriptプロジェクト全般に適用できるベストプラクティス集。破壊的操作のUX・進捗トラッキング・アラート設計・アカウント/ロール設計・分析エンジン・CSV/OCR取込・外部連携・ゲストモード・マルチテナント分離の汎用パターンを網羅。
category: その他
user-invocable: true
argument-hint: "[トピック: ux|todo|alert|account|analytics|csv|ocr|guest|integration|tenant]"
allowed-tools: Read, Edit, Write, Bash, Grep, Glob
---

# 汎用ベストプラクティス — Next.js / TypeScript

トピック: **$ARGUMENTS**

> 省略時はすべてのセクションを参照してください。

---

## 目次

| # | トピック | キーワード |
|---|---|---|
| 1 | 破壊的操作の UX | `ux` |
| 2 | TodoWrite 進捗トラッキング | `todo` |
| 3 | 管理者アラート設計 | `alert` |
| 4 | アカウント・ロール・プラン設計 | `account` |
| 5 | 分析・集計エンジン | `analytics` |
| 6 | CSV 取込パターン | `csv` |
| 7 | OCR レシート・請求書処理 | `ocr` |
| 8 | ゲストモード・デモデータ | `guest` |
| 9 | 外部サービス連携 (Drive / LINE / etc.) | `integration` |
| 10 | マルチテナント分離 | `tenant` |

---

## 1. 破壊的操作の UX (`ux`)

### 原則

1. **取消不能を明示する** — 「削除します」だけでなく「この操作は取り消せません」を必ず入れる。
2. **件数を表示する** — `${count} 件のデータを削除します`。0 件・1 件でも崩れない文言にする。
3. **進行中はボタンを無効化 + ラベル変更** — 再クリックによる二重実行を防止。
4. **成功後はサーバーから再取得** — 楽観的削除は整合性ずれの原因になる。
5. **失敗時は理由を表示** — `alert(\`削除に失敗しました: ${json.error ?? res.status}\`)`。

### 最小テンプレート

```typescript
// components/BulkDeleteButton.tsx
const [deleting, setDeleting] = useState(false);

async function handleDelete() {
  if (
    !confirm(
      `${count} 件のデータを削除します。この操作は取り消せません。続けますか？`
    )
  )
    return;

  setDeleting(true);
  try {
    const res = await fetch("/api/admin/items", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: selectedIds }),
    });
    const json = await res.json();

    if (!res.ok) {
      alert(`削除に失敗しました: ${json.error ?? res.status}`);
      return;
    }

    await refetch(); // ← サーバーから再取得
  } finally {
    setDeleting(false);
  }
}

return (
  <button onClick={handleDelete} disabled={deleting || count === 0}>
    {deleting ? "削除中…" : `${count} 件を削除`}
  </button>
);
```

### API 側ガイドライン

```typescript
// app/api/admin/items/route.ts
export async function DELETE(req: Request) {
  const { ids } = await req.json();

  // 1. 権限チェック (管理者のみ)
  const session = await getServerSession();
  if (session?.user?.role !== "admin") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  // 2. ids 検証
  if (!Array.isArray(ids) || ids.length === 0) {
    return NextResponse.json({ error: "ids required" }, { status: 400 });
  }

  // 3. トランザクションで削除
  const { count } = await db.item.deleteMany({ where: { id: { in: ids } } });

  return NextResponse.json({ deleted: count });
}
```

---

## 2. TodoWrite 進捗トラッキング (`todo`)

### 使う条件

- **3 ステップ以上**のタスク
- 並列に見える作業を順序付けて実施したい
- ユーザーが複数の依頼を同時に出した
- セッション中に新しいタスクが発見された

> 1〜2 ステップで完結するなら**使わない**（表示ノイズになる）。

### 書き方の規約

```
content:    "Add DELETE endpoint to /api/admin/sales for bulk delete"
activeForm: "Adding DELETE endpoint for bulk delete"
status:     pending | in_progress | completed
```

- `content` は **命令形**、`activeForm` は **進行形 / 現在分詞**。
- 1 タスク = 1 責務。粒度が大きすぎる場合はサブタスクに分割する。
- `in_progress` は同時に **1 件だけ** にする（並列実行の可視化を正確に保つ）。
- 完了後は即 `completed` に更新し、次の `pending` を `in_progress` へ移行する。

### ステータス遷移

```
pending → in_progress → completed
                      ↘ (blocked: コメントに理由を記載)
```

---

## 3. 管理者アラート設計 (`alert`)

### 通知チャネル

| チャネル | 用途 | ライブラリ例 |
|---|---|---|
| メール | 日次サマリ・重大インシデント | `nodemailer` / Resend |
| Slack | リアルタイムスパイク検知 | `@slack/web-api` |
| in-app | ダッシュボード内バナー | DB フラグ + polling |

### 実装パターン（スパイク検知）

```typescript
// server/services/admin-alerts.ts

export interface SpikeStats {
  windowMinutes: number;
  count: number;
  threshold: number;
}

/** 直近 N 分のイベント件数を取得 */
export async function fetchRecentCount(
  eventType: string,
  windowMinutes: number
): Promise<number> {
  const since = new Date(Date.now() - windowMinutes * 60_000);
  return db.event.count({
    where: { type: eventType, createdAt: { gte: since } },
  });
}

/** スパイク判定 → 超過時に通知 */
export async function checkSpike(params: SpikeStats & { eventType: string }) {
  const { eventType, windowMinutes, threshold } = params;
  const count =
