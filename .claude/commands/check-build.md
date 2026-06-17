# check-build

lint と型チェックを実行してエラーをすべて修正する。

## 手順

1. ESLint を実行:
   ```bash
   npx next lint 2>&1
   ```

2. TypeScript 型チェックを実行:
   ```bash
   npx next build --no-lint 2>&1 | head -100
   ```
   （`tsc --noEmit` は `next-env.d.ts` がないと誤検知しやすいため next build を優先）

3. エラーが出た場合、以下の優先順位で修正:

   **ESLint エラーの典型パターン**:
   - `no-unused-vars`: 未使用のインポートや変数を削除
   - `@typescript-eslint/no-explicit-any`: `any` を適切な型に変更
   - `react-hooks/exhaustive-deps`: useEffect の依存配列を修正

   **TypeScript エラーの典型パターン**:
   - `Property 'xxx' does not exist on type '{}'`:
     → `useActionState` の初期値に明示的な型を追加
     ```typescript
     const initialState: { error?: string; data?: SomeType } = {};
     ```
   - `Type 'string | null' is not assignable to type 'string'`:
     → null チェックを追加か `?? ""` でフォールバック
   - `Cannot find module '@/...'`:
     → `tsconfig.json` の paths 設定を確認

4. 修正後、再度 lint と build を実行してクリーンであることを確認

5. クリーンになったら変更をコミット:
   ```bash
   git add -A && git commit -m "fix(lint): resolve build errors"
   ```
