// Transport config — the one place the backend URL/token lives. Drop-in to the real
// backend is "change VITE_CP_BASE_URL", nothing in the UI render path.
export const BASE_URL = (import.meta.env?.VITE_CP_BASE_URL ?? "http://localhost:8800").replace(/\/$/, "");
export const CP_TOKEN = import.meta.env?.VITE_CP_TOKEN ?? "dev-token";
export const SESSION_ID = "t1_demo";
