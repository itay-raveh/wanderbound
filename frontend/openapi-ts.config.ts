import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "http://localhost:8000/openapi.json",
  output: "src/api",
  plugins: [
    {
      name: "@hey-api/client-axios",
      throwOnError: true,
      baseUrl: false,
    },
  ],
});
