import { ref } from "vue";

const isDragging = ref(false);

document.addEventListener("dragstart", () => {
  isDragging.value = true;
});
document.addEventListener("dragend", () => {
  isDragging.value = false;
});
document.addEventListener("drop", () => {
  isDragging.value = false;
});

/** Shared reactive boolean that is `true` while any drag is in progress. */
export function useDragState() {
  return isDragging;
}
