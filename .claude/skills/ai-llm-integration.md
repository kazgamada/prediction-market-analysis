---
name: ai-llm-integration
description: >-
  Claude API / Anthropic SDK をNext.js・サーバーアクション・Route Handlerで統合するためのパターン集。
  クライアント初期化・ストリーミング・バックグラウンド生成・マルチプロバイダー対応・プロンプト設計・エラーハンドリングを網羅する。
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
---

# AI / LLM Integration — Claude API & Anthropic SDK

## 1. セットアップ・クライアント初期化

### 推奨ディレクトリ構成

```
lib/
  ai/
    client.ts          # Anthropicクライアントのシングルトン
    providers.ts       # マルチプロバイダー抽象化
    prompts/           # プロンプトテンプレート
      system.ts
      user.ts
    utils.ts           # ストリーム変換・トークン計算など
app/
  api/
    ai/
      chat/route.ts    # ストリーミングRoute Handler
      generate/route.ts
```

### クライアントシングルトン（`lib/ai/client.ts`）

```typescript
import Anthropic from "@anthropic-ai/sdk";

// サーバーサイド専用 — クライアントコンポーネントからimportしない
if (typeof window !== "undefined") {
  throw new Error("lib/ai/client.ts はサーバーサイドのみで使用してください");
}

export const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY!,
  // タイムアウト・リトライを明示設定
  timeout: 60_000,
  maxRetries: 2,
});

/** 利用するモデルを一元管理 */
export const AI_MODELS = {
  /** 高精度・複雑なタスク向け */
  opus: "claude-opus-4-5",
  /** バランス型（推奨デフォルト） */
  sonnet: "claude-sonnet-4-5",
  /** 高速・低コスト */
  haiku: "claude-haiku-3-5",
} as const;

export type AIModel = keyof typeof AI_MODELS;
```

---

## 2. ストリーミング実装

### Route Handler — SSE ストリーミング（`app/api/ai/chat/route.ts`）

```typescript
import { NextRequest } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { anthropic, AI_MODELS } from "@/lib/ai/client";
import { z } from "zod";

const RequestSchema = z.object({
  messages: z.array(
    z.object({
      role: z.enum(["user", "assistant"]),
      content: z.string().min(1).max(100_000),
    })
  ),
  model: z.enum(["opus", "sonnet", "haiku"]).default("sonnet"),
  systemPrompt: z.string().optional(),
});

export async function POST(req: NextRequest) {
  // 1. バリデーション
  const body = await req.json().catch(() => null);
  const parsed = RequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json(
      { error: "Invalid request", details: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const { messages, model, systemPrompt } = parsed.data;

  // 2. ストリームを作成してReadableStreamに変換
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      try {
        const anthropicStream = anthropic.messages.stream({
          model: AI_MODELS[model],
          max_tokens: 4096,
          system: systemPrompt,
          messages,
        });

        for await (const event of anthropicStream) {
          // text_delta イベントのみ送信
          if (
            event.type === "content_block_delta" &&
            event.delta.type === "text_delta"
          ) {
            const chunk = `data: ${JSON.stringify({ text: event.delta.text })}\n\n`;
            controller.enqueue(encoder.encode(chunk));
          }

          // 完了イベント
          if (event.type === "message_stop") {
            controller.enqueue(encoder.encode("data: [DONE]\n\n"));
          }
        }
      } catch (error) {
        const message =
          error instanceof Anthropic.APIError
            ? `APIError: ${error.status} ${error.message}`
            : "Unexpected error";
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ error: message })}\n\n`)
        );
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
```

### クライアントサイド — SSE 受信フック（`hooks/use-chat-stream.ts`）

```typescript
"use client";

import { useState, useCallback, useRef } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export function useChatStream() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (userInput: string, systemPrompt?: string) => {
      setError(null);
      abortRef.current = new AbortController();

      const newMessages: Message[] = [
        ...messages,
        { role: "user", content: userInput },
      ];
      setMessages(newMessages);
      setIsStreaming(true);

      // アシスタントのプレースホルダーを追加
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "" },
      ]);

      try {
        const res = await fetch("/api/ai/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: newMessages, systemPrompt }),
          signal: abortRef.current.signal,
        });

        if (!res.ok || !res.body) throw new Error("Stream initiation failed");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const lines = decoder.decode(value).split("\n");
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const data = line.slice(6);
            if (data === "[DONE]") break;

            const parsed = JSON.parse(data);
            if (parsed.error) throw new Error(parsed.error);
            if (parsed.text) {
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: updated[updated.length - 1].content + parsed.text,
                };
                return updated;
              });
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
