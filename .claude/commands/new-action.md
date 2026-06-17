# new-action

新しい Server Action を作成する。

## 使い方
`/new-action <feature-name>`

例:
- `/new-action item` → `src/lib/actions/item.ts` を作成

## 手順

1. `$ARGUMENTS` を解析して feature 名を取得
2. `src/lib/actions/<feature>.ts` が既存かチェック（存在する場合は追記を提案）
3. 以下のテンプレートで新規ファイルを作成:

```typescript
"use server";

import { z } from "zod";
import { createServerClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

const create<Feature>Schema = z.object({
  // TODO: フィールドを定義
  name: z.string().min(1, "名前を入力してください"),
});

type ActionResult = { error: string } | { data: unknown };

export async function create<Feature>Action(
  _prev: unknown,
  formData: FormData
): Promise<ActionResult> {
  try {
    const supabase = await createServerClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) redirect("/login");

    const parsed = create<Feature>Schema.safeParse({
      name: formData.get("name"),
    });

    if (!parsed.success) {
      return { error: parsed.error.errors[0].message };
    }

    const { error } = await supabase
      .from("<table>")
      .insert({
        ...parsed.data,
        user_id: user.id,
      });

    if (error) return { error: error.message };
    return { data: null };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "エラーが発生しました" };
  }
}

export async function update<Feature>Action(
  id: string,
  _prev: unknown,
  formData: FormData
): Promise<ActionResult> {
  try {
    const supabase = await createServerClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) redirect("/login");

    const parsed = create<Feature>Schema.partial().safeParse({
      name: formData.get("name"),
    });

    if (!parsed.success) {
      return { error: parsed.error.errors[0].message };
    }

    const { error } = await supabase
      .from("<table>")
      .update(parsed.data)
      .eq("id", id)
      .eq("user_id", user.id); // RLS に加えて行レベルで確認

    if (error) return { error: error.message };
    return { data: null };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "エラーが発生しました" };
  }
}

export async function delete<Feature>Action(id: string): Promise<ActionResult> {
  try {
    const supabase = await createServerClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) redirect("/login");

    const { error } = await supabase
      .from("<table>")
      .delete()
      .eq("id", id)
      .eq("user_id", user.id);

    if (error) return { error: error.message };
    return { data: null };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "エラーが発生しました" };
  }
}
```

4. `<Feature>` と `<table>` プレースホルダーを実際の値に置換
5. 作成後、型チェック: `npx next lint src/lib/actions/<feature>.ts`
