import {
  defineConfigWithVueTs,
  vueTsConfigs,
} from "@vue/eslint-config-typescript";
import pluginVue from "eslint-plugin-vue";

export default defineConfigWithVueTs(
  {
    ignores: ["dist/**", "src/api/**"],
  },
  pluginVue.configs["flat/essential"],
  vueTsConfigs.recommendedTypeChecked,
);
