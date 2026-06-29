/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CP_BASE_URL?: string;
  readonly VITE_CP_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
