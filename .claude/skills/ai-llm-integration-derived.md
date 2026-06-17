---
name: ai-llm-integration-derived
description: '# AI / LLM Integration — Claude API & Anthropic SDK'
category: ai-llm
version: 1
parent: cf5668a9
changeType: derive
changeReason: テスト
changedAt: '2026-05-07T02:35:32.508Z'
---

# AI / LLM Integration — Claude API & Anthropic SDK

## 1. セットアップ

### 依存関係

```bash
npm install @anthropic-ai/sdk
# ストリーミング用（Next.js App Router）
npm install ai                    # Vercel AI SDK（任意）
```

### クライアント初期化

```typescript
// lib/anthropic.ts
import Anthropic from "@anthropic-ai/sdk";

// シングルトンにする（サーバーサイドのみ）
export const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY!, // 必須
  // maxRetries: 3,  // デフォルト 2
  // timeout: 60_000,
});
```

```
# .env.local
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 2. 基本呼び出しパターン

### 2-1. 単発テキスト生成（非ストリーム）

```typescript
// lib/ai/generate.ts
import { anthropic } from "@/lib/anthropic";

export async function generateText(
  systemPrompt: string,
  userMessage: string,
  model: AnthropicModel = "claude-opus-4-5"
): Promise<string> {
  const message = await anthropic.messages.create({
    model,
    max_tokens: 4096,
    system: systemPrompt,
    messages: [{ role: "user", content: userMessage }],
  });

  const block = message.content[0];
  if (block.type !== "text") throw new Error("Unexpected content type");
  return block.text;
}
```

### 2-2. ストリーミング（Server-Sent Events / App Router）

```typescript
// app/api/chat/route.ts
import { anthropic } from "@/lib/anthropic";
import { AnthropicStream, StreamingTextResponse } from "ai"; // Vercel AI SDK

export const runtime = "edge"; // または "nodejs"

export async function POST(req: Request) {
  const { messages, systemPrompt } = await req.json();

  const response = await anthropic.messages.create({
    model: "claude-opus-4-5",
    max_tokens: 4096,
    system: systemPrompt,
    messages,
    stream: true,
  });

  // Vercel AI SDK を使う場合
  const stream = AnthropicStream(response);
  return new StreamingTextResponse(stream);
}
```

```typescript
// Vercel AI SDK を使わない場合（生 SSE）
export async function POST(req: Request) {
  const { prompt } = await req.json();

  const encoder = new TextEncoder();
  const readable = new ReadableStream({
    async start(controller) {
      const stream = await anthropic.messages.stream({
        model: "claude-opus-4-5",
        max_tokens: 2048,
        messages: [{ role: "user", content: prompt }],
      });

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

## 3. バックグラウンド生成パターン（fire-and-forget）

非同期で重い生成処理を走らせ、DB に結果を保存する典型パターン。

```typescript
// lib/ai/background-generation.ts
import { db } from "@/lib/db";
import { anthropic } from "@/lib/anthropic";

type GenerationStatus =
  | "pending"
  | "generating"
  | "json_saved"
  | "completed"
  | "error";

/** tRPC mutation など呼び出し元から fire-and-forget で呼ぶ */
export async function runBackgroundGeneration(generationId: string) {
  try {
    // 1. ステータスを generating に更新
    await db.contentGenerations.update({
      where: { id: generationId },
      data: { status: "generating" as GenerationStatus },
    });

    // 2. コンテキスト取得
    const record = await db.contentGenerations.findUniqueOrThrow({
      where: { id: generationId },
      include: { relatedData: true },
    });

    // 3. Anthropic 呼び出し
    const rawText = await generateSingleContent(record);

    // 4. JSON パース（失敗しても status を error にして保存）
    const parsed = safeParseJson(rawText);

    // 5. 成功保存
    await db.contentGenerations.update({
      where: { id: generationId },
      data: {
        generatedJson: parsed,
        rawText,
        status: "json_saved" as GenerationStatus,
      },
    });

    // 6. 後処理（HTML 組み立てなど）
    await buildAndSaveHtml(generationId, parsed);

    await db.contentGenerations.update({
      where: { id: generationId },
      data: { status: "completed" as GenerationStatus },
    });
  } catch (error) {
    console.error("[background-generation] error:", error);
    await db.contentGenerations
      .update({
        where: { id: generationId },
        data: {
          status: "error" as GenerationStatus,
          errorMessage: String(error),
        },
      })
      .catch(() => {}); // DB 更新失敗は握りつぶす
  }
}

function safeParseJson(text: string): unknown {
  // コードブロック除去 → JSON.parse
  const cleaned = text.replace(/^```json\s*/m, "").replace(/```\s*$/m, "");
  try {
    return JSON.parse(cleaned);
  } catch {
    return { raw: text }; // フォールバック
  }
}
```

### ステータス遷移図

```
pending
  ↓ runBackgroundGeneration 開始
generating
  ↓ Anthropic API 完了
json_saved
  ↓ HTML 組み立て完了
completed
  ↓ (任意のステップで例外)
error
```

---

## 4. マルチプロバイダー対応

### プロバイダー抽象化レイヤー

```typescript
// lib/ai/providers.ts
export type AiProvider = "anthropic" | "openai" | "gemini";

export interface AiCallOptions {
  model?: string;
  maxTokens?: number;
  systemPrompt?: string;
  temperature?: number;
}

export async function callAi(
  provider: AiProvider,
  userMessage: string,
  opts: AiCallOptions = {}
): Promise<string> {
  switch (provider) {
    case "anthropic":
      return callAnthropic(userMessage, opts);
    case "openai":
      return callOpenAi(userMessage, opts);
    default:
      throw new Error(`Unsup
