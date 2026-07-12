<script lang="ts" setup>
import type { HeaderKey } from "@/components/album/albumSections";
import type { ChapterVisit } from "./types";
import { useI18n } from "vue-i18n";
import {
  symOutlinedVisibility,
  symOutlinedVisibilityOff,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();

defineProps<{
  group: ChapterVisit;
  activeSectionKey: string | null;
  hiddenHeaderSet: ReadonlySet<string>;
}>();

defineEmits<{
  scrollToHeader: [key: string];
  toggleHeader: [headerKey: HeaderKey];
}>();
</script>

<template>
  <div class="header-items">
    <div
      v-for="item in group.headerItems"
      :key="item.key"
      role="button"
      tabindex="0"
      :data-nav-section="item.key"
      :class="[
        'nav-item',
        'header-item',
        {
          visible: activeSectionKey === item.key,
          'nav-hidden': hiddenHeaderSet.has(item.headerKey),
        },
      ]"
      @click="$emit('scrollToHeader', item.key)"
      @keydown.enter="$emit('scrollToHeader', item.key)"
    >
      <q-icon :name="item.icon" size="var(--type-sm)" />
      <span>{{ item.label }}</span>
      <button
        type="button"
        class="header-toggle"
        :aria-label="
          hiddenHeaderSet.has(item.headerKey) ? t('nav.showStep') : t('nav.hideStep')
        "
        @click.stop="$emit('toggleHeader', item.headerKey)"
      >
        <q-icon
          :name="
            hiddenHeaderSet.has(item.headerKey)
              ? symOutlinedVisibilityOff
              : symOutlinedVisibility
          "
          size="var(--type-xs)"
        />
      </button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
@use "nav-item";
@use "nav-toggle" as *;

.header-items {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: var(--gap-sm);
  margin-bottom: var(--gap-sm);
}

.header-item {
  gap: var(--gap-sm);
  padding: var(--gap-sm) var(--gap-md-lg);
  font-size: var(--type-xs);
  font-weight: 600;
  color: var(--text-muted);

  > span {
    flex: 1;
  }

  &:hover {
    color: var(--text-bright);
  }

  &.visible {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
    border-inline-start-color: var(--q-primary);

    &:hover {
      background: color-mix(in srgb, var(--q-primary) 18%, transparent);
    }

    &:active {
      background: color-mix(in srgb, var(--q-primary) 24%, transparent);
    }
  }
}

.header-toggle {
  @include nav-toggle;

  .header-item:hover & {
    opacity: 1;
  }

  .header-item.nav-hidden & {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .header-item {
    transition: none;
  }
}
</style>
