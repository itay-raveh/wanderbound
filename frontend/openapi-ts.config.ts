import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "../backend/openapi.json",
  output: "./src/client",
  plugins: [
    {
      name: "@hey-api/client-fetch",
      throwOnError: true,
    },
    "@hey-api/typescript",
    { name: "@hey-api/schemas", type: "json" },
    "@hey-api/sdk",
    {
      name: "zod",
    },
  ],
});
