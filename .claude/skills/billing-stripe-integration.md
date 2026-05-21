---
name: billing-stripe-integration
description: >-
  Stripe課金連携の設計・実装・設定・トラブルシュートの包括的ガイド。Checkout Session / Customer Portal /
  Webhook処理のパターンと、Next.js/TypeScriptでの実装例を提供する。あらゆるSaaSプロジェクトで再利用できる汎用テンプレート。
category: billing
sourceSkillIds:
  - b6b9d18f
generatedAt: '2026-05-11'
---

# Stripe課金連携 — 包括的実装ガイド

## 概要・適用範囲

このSkillはStripe + Next.js + TypeScriptで課金機能を実装するすべてのプロジェクトに適用する。
SaaS月額課金・従量課金・ワンタイム決済のいずれにも対応し、Checkout Session / Customer Portal / Webhookの3本柱を軸に設計する。

---

## 1. アーキテクチャ全体像

```
┌─────────────────────────────────────────────────────┐
│  Next.js App                                        │
│  ┌──────────────┐   ┌──────────────────────────┐   │
│  │  Client      │   │  API Routes / Route Handler│  │
│  │  Components  │──▶│  /api/billing/checkout    │   │
│  │              │   │  /api/billing/portal      │   │
│  │              │   │  /api/billing/webhook     │   │
│  └──────────────┘   └────────────┬─────────────┘   │
└───────────────────────────────── │ ────────────────┘
                                   │ Stripe SDK
                          ┌────────▼────────┐
                          │   Stripe API    │
                          │  ・Customers    │
                          │  ・Subscriptions│
                          │  ・Prices       │
                          │  ・Webhooks     │
                          └─────────────────┘
                                   │ Events
                          ┌────────▼────────┐
                          │   Database      │
                          │  (Supabase/     │
                          │   Prisma/etc.)  │
                          └─────────────────┘
```

### 状態遷移

```
未課金 ──[Checkout Session]──▶ active
active ──[Customer Portal]──▶ canceled / past_due
past_due ──[支払い成功]──▶ active
canceled ──[再購読]──▶ active (新セッション)
```

---

## 2. 環境設定

### 2-1. 必要パッケージ

```bash
npm install stripe @stripe/stripe-js
```

### 2-2. 環境変数

```env
# .env.local
STRIPE_SECRET_KEY=sk_live_...          # または sk_test_...
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
NEXT_PUBLIC_APP_URL=https://yourapp.com

# オプション: Price ID を環境変数で管理
STRIPE_PRICE_ID_BASIC=price_xxx
STRIPE_PRICE_ID_PRO=price_yyy
```

### 2-3. Stripe クライアント初期化

```typescript
// lib/stripe.ts
import Stripe from 'stripe';

if (!process.env.STRIPE_SECRET_KEY) {
  throw new Error('STRIPE_SECRET_KEY is not set');
}

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY, {
  apiVersion: '2024-06-20', // 常に明示的に固定
  typescript: true,
});
```

---

## 3. Checkout Session の実装

### 3-1. API Route（App Router）

```typescript
// app/api/billing/checkout/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { stripe } from '@/lib/stripe';
import { getServerSession } from 'next-auth'; // または任意の認証ライブラリ
import { authOptions } from '@/lib/auth';

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { priceId, planName } = await req.json();

  if (!priceId) {
    return NextResponse.json({ error: 'priceId is required' }, { status: 400 });
  }

  try {
    // 既存 Customer を再利用 or 新規作成
    const customerId = await getOrCreateStripeCustomer(
      session.user.email,
      session.user.id
    );

    const checkoutSession = await stripe.checkout.sessions.create({
      customer: customerId,
      mode: 'subscription',           // 'payment' for one-time
      payment_method_types: ['card'],
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: `${process.env.NEXT_PUBLIC_APP_URL}/billing/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${process.env.NEXT_PUBLIC_APP_URL}/billing/cancel`,
      metadata: {
        userId: session.user.id,
        planName: planName ?? '',
      },
      subscription_data: {
        metadata: { userId: session.user.id },
      },
      // 日本向け設定
      locale: 'ja',
      // 税率を自動計算する場合
      // automatic_tax: { enabled: true },
    });

    return NextResponse.json({ url: checkoutSession.url });
  } catch (err) {
    console.error('[checkout] Stripe error:', err);
    return NextResponse.json(
      { error: 'Failed to create checkout session' },
      { status: 500 }
    );
  }
}

/** DB から stripeCustomerId を取得し、なければ Stripe に作成して保存 */
async function getOrCreateStripeCustomer(
  email: string,
  userId: string
): Promise<string> {
  // ── プロジェクトの DB クライアントに合わせて実装 ──
  // 例: Prisma
  // const user = await prisma.user.findUnique({ where: { id: userId } });
  // if (user?.stripeCustomerId) return user.stripeCustomerId;

  const customer = await stripe.customers.create({
    email,
    metadata: { userId },
  });

  // await prisma.user.update({
  //   where: { id: userId },
  //   data: { stripeCustomerId: customer.id },
  // });

  return customer.id;
}
```

### 3-2. クライアント側

```typescript
// components/UpgradeButton.tsx
'use client';

import { useState } from 'react';

interface Props {
  priceId: string;
  planName: string;
  label?: string;
}

export function UpgradeButton({ priceId, planName, label = 'アップグレード' }: Props) {
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/billing/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priceId, planName }),
      });
      const data = await res
