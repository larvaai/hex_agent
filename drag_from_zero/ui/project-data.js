// Fake but realistic project: "taskflow" — a task app with an agent-built auth feature.
export const PROJECT = {
  name: "taskflow",
  branch: "feat/auth-orchestrated",
  tree: [
    { type: "folder", name: "src", path: "src", children: [
      { type: "folder", name: "auth", path: "src/auth", children: [
        { type: "file", name: "session.ts", path: "src/auth/session.ts", lang: "ts" },
        { type: "file", name: "tokens.ts", path: "src/auth/tokens.ts", lang: "ts" },
      ]},
      { type: "folder", name: "api", path: "src/api", children: [
        { type: "file", name: "client.ts", path: "src/api/client.ts", lang: "ts" },
      ]},
      { type: "folder", name: "components", path: "src/components", children: [
        { type: "file", name: "LoginForm.tsx", path: "src/components/LoginForm.tsx", lang: "tsx" },
      ]},
      { type: "file", name: "app.ts", path: "src/app.ts", lang: "ts" },
    ]},
    { type: "folder", name: "tests", path: "tests", children: [
      { type: "file", name: "auth.test.ts", path: "tests/auth.test.ts", lang: "ts" },
    ]},
    { type: "file", name: "langgraph.config.ts", path: "langgraph.config.ts", lang: "ts" },
    { type: "file", name: "package.json", path: "package.json", lang: "json" },
    { type: "file", name: "README.md", path: "README.md", lang: "md" },
  ],
  files: {
    "src/auth/session.ts": `import { signToken, verifyToken } from "./tokens";
import type { ApiClient } from "../api/client";

export interface Session {
  userId: string;
  expiresAt: number;
}

// Create a 24h session for a verified user.
export async function createSession(
  api: ApiClient,
  email: string,
  password: string,
): Promise<Session> {
  const user = await api.post("/login", { email, password });
  if (!user.ok) throw new Error("invalid credentials");

  const expiresAt = Date.now() + 24 * 60 * 60 * 1000;
  const token = signToken({ sub: user.id, exp: expiresAt });
  localStorage.setItem("tf.session", token);
  return { userId: user.id, expiresAt };
}

export function readSession(): Session | null {
  const token = localStorage.getItem("tf.session");
  if (!token) return null;
  const claims = verifyToken(token);
  return claims ? { userId: claims.sub, expiresAt: claims.exp } : null;
}`,
    "src/auth/tokens.ts": `const SECRET = import.meta.env.TF_SECRET ?? "dev-secret";

interface Claims {
  sub: string;
  exp: number;
}

// Minimal HS256-style token. Replace with a vetted lib in prod.
export function signToken(claims: Claims): string {
  const body = btoa(JSON.stringify(claims));
  const sig = btoa(SECRET + body).slice(0, 24);
  return body + "." + sig;
}

export function verifyToken(token: string): Claims | null {
  const [body, sig] = token.split(".");
  if (!body || !sig) return null;
  const expected = btoa(SECRET + body).slice(0, 24);
  if (sig !== expected) return null;
  const claims = JSON.parse(atob(body)) as Claims;
  if (claims.exp < Date.now()) return null;
  return claims;
}`,
    "src/api/client.ts": `export interface ApiClient {
  post(path: string, body: unknown): Promise<any>;
  get(path: string): Promise<any>;
}

const BASE = "/api/v1";

export function createClient(): ApiClient {
  async function request(method: string, path: string, body?: unknown) {
    const res = await fetch(BASE + path, {
      method,
      headers: { "content-type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    return res.json();
  }
  return {
    post: (path, body) => request("POST", path, body),
    get: (path) => request("GET", path),
  };
}`,
    "src/components/LoginForm.tsx": `import { useState } from "react";
import { createSession } from "../auth/session";
import { createClient } from "../api/client";

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await createSession(createClient(), email, password);
      location.assign("/board");
    } catch (err) {
      setError("Could not sign you in.");
    }
  }

  return (
    <form onSubmit={onSubmit} className="login">
      <input value={email} onChange={(e) => setEmail(e.target.value)} />
      <input type="password" value={password}
        onChange={(e) => setPassword(e.target.value)} />
      {error && <p className="err">{error}</p>}
      <button type="submit">Sign in</button>
    </form>
  );
}`,
    "src/app.ts": `import { readSession } from "./auth/session";

const session = readSession();
if (!session) {
  location.assign("/login");
} else {
  console.log("welcome back", session.userId);
}`,
    "tests/auth.test.ts": `import { describe, it, expect } from "vitest";
import { signToken, verifyToken } from "../src/auth/tokens";

describe("tokens", () => {
  it("round-trips a valid claim", () => {
    const exp = Date.now() + 1000;
    const token = signToken({ sub: "u_42", exp });
    const claims = verifyToken(token);
    expect(claims?.sub).toBe("u_42");
  });

  it("rejects an expired token", () => {
    const token = signToken({ sub: "u_42", exp: Date.now() - 1 });
    expect(verifyToken(token)).toBeNull();
  });
});`,
    "langgraph.config.ts": `import { StateGraph } from "@langgraph/core";

// The orchestrator delegates the auth feature across sub-agents.
export const graph = new StateGraph({ channels: ["spec", "code", "review"] })
  .addNode("orchestrator", { role: "router" })
  .addNode("planner", { skills: ["spec", "decompose"] })
  .addNode("coder", { skills: ["typescript", "api"], hooks: ["pre-commit"] })
  .addNode("reviewer", { rules: ["no-any", "tests-required"] })
  .addNode("tester", { skills: ["vitest"], hooks: ["post-run"] })
  .addEdge("orchestrator", "planner")
  .addEdge("planner", "coder")
  .addEdge("coder", "reviewer")
  .addEdge("reviewer", "tester")
  .addEdge("tester", "orchestrator")
  .compile();`,
    "package.json": `{
  "name": "taskflow",
  "version": "0.4.1",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.0",
    "@langgraph/core": "^0.2.7"
  }
}`,
    "README.md": `# taskflow

A small task board. The auth module in this branch was
implemented by an orchestrated team of agents (see
langgraph.config.ts).

## Run
- npm run dev — start the dev server
- npm run test — run the auth test suite`,
  },
};

// The orchestrated team that built the auth module. Positions are laid out
// on an 860x540 canvas: O is the root, the workers sit in a row beneath it.
export const AGENTS = [
  {
    id: "orchestrator", name: "O", role: "Orchestrator", letter: "O",
    color: "#5b9dff", x: 280, y: 14,
    summary: "Routes the request, delegates each phase to a specialist, then closes the loop with a final review + test pass before reporting done.",
    prompt: "You are O, the orchestrator. Decompose the request into a LangGraph and delegate each node to the right specialist. Always finish with a review and a green test run before you report done.",
    skills: ["route", "delegate", "summarize"],
    hooks: ["on_request", "on_complete"],
    rules: ["always end with a review", "never merge red tests"],
    loads: ["task.md", "langgraph.config.ts"],
  },
  {
    id: "planner", name: "Planner", role: "Spec & decomposition", letter: "P",
    color: "#c792ea", x: 16, y: 134,
    summary: "Turns the task into an ordered plan of small, single-module steps and writes it out as plan.json for the Coder.",
    prompt: "Break the task into at most 6 ordered subtasks, each touching one module. Emit plan.json with an owner per step.",
    skills: ["spec", "decompose"],
    hooks: ["pre_plan"],
    rules: ["max 6 steps", "one module per step"],
    loads: ["task.md", "plan.json"],
  },
  {
    id: "coder", name: "Coder", role: "Implementation", letter: "C",
    color: "#4ec9a3", x: 280, y: 134,
    summary: "Implements each step with minimal, style-matching diffs and runs the pre-commit hook before handing off.",
    prompt: "Implement plan.json with minimal diffs that match the existing style. Run the pre-commit hook before you hand the diff to review.",
    skills: ["typescript", "api"],
    hooks: ["pre-commit"],
    rules: ["no-any", "keep diffs minimal"],
    loads: ["plan.json", "session.ts", "tokens.ts"],
  },
  {
    id: "reviewer", name: "Reviewer", role: "Code review", letter: "R",
    color: "#e0a04a", x: 544, y: 134,
    summary: "Checks the diff against the rule set and either blocks with notes (back to Coder) or approves and forwards to the Tester.",
    prompt: "Review the diff. Enforce every rule; block on any violation and hand back to Coder, otherwise approve and forward to Tester.",
    skills: ["static-analysis"],
    hooks: ["pre_merge"],
    rules: ["no-any", "tests-required", "no secrets in source"],
    loads: ["session.ts", "review.md"],
  },
  {
    id: "tester", name: "Tester", role: "Verification", letter: "T",
    color: "#5fc77e", x: 280, y: 254,
    summary: "Writes and runs the suite, fails the run closed on any regression, and reports coverage back to O.",
    prompt: "Write or extend tests for the change and run vitest. Fail closed on any regression and report coverage in report.md.",
    skills: ["vitest"],
    hooks: ["post-run"],
    rules: ["tests-required", "fail closed"],
    loads: ["auth.test.ts", "report.md"],
  },
];

// Agent-generated artifacts that aren't part of the repo tree but flow between
// nodes — openable from the file-chips on the graph edges.
export const VIRTUAL = {
  "task.md": `# Task

Implement an auth module (login + session) for taskflow.
- 24h sessions backed by signed tokens
- a LoginForm component that calls it
- unit tests for token sign / verify

Delegated by: O (orchestrator)`,
  "plan.json": `{
  "owner": "coder",
  "steps": [
    { "id": 1, "module": "auth/tokens",  "do": "sign + verify HS256-style tokens" },
    { "id": 2, "module": "auth/session", "do": "createSession + readSession (24h)" },
    { "id": 3, "module": "components",   "do": "LoginForm calls createSession" }
  ]
}`,
  "review.md": `# Review — auth module

- [x] no-any            — clean
- [x] tests-required    — tokens covered (2 cases)
- [ ] suggestion        — session.ts: prefer crypto.subtle over btoa for prod

Verdict: approve with 1 note → forward to Tester.`,
  "report.md": `# Test report

$ vitest run
  ✓ tokens > round-trips a valid claim   (3 ms)
  ✓ tokens > rejects an expired token    (1 ms)

  2 passed (0.41s)
  coverage: 86% statements / 80% branches`,
};
