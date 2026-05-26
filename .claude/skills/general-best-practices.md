---
category: other
sourceSkillIds:
  - 544d5768
  - 4c20b5c7
  - b8b6e2c7
  - af1353e3
  - b6bf62e3
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
  - 3acf4ab3
  - 11134f28
  - 9db6a344
  - b2127f6a
  - a6958a08
  - 0707f500
generatedAt: '2026-05-26'
---
```markdown
---
name: general-best-practices
description: >-
  Next.js/TypeScriptプロジェクト全般に適用できるベストプラクティス集。
  UX・型安全・セキュリティ・状態管理・進捗トラッキング・アナリティクス・通知の実装パターンを網羅する汎用ガイドライン。
  デモモード（isDemo）パターン・楽観的UI更新（Optimistic Update）・破壊的操作UX・オープンリダイレクト対策・
  キーボードナビゲーションデバッグ・TodoWrite進捗トラッキングのベストプラクティスを含む。
category: other
version: 3
effectiveTimestamp: '2026-05-22T00:00:00.000Z'
---

# General Best Practices — Next.js / TypeScript

あらゆる Next.js / TypeScript プロジェクトで再利用できる実装パターン集。
各セクションは独立しているため、必要な箇所だけ参照してください。

---

## 目次

1. [型安全・コード品質](#1-型安全コード品質)
2. [破壊的操作の UX](#2-破壊的操作の-ux)
3. [楽観的 UI 更新（Optimistic Update）](#3-楽観的-ui-更新optimistic-update)
4. [デモモード（isDemo）パターン](#4-デモモードisdemo-パターン)
5. [セキュリティ — オープンリダイレクト対策](#5-セキュリティ--オープンリダイレクト対策)
6. [状態管理の指針](#6-状態管理の指針)
7. [進捗トラッキング（TodoWrite）](#7-進捗トラッキングtodowrite)
8. [アナリティクス・通知の設計指針](#8-アナリティクス通知の設計指針)
9. [キーボードナビゲーションのデバッグパターン](#9-キーボードナビゲーションのデバッグパターン)
10. [開発サーバー・CI の基本](#10-開発サーバーci-の基本)

---

## 1. 型安全・コード品質

### 1.1 `unknown` を使って型を絞り込む

```typescript
// ❌ any は型エラーを隠す
function parseConfig(raw: any) { return raw.timeout; }

// ✅ unknown + 型ガードで安全に扱う
function parseConfig(raw: unknown): number {
  if (
    typeof raw === "object" && raw !== null &&
    "timeout" in raw && typeof (raw as Record<string, unknown>).timeout === "number"
  ) {
    return (raw as { timeout: number }).timeout;
  }
  throw new Error("Invalid config");
}
```

### 1.2 API レスポンスの型定義

```typescript
// 共通レスポンス型
export type ApiResponse<T> =
  | { ok: true;  data: T }
  | { ok: false; error: string; status: number };

// 使用例
async function fetchUser(id: string): Promise<ApiResponse<User>> {
  const res = await fetch(`/api/users/${id}`);
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    return { ok: false, error: json.error ?? "Unknown error", status: res.status };
  }
  return { ok: true, data: await res.json() };
}
```

### 1.3 `satisfies` 演算子で型推論を保持しつつ検証

```typescript
const ROUTES = {
  home:    "/",
  profile: "/profile",
  admin:   "/admin",
} satisfies Record<string, `/${string}`>;

// ROUTES.home は string ではなく "/" として推論される
```

---

## 2. 破壊的操作の UX

### 原則

| # | 原則 | 理由 |
|---|------|------|
| 1 | **取消不能を明示** | 「削除します」だけでなく「この操作は取り消せません」を含める |
| 2 | **件数を必ず表示** | `${count} 件のデータを削除します`（0件・1件でも崩れない文言） |
| 3 | **進行中はボタン無効化 + 表示変更** | 二重送信防止 |
| 4 | **成功後は再フェッチ** | 楽観的削除を**しない**（整合性ズレを防ぐ） |
| 5 | **失敗時はエラー理由を表示** | `alert(\`削除に失敗しました: ${json.error ?? res.status}\`)` |

### 最小テンプレート

```tsx
const [deleting, setDeleting] = useState(false);

async function handleDelete() {
  if (!confirm(`${count} 件のデータを削除します。この操作は取り消せません。`)) return;
  setDeleting(true);
  try {
    const res = await fetch("/api/items", { method: "DELETE", body: JSON.stringify({ ids }) });
    if (!res.ok) {
      const json = await res.json().catch(() => ({}));
      alert(`削除に失敗しました: ${json.error ?? res.status}`);
      return;
    }
    await refetch(); // ✅ 楽観的削除せず再取得
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

---

## 3. 楽観的 UI 更新（Optimistic Update）

### いつ使うか

| 操作 | 推奨アプローチ |
|------|---------------|
| **破壊的操作**（削除・一括変更） | 楽観的更新 **禁止** → 再フェッチ（§2 参照） |
| **軽量な状態トグル**（いいね・既読・並び替え） | 楽観的更新 **OK** + 失敗時リバート |
| **フォーム送信**（新規作成・編集） | ケースバイケース（データ量と UX による） |

### 失敗時リバートパターン

```tsx
const [items, setItems] = useState<Item[]>(initialItems);

async function handleToggleLike(id: string) {
  // 1. 楽観的に更新
  const prev = items;
  setItems(items.map(i => i.id === id ? { ...i, liked: !i.liked } : i));

  // 2. API 呼び出し
  const res = await fetch(`/api/items/${id}/like`, { method: "POST" });

  // 3. 失敗時はリバート
  if (!res.ok) {
    setItems(prev);
    toast.error("操作に失敗しました。再試行してください。");
  }
}
```

> **Note**: 削除・一括操作では失敗時リバート
