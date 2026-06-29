// Render the server's verdict VERBATIM — never recompute pass/fail on the client.
// The Slice-6b verifier (server.py:110-114) already folded the code-owned verdict into
// runtime.status (FAIL->blocked, PASS->done). The client reads {verdict, runtime.status};
// it does NOT re-run done_when. Critically: a verdict of "unverified" (no done_when authored)
// renders NEUTRAL — never a faked green pass.

export interface GraphNode {
  id: string;
  goal: string;
  mu: number;
  verdict: "PASS" | "FAIL" | "pending" | "unverified" | string;
  done_when: unknown[];
  depends_on: string[];
  children: string[];
  runtime: { status: string; agent?: string | null };
}

export interface NodeVisual {
  cls: "done" | "blocked" | "active" | "decomposed" | "pending" | "unverified";
  label: string;
}

export function nodeVisual(n: Pick<GraphNode, "verdict" | "runtime">): NodeVisual {
  const verdict = n.verdict;
  const status = n.runtime?.status ?? "pending";

  // code-owned overrides first (server already folded these into status, we honor both)
  if (verdict === "FAIL" || status === "blocked") return { cls: "blocked", label: "blocked" };
  if (verdict === "PASS") return { cls: "done", label: "passed" };
  // honest: a node with no authored gate is unverified, never faked-pass — even if the model said done
  if (verdict === "unverified") return { cls: "unverified", label: "unverified" };

  switch (status) {
    case "done":
      return { cls: "done", label: "done" };
    case "active":
      return { cls: "active", label: "running" };
    case "decomposed":
      return { cls: "decomposed", label: "decomposed" };
    default:
      return { cls: "pending", label: status };
  }
}
