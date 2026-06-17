# new-page

新しいダッシュボードページ（Server Component）を作成する。

## 使い方
`/new-page <route-path> [<title>]`

例:
- `/new-page items` → `src/app/(dashboard)/items/page.tsx`
- `/new-page items/[id] アイテム詳細`

## 手順

1. `$ARGUMENTS` を解析してルートパスとタイトルを取得
2. `src/app/(dashboard)/<route>/` ディレクトリを作成
3. Server Component としてページを作成:

```tsx
import { createServerClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

export default async function <Name>Page() {
  const supabase = await createServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // データフェッチ
  const { data: items } = await supabase
    .from("<table>")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false });

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold"><Title></h1>
          <p className="text-sm text-zinc-500 mt-1">
            {items?.length ?? 0} 件
          </p>
        </div>
        {/* TODO: 追加ボタン */}
      </div>

      {items?.length === 0 ? (
        <div className="text-center py-16 text-zinc-500">
          <p className="text-lg font-medium">まだデータがありません</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {items?.map((item) => (
            <div
              key={item.id}
              className="bg-zinc-900 rounded-xl border border-zinc-800 p-4"
            >
              <p className="font-medium">{item.name}</p>
              <p className="text-sm text-zinc-500 mt-1">{item.created_at}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

4. ルートが `[id]` を含む場合は動的セグメントとして:
   ```tsx
   export default async function Page({ params }: { params: Promise<{ id: string }> }) {
     const { id } = await params;
     // ...
   }
   ```
5. Client Component が必要な場合（フォーム・モーダル等）は別ファイルに分割
