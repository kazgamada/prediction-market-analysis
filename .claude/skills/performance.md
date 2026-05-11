---
name: performance
description: >-
  React Query + localStorage を用いた Stale-While-Revalidate
  パターンで「ページを開いた瞬間(≤0.1秒)に前回データを描画→裏で最新化」を実現するスキル。データ取得が遅い・キャッシュを保持したい・再ログイン後も即時表示したい・「読み込み中...」を見せたくないときに使う。tRPC
  v11 / TanStack Query v5 / Vercel Serverless / Postgres pooler で検証済み。Next.js /
  TypeScript プロジェクトで汎用的に適用可能。
category: performance
sourceSkillIds:
  - 7d2fa9fe
generatedAt: '2026-05-11'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-10T19:11:30+00:00'
adoptedFromArchive:
  - archive/SlideForgeAI/.claude/skills/instant-display-cache.md
---

# performance — Instant Display Cache (Stale-While-Revalidate)

## いつ使うか

| 症状 | 適用判断 |
|------|----------|
| ページ遷移のたびに「読み込み中...」が出る | ✅ 使う |
| API レスポンスが 500ms 以上かかる | ✅ 使う |
| ログアウト→再ログイン後も即時表示したい | ✅ 使う |
| データが秒単位で変わりリアルタイム性必須 | ⚠️ 鮮度要件を要確認 |
| 認証情報・個人情報をキャッシュする | ❌ localStorage は使わない |

---

## コアコンセプト

```
ページ表示
  └─ 1. localStorage から前回データを即時描画 (≤ 0.1 秒)
  └─ 2. バックグラウンドで API フェッチ
  └─ 3. 新データ取得後に画面を差し替え + localStorage 更新
```

これは HTTP の `stale-while-revalidate` ディレクティブをクライアントサイドで再実装したもの。

---

## 実装パターン

### 1. localStorage ベースの Persister を作る

```typescript
// lib/cache/localStoragePersister.ts
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { compress, decompress } from "lz-string"; // 大きいデータは圧縮

/**
 * localStoragePersister
 * - serialize/deserialize で LZ 圧縮を適用（任意）
 * - throttleTime: 1000ms で書き込み頻度を制限
 */
export const localStoragePersister = createSyncStoragePersister({
  storage: typeof window !== "undefined" ? window.localStorage : undefined,
  key: "APP_QUERY_CACHE", // プロジェクトごとに変更
  throttleTime: 1000,
  serialize: (data) => compress(JSON.stringify(data)),
  deserialize: (data) => JSON.parse(decompress(data)),
});
```

> **注意**: `typeof window !== "undefined"` は SSR 対応に必須。  
> `lz-string` はオプション。データが小さければ省略可。

---

### 2. QueryClient に永続化を設定する

```typescript
// lib/cache/queryClient.ts
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // キャッシュは 24 時間有効（staleTime と gcTime を同期させると混乱しにくい）
      staleTime: 1000 * 60 * 5,        // 5 分: この間は再フェッチしない
      gcTime: 1000 * 60 * 60 * 24,     // 24 時間: localStorage と合わせる
      retry: 2,
      refetchOnWindowFocus: true,       // タブ復帰時に最新化
    },
  },
});
```

```typescript
// app/providers.tsx  (Next.js App Router の場合)
"use client";

import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { queryClient } from "@/lib/cache/queryClient";
import { localStoragePersister } from "@/lib/cache/localStoragePersister";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister: localStoragePersister,
        maxAge: 1000 * 60 * 60 * 24, // 24 時間
        buster: process.env.NEXT_PUBLIC_CACHE_BUSTER ?? "", // デプロイ時に古いキャッシュを破棄
      }}
    >
      {children}
    </PersistQueryClientProvider>
  );
}
```

---

### 3. tRPC との組み合わせ（v11 対応）

```typescript
// server/api/routers/example.ts
import { z } from "zod";
import { createTRPCRouter, protectedProcedure } from "@/server/api/trpc";

export const exampleRouter = createTRPCRouter({
  getList: protectedProcedure
    .input(z.object({ page: z.number().default(1) }))
    .query(async ({ ctx, input }) => {
      // Postgres pooler 使用時は接続を使い回す
      const items = await ctx.db.item.findMany({
        take: 20,
        skip: (input.page - 1) * 20,
        orderBy: { createdAt: "desc" },
      });
      return { items, page: input.page };
    }),
});
```

```typescript
// components/ItemList.tsx
"use client";

import { api } from "@/lib/trpc/client";

export function ItemList() {
  const { data, isFetching, isLoading } = api.example.getList.useQuery(
    { page: 1 },
    {
      // Persister が有効なら isLoading=false で即 data が返る
      staleTime: 1000 * 60 * 5,
    }
  );

  // isLoading: キャッシュも含めてデータが1件もない場合のみ true
  // isFetching: バックグラウンド更新中は true
  if (isLoading) return <Skeleton />;

  return (
    <div>
      {/* 背景更新中のインジケーター（任意） */}
      {isFetching && <RefreshIndicator />}
      {data?.items.map((item) => <ItemCard key={item.id} item={item} />)}
    </div>
  );
}
```

> **ポイント**: `isLoading` と `isFetching` を使い分けることで  
> 「初回は何も出ない」と「裏で更新中」を別々に表現できる。

---

### 4. キャッシュ無効化（ユーザーアクション後）

```typescript
// ミューテーション後に関連クエリを再フェッチ
const utils = api.useUtils();

const createItem = api.example.create.useMutation({
  onSuccess: async () => {
    // 楽観的更新 → 確定後に最新化
    await utils.example.getList.invalidate();
  },
});
```

---

### 5. ログアウト
