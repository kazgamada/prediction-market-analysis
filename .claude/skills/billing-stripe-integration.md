---
name: billing-stripe-integration
description: >-
  Stripe課金連携の設計・実装・設定・トラブルシュートの包括的ガイド。Checkout Session / Customer Portal /
  Webhook処理 / 料金プラン管理のパターンと、Next.js/TypeScriptでの実装例を提供する。
  あらゆるSaaSプロジェクトで再利用できる汎用テンプレート。プラン追加・編集・削除・トライアル設定・Stripe連携・フロントエンド反映の一連の作業も包含する。
category: billing
sourceSkillIds:
  - b6b9d18f
  - '33202335'
generatedAt: '2026-06-17'
integrationStrategy: latest-first
adoptedFromArchive:
  - archive/skills/billing-stripe-integration.md
  - archive/skills/plan-config.md
---

# Stripe課金連携 — 包括的実装ガイド

## 概要・適用範囲

このSkillはStripe + Next.js + TypeScriptで課金機能を実装するすべてのプロジェクトに適用する。
SaaS月額課金・従量課金・ワンタイム決済・料金プラン管理まで、設計から運用までを網羅する。

**統合元Skill:**
- `billing-stripe-integration`（aegis-market-os）⭐ 代表進化版 — Checkout/Portal/Webhook の包括実装
- `plan-config`（BlackZero）⭐ 代表進化版 — 料金プラン設定変更プロセス

---

## 1. アーキテクチャ全体像

```
┌─────────────────────────────────────────────────────────────┐
│                          Frontend                           │
│  PricingPage → CheckoutButton → SuccessPage / CancelPage   │
│  AccountPage → CustomerPortalButton                         │
└────────────────────┬───────────────────────────────────────┘
                     │ API Routes (Next.js App Router)
┌────────────────────▼───────────────────────────────────────┐
│  /api/stripe/checkout-session   POST                        │
│  /api/stripe/customer-portal    POST                        │
│  /api/stripe/webhook            POST  (Stripe → Server)     │
│  /api/plans                     GET/POST/PUT/DELETE         │
└────────────────────┬───────────────────────────────────────┘
                     │
┌────────────────────▼───────────────────────────────────────┐
│              Stripe Dashboard / Stripe SDK                  │
│  Products / Prices / Customers / Subscriptions              │
└────────────────────┬───────────────────────────────────────┘
                     │ Webhook Events
┌────────────────────▼───────────────────────────────────────┐
│              Database (Supabase / Prisma / any)             │
│  users / subscriptions / plans / invoices                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 環境変数・初期設定

### 必須環境変数

```env
# .env.local
STRIPE_SECRET_KEY=sk_test_...          # Stripe シークレットキー
STRIPE_PUBLISHABLE_KEY=pk_test_...     # Stripe 公開キー
STRIPE_WEBHOOK_SECRET=whsec_...        # Webhook 署名シークレット

# プラン別 Price ID（Stripe Dashboard で取得）
STRIPE_PRICE_FREE=price_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_ENTERPRISE=price_...

# アプリURL
NEXT_PUBLIC_APP_URL=https://your-app.com
```

### Stripe クライアント初期化

```typescript
// lib/stripe.ts
import Stripe from 'stripe';

if (!process.env.STRIPE_SECRET_KEY) {
  throw new Error('STRIPE_SECRET_KEY is not set');
}

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY, {
  apiVersion: '2024-06-20', // 最新の安定版に固定
  typescript: true,
});

// フロントエンド用（クライアントサイド）
export const getStripeJs = async () => {
  const { loadStripe } = await import('@stripe/stripe-js');
  return loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!);
};
```

---

## 3. 料金プラン設定

### 3-1. プラン定義ファイル（中央集権管理）

```typescript
// config/plans.ts
export type PlanId = 'free' | 'pro' | 'enterprise';
export type BillingInterval = 'month' | 'year';

export interface Plan {
  id: PlanId;
  name: string;
  description: string;
  stripePriceId: Record<BillingInterval, string | null>;
  price: Record<BillingInterval, number>;  // 円 or USD cents
  currency: string;
  features: string[];
  limits: {
    seats?: number;
    storage?: number;   // GB
    apiCalls?: number;  // per month
    [key: string]: number | undefined;
  };
  trialDays?: number;
  isPopular?: boolean;
  isEnterprise?: boolean;
}

export const PLANS: Record<PlanId, Plan> = {
  free: {
    id: 'free',
    name: 'Free',
    description: '個人・小規模利用向け',
    stripePriceId: { month: null, year: null }, // 無料プランはIDなし
    price: { month: 0, year: 0 },
    currency: 'jpy',
    features: ['基本機能', '1ユーザー', '1GBストレージ'],
    limits: { seats: 1, storage: 1, apiCalls: 1000 },
  },
  pro: {
    id: 'pro',
    name: 'Pro',
    description: '成長中のチーム向け',
    stripePriceId: {
      month: process.env.STRIPE_PRICE_PRO_MONTHLY ?? '',
      year: process.env.STRIPE_PRICE_PRO_YEARLY ?? '',
    },
    price: { month: 2980, year: 29800 },
    currency: 'jpy',
    features: ['全機能', '10ユーザー', '100GBストレージ', '優先サポート'],
    limits: { seats: 10, storage: 100, apiCalls: 100000 },
    trialDays: 14,
    isPopular: true,
  },
  enterprise: {
    id: 'enterprise',
    name: 'Enterprise',
    description: '大規模組織向け',
    stripePriceId: {
      month: process.env.STRIPE_PRICE_ENTERPRISE_MONTHLY ?? '',
      year: process.env.STRIPE_PRICE_ENTERPRISE_YEARLY ?? '',
    },
    price: { month: 9800, year: 98000 },
    currency: 'jpy',
    features: ['全機能', '無制限ユーザー', '無制限ストレージ', '専任サポート', 'SLA保証'],
    limits: { seats: Infinity, storage: Infinity, apiCalls: Infinity },
    isEnterprise: true,
  },
};

export const getPlanById = (id: PlanId): Plan => PLANS[id];
export const getStripePriceId = (id: PlanId, interval: BillingInterval): string | null =>
  PLANS[id].stripePriceId[interval
