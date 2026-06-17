---
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
generatedAt: '2026-06-17'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-21T10:00:00.000Z'
adoptedFromArchive:
  - archive/skills/mobile-ui-spec.md
  - archive/skills/add-admin-api-route.md
  - archive/skills/add-admin-page.md
  - archive/skills/add-dashboard-page.md
  - archive/skills/add-nav-item.md
  - archive/skills/add-self-service-ui.md
  - archive/skills/add-tenant-api-route.md
  - archive/skills/build-check.md
  - archive/skills/frozen-scope-guard.md
  - archive/skills/japanese-business-ui.md
---
```markdown
---
name: ui-component-patterns
description: >-
  Next.js / Tailwind CSS / TypeScript プロジェクトで再利用できる UI コンポーネント実装パターンの完全ガイド。
  レスポンシブレイアウト（ボトムナビ・ドロワー・サイドバー）、モバイル操作（スワイプ・長押し・Pull-to-Refresh）、
  ページテンプレート（ダッシュボード・管理画面・アカウント設定）、ナビゲーション設計、日本語業務フォーム、
  iOS Safari 対応（safe-area・viewport）、フィードバック UI（スナックバー・Undo・Toast）、
  アクセシビリティ、ビルド検証フローを網羅。
  「スマホ UI」「モバイル対応」「ボトムナビ」「ハンバーガー」「safe-area」「スワイプ削除」
  「Pull-to-Refresh」「Undo」「長押し」「ダッシュボードページ追加」「管理画面」「ナビ追加」
  「日本語フォーム」「業務画面」「住所入力」「帳票」と言及したときにトリガー。
category: ui-component
version: 1
---

# UI Component Patterns — 汎用実装ガイド

## 目次

1. [設計原則](#1-設計原則)
2. [レイアウト・ナビゲーション構造](#2-レイアウトナビゲーション構造)
3. [レスポンシブ & モバイル UI](#3-レスポンシブ--モバイル-ui)
4. [ページテンプレート](#4-ページテンプレート)
5. [インタラクション & フィードバック UI](#5-インタラクション--フィードバック-ui)
6. [日本語業務フォーム規約](#6-日本語業務フォーム規約)
7. [iOS Safari 対応](#7-ios-safari-対応)
8. [アクセシビリティ](#8-アクセシビリティ)
9. [ビルド検証フロー](#9-ビルド検証フロー)
10. [チェックリスト](#10-チェックリスト)

---

## 1. 設計原則

| 原則 | 内容 |
|------|------|
| **モバイルファースト** | `base` → `md:` → `lg:` の順に記述 |
| **単一責務** | 1 コンポーネント = 1 役割。状態管理・表示・スタイルを分離 |
| **型安全** | Props は必ず `interface` / `type` で定義。`any` 禁止 |
| **アクセシビリティ** | WCAG 2.1 AA 準拠。`aria-*` 属性・フォーカス管理を必須実装 |
| **Tailwind 優先** | カスタム CSS は最終手段。`cn()` / `clsx` でクラス合成 |
| **ロケール考慮** | 日本語 UI では全角・和暦・敬語規約を遵守（§6 参照）|

```ts
// cn() ユーティリティ（tailwind-merge + clsx）
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

---

## 2. レイアウト・ナビゲーション構造

### 2-1. ブレークポイント運用

```
< 768px  → モバイル: ボトムナビ + ハンバーガードロワー
768px〜  → タブレット/PC: サイドバー常時表示
```

```ts
// tailwind.config.ts
theme: {
  screens: {
    sm:  "640px",
    md:  "768px",   // モバイル/デスクトップの境界
    lg:  "1024px",
    xl:  "1280px",
    "2xl": "1536px",
  },
}
```

### 2-2. サイドバーレイアウト（デスクトップ）

```tsx
// components/layout/AppLayout.tsx
interface AppLayoutProps {
  children: React.ReactNode;
  sidebar: React.ReactNode;
}

export function AppLayout({ children, sidebar }: AppLayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* デスクトップのみサイドバー表示 */}
      <aside className="hidden md:flex md:w-64 md:flex-col border-r">
        {sidebar}
      </aside>
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
```

### 2-3. ナビゲーション設定の追加手順

```ts
// config/navigation.ts — ナビ項目の一元管理
export interface NavItem {
  label: string;        // 表示テキスト（日本語可）
  href: string;         // ルートパス
  icon: LucideIcon;     // lucide-react アイコン
  section: "main" | "settings" | "admin";
  badge?: number;       // 未読カウント等
  requireRole?: "admin" | "tenant";
}

export const NAV_ITEMS: NavItem[] = [
  { label: "ダッシュボード", href: "/dashboard", icon: LayoutDashboard, section: "main" },
  { label: "設定",          href: "/settings",  icon: Settings,         section: "settings" },
];
```

**ナビ追加時の手順:**

1. `config/navigation.ts` に `NavItem` を追記
2. `section` に応じて Sidebar / BottomNav が自動反映（後述）
3. `requireRole` でアクセス制御
4. ビルド検証（§9）を実行

### 2-4. Sidebar コンポーネント

```tsx
// components/layout/Sidebar.tsx
import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_ITEMS, type NavItem } from "@/config/navigation";

interface SidebarProps {
  userRole?: "admin" | "tenant";
}

export function Sidebar({ userRole }: SidebarProps) {
  const pathname = usePathname();

  const filtered = NAV_ITEMS.filter(
    (item) => !item.requireRole || item.requireRole === userRole
  );

  return (
    <nav className="flex flex-col gap-1 p-4" aria-label="メインナビゲーション">
      {filtered.map((item) => (
        <SidebarItem key={item.href} item={item} isActive={pathname === item.href} />
      ))}
    </nav>
  );
}

function SidebarItem({ item, isActive }: { item: NavItem; isActive: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={
