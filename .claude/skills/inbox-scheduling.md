---
name: inbox-scheduling
description: >-
  メール返信時にカレンダーから空き枠をクリック／ドラッグして候補日を本文に 自動挿入し、必要なら外部カレンダー（Google Calendar 等）に
  tentative（仮押さえ） として書き込む日程調整機能の完全実装ガイド。 Picker UI・cursor-aware
  insert・設定永続化・学習ループ分離・衝突警告・ テレメトリ・仮押さえ・optimistic UI・デバッグ診断まで網羅。
category: inbox-scheduling
version: 2
effectiveTimestamp: '2026-05-19T00:00:00.000Z'
sourceSkillIds:
  - 026db7c2
  - 305f0d56
generatedAt: '2026-05-20'
---

# inbox-scheduling — メール返信 × カレンダー日程調整 完全ガイド

## 0. 全体アーキテクチャ

```
ReplyEditor (textarea / rich-text)
  └─ <SchedulingPickerTrigger>     ← ボタン or ショートカット
       └─ <CalendarSlotPicker>     ← Popover / モーダル
            ├─ 月/週ビュー (クリック & ドラッグ選択)
            ├─ 空き判定ロジック (freebusy API)
            ├─ 衝突警告バナー
            └─ [挿入] ボタン
                 ├─ cursor-aware insert → textarea
                 └─ (オプション) tentative 書き込み → Calendar API
```

**データフロー**

```
useCalendarSlots (SWR/React Query)
  └─ GET /api/calendar/freebusy
       └─ Google Calendar API (または汎用 CalendarProvider)

useSchedulingPrefs (Zustand / localStorage)
  └─ 設定永続化: duration / buffer / format / timezone

useSlotInsert
  └─ cursor 位置検出 → テキスト組み立て → textarea 更新

useTentativeBooking
  └─ POST /api/calendar/events  { status: "tentative" }
       └─ optimistic UI (SWR mutate / TanStack Query setQueryData)
```

---

## 1. Picker UI — `<CalendarSlotPicker>`

### 1-1. コンポーネント骨格

```tsx
// components/scheduling/CalendarSlotPicker.tsx
"use client";

import { useState, useCallback } from "react";
import { format, addMinutes, isBefore } from "date-fns";
import { useCalendarSlots } from "@/hooks/useCalendarSlots";
import { useSchedulingPrefs } from "@/hooks/useSchedulingPrefs";
import { SlotGrid } from "./SlotGrid";
import { ConflictWarning } from "./ConflictWarning";
import type { TimeSlot } from "@/types/scheduling";

interface CalendarSlotPickerProps {
  /** 挿入先 textarea の ref */
  targetRef: React.RefObject<HTMLTextAreaElement>;
  /** Picker を閉じるコールバック */
  onClose: () => void;
  /** 選択確定コールバック（外部で tentative 書き込み等を行う場合） */
  onConfirm?: (slots: TimeSlot[]) => void;
}

export function CalendarSlotPicker({
  targetRef,
  onClose,
  onConfirm,
}: CalendarSlotPickerProps) {
  const { prefs } = useSchedulingPrefs();
  const [selected, setSelected] = useState<TimeSlot[]>([]);
  const [viewDate, setViewDate] = useState(new Date());

  const { slots, isLoading, conflicts } = useCalendarSlots({
    viewDate,
    duration: prefs.duration,
    buffer: prefs.buffer,
  });

  const handleSelect = useCallback(
    (slot: TimeSlot) => {
      setSelected((prev) => {
        const exists = prev.some((s) => s.start === slot.start);
        return exists
          ? prev.filter((s) => s.start !== slot.start)
          : [...prev, slot].sort((a, b) =>
              isBefore(new Date(a.start), new Date(b.start)) ? -1 : 1
            );
      });
    },
    []
  );

  const handleInsert = useCallback(() => {
    if (selected.length === 0) return;
    insertSlotsAtCursor(targetRef, selected, prefs.format, prefs.timezone);
    onConfirm?.(selected);
    onClose();
  }, [selected, targetRef, prefs, onConfirm, onClose]);

  return (
    <div className="w-[480px] rounded-xl border bg-white shadow-xl p-4 space-y-3">
      <ConflictWarning conflicts={conflicts} />
      <SlotGrid
        slots={slots}
        selected={selected}
        isLoading={isLoading}
        viewDate={viewDate}
        onViewChange={setViewDate}
        onSelect={handleSelect}
      />
      <div className="flex justify-between items-center pt-2">
        <span className="text-sm text-gray-500">
          {selected.length} 件選択
        </span>
        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm rounded-lg border hover:bg-gray-50"
          >
            キャンセル
          </button>
          <button
            disabled={selected.length === 0}
            onClick={handleInsert}
            className="px-3 py-1.5 text-sm rounded-lg bg-blue-600 text-white
                       disabled:opacity-40 hover:bg-blue-700"
          >
            本文に挿入
          </button>
        </div>
      </div>
    </div>
  );
}
```

### 1-2. ドラッグ選択対応 `<SlotGrid>`

```tsx
// components/scheduling/SlotGrid.tsx
"use client";

import { useRef, useCallback } from "react";
import type { TimeSlot } from "@/types/scheduling";

interface SlotGridProps {
  slots: TimeSlot[];
  selected: TimeSlot[];
  isLoading: boolean;
  viewDate: Date;
  onViewChange: (d: Date) => void;
  onSelect: (slot: TimeSlot) => void;
}

export function SlotGrid({
  slots, selected, isLoading, viewDate, onViewChange, onSelect,
}: SlotGridProps) {
  const dragging = useRef(false);
  const dragStart = useRef<TimeSlot | null>(null);

  const handleMouseDown = useCallback((slot: TimeSlot) => {
    dragging.current = true;
    dragStart.current = slot;
    onSelect(slot);
  }, [onSelect]);

  const handleMouseEnter = useCallback((slot: TimeSlot) => {
    if (dragging.current) onSelect(slot);
  }, [onSelect]);

  const stopDrag = useCallback(() => {
    dragging.current = false;
    dragStart.current = null;
  }, []);

  if (isLoading) {
    return (
      <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
        空き枠を取得中…
      </div>
    );
  }

  return (
    <div
      className
