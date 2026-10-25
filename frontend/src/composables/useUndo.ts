import { reactive } from 'vue';

/** One global undo toast: act immediately, offer to take it back for a few seconds (no confirmation dialogs). */
export const undoState = reactive<{ message: string; action: (() => void | Promise<void>) | null; label: string; timer: number | null }>({
  message: '', action: null, label: '', timer: null,
});

export function showUndo(message: string, label: string, action: () => void | Promise<void>, ms = 6000) {
  if (undoState.timer) clearTimeout(undoState.timer);
  undoState.message = message; undoState.label = label; undoState.action = action;
  undoState.timer = window.setTimeout(dismissUndo, ms);
}
export function dismissUndo() {
  if (undoState.timer) clearTimeout(undoState.timer);
  undoState.timer = null; undoState.action = null; undoState.message = '';
}
export async function runUndo() {
  const a = undoState.action;
  dismissUndo();
  if (a) await a();
}
