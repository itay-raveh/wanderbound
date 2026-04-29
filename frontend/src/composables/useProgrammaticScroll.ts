import type { InjectionKey, Ref } from "vue";

export const PROGRAMMATIC_SCROLL_KEY: InjectionKey<Ref<boolean>> = Symbol(
  "programmatic-scroll",
);
