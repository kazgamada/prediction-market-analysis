---
name: ui-component-patterns
description: >-
  Next.js / Tailwind CSS / TypeScript プロジェクトにおける UI コンポーネントの設計・実装パターン。
  ページレイアウト、ナビゲーション、管理画面、アクセスガード、一括操作 UI、 コンポーネントスキャフォールドの標準的な作法を定義する。 日本語業務 UI
  規約・GDPR セルフサービス UI も含む。
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
  - 8a6f7ae0
  - c047749e
  - a12bfe2f
  - d411e64a
  - 42063f52
  - b4487d87
  - e0972bf4
  - 3f3245b3
generatedAt: '2026-05-11'
---

# UI Component Patterns

## 目次

1. [ディレクトリ構造と命名規則](#1-ディレクトリ構造と命名規則)
2. [コンポーネントスキャフォールド](#2-コンポーネントスキャフォールド)
3. [ページレイアウトパターン](#3-ページレイアウトパターン)
4. [ナビゲーション管理](#4-ナビゲーション管理)
5. [管理画面パターン](#5-管理画面パターン)
6. [アクセスガード](#6-アクセスガード)
7. [一括操作 UI（Bulk Actions）](#7-一括操作-ui)
8. [日本語業務 UI 規約](#8-日本語業務-ui-規約)
9. [GDPR セルフサービス UI](#9-gdpr-セルフサービス-ui)
10. [Admin API ルート](#10-admin-api-ルート)

---

## 1. ディレクトリ構造と命名規則

```
src/
├── app/                          # App Router (Next.js 13+)
│   ├── (auth)/                   # 認証不要レイアウト群
│   ├── (admin)/                  # 管理者レイアウト群
│   │   └── admin/
│   │       ├── layout.tsx        # AdminLayout（サイドバー付き）
│   │       ├── page.tsx          # AdminDashboard
│   │       ├── users/page.tsx
│   │       └── settings/page.tsx
│   ├── (viewer)/                 # 一般ユーザーレイアウト群
│   └── api/
│       └── admin/                # Admin API Routes
│           └── [resource]/
│               └── route.ts
├── components/
│   ├── ui/                       # Primitive UI（Button, Input, etc.）
│   ├── layout/                   # Header, Sidebar, Footer
│   └── features/                 # ドメイン固有コンポーネント
└── lib/
    └── auth/
        └── requireAdmin.ts
```

### 命名規則

| 対象 | 規則 | 例 |
|------|------|----|
| コンポーネントファイル | PascalCase | `UserTable.tsx` |
| ページファイル | `page.tsx` (App Router) | `app/admin/users/page.tsx` |
| フック | `use` プレフィックス | `useAdminUsers.ts` |
| 型定義 | `*.types.ts` または同ファイル内 | `UserTable.types.ts` |

> **Note (App Router バージョン差異):**  
> Next.js 13–14 では `params` は同期オブジェクト。  
> Next.js 15+ では `params` が **Promise** になる。バージョンに応じて以下を使い分ける。
>
> ```ts
> // Next.js 15+
> export default async function Page({ params }: { params: Promise<{ id: string }> }) {
>   const { id } = await params;
> }
> ```

---

## 2. コンポーネントスキャフォールド

### 基本テンプレート

```tsx
// components/features/ExampleCard.tsx
"use client"; // データフェッチのみなら不要

import { type FC } from "react";
import { cn } from "@/lib/utils"; // clsx + tailwind-merge ユーティリティ

interface ExampleCardProps {
  title: string;
  description?: string;
  className?: string;
}

export const ExampleCard: FC<ExampleCardProps> = ({
  title,
  description,
  className,
}) => {
  return (
    <div className={cn("rounded-lg border bg-card p-4 shadow-sm", className)}>
      <h3 className="text-lg font-semibold">{title}</h3>
      {description && (
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      )}
    </div>
  );
};
```

### ローディング・エラー状態を含む非同期コンポーネント

```tsx
"use client";

import { Loader2, AlertCircle } from "lucide-react";

interface AsyncContentProps<T> {
  data: T | undefined;
  isLoading: boolean;
  error: Error | null;
  children: (data: T) => React.ReactNode;
}

export function AsyncContent<T>({
  data,
  isLoading,
  error,
  children,
}: AsyncContentProps<T>) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-destructive">
        <AlertCircle className="h-4 w-4 shrink-0" />
        <p className="text-sm">{error.message}</p>
      </div>
    );
  }
  if (!data) return null;
  return <>{children(data)}</>;
}
```

---

## 3. ページレイアウトパターン

### 汎用ページテンプレート（App Router）

```tsx
// app/(viewer)/dashboard/page.tsx
import { Suspense } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { DashboardContent } from "@/components/features/DashboardContent";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata = { title: "ダッシュボード" };

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader
        title="ダッシュボード"
        description="全体の状況を確認します"
      />
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <DashboardContent />
      </Suspense>
    </div>
  );
}
```

### PageHeader コンポーネント

```tsx
// components/layout/PageHeader.tsx
interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-muted-foreground"
