import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: `${process.env.VITE_BACKEND_URL ?? "http://localhost:8000"}/api/v1/openapi.json`,
  output: "./src/client",
  plugins: [
    {
      name: "@hey-api/client-fetch",
      throwOnError: true,
    },
  ],
});
