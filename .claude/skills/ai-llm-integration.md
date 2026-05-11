---
name: ai-llm-integration
description: >-
  Claude API / Anthropic SDK をNext.js・Server Actions・Route Handlersで統合するための
  汎用パターン集。セットアップ・ストリーミング・バックグラウンド生成・マルチプロバイダー対応・
  プロンプト設計・エラーハンドリング・コンテンツ生成パイプラインを網羅する。
category: ai-llm
sourceSkillIds:
  - 497034fa
  - 7f743c01
  - 77ee08e7
  - 48e54a63
  - 88bff324
  - 92cc7dd0
  - 999c9a11
  - 94d9d45b
  - 93ace98e
  - 7989c60d
  - b11969d1
  - d4020c79
  - '40589624'
  - e0dc9bf4
  - 94d290f7
  - 38f53581
  - 07878b5c
  - a568bc6f
  - 2254a02d
  - a53ebd7b
  - 08da7454
  - 54aab08c
  - c8aaad53
  - 1f63a199
  - d10f3597
  - 44ddc9f0
  - ec0d23cc
  - defe83e6
  - d2a2da70
  - c929740d
  - f72822ef
  - e61424f7
  - 6700ab5b
  - 238f1a87
  - 1a300e69
  - f0fe97b0
  - 42f1f0ba
  - acfd57cb
  - c99c03d9
  - d58b5c44
  - 6aba5abb
  - 8c7a657e
generatedAt: '2026-05-11'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-10T19:11:30+00:00'
adoptedFromArchive:
  - archive/prediction-market-analysis/.claude/skills/ai-llm-integration.md
  - archive/aegis-market-os/.claude/skills/coding-conventions.md
  - archive/AISaaS/.claude/skills/add-email-template.md
  - archive/AISaaS/.claude/skills/content-generation-pipeline.md
  - archive/aegis-market-os/.claude/skills/ai-llm-integration-derived.md
  - archive/ai-agent-hub/.claude/skills/ai-llm-integration-derived.md
  - archive/ai-company/.claude/skills/ai-llm-integration-derived.md
  - archive/AISaaS/.claude/skills/ai-llm-integration-derived.md
  - archive/KOKOKARA/.claude/skills/ai-llm-integration-derived.md
  - archive/LINE-AI/.claude/skills/ai-llm-integration-derived.md
---

# AI / LLM Integration — Claude API & Anthropic SDK

## 1. セットアップ

### 依存関係

```bash
npm install @anthropic-ai/sdk
# ストリーミング用（Next.js App Router）
npm install ai
# 環境変数
# ANTHROPIC_API_KEY=sk-ant-...
```

### クライアント初期化

```typescript
// lib/anthropic.ts
import Anthropic from "@anthropic-ai/sdk";

export const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
});

// モデル定数（プロジェクト横断で統一）
export const CLAUDE_MODELS = {
  OPUS: "claude-opus-4-5",
  SONNET: "claude-sonnet-4-5",
  HAIKU: "claude-haiku-4-5",
} as const;
export type ClaudeModel = (typeof CLAUDE_MODELS)[keyof typeof CLAUDE_MODELS];
```

---

## 2. 基本的なメッセージ生成

### シンプルなテキスト生成

```typescript
// lib/ai/generate.ts
import { anthropic, CLAUDE_MODELS } from "@/lib/anthropic";

export async function generateText(
  prompt: string,
  options?: {
    model?: ClaudeModel;
    maxTokens?: number;
    systemPrompt?: string;
  }
): Promise<string> {
  const response = await anthropic.messages.create({
    model: options?.model ?? CLAUDE_MODELS.SONNET,
    max_tokens: options?.maxTokens ?? 1024,
    system: options?.systemPrompt,
    messages: [{ role: "user", content: prompt }],
  });

  const block = response.content[0];
  if (block.type !== "text") throw new Error("Unexpected response type");
  return block.text;
}
```

### 構造化JSON出力

```typescript
export async function generateStructuredData<T>(
  prompt: string,
  schema: string, // JSON Schema の説明
  systemPrompt?: string
): Promise<T> {
  const text = await generateText(
    `${prompt}\n\nRespond with valid JSON only. Schema: ${schema}`,
    {
      systemPrompt:
        systemPrompt ??
        "You are a helpful assistant. Always respond with valid JSON.",
    }
  );

  // JSON ブロックを抽出
  const jsonMatch = text.match(/```json\n?([\s\S]*?)\n?```/) ?? [null, text];
  return JSON.parse(jsonMatch[1].trim()) as T;
}
```

---

## 3. ストリーミング

### Route Handler（App Router）

```typescript
// app/api/ai/stream/route.ts
import { anthropic, CLAUDE_MODELS } from "@/lib/anthropic";
import { StreamingTextResponse, AnthropicStream } from "ai"; // Vercel AI SDK

export async function POST(req: Request) {
  const { messages, systemPrompt } = await req.json();

  const response = await anthropic.messages.create({
    model: CLAUDE_MODELS.SONNET,
    max_tokens: 2048,
    system: systemPrompt,
    messages,
    stream: true,
  });

  const stream = AnthropicStream(response);
  return new StreamingTextResponse(stream);
}
```

### Vercel AI SDK を使わない手動ストリーミング

```typescript
// app/api/ai/stream-manual/route.ts
export async function POST(req: Request) {
  const { prompt } = await req.json();

  const encoder = new TextEncoder();
  const readable = new ReadableStream({
    async start(controller) {
      const stream = anthropic.messages.stream({
        model: CLAUDE_MODELS.SONNET,
        max_tokens: 1024,
        messages: [{ role: "user", content: prompt }],
      });

      for await (const event of stream) {
        if (
          event.type === "content_block_delta" &&
          event.delta.type === "text_delta"
        ) {
          controller.enqueue(encoder.encode(event.delta.text));
        }
      }
      controller.close();
    },
  });

  return new Response(readable, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Transfer-Encoding": "chunked",
    },
  });
}
```

### クライアント側でストリームを読む

```typescript
// hooks/useAIStream.ts
import { useState, useCallback } from "react";

export function useAIStream(endpoint: string) {
  const [text, setText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const generate = useCallback(
    async (payload: unknown) => {
      setIsLoading(true);
      setText("");
      setError(null);

      try {
        const res = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          setText((prev) => prev + decoder.decode(value));
        }
      } catch (e) {
        setError(e instanceof Error ? e : new Error(String(e)));
      } finally {
        setIsLoading(false);
      }
    },
    [endpoint]
  );

  return { text, isLoading, error, generate };
}
```

---

## 4. Server Actions での利用

```typescript
// app/actions/ai.ts
"use server";

import { anthropic, CLAUDE_MODELS } from "@/lib/anthropic";
import { createStreamableValue } from "ai/rsc"; // Vercel AI SDK RSC

// ストリームを Server Action から返す
export async function generateWithStream(prompt: string) {
  const stream = createStreamableValue("");

  (async () => {
    const aiStream = anthropic.messages.stream({
      model: CLAUDE_MODELS.SONNET,
      max_tokens: 1024,
      messages: [{ role: "user", content: prompt }],
    });

    for await (const event of aiStream) {
      if (
        event.type === "content_block_delta" &&
        event.delta.type === "text_delta"
      ) {
        stream.update(event.delta.text);
      }
    }
    stream.done();
  })();

  return { output: stream.value };
}

// クライアント側
// const { output } = await generateWithStream(prompt);
// for await (const delta of readStreamableValue(output)) { ... }
```

---

## 5. バックグラウンド生成パイプライン

コンテンツ生成を非同期で行い、DB にステータスを記録するパターン（AISaaS / content-generation-pipeline より）。
