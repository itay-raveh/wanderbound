import {
  defineConfigWithVueTs,
  vueTsConfigs,
} from "@vue/eslint-config-typescript";
import pluginVue from "eslint-plugin-vue";

export default defineConfigWithVueTs(
  {
    ignores: ["dist/**", "src/client/**", "openapi-ts.config.ts"],
  },
  pluginVue.configs["flat/essential"],
  vueTsConfigs.recommendedTypeChecked,
);
