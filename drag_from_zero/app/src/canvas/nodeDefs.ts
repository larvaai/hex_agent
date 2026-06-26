import type { NodeType } from "../topology/serialize";

// Palette: the 5 topology node types, each with the minimal default attrs that pass
// Topology.validate + build_runtime against the builtin catalogs (tools_fs / BUILTIN_RULES /
// BUILTIN_HOOKS). The required attr is editable on the node; everything else is sensible default.
export interface PaletteItem {
  type: NodeType;
  label: string;
  reqAttr: string; // the attr the user edits inline ("" = none)
  defaults: Record<string, unknown>;
}

export const PALETTE: PaletteItem[] = [
  { type: "agent", label: "Agent", reqAttr: "role", defaults: { role: "coder" } },
  { type: "tool", label: "Tool", reqAttr: "tool", defaults: { tool: "write_file" } },
  { type: "router", label: "Router", reqAttr: "rule", defaults: { rule: "by_keyword", config: { keyword: "deploy", role: "devops" } } },
  { type: "memory", label: "Memory", reqAttr: "", defaults: { name: "scratch" } },
  { type: "hook", label: "Hook", reqAttr: "hook", defaults: { hook: "deny_delegation", phase: "pre_delegate" } },
];

export const DND_MIME = "application/dragzero-node";
