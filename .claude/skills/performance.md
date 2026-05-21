---
name: performance
description: >-
  React Query + localStorage の Stale-While-Revalidate パターンで「ページを開いた瞬間（≤
  0.1秒）に前回データを描画 → 裏で最新化」を実現するスキル。tRPC v11 / TanStack Query v5 / Next.js App
  Router / Vercel Serverless / Postgres pooler
  で検証済み。「読み込み中...」を見せたくない・キャッシュを永続化したい・再ログイン後も即時表示したい場面で使う。
category: performance
sourceSkillIds:
  - 68dca1dc
  - 16966ace
generatedAt: '2026-05-19'
---

# performance — Instant Display Cache (Stale-While-Revalidate)

## 概要

「ページを開いた瞬間（≤ 0.1秒）に前回データを描画し、裏で最新データを取得して差し替える」UX を React Query + localStorage で実現するパターン。

**使いどき:**
- データ取得に時間がかかる（DB クエリ・外部 API など）
- 「読み込み中...」スピナーをユーザーに見せたくない
- 再ログイン後・ページ再訪問時も即時表示したい
- セッションをまたいでキャッシュを保持したい

**検証済みスタック:** tRPC v11 / TanStack Query v5 / Next.js App Router / Vercel Serverless / Postgres pooler

---

## 実装パターン

### 1. localStorage パーシスター（汎用ユーティリティ）

```typescript
// lib/cache/localStoragePersister.ts
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { persistQueryClient } from "@tanstack/react-query-persist-client";
import type { QueryClient } from "@tanstack/react-query";

const CACHE_KEY = "app-query-cache";
const CACHE_MAX_AGE_MS = 1000 * 60 * 60 * 24; // 24時間

export function setupLocalStoragePersistence(queryClient: QueryClient) {
  if (typeof window === "undefined") return; // SSR ガード

  const persister = createSyncStoragePersister({
    storage: window.localStorage,
    key: CACHE_KEY,
  });

  persistQueryClient({
    queryClient,
    persister,
    maxAge: CACHE_MAX_AGE_MS,
  });
}
```

### 2. QueryClient 設定（App Router 対応）

```typescript
// lib/cache/queryClient.ts
import { QueryClient } from "@tanstack/react-query";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // キャッシュを「即時に古い」とみなし、常にバックグラウンド再取得
        staleTime: 0,
        // メモリ上のキャッシュ保持時間（localStorage とは別）
        gcTime: 1000 * 60 * 5, // 5分
        // ページフォーカス時に再取得（UX のキモ）
        refetchOnWindowFocus: true,
        // オフライン時はキャッシュを使い続ける
        networkMode: "offlineFirst",
      },
    },
  });
}
```

### 3. Provider 設定（Next.js App Router）

```tsx
// components/providers/QueryProvider.tsx
"use client";

import { useState, useEffect } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient } from "@/lib/cache/queryClient";
import { setupLocalStoragePersistence } from "@/lib/cache/localStoragePersister";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => createQueryClient());

  useEffect(() => {
    // クライアントサイドでのみ永続化を有効化
    setupLocalStoragePersistence(queryClient);
  }, [queryClient]);

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
```

```tsx
// app/layout.tsx
import { QueryProvider } from "@/components/providers/QueryProvider";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html>
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
```

### 4. データ取得フック（tRPC v11 使用例）

```typescript
// hooks/useDashboardData.ts
import { api } from "@/lib/trpc/client";

export function useDashboardData() {
  const result = api.dashboard.getSummary.useQuery(undefined, {
    // このクエリだけ長めにキャッシュしたい場合は個別上書き可能
    staleTime: 1000 * 30, // 30秒間は「新鮮」扱い
  });

  return {
    data: result.data,
    // isLoading: キャッシュなし & 取得中のみ true（初回のみ）
    isLoading: result.isLoading,
    // isFetching: バックグラウンド再取得中も true
    isFetching: result.isFetching,
    isError: result.isError,
  };
}
```

### 5. コンポーネントでの活用パターン

```tsx
// components/DashboardView.tsx
"use client";

import { useDashboardData } from "@/hooks/useDashboardData";

export function DashboardView() {
  const { data, isLoading, isFetching } = useDashboardData();

  // isLoading のみチェック → キャッシュがあれば即時描画、スピナーなし
  if (isLoading) {
    return <DashboardSkeleton />;
  }

  return (
    <div>
      {/* バックグラウンド更新中の軽量インジケーター */}
      {isFetching && (
        <div className="fixed top-2 right-2 text-xs text-muted-foreground">
          更新中...
        </div>
      )}
      <DashboardContent data={data} />
    </div>
  );
}
```

---

## キャッシュ無効化戦略

### ミューテーション後に即時反映

```typescript
// キャッシュを無効化して再取得をトリガー
const utils = api.useUtils();

const mutation = api.items.create.useMutation({
  onSuccess: () => {
    // 関連クエリを無効化（次のフォーカス or 即時再取得）
    utils.dashboard.getSummary.invalidate();
    utils.items.list.invalidate();
  },
});
```

### ユーザーセッション切り替え時のキャッシュクリア

```typescript
// lib/cache/clearCache.ts
export function clearUserCache() {
  if (typeof window === "undefined") return;
  // localStorage のキャッシュキーをクリア
  localStorage.removeItem("app-query-cache");
}

// ログアウト処理に組み込む
async function handleSignOut() {
  clearUserCache();
  await signOut({ redirect: true, callbackUrl: "/login" });
}
```

---

## よく
