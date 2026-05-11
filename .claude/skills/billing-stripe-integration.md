---
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
  - a7793ed5
  - a89cf4ff
  - 0cc54563
  - e2e85984
  - 3b693edc
  - f1f041a2
  - 9ab08e4b
generatedAt: '2026-05-11'
---
```markdown
---
name: billing-stripe-integration
description: >-
  Stripe課金連携の設計・実装・設定・トラブルシュートの包括的ガイド。Checkout Session / Customer Portal /
  Webhook処理のパターンと、Next.js App Router + TypeScriptでの実装例を提供する。
category: billing
---

# Stripe課金連携 — 設計・実装・運用ガイド

## 概要

Stripe連携は以下の **5層** で構成される。問題発生時は必ずどの層に起因するかを特定する。

| 層 | 責務 |
|---|---|
| **Dashboard設定** | Product/Price/Webhook Endpoint の登録 |
| **環境変数管理** | APIキー・Webhook Secretの安全な管理 |
| **サーバーサイド** | Checkout Session / Customer Portal / Webhook検証 |
| **クライアントサイド** | 購入ボタン・リダイレクト・状態表示 |
| **DB同期** | Webhook経由でサブスクリプション状態をDBへ反映 |

---

## ステップ0: 現状確認チェックリスト

作業を始める前に以下を確認する。

```bash
# 1. 必要な環境変数が揃っているか
grep -E "STRIPE|NEXT_PUBLIC" .env.local

# 2. Stripe SDKがインストールされているか
cat package.json | grep stripe

# 3. Webhook Endpointが登録されているか（Stripe Dashboard で確認）
# Dashboard > Developers > Webhooks
```

**最低限必要な環境変数:**

```bash
# .env.local
STRIPE_SECRET_KEY=sk_test_xxxx          # サーバーサイド専用
STRIPE_WEBHOOK_SECRET=whsec_xxxx        # Webhook検証用
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_xxxx  # クライアントサイド用
```

---

## ステップ1: Stripe Dashboard設定

### 1-1. Product と Price の作成

```
Dashboard > Products > Add product
  - Name: プラン名（例: Pro Plan）
  - Pricing model: Recurring
  - Price: 金額・通貨・請求サイクル（monthly/yearly）
  → Price ID をコピー: price_xxxxxxxx
```

### 1-2. Webhook Endpoint の登録

```
Dashboard > Developers > Webhooks > Add endpoint
  - URL: https://yourdomain.com/api/stripe/webhook
  - Events: 以下を選択
    ✓ checkout.session.completed
    ✓ customer.subscription.created
    ✓ customer.subscription.updated
    ✓ customer.subscription.deleted
    ✓ invoice.payment_succeeded
    ✓ invoice.payment_failed
  → Signing secret をコピー: whsec_xxxxxxxx
```

---

## ステップ2: Stripe クライアントの初期化

```typescript
// lib/stripe.ts
import Stripe from 'stripe';

if (!process.env.STRIPE_SECRET_KEY) {
  throw new Error('STRIPE_SECRET_KEY is not set');
}

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY, {
  apiVersion: '2024-06-20', // 最新の安定版を指定
  typescript: true,
});
```

---

## ステップ3: Checkout Session の実装

### サーバーサイド（Route Handler）

```typescript
// app/api/stripe/checkout/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { stripe } from '@/lib/stripe';
import { auth } from '@/lib/auth'; // 認証ライブラリに合わせて変更

export async function POST(req: NextRequest) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { priceId } = await req.json();

    // 既存のStripe顧客IDをDBから取得（初回はnull）
    const existingCustomerId = await getStripeCustomerId(session.user.id);

    const checkoutSession = await stripe.checkout.sessions.create({
      mode: 'subscription',
      payment_method_types: ['card'],
      line_items: [{ price: priceId, quantity: 1 }],
      // 既存顧客に紐付けるか、新規顧客として作成
      ...(existingCustomerId
        ? { customer: existingCustomerId }
        : { customer_email: session.user.email ?? undefined }),
      // Webhook で user を特定するためのメタデータ
      metadata: { userId: session.user.id },
      subscription_data: {
        metadata: { userId: session.user.id },
      },
      success_url: `${process.env.NEXT_PUBLIC_APP_URL}/dashboard?success=true`,
      cancel_url: `${process.env.NEXT_PUBLIC_APP_URL}/pricing?canceled=true`,
    });

    return NextResponse.json({ url: checkoutSession.url });
  } catch (error) {
    console.error('Checkout session creation failed:', error);
    return NextResponse.json(
      { error: 'Failed to create checkout session' },
      { status: 500 }
    );
  }
}
```

### クライアントサイド（購入ボタン）

```typescript
// components/CheckoutButton.tsx
'use client';

import { useState } from 'react';

interface CheckoutButtonProps {
  priceId: string;
  label?: string;
}

export function CheckoutButton({ priceId, label = '購入する' }: CheckoutButtonProps) {
  const [isLoading, setIsLoading] = useState(false);

  const handleCheckout = async () => {
    setIsLoading(true);
    try {
      const res = await fetch('/api/stripe/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priceId }),
      });

      if (!res.ok) throw new Error('Checkout failed');

      const { url } = await res.json();
      if (url) window.location.href = url;
    } catch (error) {
      console.error('Checkout error:', error);
      alert('エラーが発生しました。もう一度お試しください。');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <button onClick={handleCheckout} disabled={isLoading}>
      {isLoading ? '処理中...' : label}
    </button>
  );
}
```

---

## ステップ4: Customer Portal の実装

```typescript
// app/api/stripe/portal/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { stripe } from '@/lib/stripe';
import { auth } from '@/lib/auth';

export async function POST(req: NextRequest) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const customerId = await getStripeCustomerId(session.user.id);
    if (!customerId) {
      return NextResponse.json(
        { error: 'No active subscription found' },
        { status: 400 }
      );
    }

    const portalSession = await stripe
