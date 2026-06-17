# add-api-route

Next.js API Route Handler を追加する。

## 使い方
`/add-api-route <route-path> [GET|POST|PUT|DELETE|WEBHOOK]`

例:
- `/add-api-route items GET`
- `/add-api-route export/csv GET`
- `/add-api-route stripe/webhook WEBHOOK`

## 手順

1. `$ARGUMENTS` を解析してルートとメソッドを取得
2. `src/app/api/<route>/route.ts` を作成

### 通常の API Route テンプレート

```typescript
import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase/server";

export async function GET(req: NextRequest) {
  try {
    const supabase = await createServerClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // TODO: ロジック実装

    return NextResponse.json({ data: null });
  } catch (e) {
    console.error(e);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
```

### WEBHOOK テンプレート（署名検証付き）

```typescript
import { NextRequest, NextResponse } from "next/server";
import { createHmac } from "crypto";

// POST /api/<route>
export async function POST(req: NextRequest) {
  // 署名検証（HMAC-SHA256 の例）
  const rawBody = await req.text();
  const signature = req.headers.get("x-signature") ?? "";
  const secret = process.env.WEBHOOK_SECRET ?? "";

  const hmac = createHmac("sha256", secret);
  hmac.update(rawBody);
  const expected = `sha256=${hmac.digest("hex")}`;

  if (signature !== expected) {
    return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
  }

  let body: unknown;
  try {
    body = JSON.parse(rawBody);
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  // TODO: イベント処理
  console.log("Webhook received:", body);

  return NextResponse.json({ status: "ok" });
}
```

3. Webhook の場合:
   - `src/middleware.ts` の `PUBLIC_PATHS`（または matcher）に追加
   - 署名検証は必須
   - `.env.example` に `WEBHOOK_SECRET` を追記

4. 作成後、`.env.example` に必要な環境変数を追記
