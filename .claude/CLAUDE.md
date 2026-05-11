# 共通ルール（全ツール横断）

このファイルは `kaz-claude-config` リポジトリで管理されている、すべてのツールリポジトリ共通の Claude 向け指示です。各ツールリポジトリの `CLAUDE.md` から `@.claude/shared/CLAUDE.md` として参照されます。

各ツール固有のルールはツールリポジトリ側の `CLAUDE.md` で上書き・追加できます。ここに書かれているのはあくまで **デフォルト** です。

---

## 0. 蟻地獄回避ルール（最優先 / 他のルールに優先する）

エラー対応で同じ罠にハマり続ける「蟻地獄」を絶対に避ける。詰まりかけたら以下を機械的に守る。

### 0.1 ターミナルを使わない
- 修正・確認・デプロイはすべて **ブラウザ / GitHub Web UI / Vercel / Supabase Dashboard** で完結させる。
- ローカル CLI / shell / npm コマンドは原則使わない。やむを得ない最小コマンドのみ許容。
- ユーザーに「ターミナルでこれを実行してください」と要求するのは最後の手段。先に Web から実行できる経路を提示する。

### 0.2 修正は直接 main にプッシュ
- feature ブランチ / PR を経由せず、最短でデプロイされる経路を取る（Vercel が main から自動デプロイされる前提）。
- §8.1 の「feature ブランチ原則」より、**本ルールが優先**。
- 例外: 大規模リファクタや破壊的変更（DB drop、API 削除）は事前承認 + ブランチで進める。

### 0.3 原因究明を先、修正は後
- エラーが出たら **直そうとする前に原因を可視化する**。
- 第一手は `/api/health` などの診断エンドポイントで状況を表示させること（無ければ作る）。
- ログ・スタック・実データ（DB の Table Editor / Vercel Logs / ブラウザ DevTools）を **必ず実物で確認** してから仮説を立てる。
- **原因が明らかでないまま修正を試さない**。「とりあえず直してみる」は蟻地獄の入口。

### 0.4 既存知見を最初に読む
- 修正に着手する **前に必ず** `skills/troubleshoot-checklist/SKILL.md` を開いて該当セクションのチェックリストをなぞる。
- 加えて `archive/` 配下の関連 skill（`incident-response.md`, `debug.md`, `general-best-practices.md`, `devops-deploy-checklist.md`, `account-system-fixes.md` 等）を `grep -ri` で検索し、他ツール開発の知見を拾ってから実装する。
- 「該当 skill がないから新規」と早合点しない（§7.1 と整合）。

### 0.5 同じ修正を 3 回以上試したらリセット
- 同じ箇所で 3 回以上修正してダメなら、**仮説が間違っている**。
- すべての修正をリバートして「素のエラー」を再確認し、`troubleshoot-checklist` §9（メタ手順）に従って最小再現を作り直す。

### 0.6 Fly.io を使う場合
- ホスティングに Fly.io を採用するツールでは、デプロイ・環境変数・スケーリング・ロールバックの手順を `docs/setup/auto-deploy-flyio.md` に集約する。
- Fly.io 関連の作業に着手する前に **必ず `docs/setup/auto-deploy-flyio.md` を参照** し、その手順に従う。記載が無い項目は同ファイルに追記してから作業する。
- Vercel と Fly.io が混在するツールでは、本ファイル（CLAUDE.md）の §2 共通技術スタックよりも、ツールリポ側の `CLAUDE.md` および `docs/setup/auto-deploy-flyio.md` の指示を優先。

---

## 1. コミュニケーション方針

### 1.1 言語
- ユーザーへの応答は **日本語** で行うこと。
- コード内のコメントも原則日本語で記述する（OSSに貢献する場合などは英語可）。
- 変数名・関数名・ファイル名は英語（キャメルケース / ケバブケース）。

### 1.2 確認と報告
- 要件が曖昧な場合、**憶測で実装せずにユーザーへ確認する**。
- 破壊的変更（DBマイグレーション、既存APIの変更、ファイル削除など）を行う場合は、事前に計画を提示して承認を得る。
- 作業完了時は「何を変えたか / 次に何をすべきか」を1〜2文で報告する。

### 1.3 不明点への対応
- ドキュメントや既存実装から明確に導けないことは、勝手にデフォルト値を決めない。
- 検索・読み取りで確認できる範囲はまず自力で調べる。

---

## 2. 共通技術スタック

全ツール共通で採用している技術前提。個別ツールで差異がある場合はツール側の `CLAUDE.md` に明記する。

| 項目 | 採用技術 |
|------|---------|
| フロントエンド | Next.js 14（App Router） |
| 言語 | TypeScript（`strict: true`） |
| スタイル | Tailwind CSS |
| データベース / 認証 | Supabase（PostgreSQL + Auth + RLS） |
| 外部連携 | Make.com（Webhook） |
| AIモデル | Claude API（Anthropic SDK） |
| ホスティング | Vercel |

---

## 3. コーディング規約

### 3.1 命名規則
- **ファイル名**: ケバブケース（例: `user-profile.tsx`）。Next.js の特殊ファイル（`page.tsx`, `layout.tsx` 等）はフレームワーク規約に従う。
- **Reactコンポーネント名**: パスカルケース（例: `UserProfile`）。
- **変数・関数名**: キャメルケース（例: `getUserProfile`）。
- **定数**: SCREAMING_SNAKE_CASE（例: `MAX_RETRY_COUNT`）。
- **Supabase テーブル名**: スネークケース・複数形（例: `user_profiles`）。
- **環境変数**: SCREAMING_SNAKE_CASE、クライアント公開は `NEXT_PUBLIC_` プレフィックス必須。

### 3.2 import 順序
1. 外部パッケージ（`react`, `next`, ...）
2. 内部モジュール（`@/` エイリアス経由）
3. 相対パス（`./`, `../`）
4. スタイル・型定義

各グループの間に空行を1つ入れる。

### 3.3 フォーマット・Lint
- ESLint + Prettier を使用する前提。
- 既存の設定を勝手に緩めない。ルール追加が必要なら理由を添えて相談する。

### 3.4 コメント
- **デフォルトはコメントを書かない**。読みやすい命名で意図を伝える。
- WHY（なぜそうしているか）が非自明な場合のみ1行コメントを添える。
- WHAT（何をしているか）のコメントは原則禁止。

---

## 4. Supabase 関連ルール

### 4.1 RLS（Row Level Security）
- **新規テーブル作成時は RLS を必ず有効化**する。
- `public` スキーマの全テーブルに対して、最低限 `SELECT` のポリシーを設計する。
- 認証ユーザーのみアクセス可能にする場合は `auth.uid()` を条件に使う。

### 4.2 migration
- ファイル名: `<YYYYMMDDHHMMSS>_<概要>.sql`（Supabase CLI の標準形式）。
- 1 migration = 1 論理的な変更単位。複数テーブルの追加を1ファイルに混ぜない。
- 破壊的変更（`DROP`, `ALTER ... DROP COLUMN` 等）は別ファイルに分離。

### 4.3 型生成
- `supabase gen types typescript` でDB型を生成し、`src/types/database.ts` に配置。
- 手書きの型定義でDB型を置き換えない。

---

## 5. コミットメッセージ規約

**Conventional Commits** を採用する。

形式: `<type>(<scope>): <subject>`

| type | 用途 |
|------|------|
| `feat` | 新機能 |
| `fix` | バグ修正 |
| `refactor` | 機能を変えないコード整理 |
| `docs` | ドキュメントのみ |
| `style` | フォーマットのみ |
| `test` | テストの追加・修正 |
| `chore` | ビルド・補助ツール類 |

例:
```
feat(auth): add magic link login via Supabase
fix(api): handle empty webhook payload from Make.com
```

---

## 6. セキュリティ・機密情報

### 6.1 絶対にやらないこと
- `.env`, `.env.local`, `.env.production` をコミットする
- APIキー・シークレットをソースコードにハードコードする
- Supabase の `service_role` キーをクライアント側に露出させる
- 顧客固有情報・未公開の事業戦略をリポジトリに含める

### 6.2 機密情報の扱い
- 個人メモや機密は各ツールリポジトリの `CLAUDE.local.md`（`.gitignore` 済み）に限定。
- この共通リポジトリ `kaz-claude-config` には **一切の機密情報を入れない**。
- 認証情報は Vercel / Supabase / GitHub Actions の環境変数で管理。

### 6.3 依存パッケージ
- 新規パッケージ追加時は、メンテナンス状況・ダウンロード数・脆弱性履歴を軽く確認。
- 代替が標準ライブラリで済むなら標準を優先。

---

## 7. Skills 利用方針

- `.claude/shared/skills/` 配下（このリポジトリの Skills）と、`.claude/skills/` 配下（ツール固有 Skills）の両方を参照してよい。
- Skill のトリガー判断は `SKILL.md` の `description` に従う。マッチする場面では積極的に活用する。
- 同名の Skill が共通・ツール固有の両方に存在する場合、**ツール固有を優先**する。

### 7.1 既存 Skill で対応できない要件への対応フロー

新しい要件に対して `skills/` 配下の稼働中 Skill が一致しない場合は、**実装に着手する前に必ず `archive/` フォルダー全体を調査する**。

調査対象（共通リポでは `archive/`、ツール側からは `.claude/shared/archive/`）:

| サブディレクトリ | 内容 |
|------|------|
| `archive/_crawled/<owner>__<repo>/<skill>/` | 公開 GitHub からクロールしたスキル候補。`SKILL.md` 本体・`_source.json`（取得元）・`_summary.json`（日本語要約） |
| `archive/<project>/.claude/skills/`<br>`archive/<project>/docs/skills/` | 社内ツールから収集した過去の Skill |
| `archive/<project>/CLAUDE.md` 等 | プロジェクト固有のルール |

調査手順:

1. 要件のキーワードで `archive/` 全体を再帰的に検索（`grep -ri "<keyword>" archive/`）。`_summary.json` の日本語解説/用途も検索対象に含める
2. 関連しそうな `SKILL.md` を読み込み、要件にマッチするか確認
3. **見つかった場合**: その Skill の内容を参照しつつ実装。再利用価値が高ければ `skills/` への昇格をユーザーに提案
4. **見つからなかった場合のみ**: Skill 無しで実装するか、新規 Skill 作成をユーザーに提案

「既存 Skill が無いから新規実装」と早合点せず、`archive/` を必ず一通り見てから判断すること。

### 7.2 ツール側で Skill を進化させるときのルール

`.claude/skills/<slug>.md`（フラット形式）または `.claude/skills/<slug>/SKILL.md`（ディレクトリ形式）をツール側で改良した場合は、以下を **必ず** 守る。`kaz-claude-config` の collect ワークフローが日付ベースで「マスターより新しい改良」として検出し、Builder の Ideal 統合で漏れなく取り込めるようになる。

1. **frontmatter の `version` を +1** する（例: `version: 2` → `version: 3`）
2. **`changedAt`** を ISO 8601（例: `'2026-05-11T07:00:00.000Z'`）で更新
3. 必要に応じて `changeType: fix | derive` と `changeReason: "<1行で意図>"` を付与
4. コミットメッセージは `fix(skill: <slug>): <reason>` 形式

これらを忘れても `git log` の commit time から救済されるが、frontmatter を正しく更新するのが第一原則。マスター（`skills/<slug>/SKILL.md`）を直接編集してはならない（マスター更新は kaz-claude-config 側で行う）。

---

## 8. 作業フロー

### 8.1 ブランチ
- **§0.2 蟻地獄回避ルールが優先**。日常の修正は main に直接 push して Vercel の自動デプロイで反映する。
- 大規模リファクタや破壊的変更（DB drop、既存 API 削除、ロールバック困難な変更）のときのみ feature ブランチを切る。
- ブランチ名: `feat/<概要>`, `fix/<概要>`, `chore/<概要>` 等。

### 8.2 PR
- PR 作成は **ユーザーが明示的に指示した場合のみ** 行う。
- PR 本文には変更の要約と動作確認手順を含める。

### 8.3 テスト
- 既存のテストを壊さないこと。
- 新規機能には最低限ハッピーパスのテストを追加する（ツール側の方針に従う）。

---

## 9. よく使うドメイン用語（日本語ビジネス文脈）

| 用語 | 意味・備考 |
|------|-----------|
| 顧客 / クライアント | 原則「顧客」で統一 |
| ユーザー | アプリを操作する人 |
| 管理者 / 運営 | システム運営側 |
| 案件 / プロジェクト | 文脈により使い分け（ツール側で定義） |

---

## 10. この共通ルールの更新

- このファイル（`kaz-claude-config/CLAUDE.md`）を更新する際は、影響範囲が全ツールに及ぶことを意識する。
- 大きな変更を加える場合はパイロット1リポジトリで検証してから全体に展開する。
- 変更履歴はコミットログで追跡する（別途 CHANGELOG は作らない）。

---

## Shared Skills

以下の統合Skillsが利用可能です。Claude Codeは各Skillの内容を自動参照します。

@.claude/skills/ai-llm-integration.md
@.claude/skills/api-route-patterns.md
@.claude/skills/auth-complete-flow.md
@.claude/skills/billing-stripe-integration.md
@.claude/skills/general-best-practices.md
@.claude/skills/database-migration-pattern.md
@.claude/skills/devops-deploy-checklist.md
@.claude/skills/ui-component-patterns.md
@.claude/skills/security-best-practices.md
