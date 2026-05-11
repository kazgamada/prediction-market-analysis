---
name: ui-component-patterns
description: >-
  Next.js/Tailwind
  CSS/TypeScriptプロジェクトでUIコンポーネントを実装・スキャフォールドするときに使う。コンポーネント構造・命名規則・ナビゲーション設定・フォームパターン・日本語業務UI規約（姓名順・郵便番号補完・和暦・全角半角・金額表示）・管理画面ガード・メールテンプレートを含む。「コンポーネント追加」「ナビ追加」「フォーム」「管理画面」「業務画面」「帳票」と言及したときにトリガー。
category: ui-component
sourceSkillIds:
  - 31a30658
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
  - 2a92e748
  - d3686b17
  - b0a42ccc
  - 89d0d7de
  - 3ec995d8
  - ee3f7180
  - 72a9c66e
  - 829c79d8
  - d645c58a
  - a5c0b83b
  - 6a4eae1f
  - 33d841a8
  - 7415edf9
  - '33593959'
  - 396f57ca
  - a1155806
  - 445b6452
  - 02943869
  - 8c82e4e2
  - 4e8f1d59
  - 006d9e9f
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
  - d8ff8fe6
  - 1e11f2ae
  - b192776e
  - cd6696c6
  - b0301649
  - 263c55d6
  - dc43009e
  - d675c999
  - 6a42ba2b
  - f03a99ec
  - 155f83e7
  - 5f865b4b
  - 7773eb42
  - 3728b7e1
  - 4c88935b
  - c11d1ffe
  - 8c1bdc2f
  - d9f02e80
  - aac58b03
  - 5c3327ac
  - 69aa32ef
  - 88a081a3
  - 37ab3c26
  - e7f652fa
  - 3057d446
  - fa8b7acd
  - 436fe824
  - 2444360f
  - 223550d1
  - 852eb091
  - c5225752
  - '59199837'
  - 2b3ac591
  - 00718710
  - ab6a4325
  - 258bff15
  - b8f1e1bd
  - 0affee22
  - 77f23611
  - 434eaa55
generatedAt: '2026-05-11'
---

# UI コンポーネントパターン

## 概要

Next.js / Tailwind CSS / TypeScript プロジェクト全般で適用するコンポーネント設計・実装規約。  
汎用的なコンポーネント構造から、日本語業務アプリ特有の入力パターン・管理画面ガードまでをカバーする。

---

## 1. コンポーネント基本構造

### ファイル配置規則

```
src/
  components/
    ui/               # 汎用プリミティブ（Button, Input, Modal…）
    features/         # 機能単位の複合コンポーネント
    layouts/          # ページレイアウト
    guards/           # 認証・権限ガード
  app/
    (dashboard)/      # 認証済みルート群
      admin/          # 管理者専用ページ
```

### 標準コンポーネントテンプレート

```tsx
// src/components/features/<ComponentName>.tsx
'use client'; // クライアント操作が必要な場合のみ

import { useState } from 'react';
import { SomeIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

// ---- 型定義 ----
interface <ComponentName>Props {
  /** 表示ラベル */
  label: string;
  /** 追加CSSクラス */
  className?: string;
  /** コールバック */
  onAction?: (value: string) => void;
}

// ---- コンポーネント ----
export function <ComponentName>({ label, className, onAction }: <ComponentName>Props) {
  const [isLoading, setIsLoading] = useState(false);

  return (
    <div className={cn('rounded-lg border bg-white p-4 shadow-sm', className)}>
      <h2 className="text-sm font-medium text-gray-700">{label}</h2>
      {/* 実装 */}
    </div>
  );
}

export default <ComponentName>;
```

### 命名・エクスポート規則

| 種別 | 規則 | 例 |
|------|------|-----|
| コンポーネント名 | PascalCase | `UserProfileCard` |
| ファイル名 | kebab-case | `user-profile-card.tsx` |
| Props型 | `<Name>Props` | `UserProfileCardProps` |
| エクスポート | named + default 両方 | `export function X` & `export default X` |
| hooks | `use` プレフィックス | `useUserProfile` |

---

## 2. ナビゲーション設定パターン

### Nav設定ファイル構造

```tsx
// src/config/navigation.ts
import { LayoutDashboard, Settings, Shield, Users } from 'lucide-react';

export type NavSection = 'main' | 'settings' | 'admin';

export interface NavItem {
  label: string;        // 表示テキスト（日本語可）
  href: string;         // ルートパス
  icon: React.ComponentType<{ className?: string }>;
  section: NavSection;
  badge?: string;       // バッジテキスト（任意）
  requireAdmin?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  // main
  { label: 'ダッシュボード', href: '/dashboard',  icon: LayoutDashboard, section: 'main' },
  { label: 'ユーザー管理',   href: '/users',       icon: Users,           section: 'main' },
  // settings
  { label: '設定',           href: '/settings',    icon: Settings,        section: 'settings' },
  // admin
  { label: '管理者設定',     href: '/admin',       icon: Shield,          section: 'admin', requireAdmin: true },
];
```

### Sidebar コンポーネント

```tsx
// src/components/layouts/Sidebar.tsx
'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { NAV_ITEMS, NavSection } from '@/config/navigation';
import { cn } from '@/lib/utils';

const SECTION_LABELS: Record<NavSection, string> = {
  main:     'メニュー',
  settings: '設定',
  admin:    '管理',
};

export function Sidebar({ isAdmin = false }: { isAdmin?: boolean }) {
  const pathname = usePathname();
  const sections: NavSection[] = ['main', 'settings', 'admin'];

  return (
    <aside className="flex h-full w-60 flex-col border-r bg-gray-50 px-3 py-4">
      {sections.map((section) => {
        const items = NAV_ITEMS.filter(
          (item) => item.section === section && (!item.requireAdmin || isAdmin)
        );
        if (!items.length) return null;
        return (
          <div key={section} className="mb-6">
            <p className="mb-1 px-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
              {SECTION_LABELS[section]}
            </p>
            <nav className="space-y-0.5">
              {items.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors',
                    pathname.startsWith(item.href)
                      ? 'bg-primary/10 font-medium text-primary'
                      : 'text-gray-600 hover:bg-gray-100'
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {item.label}
                  {item.badge && (
                    <span className="ml-auto rounded-full bg-primary px-1.5 py-0.5 text-[10px] text-white">
                      {item.badge}
                    </span>
                  )}
                </Link>
              ))}
            </nav>
          </div>
        );
      })}
    </aside>
  );
}
```

---

## 3. 管理画面ガードパターン

### AdminGuard コンポーネント

```tsx
// src/components/guards/admin-guard.tsx
'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/hooks/use-auth'; // プロジェクトの認証hookに合わせて変更

interface AdminGuardProps {
  children: React.ReactNode;
  /** true の場合は site
