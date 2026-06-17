---
name: ai-llm-integration
description: >-
  Claude API / Anthropic SDK を Next.js（App Router）・Server Actions・Route Handlers
  で 統合するための汎用パターン集。セットアップ・ストリーミング・バックグラウンド生成・
  マルチプロバイダー対応・プロンプト設計・エラーハンドリング・コスト管理を網羅する。
category: ai-llm
version: 3
sourceSkillIds:
  - 4119be00
  - acad8888
  - 5b9df56e
  - b844a094
  - 56cb7e84
  - d4c30a79
  - c12cc421
  - f9f3f13b
  - f3fd7006
  - 50e467ba
  - e62d03ca
  - 0ad01970
  - 150f406c
  - c4ce7df6
  - 5070feb9
generatedAt: '2026-06-17'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-07T02:35:32.508Z'
adoptedFromArchive:
  - archive/skills/ai-llm-integration-derived.md
  - archive/skills/add-email-template.md
  - archive/skills/ai-llm-integration.md
  - archive/skills/ai-operations.md
  - archive/skills/approval-workflow.md
  - archive/skills/content-generation-pipeline.md
  - archive/skills/daily-report.md
  - archive/skills/gmail-sync-debug.md
  - archive/skills/ingest-pipeline.md
  - archive/skills/07-admin-list-selection-ui.md
---

# AI / LLM Integration — Claude API & Anthropic SDK

> **対象スタック**: Claude API · Anthropic SDK · Next.js App Router · TypeScript  
> **統合元**: aegis-market-os（ai-llm-integration v2 + derived v1）· AISaaS（content-generation-pipeline）· BlackZero（ai-operations · ingest-pipeline）

---

## 目次

1. [セットアップ](#1-セットアップ)
2. [基本的な呼び出しパターン](#2-基本的な呼び出しパターン)
3. [ストリーミング](#3-ストリーミング)
4. [バックグラウンド生成パイプライン](#4-バックグラウンド生成パイプライン)
5. [Server Actions での統合](#5-server-actions-での統合)
6. [Route Handler での統合](#6-route-handler-での統合)
7. [プロンプト設計パターン](#7-プロンプト設計パターン)
8. [マルチプロバイダー対応](#8-マルチプロバイダー対応)
9. [エラーハンドリング](#9-エラーハンドリング)
10. [コスト管理・モニタリング](#10-コスト管理モニタリング)
11. [AI モジュール分類パターン（BlackZero 由来）](#11-ai-モジュール分類パターン)
12. [よくある落とし穴と修正パターン](#12-よくある落とし穴と修正パターン)

---

## 1. セットアップ

### 依存関係

```bash
# Anthropic SDK（必須）
npm install @anthropic-ai/sdk

# Vercel AI SDK（ストリーミング・Next.js App Router 向け）
npm install ai

# OpenAI 互換フォールバックが必要な場合
npm install openai
```

### 環境変数

```bash
# .env.local
ANTHROPIC_API_KEY=sk-ant-...

# マルチプロバイダー構成
OPENAI_API_KEY=sk-...
GOOGLE_AI_API_KEY=...

# コスト管理用（任意）
AI_BUDGET_USD_DAILY=10.00
AI_BUDGET_USD_MONTHLY=200.00
```

### クライアントシングルトン

```typescript
// lib/ai/client.ts
import Anthropic from "@anthropic-ai/sdk";

let _client: Anthropic | null = null;

export function getAnthropicClient(): Anthropic {
  if (!_client) {
    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) throw new Error("ANTHROPIC_API_KEY is not set");
    _client = new Anthropic({ apiKey });
  }
  return _client;
}
```

### モデル定数

```typescript
// lib/ai/models.ts
export const AI_MODELS = {
  // 高性能・高コスト
  CLAUDE_OPUS: "claude-opus-4-5",
  // バランス型（推奨デフォルト）
  CLAUDE_SONNET: "claude-sonnet-4-5",
  // 高速・低コスト
  CLAUDE_HAIKU: "claude-haiku-4-5",
} as const;

export type AIModel = (typeof AI_MODELS)[keyof typeof AI_MODELS];

/** タスク種別ごとの推奨モデル */
export const MODEL_ROUTING: Record<string, AIModel> = {
  chat: AI_MODELS.CLAUDE_SONNET,
  classify: AI_MODELS.CLAUDE_HAIKU,
  summarize: AI_MODELS.CLAUDE_HAIKU,
  generate: AI_MODELS.CLAUDE_SONNET,
  analyze: AI_MODELS.CLAUDE_OPUS,
};
```

---

## 2. 基本的な呼び出しパターン

### シンプルなメッセージ生成

```typescript
// lib/ai/generate.ts
import { getAnthropicClient } from "./client";
import { AI_MODELS } from "./models";

interface GenerateOptions {
  system?: string;
  prompt: string;
  model?: string;
  maxTokens?: number;
  temperature?: number;
}

interface GenerateResult {
  content: string;
  inputTokens: number;
  outputTokens: number;
}

export async function generateText(
  opts: GenerateOptions
): Promise<GenerateResult> {
  const client = getAnthropicClient();

  const response = await client.messages.create({
    model: opts.model ?? AI_MODELS.CLAUDE_SONNET,
    max_tokens: opts.maxTokens ?? 1024,
    system: opts.system,
    messages: [{ role: "user", content: opts.prompt }],
  });

  const content = response.content
    .filter((b) => b.type === "text")
    .map((b) => b.text)
    .join("");

  return {
    content,
    inputTokens: response.usage.input_tokens,
    outputTokens: response.usage.output_tokens,
  };
}
```

### JSON 構造化出力

```typescript
// lib/ai/structured.ts
export async function generateJSON<T>(opts: {
  system?: string;
  prompt: string;
  schema: string; // JSON Schema の説明文
  model?: string;
}): Promise<T> {
  const { content } = await generateText({
    ...opts,
    system: [
      opts.system,
      "必ず有効な JSON のみを返してください。マークダウンコードブロックは不要です。",
      `期待するスキーマ: ${opts.schema}`,
    ]
      .filter(Boolean)
      .join("\n\n"),
  });

  // JSON ブロックを抽出（```json ... ``` を含む場合に対応）
  const jsonMatch = content.match(/```json\s*([\s\S]*?)\s*```/) ||
    content.match(/```\s*([\s\S]*?)\s*```/);
  const jsonStr = jsonMatch ? jsonMatch[1] : content.trim();

  return JSON.parse(jsonStr) as T;
}
```

---

## 3. ストリーミング

### Route Handler（App Router）

```typescript
// app/api/chat/route.ts
import { StreamingTextResponse, streamText } from "ai";
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();

export async function POST(req: Request) {
  const { messages, systemPrompt } = await req.json();

  const stream = await client.messages.stream({
    model: "claude-sonnet-4-5",
    max_tokens: 2048,
    system: systemPrompt,
    messages,
  });

  // Vercel AI SDK の StreamingTextResponse を利用
  const textStream = new ReadableStream({
    async start(controller) {
      for await (const chunk of stream) {
        if (
          
