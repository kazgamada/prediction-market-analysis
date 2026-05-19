---
name: ai-llm-integration
description: >-
  Claude API / Anthropic SDK を Next.js（App Router）・Server Actions・Route Handlers
  で 統合するための汎用パターン集。セットアップ・ストリーミング・バックグラウンド生成・
  マルチプロバイダー対応・プロンプト設計・エラーハンドリング・コスト管理を網羅する。
category: ai-llm
version: 2
sourceSkillIds:
  - 4119be00
  - acad8888
  - 5b9df56e
  - d4c30a79
  - 50e467ba
  - e62d03ca
  - 0ad01970
  - 150f406c
  - c4ce7df6
generatedAt: '2026-05-11'
---

<!-- 
統合メモ:
- ベース: ai-llm-integration（prediction-market-analysis）+ ai-llm-integration-derived（aegis-market-os, changedAt: 2026-05-07）
- aegis-market-os 版はテスト用 derive だが effectiveTimestamp が新しいため、差分（セクション構成・補足注記）を優先採用
- content-generation-pipeline（AISaaS）のバックグラウンド生成パターン・ステータス遷移を §5 に統合
- add-email-template / KOKOKARA skills（選択UI・ダークテーマ・ブランチ運用・deferred tool）は
  ai-llm-integration カテゴリと無関係のため棄却。参照先: add-email-template, skills-KOKOKARA
-->

# AI / LLM Integration — Claude API & Anthropic SDK

## 1. セットアップ

### 依存関係

```bash
npm install @anthropic-ai/sdk
# ストリーミング用（Next.js App Router）
npm install ai
# マルチプロバイダー対応（任意）
npm install @ai-sdk/anthropic @ai-sdk/openai
```

### 環境変数

```bash
# .env.local
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...          # マルチプロバイダー時
AI_DEFAULT_PROVIDER=anthropic  # 切り替え制御
```

### クライアント初期化（シングルトン）

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

---

## 2. 基本テキスト生成

### Server Action（非ストリーミング）

```typescript
// app/actions/generate.ts
"use server";

import { getAnthropicClient } from "@/lib/ai/client";

export async function generateText(prompt: string): Promise<string> {
  const client = getAnthropicClient();

  const message = await client.messages.create({
    model: "claude-opus-4-5",      // 最新モデルを常に確認
    max_tokens: 1024,
    messages: [{ role: "user", content: prompt }],
  });

  const block = message.content[0];
  if (block.type !== "text") throw new Error("Unexpected content type");
  return block.text;
}
```

### Route Handler（非ストリーミング）

```typescript
// app/api/generate/route.ts
import { NextRequest, NextResponse } from "next/server";
import { getAnthropicClient } from "@/lib/ai/client";

export async function POST(req: NextRequest) {
  const { prompt } = await req.json();

  const client = getAnthropicClient();
  const message = await client.messages.create({
    model: "claude-opus-4-5",
    max_tokens: 1024,
    messages: [{ role: "user", content: prompt }],
  });

  const text =
    message.content[0].type === "text" ? message.content[0].text : "";
  return NextResponse.json({ text });
}
```

---

## 3. ストリーミング

### Route Handler + Vercel AI SDK

```typescript
// app/api/stream/route.ts
import { anthropic } from "@ai-sdk/anthropic";
import { streamText } from "ai";

export const maxDuration = 60; // Vercel Functions タイムアウト

export async function POST(req: Request) {
  const { messages } = await req.json();

  const result = await streamText({
    model: anthropic("claude-opus-4-5"),
    messages,
    system: "You are a helpful assistant.",
  });

  return result.toDataStreamResponse();
}
```

### クライアント側（`useChat` フック）

```typescript
// app/components/ChatInterface.tsx
"use client";
import { useChat } from "ai/react";

export function ChatInterface() {
  const { messages, input, handleInputChange, handleSubmit, isLoading } =
    useChat({ api: "/api/stream" });

  return (
    <div>
      {messages.map((m) => (
        <div key={m.id}>
          <strong>{m.role}:</strong> {m.content}
        </div>
      ))}
      <form onSubmit={handleSubmit}>
        <input value={input} onChange={handleInputChange} disabled={isLoading} />
        <button type="submit" disabled={isLoading}>送信</button>
      </form>
    </div>
  );
}
```

### 生 Anthropic SDK でストリーミング（Vercel AI SDK を使わない場合）

```typescript
// app/api/stream-raw/route.ts
import Anthropic from "@anthropic-ai/sdk";

export async function POST(req: Request) {
  const { prompt } = await req.json();
  const client = new Anthropic();

  const stream = await client.messages.stream({
    model: "claude-opus-4-5",
    max_tokens: 1024,
    messages: [{ role: "user", content: prompt }],
  });

  const encoder = new TextEncoder();
  const readable = new ReadableStream({
    async start(controller) {
      for await (const chunk of stream) {
        if (
          chunk.type === "content_block_delta" &&
          chunk.delta.type === "text_delta"
        ) {
          controller.enqueue(encoder.encode(chunk.delta.text));
        }
      }
      controller.close();
    },
  });

  return new Response(readable, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
```

---

## 4. システムプロンプトとコンテキスト設計

```typescript
// lib/ai/prompts.ts

export const SYSTEM_PROMPTS = {
  analyst: `You are an expert analyst. Respond in JSON only.
Rules:
- Be concise and factual
- Include confidence scores (0-1)
- Flag uncertainty explicitly`,

  assistant: `You are a helpful assistant for {appName}.
- Answer in the user's language
- Cite sources when available`,
} as const;

// 変数展開ユーティリティ
export function buildSystemPrompt(
  key: keyof typeof SYSTEM_PROMPTS,
  vars: Record<string, string> = {}
): string {
  let prompt = SYSTEM_PROMPTS[key] as string;
  for (const [k, v] of Object.
