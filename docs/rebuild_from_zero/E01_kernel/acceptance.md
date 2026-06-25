# E01 — Acceptance Criteria (draft)

## S01.1 execute registered tool
- Given a tool `echo` registered to a feature, When `execute_tool("echo", {...})`, Then result has `ok=true`, `capability="echo"`, `feature` set, payload under `data`.

## S01.2 unknown tool
- Given no tool named `nope`, When `execute_tool("nope")`, Then `ok=false` and `missing_capability=true` and no exception propagates.

## S01.3 disabled feature
- Given feature `mcp_tools.enabled=false`, When the kernel boots and a tool from it is called, Then kernel boot succeeds and the call returns `missing_capability`.

## S01.4 feature install
- Given `features.yaml` enables feature X, When bootstrap runs, Then X's declared capabilities appear in `registry.list_tools()`.

## S01.5 events
- Given any tool call, When it completes, Then an event `tool.completed` (or `tool.failed`) is published with `tool` and `request_id`.

## S01.6 envelope normalization
- Given a tool returning a bare dict without envelope keys, When executed, Then output is wrapped into a full `CapabilityResult` (data/metadata populated).
