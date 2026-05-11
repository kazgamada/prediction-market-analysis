---
name: general-best-practices
description: >-
  Next.js/TypeScriptプロジェクト全般に適用できるベストプラクティス集。
  UX・型安全・セキュリティ・状態管理・進捗トラッキング・アナリティクス・通知の 実装パターンを網羅する汎用ガイドライン。
category: other
sourceSkillIds:
  - edaeb07a
  - f166cb84
  - '58003741'
  - b0b81d04
  - d1e6b496
  - e134e8f8
  - 9411d04d
  - e301cd65
  - 74ffc8bf
  - c9088125
  - 8a117c47
  - 2c100c6b
  - acaf99c8
  - 0eb20442
  - 2b5a0039
  - 8858b341
  - 8b5dde02
  - 42f265c6
  - a063eb59
  - 951a8d02
  - d0fbe2de
  - 61accb90
  - f39e4252
  - e8385482
  - 8b693914
  - 7f3001e7
  - efef9795
  - d9258a7e
  - dfcc72f0
  - dcb55994
  - 6c7abe15
  - f654b05f
  - 8f0a931f
  - b0daf76b
  - d76b5267
  - bd5ba427
  - 2e7aae43
  - 6898907b
  - 99551a8a
  - 81ab112c
  - c9059c14
  - 5bea7d75
  - cdf33693
  - d7c9e9fd
  - '18060776'
  - e222d135
  - 698872c1
  - c9e5eed7
  - 7d2fa9fe
  - a054e89b
  - 1cbf55ef
  - 12f7940a
  - a5df638b
  - e62ee81d
  - cdb391a7
  - 0d809ae6
  - baae9114
generatedAt: '2026-05-11'
---

# Next.js / TypeScript — 汎用ベストプラクティス

あらゆる Next.js/TypeScript プロジェクトで共通して適用できる設計原則と実装パターン。
新規機能の実装前に必ず参照し、既存コードのレビュー基準としても活用する。

---

## 1. TypeScript 型安全の原則

### 基本方針
- `any` は禁止。不明な型には `unknown` を使い、型ガードで絞り込む
- `as` キャストは最終手段。使う場合はコメントで理由を明記する
- API レスポンス・外部入力は必ず Zod でバリデーションする

### 型定義パターン

```typescript
// ✅ 良い例：Zod スキーマから型を導出
import { z } from "zod";

const UserSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  role: z.enum(["admin", "user", "viewer"]),
  createdAt: z.string().datetime(),
});

type User = z.infer<typeof UserSchema>;

// API レスポンスのバリデーション
async function fetchUser(id: string): Promise<User> {
  const res = await fetch(`/api/users/${id}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return UserSchema.parse(await res.json()); // 実行時バリデーション
}

// ❌ 悪い例
const user = (await res.json()) as User; // バリデーションなし
```

### 判別可能なユニオン型

```typescript
// 非同期状態の型安全なモデリング
type AsyncState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; error: string };

// 使用例
function UserCard({ state }: { state: AsyncState<User> }) {
  switch (state.status) {
    case "idle":     return <Placeholder />;
    case "loading":  return <Skeleton />;
    case "success":  return <Profile user={state.data} />;
    case "error":    return <ErrorMessage message={state.error} />;
  }
}
```

---

## 2. UX — ローディング・エラー・フィードバック

### 原則
- すべての非同期処理に **loading / error / success** の3状態を実装する
- ユーザーアクション（ボタン等）は処理中に必ず無効化する
- エラーメッセージは技術的詳細を隠し、ユーザーが取れる行動を示す

### 汎用フォームフック

```typescript
// hooks/useAsyncAction.ts
import { useState, useCallback } from "react";

interface AsyncActionState {
  isLoading: boolean;
  error: string | null;
  success: boolean;
}

export function useAsyncAction<TArgs extends unknown[]>(
  action: (...args: TArgs) => Promise<void>
) {
  const [state, setState] = useState<AsyncActionState>({
    isLoading: false,
    error: null,
    success: false,
  });

  const execute = useCallback(
    async (...args: TArgs) => {
      setState({ isLoading: true, error: null, success: false });
      try {
        await action(...args);
        setState({ isLoading: false, error: null, success: true });
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "予期しないエラーが発生しました";
        setState({ isLoading: false, error: message, success: false });
      }
    },
    [action]
  );

  return { ...state, execute };
}

// 使用例
function SubmitButton({ onSubmit }: { onSubmit: () => Promise<void> }) {
  const { isLoading, error, execute } = useAsyncAction(onSubmit);
  return (
    <>
      <button onClick={execute} disabled={isLoading}>
        {isLoading ? "送信中…" : "送信"}
      </button>
      {error && <p className="text-red-500">{error}</p>}
    </>
  );
}
```

### 進捗トラッキング（長時間処理）

```typescript
// 複数ステップの処理進捗を管理するパターン
interface ProgressStep {
  id: string;
  label: string;
  status: "pending" | "running" | "done" | "error";
}

function useProgressTracker(steps: string[]) {
  const [progress, setProgress] = useState<ProgressStep[]>(
    steps.map((label, i) => ({ id: String(i), label, status: "pending" }))
  );

  const advance = (stepId: string, status: ProgressStep["status"]) =>
    setProgress((prev) =>
      prev.map((s) => (s.id === stepId ? { ...s, status } : s))
    );

  const percentage = Math.round(
    (progress.filter((s) => s.status === "done").length / progress.length) * 100
  );

  return { progress, advance, percentage };
}
```

---

## 3. 状態管理

### 原則
- **サーバー状態**（fetch データ）: `SWR` または `TanStack Query` で管理
- **UI 状態**（モーダル開閉等）: `useState` / `useReducer` でローカル管理
- **グローバル状態**（認証・テーマ）: Context + `useReducer` または Zustand
- URL パラメータは状態として扱う（`useSearchParams`）

### 動的キャッシュキーのバグ回避

```typescript
// ❌ 悪い例：依存値が変わっても再フェッチされない
function FriendList({ accountId }: { accountId: string }) {
  const { data } = useCachedFetch("/api/friends"); // キーに accountId が含まれていない
  // ...
}

// ✅ 良い例：依存値をキーに含める
function FriendList({ accountId }: { accountId: string }) {
  const { data, isLoading } = useSWR(
    accountId ? `/api/friends?accountId=${accountId}` : null,
    fetcher
  );
  // accountId が変わると自動再フェッチ
}

// ✅ useEffect を使う場合も依存配列を正確に
useEffect(() => {
  if (!accountId) return;
  fetchFriends(accountId).then(setFriends);
}, [accountId]); // ← 依存値を必ず列挙
```

### Context パターン

```typescript
// contexts/AuthContext.tsx
interface AuthState {
  user: User | null;
  isLoading: boolean;
}

type AuthAction =
  | { type: "LOGIN";
