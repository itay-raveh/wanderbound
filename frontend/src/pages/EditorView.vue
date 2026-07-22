<script lang="ts" setup>
import AlbumNav from "@/components/editor/AlbumNav.vue";
import AlbumToolbar from "@/components/editor/AlbumToolbar.vue";
import AlbumViewer from "@/components/AlbumViewer.vue";
import EditorHeader from "@/components/editor/EditorHeader.vue";
import EditorRailControl from "@/components/editor/EditorRailControl.vue";
import InspectorDrawer from "@/components/editor/InspectorDrawer.vue";
import { useUserQuery } from "@/queries/useUserQuery";
import {
  useAlbumQuery,
  useMediaQuery,
  useStepsQuery,
  useSegmentsQuery,
} from "@/queries/queries";
import { useLocale } from "@/composables/useLocale";
import { useEditorKeyboard } from "@/composables/useEditorKeyboard";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { useUndoStack } from "@/composables/useUndoStack";
import { useActiveSection } from "@/composables/useActiveSection";
import { useLocalStorage } from "@vueuse/core";
import { useMeta, useQuasar } from "quasar";
import { useI18n } from "vue-i18n";
import { computed, watch, nextTick, onBeforeUnmount, ref } from "vue";

const { t } = useI18n();

useMeta({ title: "Editor" });

import { LAST_ALBUM_KEY } from "@/utils/storage-keys";
const DRAWER_WIDTH = 280;
const NAVIGATION_BREAKPOINT = 1199;
const INSPECTOR_BREAKPOINT = 1439;

const $q = useQuasar();
const navigationStandard = computed(
  () => $q.screen.width > NAVIGATION_BREAKPOINT,
);
const inspectorStandard = computed(
  () => $q.screen.width > INSPECTOR_BREAKPOINT,
);
const navigationOpen = ref(navigationStandard.value);
const inspectorOpen = ref(inspectorStandard.value);
const navigationOpenControl = ref<InstanceType<typeof EditorRailControl> | null>(
  null,
);
const navigationEdgeControl = ref<InstanceType<typeof EditorRailControl> | null>(
  null,
);
const inspectorOpenControl = ref<InstanceType<typeof EditorRailControl> | null>(
  null,
);
const inspectorEdgeControl = ref<InstanceType<typeof EditorRailControl> | null>(
  null,
);

function toggleNavigation() {
  navigationOpen.value = !navigationOpen.value;
  void nextTick(() =>
    (navigationOpen.value
      ? navigationOpenControl
      : navigationEdgeControl
    ).value?.focus(),
  );
}

function toggleInspector() {
  inspectorOpen.value = !inspectorOpen.value;
  void nextTick(() =>
    (
      inspectorOpen.value ? inspectorOpenControl : inspectorEdgeControl
    ).value?.focus(),
  );
}

watch(navigationStandard, (standard) => {
  navigationOpen.value = standard;
});
watch(inspectorStandard, (standard) => {
  inspectorOpen.value = standard;
});

const selectedAlbumId = useLocalStorage<string | null>(LAST_ALBUM_KEY, null);

const { data: userData, locale, isDemo, exitDemo } = useUserQuery();
const albumIds = computed(() => userData.value?.album_ids ?? null);

// Auto-select first album when none saved (VueUse `whenever` pattern)
if (!selectedAlbumId.value) {
  const stop = watch(
    albumIds,
    (ids) => {
      if (ids?.length) {
        selectedAlbumId.value = ids[0]!;
        void nextTick(() => stop());
      }
    },
    { immediate: true },
  );
}

const { data: album } = useAlbumQuery(selectedAlbumId);
const { data: media } = useMediaQuery(selectedAlbumId);
const { data: steps } = useStepsQuery(selectedAlbumId);
const { data: segmentOutlines } = useSegmentsQuery(selectedAlbumId);

useLocale(locale);

useEditorKeyboard();
const undoStack = useUndoStack();
const photoFocus = usePhotoFocus();
watch(selectedAlbumId, () => {
  undoStack.clear();
  photoFocus.blur();
  resetActiveSection();
});

const { activeStepId, activeSectionKey, resetActiveSection } =
  useActiveSection();
onBeforeUnmount(resetActiveSection);
const displayedSteps = computed(() => steps.value);
const activeStep = computed(() =>
  activeStepId.value != null
    ? displayedSteps.value?.find((s) => s.id === activeStepId.value)
    : undefined,
);
</script>

<template>
  <EditorHeader class="print-hide">
    <template #banner>
      <div v-if="isDemo" class="demo-banner">
        <span>{{ t("demo.bannerText") }}</span>
        <q-btn
          :label="t('demo.bannerCta')"
          flat
          dense
          no-caps
          color="white"
          class="demo-banner-cta"
          @click="exitDemo"
        />
      </div>
    </template>

    <AlbumToolbar v-if="album" :album="album" />
  </EditorHeader>

  <q-drawer
    side="left"
    :model-value="navigationOpen"
    :breakpoint="NAVIGATION_BREAKPOINT"
    persistent
    bordered
    :width="DRAWER_WIDTH"
    :aria-label="t('nav.stepNavigation')"
    class="print-hide"
    @update:model-value="navigationOpen = $event"
  >
    <div id="editor-navigation" class="editor-rail fit column no-wrap">
      <EditorRailControl
        ref="navigationOpenControl"
        side="left"
        :open="true"
        :title="t('nav.album')"
        controls="editor-navigation"
        :show-label="t('nav.showNavigation')"
        :hide-label="t('nav.hideNavigation')"
        @toggle="toggleNavigation"
      />
      <div class="editor-rail__content">
        <AlbumNav
          v-if="album && displayedSteps"
          v-model:album-id="selectedAlbumId"
          :album-ids="albumIds ?? undefined"
          :steps="displayedSteps"
          :album="album"
          :hidden-steps="album.hidden_steps ?? undefined"
          :hidden-headers="album.hidden_headers ?? undefined"
          :colors="album.colors ?? undefined"
          :maps-ranges="album.maps_ranges ?? undefined"
        />
        <div v-else class="fit flex flex-center" role="status">
          <q-spinner-dots
            color="primary"
            size="2rem"
            :aria-label="t('album.loading', { name: '' })"
          />
        </div>
      </div>
    </div>
  </q-drawer>

  <q-drawer
    side="right"
    :model-value="inspectorOpen"
    :breakpoint="INSPECTOR_BREAKPOINT"
    persistent
    bordered
    :width="DRAWER_WIDTH"
    :aria-label="t('nav.inspector')"
    class="print-hide"
    @update:model-value="inspectorOpen = $event"
  >
    <div id="editor-inspector" class="editor-rail fit column no-wrap">
      <EditorRailControl
        ref="inspectorOpenControl"
        side="right"
        :open="true"
        :title="t('nav.inspector')"
        controls="editor-inspector"
        :show-label="t('nav.showInspector')"
        :hide-label="t('nav.hideInspector')"
        @toggle="toggleInspector"
      />
      <div class="editor-rail__content">
        <InspectorDrawer
          v-if="album && media && displayedSteps"
          :album="album"
          :media="media"
          :steps="displayedSteps"
          :step="activeStep"
          :section-key="activeSectionKey"
        />
      </div>
    </div>
  </q-drawer>

  <q-page class="editor-page">
    <AlbumViewer
      v-if="album && displayedSteps && media && segmentOutlines"
      :album="album"
      :media="media"
      :steps="displayedSteps"
      :segment-outlines="segmentOutlines"
    />
    <q-page-sticky
      v-if="!navigationOpen"
      position="top-left"
      class="print-hide"
    >
      <EditorRailControl
        ref="navigationEdgeControl"
        side="left"
        :open="false"
        :title="t('nav.album')"
        controls="editor-navigation"
        :show-label="t('nav.showNavigation')"
        :hide-label="t('nav.hideNavigation')"
        @toggle="toggleNavigation"
      />
    </q-page-sticky>
    <q-page-sticky
      v-if="!inspectorOpen"
      position="top-right"
      class="print-hide"
    >
      <EditorRailControl
        ref="inspectorEdgeControl"
        side="right"
        :open="false"
        :title="t('nav.inspector')"
        controls="editor-inspector"
        :show-label="t('nav.showInspector')"
        :hide-label="t('nav.hideInspector')"
        @toggle="toggleInspector"
      />
    </q-page-sticky>
  </q-page>
</template>

<style lang="scss" scoped>
.demo-banner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--gap-md);
  padding: var(--gap-sm) var(--gap-lg);
  background: var(--q-primary);
  color: white;
  font-size: var(--type-sm);
}

.demo-banner-cta {
  text-decoration: underline;
}

.editor-page {
  background: var(--bg);
}

.editor-rail__content {
  flex: 1;
  min-height: 0;
}

@media print {
  @page {
    size: A4 landscape;
  }

  * {
    margin: 0;
    padding: 0;
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
}
</style>
