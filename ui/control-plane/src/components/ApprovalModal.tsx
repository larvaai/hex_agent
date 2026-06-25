// STUB (Phase 4) — replaced in Phase 6 by the Approval modal (S21.21).
import { useCPState } from "../state/store";

export function ApprovalModal() {
  const { snapshot } = useCPState();
  const waiting = (snapshot?.checkpoints ?? []).filter((c) => (c as { status?: string }).status === "waiting");
  if (waiting.length === 0) return null;
  return (
    <div role="dialog" aria-label="approval" className="cp-modal">
      {waiting.length} checkpoint(s) waiting
    </div>
  );
}
