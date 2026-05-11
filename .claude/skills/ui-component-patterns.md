---
name: ui-component-patterns
description: >-
  Next.js/Tailwind CSS/TypeScriptプロジェクトにおけるUIコンポーネントの設計・実装パターン。
  ページレイアウト、ナビゲーション、管理画面、アクセスガード、多段ウィザード、
  localStorage永続化、コンポーネントスキャフォールドの標準的な作法を定義する。
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
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-10T19:11:30+00:00'
adoptedFromArchive:
  - archive/prediction-market-analysis/.claude/skills/ui-component-patterns.md
  - archive/aegis-market-os/.claude/skills/admin-panel.md
  - archive/aegis-market-os/.claude/skills/auto-pipeline.md
  - archive/aegis-market-os/.claude/skills/cache-contract.md
  - archive/aegis-market-os/.claude/skills/localstorage-persistence.md
  - archive/aegis-market-os/.claude/skills/nav-menu-patterns.md
  - archive/aegis-market-os/.claude/skills/sim-3d.md
  - archive/aegis-market-os/.claude/skills/strategy-lifecycle.md
  - archive/aegis-market-os/.claude/skills/wizard-design.md
  - archive/ai-company/.claude/skills/add-admin-api-route/SKILL.md
---

# ui-component-patterns

Next.js / Tailwind CSS / TypeScript プロジェクト全般で再利用できる UI 実装パターン集。  
管理画面・ナビゲーション・多段ウィザード・localStorage 永続化・アクセスガード・SVG ビジュアライゼーションの標準作法を定義する。

---

## 1. コンポーネントスキャフォールド（最小テンプレート）

新規コンポーネントは必ずこの構造から始める。

```tsx
// src/components/FeatureCard.tsx
'use client'; // App Router の場合のみ必要な行

import { type FC } from 'react';
import { cn } from '@/lib/utils'; // clsx + tailwind-merge のユーティリティ

interface FeatureCardProps {
  title: string;
  description?: string;
  className?: string;
  children?: React.ReactNode;
}

const FeatureCard: FC<FeatureCardProps> = ({
  title,
  description,
  className,
  children,
}) => {
  return (
    <div className={cn('rounded-lg border bg-card p-4 shadow-sm', className)}>
      <h3 className="text-sm font-semibold">{title}</h3>
      {description && (
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      )}
      {children}
    </div>
  );
};

export default FeatureCard;
```

**命名規則**

| 種別 | 規則 | 例 |
|------|------|----|
| コンポーネントファイル | PascalCase | `UserTable.tsx` |
| フックファイル | camelCase + `use` prefix | `useMarketData.ts` |
| ユーティリティ | camelCase | `formatCurrency.ts` |
| 型定義 | PascalCase + `types.ts` | `market.types.ts` |

---

## 2. ページレイアウトパターン

### 2-1. 通常レイアウト（サイドバー + メインコンテンツ）

```tsx
// src/components/AppLayout.tsx
'use client';

import { useState } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';

interface AppLayoutProps {
  children: React.ReactNode;
}

export default function AppLayout({ children }: AppLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar open={sidebarOpen} onToggle={() => setSidebarOpen((v) => !v)} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header onMenuClick={() => setSidebarOpen((v) => !v)} />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
```

### 2-2. 管理画面専用レイアウト（通常レイアウトとは分離）

管理画面は独立した `AdminLayout` を持ち、通常の `AppLayout` と**共用しない**。

```tsx
// src/pages/admin/AdminLayout.tsx  (~75行が目安)
'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';

const NAV_ITEMS = [
  { path: '/admin', label: 'Dashboard', icon: '📊' },
  { path: '/admin/users', label: 'Users', icon: '👥' },
  { path: '/admin/organizations', label: 'Organizations', icon: '🏢' },
  { path: '/admin/settings', label: 'Settings', icon: '⚙️' },
  { path: '/admin/audit-log', label: 'Audit Log', icon: '📋' },
] as const;

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-screen overflow-hidden">
      {/* サイドバー */}
      <aside className="w-56 shrink-0 border-r bg-muted/40">
        <div className="flex h-14 items-center border-b px-4">
          <span className="text-sm font-bold text-destructive">Admin Panel</span>
        </div>
        <nav className="space-y-1 p-2">
          {NAV_ITEMS.map(({ path, label, icon }) => (
            <Link
              key={path}
              href={path}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors',
                pathname === path
                  ? 'bg-primary text-primary-foreground'
                  : 'hover:bg-accent',
              )}
            >
              <span>{icon}</span>
              {label}
            </Link>
          ))}
        </nav>
      </aside>

      {/* メインコンテンツ */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-14 items-center border-b px-6">
          <h1 className="text-sm font-semibold">Administration</h1>
        </header>
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
```

**管理画面ページ構成**

```
src/pages/admin/
├── AdminLayout.tsx       # 専用レイアウト（~75行）
├── AdminDashboard.tsx    # トップページ
├── AdminUsers.tsx        # ユーザーCRUD
├── AdminOrganizations.tsx
├── AdminSettings.tsx     # APIキー・AIプロバイダー等
└── AdminAuditLog.tsx     # 監査ログビューア
```

---

## 3. ナビゲーションパターン

### 3-1. グループ折りたたみナビゲーション

```tsx
// src/components/Sidebar.tsx
'use client';

import { useState, useCallback } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { loadGroupOpen, saveGroupOpen } from '@/lib/navStorage';

// ナビグループ定義の型
interface NavItem {
  path: string;
  label: string;
  icon?: React.ReactNode;
  adminOnly?: boolean;
  badge?: string | number;
}

interface NavGroup {
  id: string;
  label: string;
  sublabel?: string;
  icon?: React.ReactNode;
  items: NavItem[];
}

// 5グループ構成例（実プロジ
