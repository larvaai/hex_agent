/**
 * Prompt box — inject a prompt as a SubmitPrompt command. Epic E21 (S21.15).
 *
 * Send posts a real RuntimeCommand through the adapter and surfaces the synchronous CommandAck
 * (command_id + status). The applied/accepted outcome arrives later as a command.* event on the
 * stream (rendered by the Timeline) — the box never edits runtime state directly.
 */
import { useState } from "react";

import { postCommand } from "../adapter/controlPlane";
import type { CommandAck } from "../contracts/generated";
import { submitPrompt } from "../lib/commands";

export function PromptBox() {
  const [text, setText] = useState("");
  const [ack, setAck] = useState<CommandAck | null>(null);
  const [busy, setBusy] = useState(false);

  const send = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const result = await postCommand(submitPrompt(text));
      setAck(result);
      setText("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cp-prompt" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <textarea
        aria-label="prompt"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Inject a prompt for the orchestrator…"
        rows={3}
        style={{ background: "#0b1620", color: "#c9d6df", border: "1px solid #1e3343", borderRadius: 6, padding: 6 }}
      />
      <div>
        <button onClick={send} disabled={busy}>
          Send
        </button>
      </div>
      {ack && (
        <div className="cp-ack" role="status" style={{ fontSize: 12, color: "#93a1a1" }}>
          ack <code>{ack.command_id}</code>: {ack.status}
          {ack.rejection_reason ? ` — ${ack.rejection_reason}` : ""}
        </div>
      )}
    </div>
  );
}
