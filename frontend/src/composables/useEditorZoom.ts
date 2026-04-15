import { ref } from "vue";

export const MIN_ZOOM = 0.3;
export const MAX_ZOOM = 1;
export const ZOOM_STEP = 0.05;
const DEFAULT_ZOOM = 0.7;

export const editorZoom = ref(DEFAULT_ZOOM);

export function setEditorZoom(value: number) {
  const clamped =
    Math.round(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value)) * 100) / 100;
  if (editorZoom.value === clamped) return;
  editorZoom.value = clamped;
}
