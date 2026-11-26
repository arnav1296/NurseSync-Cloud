/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "" in the cloud build (same origin via CloudFront); http://localhost:8000 locally */
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_COGNITO_USER_POOL_ID: string;
  readonly VITE_COGNITO_CLIENT_ID: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
