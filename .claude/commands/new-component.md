# new-component

再利用可能な UI コンポーネントを作成する。

## 使い方
`/new-component <ComponentName> [ui|lp|dashboard]`

例:
- `/new-component StatusBadge ui` → `src/components/ui/StatusBadge.tsx`
- `/new-component ItemCard dashboard` → `src/components/dashboard/ItemCard.tsx`
- `/new-component PricingCard lp` → `src/components/lp/PricingCard.tsx`

## 手順

1. `$ARGUMENTS` を解析してコンポーネント名とカテゴリを取得
2. カテゴリに対応するディレクトリに作成:
   - `ui` → `src/components/ui/`
   - `lp` → `src/components/lp/`
   - `dashboard` → `src/components/dashboard/`（なければ作成）

3. **Server Component**（デフォルト）のテンプレート:

```tsx
import { cn } from "@/lib/utils";

interface <Name>Props {
  // TODO: props を定義
  className?: string;
}

export function <Name>({ className }: <Name>Props) {
  return (
    <div className={cn("", className)}>
      {/* TODO */}
    </div>
  );
}
```

4. **Client Component** が必要な場合（インタラクション・状態管理）:
   - ファイル先頭に `"use client";` を追加
   - useState/useEffect 等は Client Component のみ

5. **UI コンポーネント**（`ui/` カテゴリ）のルール:
   - `cva` で variant を定義
   - `cn()` で className をマージ
   - Radix UI プリミティブを活用

   ```tsx
   import { cva, type VariantProps } from "class-variance-authority";
   import { cn } from "@/lib/utils";

   const <name>Variants = cva("base-classes", {
     variants: {
       variant: {
         default: "...",
         success: "...",
         warning: "...",
         destructive: "...",
       },
       size: {
         sm: "text-xs px-2 py-0.5",
         md: "text-sm px-3 py-1",
       },
     },
     defaultVariants: { variant: "default", size: "md" },
   });

   export interface <Name>Props
     extends React.HTMLAttributes<HTMLSpanElement>,
       VariantProps<typeof <name>Variants> {}

   export function <Name>({ className, variant, size, ...props }: <Name>Props) {
     return <span className={cn(<name>Variants({ variant, size }), className)} {...props} />;
   }
   ```

6. 作成後、必要に応じてバレルエクスポート（`index.ts`）への追記を提案
