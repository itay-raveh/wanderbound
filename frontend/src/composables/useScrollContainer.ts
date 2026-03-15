import type { InjectionKey, Ref } from "vue";

export const SCROLL_CONTAINER_KEY: InjectionKey<Ref<HTMLElement | undefined>> =
  Symbol("scroll-container");
