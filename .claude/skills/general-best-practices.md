---
category: other
sourceSkillIds:
  - 544d5768
  - 4c20b5c7
  - b8b6e2c7
  - af1353e3
  - 9805f577
  - e679a935
  - a0cd9eec
  - 79dd4189
  - 528ae376
  - af5835a8
  - b65d7e1f
  - 5c2b73a0
  - b32c6c80
  - 833f68c8
  - 68c72247
  - c0d09ec0
  - 4537f343
  - 9b072ef4
  - 350b3fe4
  - 6d68ad95
  - cd3cafd4
  - b6bf62e3
  - 3acf4ab3
  - 11134f28
  - 9db6a344
  - b2127f6a
  - a6958a08
  - 0707f500
generatedAt: '2026-06-22'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-06-21T02:36:25Z'
adoptedFromArchive:
  - archive/skills/remove-placeholder.md
  - archive/skills/general-best-practices.md
  - archive/skills/08-destructive-action-ux.md
  - archive/skills/15-planning-with-todos.md
  - archive/skills/16-restore-point-tags.md
  - archive/skills/19-rls-organization-isolation.md
  - archive/skills/26-phased-table-deprecation.md
  - archive/skills/33-decision-locked-plans.md
  - archive/skills/36-exploratory-question-handling.md
  - archive/skills/37-rollback-runbook.md
---
```markdown
---
name: general-best-practices
description: Next.js/TypeScriptプロジェクト全般に適用できるベストプラクティス集。破壊的操作のUX・進捗トラッキング・スナップショット運用・RLSポリシー・テーブル段階的廃止・意思決定ログ・探索的相談への返し方・ロールバック計画・プレースホルダー排除の汎用パターンを網羅。
category: other
---

# General Best Practices — Next.js / TypeScript

> 複数プロジェクトから抽出した「どのプロジェクトでも成立する」原則集。
> コードテンプレートは最小限に留め、原則と判断基準を優先して記述する。

---

## 目次

1. [破壊的操作のUX](#1-破壊的操作のux)
2. [TodoWriteを使った進捗トラッキング](#2-todowriteを使った進捗トラッキング)
3. [Gitスナップショット運用](#3-gitスナップショット運用)
4. [組織境界のRLSポリシー](#4-組織境界のrlsポリシー)
5. [テーブルの段階的廃止](#5-テーブルの段階的廃止)
6. [意思決定ログ付きプラン](#6-意思決定ログ付きプラン)
7. [探索的な問いへの返し方](#7-探索的な問いへの返し方)
8. [ロールバック手順を最初から書く](#8-ロールバック手順を最初から書く)
9. [意味のない画面の排除](#9-意味のない画面の排除)

---

## 1. 破壊的操作のUX

### 原則

| # | ルール | 理由 |
|---|--------|------|
| 1 | **取消不能であることを明示する** | 「削除します」だけでは重大度が伝わらない |
| 2 | **件数を必ず表示する** | `${count} 件を削除します` — 0件・1件でも崩れない文言にする |
| 3 | **進行中はボタンを無効化＋表示変更** | 再クリックで二重実行を防ぐ |
| 4 | **成功後はサーバーから再取得** | 楽観的削除は整合性ズレがdevtoolsでしか分からなくなる |
| 5 | **失敗時はalertに「なぜ」を出す** | `alert(\`削除に失敗しました: ${json.error ?? res.status}\`)` |

### 最小テンプレート

```ts
const [deleting, setDeleting] = useState(false);

async function handleDelete() {
  if (!confirm(`${count} 件を削除します。この操作は取り消せません。`)) return;
  setDeleting(true);
  try {
    const res = await fetch('/api/items', { method: 'DELETE', body: JSON.stringify({ ids }) });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error ?? String(res.status));
    await refetch(); // サーバーから再取得
  } catch (e) {
    alert(`削除に失敗しました: ${e instanceof Error ? e.message : e}`);
  } finally {
    setDeleting(false);
  }
}

<button onClick={handleDelete} disabled={deleting}>
  {deleting ? '削除中…' : `${count} 件を削除`}
</button>
```

---

## 2. TodoWriteを使った進捗トラッキング

### 使うべき条件

- 3ステップ以上のタスク
- 並列に見える作業を順序付けて実施したい
- ユーザーが複数の依頼を同時に出した
- セッション中に新しいタスクが発見された

> 1〜2ステップで完結するなら **使わない**（表示のノイズになる）。

### Todoの書き方

```
content:    "Add DELETE endpoint to /api/admin/sales for bulk delete"
activeForm: "Adding DELETE endpoint for bulk delete"
status:     pending | in_progress | completed
```

- `content` は命令形、`activeForm` は進行形／現在分詞
- 粒度は「1コミットで完結する単位」を目安にする
- 完了したタスクは速やかに `completed` にして視認性を保つ

---

## 3. Gitスナップショット運用

### 目的

1セッションで多くの変更を重ねた後「この時点に戻りたい」が発生しやすい。
`reflog` だけに頼らず、**明示的な復元点**を残す。

### 手順

```bash
# 意味のある区切り（機能実装完了・デプロイ直前など）でannotated tagを付ける
git tag -a snapshot/2026-04-20-bulk-delete-sales \
  -m "Restore point: sales bulk delete (page + filter-wide) implemented"

# リモートへpush（可能なら）
git push origin snapshot/2026-04-20-bulk-delete-sales
```

### 命名規則

```
snapshot/YYYY-MM-DD-<kebab-case-feature-description>
```

### 復元方法

```bash
# 内容確認
git show snapshot/2026-04-20-bulk-delete-sales

# そのコミットに戻す（新しいブランチを切ってから）
git checkout -b restore/bulk-delete-sales snapshot/2026-04-20-bulk-delete-sales
```

---

## 4. 組織境界のRLSポリシー

### ポリシーは4種に分けて書く

| 種別 | 例 |
|------|----|
| Self-read | 自分の所属組織だけ見える |
| Self-write | 自分の所属組織なら更新できる |
| Admin-read | ロール `admin` なら全件見える |
| Admin-write | ロール `admin` なら更新／削除できる |

各テーブルは2〜4ポリシーを持つ。
**ポリシー名に意図を書く**: `orders_select_own_org`, `orders_update_admin_only`
→ RLSが起因のバグは追いにくいため、名前から即座に判断できるようにする。

### 自組織を取り出す共通サブクエリ

```sql
-- 自組織IDを返すヘルパサブクエリ（各ポリシーで再利用）
(
  SELECT organization_id
  FROM users
  WHERE id = auth.uid()
)
```

### RLSポリシーテンプレート

```sql
-- Self-read
CREATE POLICY "orders_select_own_org" ON orders
  FOR SELECT USING (
    organization_id = (SELECT organization_id FROM users WHERE id = auth.uid())
  );

-- Admin-write
CREATE POLICY "orders_update_admin_only" ON orders
  FOR UPDATE USING (
    EXISTS (SELECT 1
