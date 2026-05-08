---
name: general-best-practices
description: >-
  Next.js/TypeScriptプロジェクト全般に適用できるベストプラクティス集。
  UX・型安全・セキュリティ・状態管理・進捗トラッキング・アナリティクス・通知の 実装パターンを網羅する汎用ガイドライン。
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
  - c9059c14
  - cdf33693
  - d7c9e9fd
  - e222d135
  - c9e5eed7
  - 1cbf55ef
  - 12f7940a
  - a5df638b
  - cdb391a7
generatedAt: '2026-05-08'
---

# Next.js / TypeScript 汎用ベストプラクティス

あらゆるNext.js/TypeScriptプロジェクトに適用できる設計原則と実装パターン集。
新規機能追加・コードレビュー・リファクタリング時の判断基準として参照する。

---

## 1. TypeScript 型安全の原則

### 1-1. `any` を使わない

```typescript
// ❌ Bad
function process(data: any) { ... }

// ✅ Good
function process(data: unknown) {
  if (typeof data === 'string') { ... }
}

// ✅ Good — 外部API応答には Zod でバリデーション
import { z } from 'zod';

const ResponseSchema = z.object({
  id: z.string(),
  name: z.string(),
  createdAt: z.coerce.date(),
});
type Response = z.infer<typeof ResponseSchema>;
```

### 1-2. 共有型は `types/` に集約する

```
src/
  types/
    api.ts        # APIリクエスト/レスポンス型
    domain.ts     # ドメインモデル型
    ui.ts         # UIコンポーネントProps型
```

```typescript
// types/domain.ts
export interface User {
  id: string;
  email: string;
  role: 'admin' | 'member' | 'viewer';
  createdAt: Date;
}

// 型の再エクスポートで一元管理
export type { User };
```

### 1-3. 関数の戻り値型を明示する

```typescript
// ❌ Bad — 戻り値型が推論に依存
async function fetchUser(id: string) {
  return await db.user.findUnique({ where: { id } });
}

// ✅ Good — 明示的な戻り値型
async function fetchUser(id: string): Promise<User | null> {
  return await db.user.findUnique({ where: { id } });
}
```

---

## 2. コンポーネント設計パターン

### 2-1. Server Component / Client Component の分離

```
// ✅ データ取得はServer Componentで行い、
//    インタラクティブな部分のみClient Componentに委譲する

// app/users/page.tsx (Server Component)
import { UserList } from '@/components/UserList';
import { fetchUsers } from '@/lib/api/users';

export default async function UsersPage() {
  const users = await fetchUsers();
  return <UserList initialUsers={users} />;
}

// components/UserList.tsx (Client Component)
'use client';
export function UserList({ initialUsers }: { initialUsers: User[] }) {
  const [users, setUsers] = useState(initialUsers);
  // インタラクション処理...
}
```

### 2-2. ローディング・エラー・空状態を必ず実装する

```typescript
// components/DataView.tsx
interface DataViewProps<T> {
  data: T[] | undefined;
  isLoading: boolean;
  error: Error | null;
  renderItem: (item: T) => React.ReactNode;
  emptyMessage?: string;
}

export function DataView<T>({
  data,
  isLoading,
  error,
  renderItem,
  emptyMessage = 'データがありません',
}: DataViewProps<T>) {
  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage message={error.message} />;
  if (!data?.length) return <EmptyState message={emptyMessage} />;

  return <ul>{data.map(renderItem)}</ul>;
}
```

### 2-3. カスタムフックでロジックを分離する

```typescript
// hooks/useAsync.ts
export function useAsync<T>(
  asyncFn: () => Promise<T>,
  deps: React.DependencyList = []
) {
  const [state, setState] = useState<{
    data: T | null;
    isLoading: boolean;
    error: Error | null;
  }>({ data: null, isLoading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    setState(prev => ({ ...prev, isLoading: true, error: null }));

    asyncFn()
      .then(data => {
        if (!cancelled) setState({ data, isLoading: false, error: null });
      })
      .catch(error => {
        if (!cancelled) setState({ data: null, isLoading: false, error });
      });

    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
```

---

## 3. 状態管理パターン

### 3-1. 状態の置き場所の選択基準

```
UIローカル状態 (useState)
  ↓ 複数コンポーネントで共有
Context + useReducer
  ↓ サーバー状態（fetch/cache）
TanStack Query / SWR
  ↓ グローバルクライアント状態
Zustand / Jotai
```

### 3-2. URLを状態として扱う（検索・フィルタ）

```typescript
// hooks/useSearchParams.ts
'use client';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';

export function useUrlState<T extends Record<string, string>>(defaults: T) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const state = Object.fromEntries(
    Object.entries(defaults).map(([key, defaultVal]) => [
      key,
      searchParams.get(key) ?? defaultVal,
    ])
  ) as T;

  const setState = (updates: Partial<T>) => {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(updates).forEach(([key, value]) => {
      if (value === defaults[key]) {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    });
    router.replace(`${pathname}?${params.toString()}`);
  };

  return [state, setState] as const;
}
```

### 3-3. 動的依存値を持つキャッシュに注意する

```typescript
// ❌ Bad — accountId が変わっても再フェッチされない
const { data } = useCachedFetch(`/api/data`); // 固定キー

// ✅ Good — 依存値をキーに含め、変化を検知する
const { data } = useQuery({
  queryKey: ['data', accountId, filter],  // 動的キー
  queryFn: () => fetchData(accountId, filter),
  enabled: !!accountId,
});

// ✅ Good — useEffect で明示的に依存を管理する場合
const [data, setData] = useState(null);
useEffect(() => {
  if (!accountId) return;
  fetchData(accountId
