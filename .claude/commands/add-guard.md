# add-guard

Server Action またはページにロールベースの認証ガードを追加する。

## 使い方
`/add-guard <file-path> <guard-level>`

例:
- `/add-guard src/lib/actions/billing.ts admin`
- `/add-guard src/app/(dashboard)/admin/page.tsx admin`
- `/add-guard src/app/api/admin/route.ts admin`

## ガードレベル

| レベル    | 許可              | 用途             |
|----------|-------------------|-----------------|
| `auth`   | ログイン済み全員   | 通常の読み書き   |
| `admin`  | 管理者ロール以上   | 設定・管理操作   |

> **プロジェクト固有のロール定義**はプロジェクトの `CLAUDE.md` またはコードベースを参照してください。

## 手順

1. 対象ファイルを読み込んで現在の認証状態を確認

2. **Server Action の場合**:
   ```typescript
   "use server";
   import { createServerClient } from "@/lib/supabase/server";
   import { redirect } from "next/navigation";

   export async function someAction() {
     const supabase = await createServerClient();
     const { data: { user } } = await supabase.auth.getUser();
     if (!user) redirect("/login");

     // admin ガードの場合: ロールチェックを追加
     // const { data: profile } = await supabase.from("profiles").select("role").eq("id", user.id).single();
     // if (profile?.role !== "admin") return { error: "権限がありません" };
   }
   ```

3. **Server Component（ページ）の場合**:
   ```typescript
   import { createServerClient } from "@/lib/supabase/server";
   import { redirect } from "next/navigation";

   export default async function Page() {
     const supabase = await createServerClient();
     const { data: { user } } = await supabase.auth.getUser();
     if (!user) redirect("/login");

     // admin チェック例
     // const { data: profile } = await supabase.from("profiles").select("role").eq("id", user.id).single();
     // if (profile?.role !== "admin") redirect("/app");
   }
   ```

4. **API Route の場合**:
   ```typescript
   const { data: { user } } = await supabase.auth.getUser();
   if (!user) {
     return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
   }
   // admin チェック例
   // if (profile?.role !== "admin") {
   //   return NextResponse.json({ error: "Forbidden" }, { status: 403 });
   // }
   ```

5. 変更後、ガードが正しく動作するか確認:
   - 未認証でアクセスしたときに `/login` へリダイレクトされるか
   - 権限不足のロールで適切にブロックされるか
