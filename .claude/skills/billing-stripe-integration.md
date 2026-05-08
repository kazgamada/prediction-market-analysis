---
name: billing-stripe-integration
description: >-
  Stripe課金連携の設計・実装・設定・トラブルシュートの包括的ガイド。Checkout Session / Customer Portal /
  Webhook処理のパターンと、Next.js/TypeScriptでの実装例を提供する。あらゆるSaaSプロジェクトで再利用できる汎用テンプレート。
category: billing
sourceSkillIds:
  - 8477c186
  - 27e443d2
  - c55f089d
  - 90e620fe
  - 42ce90c3
  - 4bd073c9
  - fd4edcf8
  - 8851fb4d
  - '68721077'
  - b4634f63
  - f5fe3032
  - a89cf4ff
  - 0cc54563
  - e2e85984
  - 3b693edc
  - f1f041a2
  - 9ab08e4b
generatedAt: '2026-05-08'
---

# Stripe課金連携 — 設計・実装・運用ガイド

## 概要

Stripe連携は以下の **5層構造** で構成される。問題が発生した場合、必ずこの層のどこかに起因する。

| 層 | 担当範囲 |
|---|---|
| **Layer 1** | Stripe Dashboard 設定 |
| **Layer 2** | サーバーサイド実装（API Routes / Server Actions） |
| **Layer 3** | クライアントサイド実装 |
| **Layer 4** | Webhook 処理 |
| **Layer 5** | 環境変数管理 |

---

## ステップ0: 現状確認チェックリスト

新規実装・トラブルシュート前に必ず確認する。

```bash
# 環境変数の存在確認
echo $STRIPE_SECRET_KEY        # sk_test_... or sk_live_...
echo $STRIPE_WEBHOOK_SECRET    # whsec_...
echo $NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY  # pk_test_... or pk_live_...

# Stripe CLIバージョン確認
stripe --version

# ローカルWebhookリスナー起動確認
stripe listen --forward-to localhost:3000/api/webhooks/stripe
```

**確認項目:**

- [ ] Stripe Dashboard でプロダクト・価格 (Price) が作成済み
- [ ] Webhook エンドポイントが登録されている（本番・テスト両環境）
- [ ] 必要なイベントが Webhook に設定されている
- [ ] `customer.email` がアプリのユーザーと紐付いている

---

## Layer 1: Stripe Dashboard 設定

### 必須設定項目

```
Products & Prices
├── Product（例: "Pro Plan"）
│   ├── Price ID: price_xxx（月額）
│   └── Price ID: price_yyy（年額）
Customer Portal
├── 有効化: ON
├── キャンセル: 許可/不許可
└── プラン変更: 許可するプラン一覧
Webhooks
├── エンドポイント URL: https://yourdomain.com/api/webhooks/stripe
└── 購読イベント（後述）
```

### 購読すべき Webhook イベント

```
checkout.session.completed       # 購入完了 → サブスクリプション有効化
customer.subscription.updated    # プラン変更・更新
customer.subscription.deleted    # サブスクリプション終了
invoice.payment_succeeded        # 請求成功
invoice.payment_failed           # 請求失敗 → ユーザー通知
customer.updated                 # 顧客情報更新
```

---

## Layer 2: サーバーサイド実装

### Stripe クライアントの初期化

```typescript
// lib/stripe.ts
import Stripe from 'stripe';

if (!process.env.STRIPE_SECRET_KEY) {
  throw new Error('STRIPE_SECRET_KEY is not set');
}

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY, {
  apiVersion: '2024-06-20', // 常に最新の安定版を指定
  typescript: true,
});
```

### Checkout Session の作成

```typescript
// app/api/billing/checkout/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { stripe } from '@/lib/stripe';
import { getServerSession } from 'next-auth'; // or your auth solution
import { authOptions } from '@/lib/auth';

export async function POST(req: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user?.email) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { priceId, mode = 'subscription' } = await req.json();

    // 既存 Customer の取得 or 新規作成
    let customerId: string | undefined;
    const existingCustomers = await stripe.customers.list({
      email: session.user.email,
      limit: 1,
    });
    if (existingCustomers.data.length > 0) {
      customerId = existingCustomers.data[0].id;
    }

    const checkoutSession = await stripe.checkout.sessions.create({
      mode,                          // 'subscription' | 'payment' | 'setup'
      customer: customerId,
      customer_email: customerId ? undefined : session.user.email,
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: `${process.env.NEXT_PUBLIC_APP_URL}/billing/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${process.env.NEXT_PUBLIC_APP_URL}/billing/cancel`,
      metadata: {
        userId: session.user.id, // DBと紐付けるためのキー
      },
      // サブスクリプション向け追加設定
      subscription_data: mode === 'subscription' ? {
        metadata: { userId: session.user.id },
        trial_period_days: 14, // 必要な場合のみ
      } : undefined,
    });

    return NextResponse.json({ url: checkoutSession.url });
  } catch (error) {
    console.error('[Checkout] Error:', error);
    return NextResponse.json(
      { error: 'Failed to create checkout session' },
      { status: 500 }
    );
  }
}
```

### Customer Portal セッションの作成

```typescript
// app/api/billing/portal/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { stripe } from '@/lib/stripe';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { db } from '@/lib/db'; // your DB client

export async function POST(req: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // DB から stripeCustomerId を取得
    const user = await db.user.findUnique({
      where: { id: session.user.id },
      select: { stripeCustomerId: true },
    });

    if (!user?.stripeCustomerId) {
      return NextResponse.json(
        { error: 'No billing account found' },
        { status: 404 }
      );
    }

    const portalSession = await stripe.billingPortal.sessions.create({
      customer: user.stripeCustomerId,
      return_url: `${process.env.NEXT_PUBLIC_APP_URL}/billing`,
    });

    return NextResponse.json({ url: portalSession.url });
  } catch (error) {
    console.error('[Portal] Error:', error);
    return NextResponse.json(
      { error: 'Failed to create portal session' },
      { status: 500 }
    );
  
