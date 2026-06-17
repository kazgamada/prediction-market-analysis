---
name: claude-api-spec-gen
description: Claude API（Anthropic SDK）を使って、ユーザーのアイデアや要望から実装仕様書（要件定義・画面設計・データモデル・API 定義）を自動生成する機能を実装するときに使う。プロンプト構成、プロンプトキャッシュ（cache_control）、ツール使用、構造化出力（JSON mode 相当）、長文生成時のストリーミング、コスト最適化（Haiku/Sonnet/Opus の使い分け）を含む。ユーザーが「アイデアから仕様書を作る」「Claude で要件定義を生成」「AI で設計書」「LLM で spec 出力」と言及したときにトリガー。
---

# Claude API による仕様書生成パターン

## 概要

「アイデア → Claude API → 実装仕様書」の既存フローをテンプレ化する Skill。Kaz の複数ツール（BlackZero, GAIA 等）で類似の実装があるため、共通パターンとして切り出す。

## 使用タイミング

- 新しいツールに「アイデアから仕様書を自動生成」機能を追加するとき
- 既存の仕様書生成機能を Claude の新モデル（4.x 系）へ移行するとき
- プロンプトキャッシュを導入してコスト削減するとき

## 手順

TODO: 追記予定

### モデル選定

| 用途 | 推奨モデル | 備考 |
|------|-----------|------|
| ドラフト生成（広く浅く） | Haiku 4.5 | 高速・低コスト |
| 本番の仕様書生成 | Sonnet 4.6 | バランス型。デフォルト推奨 |
| 複雑な技術設計・アーキテクチャ判断 | Opus 4.7 | 精度重視、コスト高 |

### プロンプト構成

1. **System prompt**: 仕様書のフォーマット定義、出力ルール、ドメイン知識を含める
   - `cache_control: { type: "ephemeral" }` でキャッシュ（同じ System prompt で複数生成する場合に有効）
2. **User prompt**: ユーザーのアイデア入力
3. **Assistant prefill**: 出力を安定させるため `<specification>` タグ等で始める

### 構造化出力

- JSON で欲しい場合: Tool Use（`tools` パラメータ）でスキーマを定義
- 自由フォーマットで欲しい場合: Markdown + 見出し構成を System prompt で固定

### プロンプトキャッシュ

- System prompt が 1024 トークン以上なら必ずキャッシュする
- キャッシュヒット率を監視し、キャッシュブロックの配置を調整

### ストリーミング

- 仕様書は長文になるので `stream: true` で Server-Sent Events 経由で返す
- Next.js の Route Handler なら `ReadableStream` で返却

### エラーハンドリング

- `overloaded_error`: 指数バックオフで再試行（最大3回）
- `rate_limit_error`: `retry-after` ヘッダに従う
- `invalid_request_error`: 即座に失敗、ユーザーへ伝達

## 補助ファイル

TODO: `examples/spec-gen-route.ts`, `examples/system-prompt.md` を追加予定

## 備考

- API キーは `ANTHROPIC_API_KEY` 環境変数、サーバーサイドのみ
- モデル ID は時期により更新されるため、環境変数で切り替え可能にしておく
- コスト監視のため、各生成のトークン数を Supabase に記録すると運用が楽
