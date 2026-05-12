---
name: performance
description: >-
  React Query + localStorage の Stale-While-Revalidate パターンで「ページを開いた瞬間（≤
  0.1秒）に前回データを描画 → 裏で最新化」を実現するスキル。tRPC v11 / TanStack Query v5 / Next.js App
  Router で検証済み。「読み込み中...」を見せたくない・キャッシュを永続化したい・再ログイン後も即時表示したい場面で使う。
category: performance
sourceSkillIds:
  - 68dca1dc
generatedAt: '2026-05-11'
---

# performance — Instant Display Cache (Stale-While-Revalidate)

## 🎯 このスキルで解決する問題

| 症状 | 原因 | このスキルの解決策 |
|---|---|---|
| ページを開くたびに「読み込み中...」が出る | React Query のキャッシュがメモリのみで消える | localStorage に永続化してページ起動時に即注入 |
| 再ログイン後にデータが消える | セッション切断でメモリキャッシュがクリアされる | ユーザーをキーに localStorage で保持 |
| API が遅くてユーザーが離脱する | ネットワーク待ちがそのままUXに直結する | 旧データを先に表示しながら裏でフェッチ |

---

## 🏗️ アーキテクチャ概要

```
ページ表示 (0ms)
    │
    ▼
[localStorage] ──即時注入──▶ [React Query Cache] ──▶ 画面に旧データ表示 (≤100ms)
                                      │
                                      ▼ 裏でフェッチ開始
                               [API / tRPC]
                                      │
                                      ▼ 新データ到着
                               [React Query Cache] ──▶ 画面を静かに更新
                                      │
                                      ▼ 同時に保存
                               [localStorage] ◀── 次回起動用に永続化
```

---

## 📦 実装パターン

### 1. localStorage ブリッジ（ユーティリティ）

```typescript
// lib/cache/localStorageBridge.ts

const CACHE_VERSION = "v1"; // スキーマ変更時にインクリメント

function buildKey(userId: string, queryKey: string): string {
  return `qc:${CACHE_VERSION}:${userId}:${queryKey}`;
}

export function saveToLocalStorage<T>(
  userId: string,
  queryKey: string,
  data: T
): void {
  try {
    const payload = {
      data,
      savedAt: Date.now(),
    };
    localStorage.setItem(buildKey(userId, queryKey), JSON.stringify(payload));
  } catch (e) {
    // localStorage が満杯 or プライベートモードでも静かに失敗
    console.warn("[cache] localStorage write failed:", e);
  }
}

export function loadFromLocalStorage<T>(
  userId: string,
  queryKey: string,
  maxAgeMs = 24 * 60 * 60 * 1000 // デフォルト24時間
): T | undefined {
  try {
    const raw = localStorage.getItem(buildKey(userId, queryKey));
    if (!raw) return undefined;

    const { data, savedAt } = JSON.parse(raw) as { data: T; savedAt: number };

    // 有効期限チェック（古すぎるキャッシュは使わない）
    if (Date.now() - savedAt > maxAgeMs) {
      localStorage.removeItem(buildKey(userId, queryKey));
      return undefined;
    }

    return data;
  } catch {
    return undefined;
  }
}

/** ユーザーログアウト時に全キャッシュを削除 */
export function clearUserCache(userId: string): void {
  const prefix = `qc:${CACHE_VERSION}:${userId}:`;
  Object.keys(localStorage)
    .filter((k) => k.startsWith(prefix))
    .forEach((k) => localStorage.removeItem(k));
}
```

---

### 2. QueryClient にキャッシュを事前注入するプロバイダー

```typescript
// providers/QueryProvider.tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { loadFromLocalStorage, saveToLocalStorage } from "@/lib/cache/localStorageBridge";

interface QueryProviderProps {
  children: React.ReactNode;
  userId?: string; // 未ログイン時は undefined
}

export function QueryProvider({ children, userId }: QueryProviderProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // ウィンドウフォーカス時に自動リフェッチ（SWR の核心）
            refetchOnWindowFocus: true,
            // キャッシュは5分間有効（staleTime 中は再フェッチしない）
            staleTime: 5 * 60 * 1000,
            // gcTime は長めに（メモリ上でのキャッシュ保持期間）
            gcTime: 10 * 60 * 1000,
          },
        },
      })
  );

  // ① ページ起動時: localStorage → QueryClient へ注入
  useEffect(() => {
    if (!userId) return;

    const KEYS_TO_PRELOAD = ["slides", "userProfile", "projects"] as const;

    for (const key of KEYS_TO_PRELOAD) {
      const cached = loadFromLocalStorage(userId, key);
      if (cached) {
        // setQueryData で即時注入（ネットワークなし）
        queryClient.setQueryData([key, userId], cached);
      }
    }
  }, [userId, queryClient]);

  // ② データ更新時: QueryClient → localStorage へ保存
  useEffect(() => {
    if (!userId) return;

    const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
      // 新鮮なデータが到着したときだけ保存
      if (event.type === "updated" && event.query.state.status === "success") {
        const [key] = event.query.queryKey as string[];
        if (key && event.query.state.data) {
          saveToLocalStorage(userId, key, event.query.state.data);
        }
      }
    });

    return unsubscribe;
  }, [userId, queryClient]);

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
```

---

### 3. tRPC と組み合わせる場合

```typescript
// app/layout.tsx (App Router)
import { QueryProvider } from "@/providers/QueryProvider";
import { TRPCProvider } from "@/providers/TRPCProvider";
import { auth } from "@/lib/auth";

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  return (
    <html lang="ja">
      <body>
        {/* tRPC は QueryClient を内部で使うので QueryProvider の内側に置く */}
        <QueryProvider userId={session?.user?.id}>
          <TRP
