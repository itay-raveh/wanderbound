type FrontendConfig = Readonly<Record<`VITE_${string}`, string | undefined>>;

const runtimeConfig = (
  globalThis as typeof globalThis & {
    WANDERBOUND_CONFIG?: FrontendConfig;
  }
).WANDERBOUND_CONFIG ?? {};

export const frontendConfig: FrontendConfig = import.meta.env.DEV
  ? import.meta.env
  : runtimeConfig;
