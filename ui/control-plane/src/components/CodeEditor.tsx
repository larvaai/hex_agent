/**
 * Code Editor — CodeMirror 6 with open-file tabs, dirty tracking, and Cmd/Ctrl+S save. Epic E21 / IDE.
 *
 * This is the "edit the file" half of the IDE. The agent writes through its fs tools; the user writes
 * here — both land in the same workspace, and the diff panel reconciles who changed what. The editor
 * is a controlled component bound to the active tab in the file store, so a save is just "write the
 * tab's content"; an external change the agent made reloads the buffer (handled in the store) when the
 * tab is clean.
 */
import { useEffect, useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { oneDark } from "@codemirror/theme-one-dark";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import type { Extension } from "@codemirror/state";

import { fileStore, tabKey, useFileState } from "../state/fileStore";

function languageExtension(language: string): Extension[] {
  switch (language) {
    case "python":
      return [python()];
    case "javascript":
      return [javascript({ jsx: true, typescript: true })];
    case "json":
      return [json()];
    case "markdown":
      return [markdown()];
    default:
      return [];
  }
}

export function CodeEditor() {
  const { tabs, activeKey } = useFileState();
  const active = tabs.find((t) => tabKey(t.scope, t.path) === activeKey) ?? null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void fileStore.saveActive();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const extensions = useMemo(() => languageExtension(active?.language ?? "text"), [active?.language]);

  return (
    <div className="ide-editor">
      <div className="ide-tabs" role="tablist">
        {tabs.map((t) => {
          const key = tabKey(t.scope, t.path);
          return (
            <div
              key={key}
              className={`ide-tab${key === activeKey ? " is-active" : ""}`}
              onClick={() => fileStore.setActive(key)}
              title={`${t.scope}: ${t.path}`}
            >
              <span className="ide-tab-name">
                {t.dirty ? "● " : ""}
                {t.name}
              </span>
              <button
                className="ide-tab-close"
                onClick={(e) => {
                  e.stopPropagation();
                  fileStore.closeTab(key);
                }}
              >
                ✕
              </button>
            </div>
          );
        })}
        {active && (
          <button
            className="ide-save"
            disabled={!active.dirty}
            onClick={() => void fileStore.saveActive()}
            title="Save (⌘/Ctrl+S)"
          >
            Save
          </button>
        )}
      </div>

      {active ? (
        <div className="ide-cm">
          <CodeMirror
            value={active.content}
            height="100%"
            theme={oneDark}
            extensions={extensions}
            onChange={(value) => fileStore.editActive(value)}
            basicSetup={{ lineNumbers: true, highlightActiveLine: true, foldGutter: true }}
          />
        </div>
      ) : (
        <div className="ide-empty ide-editor-empty">
          Open a file from the explorer, or prompt the agent to create one.
        </div>
      )}
    </div>
  );
}
