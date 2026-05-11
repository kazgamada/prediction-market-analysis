---
name: performance
description: >-
  React Query + localStorage による Stale-While-Revalidate パターンで「ページを開いた瞬間（≤
  0.1秒）に前回データを描画 →
  裏で最新化」を実現するスキル。データ取得が遅い・キャッシュを保持したい・再ログイン後も即時表示したい・「読み込み中...」を見せたくないときに使う。tRPC
  v11 / TanStack Query v5 / Next.js App Router / Vercel Serverless
  で検証済み。あらゆるNext.js/TypeScriptプロジェクトに適用可能。
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

| 症状 | このスキルで解決 |
|------|----------------|
| ページ遷移のたびに「読み込み中...」が出る | ✅ |
| 再ログイン後もデータが消えてしまう | ✅ |
| APIレスポンスが500ms以上かかる | ✅ |
| ユーザーが同じデータを繰り返し見る | ✅ |
| ネットワーク不安定環境でも即表示したい | ✅ |

---

## コアコンセプト

```
ページ表示
    │
    ├─① localStorage から前回データを即時描画 (≤ 0.1秒)
    │
    └─② バックグラウンドでAPIフェッチ
            │
            └─③ 新データが来たら静かに差し替え
```

これが **Stale-While-Revalidate (SWR)** パターン。  
「古くてもまず見せる → 裏で更新」の優先順位がUXの核心。

---

## 実装

### 1. localStorage キャッシュユーティリティ

```typescript
// lib/cache/localStorageCache.ts

const CACHE_VERSION = 'v1'; // スキーマ変更時にインクリメント

interface CacheEntry<T> {
  data: T;
  cachedAt: number;  // Unix timestamp (ms)
  version: string;
}

export const localStorageCache = {
  /**
   * データを保存。TTLを超えたエントリは get() 時に破棄される。
   */
  set<T>(key: string, data: T): void {
    if (typeof window === 'undefined') return; // SSR ガード
    try {
      const entry: CacheEntry<T> = {
        data,
        cachedAt: Date.now(),
        version: CACHE_VERSION,
      };
      localStorage.setItem(`cache:${key}`, JSON.stringify(entry));
    } catch (e) {
      // localStorage が満杯の場合は無視（機能は継続）
      console.warn('[cache] set failed:', e);
    }
  },

  /**
   * キャッシュを取得。TTL超過・バージョン不一致は null を返す。
   * @param ttlMs ミリ秒。デフォルト 5分。
   */
  get<T>(key: string, ttlMs = 5 * 60 * 1000): T | null {
    if (typeof window === 'undefined') return null;
    try {
      const raw = localStorage.getItem(`cache:${key}`);
      if (!raw) return null;

      const entry: CacheEntry<T> = JSON.parse(raw);

      // バージョン不一致は破棄
      if (entry.version !== CACHE_VERSION) {
        localStorage.removeItem(`cache:${key}`);
        return null;
      }

      // TTL チェック
      if (Date.now() - entry.cachedAt > ttlMs) {
        localStorage.removeItem(`cache:${key}`);
        return null;
      }

      return entry.data;
    } catch {
      return null;
    }
  },

  remove(key: string): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem(`cache:${key}`);
  },

  /** プレフィックスが一致するキャッシュを一括削除（ログアウト時など） */
  clearByPrefix(prefix: string): void {
    if (typeof window === 'undefined') return;
    Object.keys(localStorage)
      .filter(k => k.startsWith(`cache:${prefix}`))
      .forEach(k => localStorage.removeItem(k));
  },
};
```

---

### 2. 汎用 SWR フック

```typescript
// hooks/useInstantCache.ts
import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient, QueryKey } from '@tanstack/react-query';
import { localStorageCache } from '@/lib/cache/localStorageCache';

interface UseInstantCacheOptions<T> {
  queryKey: QueryKey;
  /** キャッシュストレージのキー（文字列で一意にする） */
  cacheKey: string;
  fetchFn: () => Promise<T>;
  /** localStorage TTL（ms）。デフォルト 5分 */
  cacheTtlMs?: number;
  /** React Query の staleTime（ms）。デフォルト 0（常にバックグラウンド再検証） */
  staleTimeMs?: number;
  /** キャッシュ無効化（ログアウト後など false にするとキャッシュを使わない） */
  enabled?: boolean;
}

export function useInstantCache<T>({
  queryKey,
  cacheKey,
  fetchFn,
  cacheTtlMs = 5 * 60 * 1000,
  staleTimeMs = 0,
  enabled = true,
}: UseInstantCacheOptions<T>) {
  const queryClient = useQueryClient();
  const initializedRef = useRef(false);

  // ① マウント時に localStorage → QueryClient へ即時注入
  useEffect(() => {
    if (!enabled || initializedRef.current) return;
    initializedRef.current = true;

    const cached = localStorageCache.get<T>(cacheKey, cacheTtlMs);
    if (cached !== null) {
      queryClient.setQueryData(queryKey, cached);
    }
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  // ② React Query が バックグラウンドでフェッチ → 成功時に localStorage 更新
  const query = useQuery({
    queryKey,
    queryFn: async () => {
      const fresh = await fetchFn();
      localStorageCache.set(cacheKey, fresh); // キャッシュ更新
      return fresh;
    },
    staleTime: staleTimeMs,
    enabled,
    // キャッシュ済みデータがあれば placeholderData として使う（ローディング状態を出さない）
    placeholderData: (prev) => prev,
  });

  return query;
}
```

---

### 3. 使用例 — ダッシュボードページ

```typescript
// app/dashboard/page.tsx  (Next.js App Router)
'use client';

import { useInstantCache } from '@/hooks/useInstantCache';

interface DashboardData {
  projects: { id: string; name: string; updatedAt: string }[];
  stats: { total: number; active: number };
