---
category: ui-component
sourceSkillIds:
  - 64a324c6
  - a863600a
  - '81222662'
  - debfceca
  - 8ed74b50
  - 3a311cce
  - 9db061b3
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
  - 3f3245b3
  - b4487d87
  - e0972bf4
generatedAt: '2026-06-22'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-06-21T02:36:25Z'
adoptedFromArchive:
  - archive/skills/blank-page-debug.md
  - archive/skills/japanese-business-ui.md
  - archive/skills/ui-component-patterns.md
  - archive/skills/add-admin-api-route.md
  - archive/skills/add-admin-page.md
  - archive/skills/add-dashboard-page.md
  - archive/skills/add-tenant-api-route.md
  - archive/skills/frozen-scope-guard.md
  - archive/skills/01-nextjs-16-app-router.md
  - archive/skills/06-admin-bulk-delete-api.md
---
```markdown
---
name: ui-component-patterns
description: >-
  Next.js / Tailwind CSS / TypeScript プロジェクトで再利用できる UI コンポーネント実装パターンの完全ガイド。
  レスポンシブレイアウト（ボトムナビ・ドロワー・サイドバー）、モバイル操作（スワイプ・長押し・Pull-to-Refresh）、
  フォーム設計（React Hook Form + Zod）、テーブル・一括操作、ページネーション、モーダル・トースト、
  ダークテーマ、日本語業務 UI 規約、本番白紙デバッグまでを網羅。
  「コンポーネントを作って」「レイアウトを整えて」「フォームを追加」「テーブルに一括削除」
  「モバイル対応」「日本語フォーム」「画面が真っ白」などでトリガー。
category: ui-component
---

# UI コンポーネントパターン完全ガイド

## 目次

1. [プロジェクト構造の規約](#1-プロジェクト構造の規約)
2. [レイアウトパターン](#2-レイアウトパターン)
3. [フォーム設計](#3-フォーム設計)
4. [テーブル・一括操作](#4-テーブル一括操作)
5. [モーダル・トースト](#5-モーダルトースト)
6. [モバイル操作パターン](#6-モバイル操作パターン)
7. [ページルーティング規約（App Router）](#7-ページルーティング規約app-router)
8. [日本語業務 UI 規約](#8-日本語業務-ui-規約)
9. [ダークテーマ規約](#9-ダークテーマ規約)
10. [本番白紙デバッグ](#10-本番白紙デバッグ)

---

## 1. プロジェクト構造の規約

```
src/
├── app/                        # App Router（pages/ は未使用）
│   ├── (admin)/               # 管理画面ルートグループ（URL に現れない）
│   ├── (dashboard)/           # テナント向けダッシュボード
│   ├── (auth)/                # 認証画面
│   └── api/
│       ├── admin/             # プラットフォーム管理 API（requireAdmin）
│       └── tenant/            # テナントスコープ API（requireTenantUser）
├── components/
│   ├── ui/                    # 汎用プリミティブ（Button, Input, Modal など）
│   ├── admin/                 # 管理画面専用（AdminSidebar など）
│   └── dashboard/             # テナント画面専用
└── lib/
    ├── hooks/                  # カスタムフック
    └── utils/                  # 型・ユーティリティ
```

### コンポーネントファイル命名

```
components/
├── ui/
│   ├── Button.tsx             # PascalCase
│   ├── Button.test.tsx
│   └── index.ts               # barrel export
```

---

## 2. レイアウトパターン

### 2-1. サイドバー + メインエリア（デスクトップ）

```tsx
// app/(dashboard)/layout.tsx
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-gray-950">
      <DashboardSidebar />                          {/* 固定幅 w-64 */}
      <main className="flex-1 overflow-y-auto p-6">
        {children}
      </main>
    </div>
  );
}
```

```tsx
// components/dashboard/DashboardSidebar.tsx
'use client';

const NAV_ITEMS = [
  { href: '/dashboard',          label: 'ホーム',    icon: HomeIcon },
  { href: '/dashboard/settings', label: '設定',      icon: SettingsIcon },
];

export function DashboardSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 flex-shrink-0 bg-gray-900 flex flex-col">
      <div className="p-4 border-b border-gray-800">
        <Logo />
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
              pathname === href
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:bg-gray-800 hover:text-white'
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
```

### 2-2. モバイル：ボトムナビ

```tsx
'use client';
// 画面下部に固定。アイコン + ラベル構成。
export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="fixed bottom-0 inset-x-0 bg-white border-t border-gray-200 
                    flex items-center justify-around h-16 safe-area-pb z-40 md:hidden">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active = pathname.startsWith(href);
        return (
          <Link key={href} href={href}
            className={cn('flex flex-col items-center gap-0.5 py-1 px-3',
              active ? 'text-blue-600' : 'text-gray-500')}
          >
            <Icon className="w-5 h-5" />
            <span className="text-xs">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
// tailwind.config.ts に safe-area-pb を追加
// padding-bottom: env(safe-area-inset-bottom)
```

### 2-3. ドロワー（モバイルサイドメニュー）

```tsx
'use client';

export function Drawer({ open, onClose, children }: DrawerProps) {
  // スクロールロック
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  return (
    <>
      {/* オーバーレイ */}
      <div
        className={cn(
          'fixed inset-0 bg-black/50 z-40 transition-opacity',
          open ? 'opacity-100' : 'opacity-0 pointer-events-none'
        )}
        onClick={onClose}
      />
      {/* ドロワー本体 */}
      <div
        className={cn(
          'fixed left-0 top-0 h-full w-72 bg-white shadow-xl z-50',
