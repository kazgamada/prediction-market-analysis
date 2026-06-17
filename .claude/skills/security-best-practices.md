---
name: security-best-practices
description: >-
  Next.js/Supabase/TypeScriptプロジェクトにおけるセキュリティのベストプラクティス。
  認証・認可、レート制限、PII暗号化、監査ログ、インシデント対応、シークレット管理を網羅した包括的なセキュリティガイド。
category: security
sourceSkillIds:
  - d1d927c6
  - b5f82bc0
  - 550a948c
  - 75f78551
  - 2e1f3893
  - df5813f3
  - 0f81e61b
  - dba5acfd
generatedAt: '2026-06-17'
integrationStrategy: latest-first
adoptedFromArchive:
  - archive/skills/add-audit-log.md
  - archive/skills/add-encrypted-field.md
  - archive/skills/add-rate-limit.md
  - archive/skills/incident-response.md
  - archive/skills/rotate-secret.md
  - archive/skills/security-best-practices.md
  - archive/skills/security-rate-limit.md
  - archive/skills/security-review.md
---

# セキュリティ ベストプラクティス

Next.js / Supabase / TypeScript プロジェクト全体に適用する、多層防御のセキュリティガイド。
**このドキュメントは「何かやろうとしたときに開く」ではなく、「実装前に確認する」ために存在する。**

---

## 0. 全体マップ（どこに何があるか）

```
セキュリティの柱
├── 1. 認証・認可      → Supabase RLS + tRPC procedure 区分
├── 2. ミドルウェア    → helmet / CORS / trust proxy
├── 3. レート制限      → lib/rate-limit.ts の rateLimit()
├── 4. PII 暗号化      → server/services/crypto.ts の encrypt()/decrypt()
├── 5. 監査ログ        → recordAudit() — 変更系操作に必須
├── 6. シークレット管理 → .env の鍵分類と禁止事項
└── 7. インシデント対応 → Sev 判定 → 封じ込め → 通知 → ポストモーテム
```

---

## 1. 認証・認可

### 1-1. tRPC Procedure の使い分け

| Procedure | 用途 | 注意 |
|-----------|------|------|
| `publicProcedure` | ログイン不要な読み取り | 不要なデータを公開しない |
| `protectedProcedure` | 認証済みユーザー操作 | **必ず `ctx.user.id` でフィルタ** |
| `adminProcedure` | 管理者専用 | 用途を最小化する |

```typescript
// ✅ 正しい — 自分のデータだけ取得
export const getMyItems = protectedProcedure.query(async ({ ctx }) => {
  return db.items.findMany({ where: { userId: ctx.user.id } });
});

// ❌ 誤り — userId を検証せず全件返す
export const getItems = protectedProcedure.query(async ({ ctx }) => {
  return db.items.findMany(); // IDOR脆弱性
});
```

### 1-2. セッション・Cookie 設定

```typescript
// 推奨設定（変更時はセキュリティレビュー必須）
{
  httpOnly: true,
  sameSite: "lax",
  secure: process.env.NODE_ENV === "production",
  maxAge: 60 * 60 * 24 * 30, // 30日（用途に応じて調整）
}
```

### 1-3. Supabase RLS チェックリスト

- [ ] 全テーブルに RLS を有効化（`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`）
- [ ] `SELECT` / `INSERT` / `UPDATE` / `DELETE` それぞれにポリシーを定義
- [ ] `auth.uid()` を使って行単位でアクセス制限
- [ ] サービスロールキーはサーバーサイドのみで使用（クライアントに漏洩禁止）

```sql
-- 例: users テーブルの SELECT ポリシー
CREATE POLICY "Users can view own data"
  ON users FOR SELECT
  USING (auth.uid() = id);
```

---

## 2. ミドルウェア標準構成

`server/_core/security.ts` の `applySecurityMiddleware(app)` で一括適用:

```typescript
import helmet from "helmet";
import cors from "cors";

export function applySecurityMiddleware(app: Express) {
  // 1. Helmet — CSP / HSTS / X-Frame-Options
  app.use(helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        scriptSrc: ["'self'"],
        // 外部CDNを使う場合はここに追加（都度レビュー）
      },
    },
  }));

  // 2. CORS — 本番は許可オリジンを明示的に絞る
  app.use(cors({
    origin: process.env.NODE_ENV === "production"
      ? [process.env.ALLOWED_ORIGIN!] // ✅ 明示的に指定
      : true,                          // 開発のみワイルドカード許可
    credentials: true,
  }));

  // 3. Vercel / Railway の X-Forwarded-For を有効化
  app.set("trust proxy", 1);
}
```

---

## 3. レート制限

### 3-1. limiter の種類と用途

| limiter 名 | 対象パス | 推奨制限 | 理由 |
|------------|---------|---------|------|
| `apiLimiter` | `/api/trpc` `/api/ai` `/api/market-data` | 60 req/min/IP | 通常 API |
| `authLimiter` | `/api/oauth` `/api/auth` | 10 req/min/IP | 認証攻撃防止 |
| `emailLimiter` | メール送信トリガー | 3 req/min/IP | 通知爆撃・課金攻撃防止 |
| `searchLimiter` | 重い検索 API | 20 req/min/user | DB 負荷軽減 |
| `formLimiter` | 公開 POST フォーム | 10 req/min/IP | スパム・DoS 防止 |

### 3-2. 実装パターン

```typescript
// lib/rate-limit.ts
import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";

const redis = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL!,
  token: process.env.UPSTASH_REDIS_REST_TOKEN!,
});

export function rateLimit(requests: number, window: string) {
  return new Ratelimit({
    redis,
    limiter: Ratelimit.slidingWindow(requests, window),
  });
}

// --- API Route での使い方 ---
// app/api/contact/route.ts
import { rateLimit } from "@/lib/rate-limit";

const limiter = rateLimit(10, "1 m");

export async function POST(req: Request) {
  const ip = req.headers.get("x-forwarded-for") ?? "anonymous";
  const { success } = await limiter.limit(ip);

  if (!success) {
    return Response.json(
      { error: "Too many requests" },
      { status: 429, headers: { "Retry-After": "60" } }
    );
  }
  // ... 処理続行
}
```

> **新規エンドポイント追加時のルール**: 認証不要な POST / メール送信
