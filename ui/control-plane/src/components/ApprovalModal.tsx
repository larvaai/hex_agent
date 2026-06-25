/**
 * Approval modal — a waiting checkpoint turns into Approve/Reject commands. Epic E21 (S21.21).
 *
 * Clicking Approve/Reject posts a real RuntimeCommand through the adapter and stops there: the UI
 * does NOT optimistically resolve the checkpoint. It stays open until the runtime publishes the
 * resolving event and the snapshot updates — the "UI never mutates state directly" invariant.
 */
import { postCommand } from "../adapter/controlPlane";
import { approveCheckpoint, rejectCheckpoint } from "../lib/commands";
import { useCPState } from "../state/store";

export function ApprovalModal() {
  const { snapshot } = useCPState();
  const waiting = (snapshot?.checkpoints ?? []).filter((c) => (c as { status?: string }).status === "waiting");
  if (waiting.length === 0) return null;

  const cp = waiting[0] as Record<string, unknown>;
  const checkpointId = String(cp.checkpoint_id ?? "");

  return (
    <div role="dialog" aria-label="approval" className="cp-modal" style={modalStyle}>
      <h3 style={{ marginTop: 0 }}>Checkpoint waiting</h3>
      <div>type: {String(cp.checkpoint_type ?? "—")}</div>
      <div>risk: {String(cp.risk_level ?? "—")}</div>
      <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
        <button onClick={() => postCommand(approveCheckpoint(checkpointId))}>Approve</button>
        <button onClick={() => postCommand(rejectCheckpoint(checkpointId))}>Reject</button>
      </div>
    </div>
  );
}

const modalStyle: React.CSSProperties = {
  position: "fixed",
  right: 20,
  bottom: 20,
  background: "#11212e",
  border: "1px solid #cb4b16",
  borderRadius: 8,
  padding: 14,
  minWidth: 240,
  boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
};
