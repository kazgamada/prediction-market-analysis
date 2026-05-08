---
name: ui-component-patterns
description: >-
  Next.js/Tailwind CSS/TypeScriptプロジェクトにおけるUIコンポーネントの設計・実装パターン。
  ページレイアウト、ナビゲーション、管理画面、アクセスガード、コンポーネントスキャフォールドの標準的な作法を定義する。
category: ui-component
sourceSkillIds:
  - 599fb175
  - '6e708673'
  - dbcda494
  - 58b43453
  - b3100292
  - 1a340d56
  - 3c2e65fe
  - c0e8c7a4
  - c5409679
  - 1217c356
  - e7b097a2
  - e9390261
  - 12de9eb8
  - d3686b17
  - b0a42ccc
  - 89d0d7de
  - 3ec995d8
  - ee3f7180
  - 72a9c66e
  - d645c58a
  - a5c0b83b
  - 6a4eae1f
  - 33d841a8
  - '33593959'
  - 396f57ca
  - a1155806
  - 445b6452
  - 02943869
  - 8c82e4e2
  - 4e8f1d59
  - b2517622
  - 35d0dc33
  - 24d1d816
  - 92db6536
  - 0488cb30
  - d4497da7
  - ddd494df
  - e47ac311
  - 3a698492
  - 595255b8
  - 65a92c76
  - cdb9241f
  - 1e11f2ae
  - b192776e
  - cd6696c6
  - b0301649
  - dc43009e
  - 6a42ba2b
  - 155f83e7
  - 7773eb42
  - 4c88935b
  - c11d1ffe
  - 8c1bdc2f
  - d9f02e80
  - aac58b03
  - 69aa32ef
  - 88a081a3
  - 37ab3c26
  - e7f652fa
  - fa8b7acd
  - 436fe824
  - 2444360f
  - 223550d1
  - 852eb091
  - '59199837'
  - 00718710
  - 258bff15
  - b8f1e1bd
  - 0affee22
  - 434eaa55
  - 6b5055b4
  - baae9114
generatedAt: '2026-05-08'
---

# UI Component Patterns

Next.js (App Router) + Tailwind CSS + TypeScript プロジェクトにおける、UIコンポーネントの設計・実装の標準パターン集。

---

## 1. ディレクトリ構造の原則

```
src/
├── app/
│   ├── (admin)/          # 管理者用ルートグループ（URLに現れない）
│   ├── (auth)/           # 認証系ルートグループ
│   ├── (dashboard)/      # 一般ユーザー用ダッシュボード
│   └── (legal)/          # 利用規約等
├── components/
│   ├── ui/               # 汎用Atomicコンポーネント（Button, Input等）
│   ├── layout/           # レイアウト系（Header, Sidebar, Footer）
│   ├── guards/           # アクセス制御コンポーネント
│   └── features/         # 機能別コンポーネント
└── lib/
    └── api/              # APIクライアント
```

**ルートグループ（Route Groups）** を使ってレイアウトを分離する。`(admin)`, `(dashboard)`, `(auth)` などは URL に影響しない。

---

## 2. レイアウトコンポーネント

### 基本レイアウト構造

```tsx
// src/components/layout/AppLayout.tsx
import { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

### 管理者専用レイアウト

```tsx
// src/components/layout/AdminLayout.tsx
import { ReactNode } from "react";
import { AdminSidebar } from "./AdminSidebar";
import { AdminHeader } from "./AdminHeader";

interface AdminLayoutProps {
  children: ReactNode;
}

export function AdminLayout({ children }: AdminLayoutProps) {
  return (
    <div className="flex h-screen bg-gray-100">
      <AdminSidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <AdminHeader />
        <main className="flex-1 overflow-y-auto p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
```

### App Router での layout.tsx への適用

```tsx
// src/app/(admin)/layout.tsx
import { AdminLayout } from "@/components/layout/AdminLayout";
import { AdminGuard } from "@/components/guards/AdminGuard";

export default function AdminRootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AdminGuard requireSiteOwner>
      <AdminLayout>{children}</AdminLayout>
    </AdminGuard>
  );
}
```

---

## 3. ナビゲーション設定パターン

ナビゲーション項目は **設定オブジェクト** として一元管理する。

```tsx
// src/config/navigation.ts
import {
  LayoutDashboard,
  Users,
  Settings,
  FileText,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  section: "main" | "settings" | "admin";
  badge?: string | number;
}

export const NAV_ITEMS: NavItem[] = [
  // main
  { label: "ダッシュボード", href: "/dashboard",    icon: LayoutDashboard, section: "main" },
  { label: "ユーザー管理",   href: "/admin/users",  icon: Users,           section: "admin" },
  { label: "設定",           href: "/settings",     icon: Settings,        section: "settings" },
  { label: "ドキュメント",   href: "/docs",         icon: FileText,        section: "main" },
];
```

```tsx
// src/components/layout/Sidebar.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_ITEMS, type NavItem } from "@/config/navigation";
import { cn } from "@/lib/utils";

function NavLink({ item }: { item: NavItem }) {
  const pathname = usePathname();
  const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
        isActive
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      )}
    >
      <Icon className="h-4 w-4" />
      {item.label}
      {item.badge && (
        <span className="ml-auto rounded-full bg-red-500 px-1.5 py-0.5 text-xs text-white">
          {item.badge}
        </span>
      )}
    </Link>
  );
}

export function Sidebar() {
  const mainItems    = NAV_ITEMS.filter((i) => i.section === "main");
  const settingsItems = NAV_ITEMS.filter((i) => i.section === "settings");

  return (
    <aside className="w-64 border-r bg-white flex flex-col">
      <div className="p-4 border-b">
        <h1 className="text-lg font-bold">App Name</h1>
      </div>
      <nav className="flex-1 p-4 space-y-1">
        {mainItems.map((item) => (
          <NavLink key={item.href} item={item} />
        ))}
      </nav>
      <div className="p-4 border-t space-y-1">
        {settingsItems.map((item) => (
          <NavLink key={item.href} item={item} />
        ))}
      </div>
    </aside>
  );
}
```

---

## 4. アクセスガードパターン

### クライアントサイドガード

```tsx
// src/components/guards/AdminGuard.tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

interface AdminGuardProps {
  children: React.ReactNode;
  requireSiteOwner?: boolean;
}

export function AdminGuard({ children, requireSiteOwner = false }: AdminGuardProps) {
  const {
