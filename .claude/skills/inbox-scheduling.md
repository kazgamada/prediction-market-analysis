---
name: inbox-scheduling
description: >-
  メール返信時にカレンダーから空き枠をクリック／ドラッグして候補日を本文に 自動挿入し、必要なら外部カレンダー（Google Calendar等）に
  tentative（仮押さえ） として書き込む日程調整機能の完全実装ガイド。 Picker UI・cursor-aware
  insert・設定永続化・学習ループ分離・衝突警告・ テレメトリ・仮押さえ・optimistic UI・デバッグ診断まで網羅。
category: inbox-scheduling
version: 1
effectiveTimestamp: '2026-05-12T16:00:00.000Z'
sourceSkillIds:
  - 026db7c2
generatedAt: '2026-05-19'
---

# inbox-scheduling — メール返信 × カレンダー日程調整

## 概要

メール返信フロー内でカレンダーUIを開き、空き枠をクリック／ドラッグして
候補日時を本文に自動挿入する機能群。外部カレンダーへの仮押さえ書き込みも含む。

```
[メール返信エディタ]
       ↓ 「日程候補を挿入」ボタン
[CalendarPicker オーバーレイ]
  ├─ 空き枠クリック → candidateSlots[] に追加
  ├─ ドラッグ選択 → 範囲をスロットに変換
  └─ 「挿入」ボタン → cursor位置に候補日テキスト挿入
       ↓ オプション
[Google Calendar API] → tentative イベント作成
```

---

## 1. ディレクトリ構造

```
src/
├── components/scheduling/
│   ├── CalendarPicker.tsx          # メインUI
│   ├── CalendarPickerHeader.tsx    # 月ナビ・表示切替
│   ├── CalendarPickerGrid.tsx      # 時間グリッド
│   ├── SlotChip.tsx                # 選択済みスロット表示
│   └── ConflictBadge.tsx           # 衝突警告バッジ
├── hooks/
│   ├── useCalendarPicker.ts        # ピッカーUI状態管理
│   ├── useSlotSelection.ts         # スロット選択ロジック
│   ├── useCursorInsert.ts          # カーソル位置挿入
│   ├── usePickerSettings.ts        # 設定永続化
│   └── useSchedulingTelemetry.ts   # テレメトリ
├── lib/scheduling/
│   ├── slotFormatter.ts            # 候補日テキスト生成
│   ├── conflictDetector.ts         # 衝突検出
│   ├── tentativeWriter.ts          # 仮押さえAPI呼び出し
│   └── learningLoop.ts             # 学習ループ（分離）
├── stores/
│   └── schedulingStore.ts          # Zustand グローバル状態
└── types/scheduling.ts             # 型定義
```

---

## 2. 型定義

```typescript
// types/scheduling.ts

export interface TimeSlot {
  id: string;
  start: Date;
  end: Date;
  durationMinutes: number;
  isBusy: boolean;
  tentativeEventId?: string;
}

export interface CandidateSlot extends TimeSlot {
  selected: boolean;
  conflictLevel: 'none' | 'soft' | 'hard';
  label: string; // フォーマット済みテキスト
}

export interface PickerSettings {
  defaultDurationMinutes: number;   // デフォルト: 30
  workHoursStart: number;           // 0-23, デフォルト: 9
  workHoursEnd: number;             // 0-23, デフォルト: 18
  timezone: string;                 // IANA timezone
  locale: string;
  autoTentative: boolean;           // 選択時に自動仮押さえ
  maxCandidates: number;            // デフォルト: 3
  insertFormat: 'bullet' | 'table' | 'natural';
}

export interface SchedulingSession {
  sessionId: string;
  emailThreadId: string;
  candidateSlots: CandidateSlot[];
  insertedAt?: Date;
  confirmedSlot?: TimeSlot;
}

export interface CalendarPickerProps {
  threadId: string;
  editorRef: React.RefObject<HTMLElement>;
  onInsert: (text: string, slots: CandidateSlot[]) => void;
  onClose: () => void;
  existingEvents?: TimeSlot[];
}
```

---

## 3. 状態管理 (Zustand)

```typescript
// stores/schedulingStore.ts
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { CandidateSlot, PickerSettings, SchedulingSession } from '@/types/scheduling';

interface SchedulingState {
  isPickerOpen: boolean;
  session: SchedulingSession | null;
  settings: PickerSettings;
  // actions
  openPicker: (threadId: string) => void;
  closePicker: () => void;
  addSlot: (slot: CandidateSlot) => void;
  removeSlot: (slotId: string) => void;
  clearSlots: () => void;
  updateSettings: (patch: Partial<PickerSettings>) => void;
}

const DEFAULT_SETTINGS: PickerSettings = {
  defaultDurationMinutes: 30,
  workHoursStart: 9,
  workHoursEnd: 18,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  locale: navigator?.language ?? 'ja-JP',
  autoTentative: false,
  maxCandidates: 3,
  insertFormat: 'bullet',
};

export const useSchedulingStore = create<SchedulingState>()(
  immer((set) => ({
    isPickerOpen: false,
    session: null,
    settings: DEFAULT_SETTINGS,

    openPicker: (threadId) =>
      set((s) => {
        s.isPickerOpen = true;
        s.session = {
          sessionId: crypto.randomUUID(),
          emailThreadId: threadId,
          candidateSlots: [],
        };
      }),

    closePicker: () =>
      set((s) => {
        s.isPickerOpen = false;
        // session は意図的に保持（挿入後の参照用）
      }),

    addSlot: (slot) =>
      set((s) => {
        if (!s.session) return;
        const already = s.session.candidateSlots.some((c) => c.id === slot.id);
        if (!already && s.session.candidateSlots.length < s.settings.maxCandidates) {
          s.session.candidateSlots.push(slot);
        }
      }),

    removeSlot: (slotId) =>
      set((s) => {
        if (!s.session) return;
        s.session.candidateSlots = s.session.candidateSlots.filter(
          (c) => c.id !== slotId
        );
      }),

    clearSlots: () =>
      set((s) => {
        if (s.session) s.session.candidate
