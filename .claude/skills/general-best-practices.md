---
name: general-best-practices
description: >-
  Next.js/TypeScriptプロジェクト全般に適用できるベストプラクティス集。
  UX・型安全・セキュリティ・状態管理・進捗トラッキング・アナリティクス・通知・
  ルーティング・チャート・キーボードアクセシビリティの実装パターンを網羅する汎用ガイドライン。
category: other
sourceSkillIds:
  - edaeb07a
  - f166cb84
  - '58003741'
  - b0b81d04
  - d1e6b496
  - e134e8f8
  - 9411d04d
  - 74ffc8bf
  - 8a117c47
  - acaf99c8
  - 0eb20442
  - 2b5a0039
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
  - d9258a7e
  - dfcc72f0
  - 6c7abe15
  - f654b05f
  - b0daf76b
  - bd5ba427
  - 6898907b
  - 81ab112c
  - c9059c14
  - cdf33693
  - d7c9e9fd
  - e222d135
  - c9e5eed7
  - 1cbf55ef
  - 12f7940a
  - a5df638b
  - cdb391a7
generatedAt: '2026-05-11'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-10T19:11:30+00:00'
adoptedFromArchive:
  - archive/prediction-market-analysis/.claude/skills/general-best-practices.md
  - archive/aegis-market-os/.claude/skills/open-redirect-next.md
  - archive/aegis-market-os/.claude/skills/profitability-ranking.md
  - archive/aegis-market-os/.claude/skills/route-migration.md
  - archive/aegis-market-os/.claude/skills/sample-curve-interp.md
  - archive/aegis-market-os/.claude/skills/sim-combos.md
  - archive/AISaaS/.claude/skills/add-admin-alert.md
  - archive/AISaaS/.claude/skills/tool-visibility-rules.md
  - archive/task-matrix/.claude/skills/calendar-keyboard-nav.md
  - archive/task-matrix/.claude/skills/dev.md
---

# General Best Practices — Next.js / TypeScript

あらゆる Next.js / TypeScript プロジェクトで横断的に適用できるベストプラクティス集。  
セキュリティ・UX・型安全・状態管理・通知・チャート・アクセシビリティを網羅する。

---

## 目次

1. [セキュリティ — オープンリダイレクト対策](#1-セキュリティ--オープンリダイレクト対策)
2. [ルーティング — レガシー URL の移行パターン](#2-ルーティング--レガシー-url-の移行パターン)
3. [チャート — 複数系列の長さ不一致を補間で解決](#3-チャート--複数系列の長さ不一致を補間で解決)
4. [状態管理 — 単一ソース原則 (Single Source of Truth)](#4-状態管理--単一ソース原則-single-source-of-truth)
5. [管理者通知 — スパイク検知 / 日次サマリ](#5-管理者通知--スパイク検知--日次サマリ)
6. [コンテンツ公開状態 — ステータス × ステージ管理](#6-コンテンツ公開状態--ステータス--ステージ管理)
7. [アクセシビリティ — カレンダーキーボードナビゲーション](#7-アクセシビリティ--カレンダーキーボードナビゲーション)
8. [開発環境 — 開発サーバー起動チェックリスト](#8-開発環境--開発サーバー起動チェックリスト)
9. [スコアリング — 複合指標の設計パターン](#9-スコアリング--複合指標の設計パターン)

---

## 1. セキュリティ — オープンリダイレクト対策

### 背景

認証成功後に `?next=...` で元ページへ戻す UX は標準的だが、  
**無検証の `res.redirect(302, next)` はオープンリダイレクト脆弱性**になる。  
外部 URL を差し込まれフィッシング補助に悪用される。

### 対策：`sanitizeNext()` で相対パスのみ許可

```ts
// lib/auth/redirect.ts
export function sanitizeNext(raw: unknown, fallback = "/"): string {
  if (typeof raw !== "string" || raw.length === 0) return fallback;
  // 相対パス（/で始まる）のみ許可。プロトコル相対 (//) も拒否
  if (!raw.startsWith("/") || raw.startsWith("//")) return fallback;
  // javascript: などのスキームを拒否
  try {
    const url = new URL(raw, "http://localhost");
    if (url.origin !== "http://localhost") return fallback;
  } catch {
    return fallback;
  }
  return raw;
}
```

### 使用例

```ts
// pages/api/auth/callback.ts
import { sanitizeNext } from "@/lib/auth/redirect";

export default async function handler(req, res) {
  // ...認証処理...
  const redirectTo = sanitizeNext(req.query.next, "/dashboard");
  res.redirect(302, redirectTo);
}
```

### チェックリスト

- [ ] `next` パラメータは必ず `sanitizeNext()` を通す
- [ ] 外部ドメインへのリダイレクトは明示的な allowlist で管理
- [ ] テスト: `next=https://evil.com` → `/` にフォールバックすること

---

## 2. ルーティング — レガシー URL の移行パターン

### パターン：クエリ文字列を保持したまま新パスへ転送

古いルートを廃止しつつ、`?tab=...` などのパラメータを引き継ぐ場合に使う。

```tsx
// components/RedirectTo.tsx
import { useEffect } from "react";
import { useRouter } from "next/router"; // App Router の場合は useRouter / redirect

interface Props {
  to: string;
}

export function RedirectTo({ to }: Props) {
  const router = useRouter();

  useEffect(() => {
    const search =
      typeof window !== "undefined" ? window.location.search : "";
    // replace: true で履歴を汚染しない
    router.replace(to + search);
  }, [to, router]);

  return null;
}
```

### Next.js App Router での静的リダイレクト

```ts
// next.config.ts
const nextConfig = {
  async redirects() {
    return [
      {
        source: "/old-path/:slug",
        destination: "/new-path/:slug",
        permanent: true, // 301
      },
    ];
  },
};
```

### 使用指針

| 方法 | 用途 |
|---|---|
| `next.config.ts` の `redirects` | 静的・大量・SEO 重視のルート移行 |
| `RedirectTo` コンポーネント | クエリ文字列保持が必要な動的移行 |
| `middleware.ts` | 認証状態に応じた条件付きリダイレクト |

---

## 3. チャート — 複数系列の長さ不一致を補間で解決

### 問題

Recharts の `LineChart` は `data=[{t, a, b, c}]` の各行を x 軸に配置する。  
系列ごとに長さが違うと**端が欠けて描画される**。

### 解決策：`sampleCurve` で固定点数に補間

```ts
// lib/chart/sampleCurve.ts

/** 線形補間で curve を n 点の等間隔サンプルに変換 */
export function sampleCurve(
  curve: { x: number; y: number }[],
  n: number
): { x: number; y: number }[] {
  if (curve.length === 0) return [];
  if (curve.length === 1) return Array(n).fill(curve[0]);

  const result: { x: number; y: number }[] = [];
  const xMin = curve[0].x;
  const xMax = curve[curve.length - 1].x;

  for (let i = 0; i < n; i++) {
    const x = xMin + ((xMax - xMin) * i) / (n - 1);
    // 隣接する2点を探して線形補間
    const idx = curve.findIndex((p) => p.x >= x);
    if (idx === 0) {
      result.push
