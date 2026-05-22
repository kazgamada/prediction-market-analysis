---
name: ui-component-patterns
description: >-
  Next.js/Tailwind CSS/TypeScript プロジェクトにおける UI コンポーネント設計の汎用パターン集。
  ページ追加・ナビゲーション構成・管理画面レイアウト・フォーム設計・モバイル対応・日本語業務UI・
  一括操作UIなど、実装頻度の高いパターンを網羅する。「新しいページを追加」「ナビに項目を追加」
  「管理画面を作る」「モバイル対応」「フォームを作る」「一括削除」「日本語フォーム」と言及したときにトリガー。
category: ui-component
version: 2
effectiveTimestamp: '2026-05-20T18:00:00.000Z'
sourceSkillIds:
  - 64a324c6
  - a863600a
  - '81222662'
  - debfceca
  - 8ed74b50
  - 3a311cce
  - 85dcabfc
  - 7ee36646
  - edc407e2
  - 8322f98c
  - 9dde8e3a
  - 3d7e0994
  - 96b3e3af
  - bd1252ec
  - d91aec82
  - d055fb14
  - c66b7f6e
  - '36153534'
  - bc950ac7
  - 5f50170c
  - 5a130b89
  - 90c74276
  - 8a6f7ae0
  - c047749e
  - 3d565ab7
  - a12bfe2f
  - d411e64a
  - 42063f52
  - b4487d87
  - e0972bf4
  - 3f3245b3
generatedAt: '2026-05-21'
---

# UI Component Patterns

Next.js / Tailwind CSS / TypeScript プロジェクト向け、再利用可能な UI 実装パターン集。

---

## 目次

1. [ページ追加の基本パターン](#1-ページ追加の基本パターン)
2. [ナビゲーション構成](#2-ナビゲーション構成)
3. [管理画面レイアウト](#3-管理画面レイアウト)
4. [フォーム設計](#4-フォーム設計)
5. [モバイル対応](#5-モバイル対応)
6. [日本語業務 UI](#6-日本語業務-ui)
7. [一括操作 UI](#7-一括操作-ui)
8. [共通コンポーネント指針](#8-共通コンポーネント指針)

---

## 1. ページ追加の基本パターン

### App Router（Next.js 13+）

```
app/
├── (auth)/          # 認証必須グループ
│   └── dashboard/
│       └── page.tsx
├── (admin)/         # 管理者専用グループ
│   └── admin/
│       └── page.tsx
├── (public)/        # 公開グループ
│   └── about/
│       └── page.tsx
└── api/
    └── admin/
        └── [resource]/
            └── route.ts
```

**URL に影響しない**ルートグループ `(group)` でレイアウトを分離する。

### ページテンプレート（認証必須）

```typescript
// app/(auth)/feature/page.tsx
import { Suspense } from "react";
import { requireAuth } from "@/lib/auth"; // プロジェクト固有の認証ヘルパー
import { FeatureContent } from "./_components/FeatureContent";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";

export const metadata = { title: "機能名 | AppName" };

export default async function FeaturePage() {
  // サーバーコンポーネントで認証チェック
  const session = await requireAuth();

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold mb-6">機能名</h1>
      <Suspense fallback={<LoadingSpinner />}>
        <FeatureContent userId={session.userId} />
      </Suspense>
    </div>
  );
}
```

### App Router での動的パラメータ

```typescript
// app/(auth)/items/[id]/page.tsx
// ⚠️ Next.js 15+ では params が Promise になる
export default async function ItemPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params; // await 必須
  // ...
}
```

> **注意**: Next.js のバージョンにより `params` の型が変わる。
> v14 以前: `{ id: string }` / v15+: `Promise<{ id: string }>`
> プロジェクトの `package.json` で確認し、適切な方を使うこと。

---

## 2. ナビゲーション構成

### ナビ定義ファイルの一元管理

```typescript
// lib/nav-config.ts
import {
  LayoutDashboard,
  Users,
  Settings,
  Shield,
  type LucideIcon,
} from "lucide-react";

export type NavSection = "main" | "settings" | "admin";

export interface NavItem {
  label: string;          // 表示テキスト（日本語可）
  href: string;           // ルートパス
  icon: LucideIcon;       // Lucide アイコン
  section: NavSection;
  badge?: string | number; // 通知バッジ（任意）
  requiredRole?: "admin" | "user"; // 表示制御
}

export const NAV_ITEMS: NavItem[] = [
  // --- main ---
  {
    label: "ダッシュボード",
    href: "/dashboard",
    icon: LayoutDashboard,
    section: "main",
  },
  {
    label: "ユーザー管理",
    href: "/users",
    icon: Users,
    section: "main",
    requiredRole: "admin",
  },
  // --- settings ---
  {
    label: "設定",
    href: "/settings",
    icon: Settings,
    section: "settings",
  },
  // --- admin ---
  {
    label: "管理パネル",
    href: "/admin",
    icon: Shield,
    section: "admin",
    requiredRole: "admin",
  },
];
```

### サイドバーコンポーネント

```typescript
// components/layout/Sidebar.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { NAV_ITEMS, type NavSection } from "@/lib/nav-config";

interface SidebarProps {
  userRole?: "admin" | "user";
}

const SECTION_LABELS: Record<NavSection, string> = {
  main: "メイン",
  settings: "設定",
  admin: "管理",
};

export function Sidebar({ userRole = "user" }: SidebarProps) {
  const pathname = usePathname();

  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.requiredRole || item.requiredRole === userRole
  );

  const sections = (["main", "settings", "admin"] as NavSection[]).filter(
    (section) => visibleItems.some((item) => item.section === section)
  );

  return (
    <aside className="w-64 min-h-screen bg-gray-900 text-white flex flex-col">
      <div className="p-4 border-b border-gray-700">
        <span className="font-bold text-lg">AppName</span>
      </div>
      <nav className="flex-1 p-4 space-y-6">
        {sections.map((section) => (
          <div key={section}>
            <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">
              {SECTION_LABELS[section]}
            </p>
            <ul className="space-y-1">
              {visibleItems
                .filter((item) => item.section === section)
                .map((item) => {
                  const isActive = pathname.startsWith
