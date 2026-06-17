---
name: billing-stripe-integration
description: >-
  Stripe課金連携の設計・実装・設定・トラブルシュートの包括的ガイド。Checkout Session / Customer Portal /
  Webhook処理 / 料金プラン管理のパターンと、Next.js/TypeScriptでの実装例を提供する。
  あらゆるSaaSプロジェクト（月額・従量・トライアル・プラン変更）で再利用できる汎用テンプレート。
category: billing
sourceSkillIds:
  - b6b9d18f
  - '33202335'
generatedAt: '2026-05-23'
---

# Stripe課金連携 — 包括的実装ガイド

## 概要・適用範囲

このSkillは **Stripe + Next.js + TypeScript** で課金機能を実装するすべてのプロジェクトに適用する。

| 対象ユースケース | 説明 |
|---|---|
| SaaS月額・年額課金 | Subscription + Checkout Session |
| 従量課金 | Usage Records + Metered Billing |
| トライアル期間 | trial_period_days / trial_end 設定 |
| プラン追加・変更・削除 | Plan Config ワークフロー |
| セルフサービス管理 | Customer Portal |
| Webhook受信 | 署名検証 + イベント処理 |

---

## 1. 環境変数・初期設定

```bash
# .env.local
STRIPE_SECRET_KEY=sk_live_...          # サーバーサイドのみ
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...        # stripe listen で取得
NEXT_PUBLIC_APP_URL=https://your-app.com
```

```typescript
// lib/stripe.ts — シングルトンクライアント
import Stripe from 'stripe';

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2024-04-10',
  typescript: true,
});
```

> ⚠️ `STRIPE_SECRET_KEY` はサーバーサイドのみ使用。クライアントに漏洩しないこと。

---

## 2. 料金プラン管理ワークフロー

> plan-config Skill（BlackZero）を統合。プロジェクト固有のファイルパスは読み替えること。

### 2-1. プラン定義ファイル（コード管理）

```typescript
// config/plans.ts
export type PlanId = 'free' | 'starter' | 'pro' | 'enterprise';

export interface Plan {
  id: PlanId;
  name: string;
  stripePriceId: string;          // 環境変数から取得推奨
  stripeProductId: string;
  price: number;                  // 円 or セント
  currency: 'jpy' | 'usd';
  interval: 'month' | 'year';
  trialDays?: number;
  features: string[];
  limits: Record<string, number>;
}

export const PLANS: Record<PlanId, Plan> = {
  free: {
    id: 'free',
    name: 'Free',
    stripePriceId: '',            // Stripe不要プランは空文字
    stripeProductId: '',
    price: 0,
    currency: 'jpy',
    interval: 'month',
    features: ['機能A', '機能B'],
    limits: { projects: 1, members: 1 },
  },
  starter: {
    id: 'starter',
    name: 'Starter',
    stripePriceId: process.env.STRIPE_PRICE_STARTER!,
    stripeProductId: process.env.STRIPE_PRODUCT_STARTER!,
    price: 1980,
    currency: 'jpy',
    interval: 'month',
    trialDays: 14,
    features: ['機能A', '機能B', '機能C'],
    limits: { projects: 5, members: 3 },
  },
  pro: {
    id: 'pro',
    name: 'Pro',
    stripePriceId: process.env.STRIPE_PRICE_PRO!,
    stripeProductId: process.env.STRIPE_PRODUCT_PRO!,
    price: 4980,
    currency: 'jpy',
    interval: 'month',
    trialDays: 14,
    features: ['機能A', '機能B', '機能C', '機能D'],
    limits: { projects: 20, members: 10 },
  },
  enterprise: {
    id: 'enterprise',
    name: 'Enterprise',
    stripePriceId: process.env.STRIPE_PRICE_ENTERPRISE!,
    stripeProductId: process.env.STRIPE_PRODUCT_ENTERPRISE!,
    price: 19800,
    currency: 'jpy',
    interval: 'month',
    features: ['全機能', 'SLA', '専任サポート'],
    limits: { projects: Infinity, members: Infinity },
  },
};

export const getPlan = (id: PlanId): Plan => PLANS[id];
export const getPaidPlans = (): Plan[] =>
  Object.values(PLANS).filter((p) => p.stripePriceId);
```

### 2-2. プラン操作別チェックリスト

#### `add` — プラン追加

```
1. Stripeダッシュボードで Product + Price を作成
2. .env に STRIPE_PRICE_xxx / STRIPE_PRODUCT_xxx を追加
3. config/plans.ts に新プランエントリを追加
4. DBマイグレーション: plans テーブルに行を追加（必要な場合）
5. フロントエンドの料金ページUIを更新
6. E2Eテスト: Checkout → Webhook → DB反映
```

#### `edit` — プラン編集

```
1. Stripeでは既存Priceを編集不可 → 新Priceを作成してarchive旧Price
2. stripePriceId を新しいものに差し替え
3. 既存サブスクリプションの移行が必要か確認（migrate操作参照）
4. フロントエンドの表示文言・制限値を更新
```

#### `delete` — プラン削除

```
1. 既存サブスクリプションがあれば先に migrate
2. Stripeで Price を archive（削除不可）
3. config/plans.ts からエントリを削除（またはdeprecatedフラグ追加）
4. DBマイグレーション: プラン参照の外部キー整合性を確認
```

#### `migrate` — プラン移行（既存サブスクへ適用）

```typescript
// scripts/migrate-subscriptions.ts
import { stripe } from '../lib/stripe';
import { db } from '../lib/db';

async function migrateSubscriptions(fromPriceId: string, toPriceId: string) {
  const subscriptions = await db.subscriptions.findMany({
    where: { stripePriceId: fromPriceId, status: 'active' },
  });

  for (const sub of subscriptions) {
    const stripeSub = await stripe.subscriptions.retrieve(
