/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

declare const __APP_VERSION__: string

interface ImportMetaEnv {
  readonly VITE_MAX_UPLOAD_GB: string
  readonly VITE_BACKEND_URL: string
  readonly VITE_MAPBOX_TOKEN: string
  readonly VITE_GOOGLE_CLIENT_ID: string
  readonly VITE_CONTACT_EMAIL?: string
  readonly VITE_GITHUB_URL?: string
  readonly VITE_AUTHOR_NAME?: string
  readonly VITE_AUTHOR_URL?: string
  readonly VITE_SENTRY_DSN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
