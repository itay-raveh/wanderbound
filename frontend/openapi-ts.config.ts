import { existsSync } from "node:fs";
import { defineConfig } from "@hey-api/openapi-ts";

// Docker build: use the static spec copied from the backend image.
// Dev: fall back to the live backend URL.
const input = existsSync("./openapi.json")
  ? "./openapi.json"
  : `${process.env.VITE_BACKEND_URL ?? "http://localhost:8000"}/api/v1/openapi.json`;

export default defineConfig({
  input,
  output: "./src/client",
  plugins: [
    {
      name: "@hey-api/client-fetch",
      throwOnError: true,
    },
  ],
});
