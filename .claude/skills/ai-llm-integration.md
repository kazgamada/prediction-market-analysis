---
name: ai-llm-integration
description: >-
  Claude API / Anthropic SDK をNext.js・Server Actions・Route Handlersで統合するための
  汎用パターン集。セットアップ・ストリーミング・バックグラウンド生成・マルチプロバイダー対応・ プロンプト設計・エラーハンドリングを網羅する。
category: ai-llm
sourceSkillIds:
  - 497034fa
  - 77ee08e7
  - 48e54a63
  - 92cc7dd0
  - 94d9d45b
  - 93ace98e
  - b11969d1
  - d4020c79
  - e0dc9bf4
  - 94d290f7
  - 38f53581
  - 07878b5c
  - a568bc6f
  - a53ebd7b
  - 08da7454
  - 54aab08c
  - 1f63a199
  - 44ddc9f0
  - defe83e6
  - f72822ef
  - 6700ab5b
  - 1a300e69
  - 42f1f0ba
  - c99c03d9
  - 6aba5abb
generatedAt: '2026-05-08'
---

# AI / LLM Integration — Claude API & Anthropic SDK

## 1. セットアップ

### 1-1. インストール

```bash
pnpm add @anthropic-ai/sdk ai
```

### 1-2. 環境変数

```env
# .env.local
ANTHROPIC_API_KEY=sk-ant-...
# マルチプロバイダー使用時
OPENAI_API_KEY=sk-...
GOOGLE_GENERATIVE_AI_API_KEY=...
```

### 1-3. シングルトンクライアント

```typescript
// lib/ai/client.ts
import Anthropic from "@anthropic-ai/sdk";

let _client: Anthropic | null = null;

export function getAnthropicClient(): Anthropic {
  if (!_client) {
    if (!process.env.ANTHROPIC_API_KEY) {
      throw new Error("ANTHROPIC_API_KEY is not set");
    }
    _client = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY,
    });
  }
  return _client;
}
```

---

## 2. 基本パターン

### 2-1. 非ストリーミング（Server Action）

```typescript
// app/actions/generate.ts
"use server";

import { getAnthropicClient } from "@/lib/ai/client";

export async function generateText(prompt: string): Promise<string> {
  const client = getAnthropicClient();

  const message = await client.messages.create({
    model: "claude-opus-4-5",
    max_tokens: 1024,
    messages: [{ role: "user", content: prompt }],
  });

  const block = message.content[0];
  if (block.type !== "text") throw new Error("Unexpected response type");
  return block.text;
}
```

### 2-2. 非ストリーミング（Route Handler）

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

  const block = message.content[0];
  if (block.type !== "text") {
    return NextResponse.json({ error: "Unexpected type" }, { status: 500 });
  }

  return NextResponse.json({ text: block.text });
}
```

---

## 3. ストリーミング

### 3-1. Route Handler でストリーミング

```typescript
// app/api/stream/route.ts
import { NextRequest } from "next/server";
import { getAnthropicClient } from "@/lib/ai/client";

export async function POST(req: NextRequest) {
  const { prompt, systemPrompt } = await req.json();
  const client = getAnthropicClient();

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const anthropicStream = await client.messages.create({
        model: "claude-opus-4-5",
        max_tokens: 2048,
        system: systemPrompt,
        messages: [{ role: "user", content: prompt }],
        stream: true,
      });

      try {
        for await (const event of anthropicStream) {
          if (
            event.type === "content_block_delta" &&
            event.delta.type === "text_delta"
          ) {
            controller.enqueue(encoder.encode(event.delta.text));
          }
          if (event.type === "message_stop") break;
        }
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Transfer-Encoding": "chunked",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
```

### 3-2. Vercel AI SDK を使ったストリーミング（推奨）

```typescript
// app/api/chat/route.ts
import { anthropic } from "@ai-sdk/anthropic";
import { streamText } from "ai";

export const maxDuration = 60;

export async function POST(req: Request) {
  const { messages, system } = await req.json();

  const result = streamText({
    model: anthropic("claude-opus-4-5"),
    system,
    messages,
    maxTokens: 2048,
  });

  return result.toDataStreamResponse();
}
```

### 3-3. クライアントサイド（useChat フック）

```typescript
// components/ChatInterface.tsx
"use client";

import { useChat } from "ai/react";

export function ChatInterface({ systemPrompt }: { systemPrompt?: string }) {
  const { messages, input, handleInputChange, handleSubmit, isLoading, error } =
    useChat({
      api: "/api/chat",
      body: { system: systemPrompt },
    });

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-4 p-4">
        {messages.map((m) => (
          <div
            key={m.id}
            className={m.role === "user" ? "text-right" : "text-left"}
          >
            <span className="inline-block px-3 py-2 rounded-lg bg-muted">
              {m.content}
            </span>
          </div>
        ))}
        {isLoading && (
          <div className="text-muted-foreground text-sm animate-pulse">
            生成中...
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="p-4 border-t flex gap-2">
        <input
          value={input}
          onChange={handleInputChange}
          placeholder="メッセージを入力..."
          disabled={isLoading}
          className="flex-1 px-3 py-2 border rounded-lg"
        />
        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg disabled:opacity-50"
        >
          送信
        </button>
      </form>
    </div>
  );
}
```

### 3-4. 手動ストリーミング（fetch + ReadableStream）

```typescript
// hooks/useStreamingGeneration.ts
"use client";

import { useState, useCallback } from "react";

export function useStreamingGeneration() {
  const [output, setOutput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = useCallback(async (prompt: string) => {
    setOutput("");
    setError(null);
    setIsStreaming(true);

    try {
      
