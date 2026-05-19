---
name: ui-component-patterns
description: >-
  Next.js/Tailwind CSS/TypeScript プロジェクトにおける UI
  コンポーネント設計・実装パターンの統合ガイド。ページ追加、ナビゲーション構成、管理画面レイアウト、フォーム規約、コンポーネント分類を含む。「ページを追加したい」「ナビにリンクを追加」「管理画面を作りたい」「フォームを実装したい」と言及したときにトリガー。
category: ui-component
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
generatedAt: '2026-05-19'
---

# UI Component Patterns

## 概要

Next.js App Router + Tailwind CSS + TypeScript プロジェクトにおける、UI コンポーネントの設計・実装パターン集。  
ページ追加・ナビゲーション構成・管理画面・フォーム・削除操作など、頻出ユースケースのパターンを提供する。

---

## 1. ディレクトリ構成の原則

```
src/
├── app/                        # App Router (Next.js)
│   ├── (auth)/                 # 認証グループ（URL に現れない）
│   ├── (admin)/                # 管理者グループ
│   │   └── admin/
│   │       ├── layout.tsx      # 管理レイアウト（AdminSidebar 含む）
│   │       └── [resource]/
│   │           └── page.tsx
│   ├── (app)/                  # 一般ユーザーグループ
│   │   └── [feature]/
│   │       └── page.tsx
│   └── api/
│       └── admin/
│           └── [resource]/
│               └── route.ts
├── components/
│   ├── ui/                     # 汎用プリミティブ（Button, Input, Badge…）
│   ├── layout/                 # Sidebar, Header, PageWrapper
│   ├── admin/                  # 管理画面専用
│   └── [feature]/              # 機能別コンポーネント
└── lib/
    └── nav.ts                  # ナビゲーション定義（単一ソース）
```

### ルーティングルール

- **App Router のみ**使用。`pages/` ディレクトリは作らない。
- ルートグループ `(group)` でレイアウトを分離し、URL には現れない。
- 動的セグメントは `[id]` 形式。
- Next.js 15 以降: `params` / `searchParams` は **Promise** で受け取る。

```ts
// app/admin/users/[id]/page.tsx
export default async function UserDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  // ...
}
```

---

## 2. ページ追加パターン

### 2-1. 基本ページテンプレート

```tsx
// app/(app)/[feature]/page.tsx
import { Suspense } from "react";
import { Loader2 } from "lucide-react";
import { FeatureList } from "@/components/[feature]/FeatureList";

export const metadata = { title: "機能名 | AppName" };

export default function FeaturePage() {
  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">機能名</h1>
      </div>
      <Suspense fallback={<Loader2 className="animate-spin" />}>
        <FeatureList />
      </Suspense>
    </div>
  );
}
```

### 2-2. 認証必須ページ（tRPC 使用例）

```tsx
// components/[feature]/FeatureList.tsx
"use client";

import { trpc } from "@/lib/trpc";
import { Loader2 } from "lucide-react";

export function FeatureList() {
  const { data, isLoading } = trpc.feature.list.useQuery();

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <ul className="divide-y rounded-lg border">
      {data?.map((item) => (
        <li key={item.id} className="flex items-center gap-4 p-4">
          <span>{item.name}</span>
        </li>
      ))}
    </ul>
  );
}
```

---

## 3. ナビゲーション構成

### 3-1. ナビ定義ファイル（単一ソース）

```ts
// lib/nav.ts
import {
  LayoutDashboard,
  Users,
  Settings,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export type NavSection = "main" | "settings" | "admin";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  section: NavSection;
  badge?: string;          // "NEW" などの任意バッジ
  requiredRole?: "admin";  // ロールゲート
}

export const NAV_ITEMS: NavItem[] = [
  { label: "ダッシュボード", href: "/dashboard", icon: LayoutDashboard, section: "main" },
  { label: "ユーザー管理",   href: "/users",     icon: Users,           section: "main" },
  { label: "設定",           href: "/settings",  icon: Settings,        section: "settings" },
  { label: "管理者",         href: "/admin",     icon: ShieldCheck,     section: "admin", requiredRole: "admin" },
];
```

### 3-2. ナビアイテム追加時の手順

1. `lib/nav.ts` の `NAV_ITEMS` 配列に追記する（**他ファイルを直接編集しない**）。
2. Sidebar / Header コンポーネントは `NAV_ITEMS` を `section` でフィルタして描画する。
3. `requiredRole: "admin"` を付与するとロールチェック後にのみ表示される。

```tsx
// components/layout/Sidebar.tsx（抜粋）
import { NAV_ITEMS } from "@/lib/nav";

const mainItems = NAV_ITEMS.filter((i) => i.section === "main");

export function Sidebar() {
  return (
    <nav className="flex flex-col gap-1 p-3">
      {mainItems.map((item) => (
        <SidebarLink key={item.href} item={item} />
      ))}
    </nav>
  );
}
```

---

## 4. 管理画面パターン

### 4-1. 管理レイアウト

```tsx
// app/(admin)/admin/layout.tsx
import { redirect } from "next/navigation";
import { requireAdmin } from "@/lib/auth";
import { AdminSidebar } from "@/components/admin/AdminSidebar";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await requireAdmin();      // 未認証 or
