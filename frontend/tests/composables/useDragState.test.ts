import { useDragState } from "@/composables/useDragState";

describe("useDragState", () => {
  it("becomes true on dragstart event", () => {
    const isDragging = useDragState();
    isDragging.value = false; // reset

    document.dispatchEvent(new Event("dragstart"));
    expect(isDragging.value).toBe(true);
  });

  it("becomes false on dragend event", () => {
    const isDragging = useDragState();
    isDragging.value = true; // simulate active drag

    document.dispatchEvent(new Event("dragend"));
    expect(isDragging.value).toBe(false);
  });

  it("becomes false on drop event", () => {
    const isDragging = useDragState();
    isDragging.value = true; // simulate active drag

    document.dispatchEvent(new Event("drop"));
    expect(isDragging.value).toBe(false);
  });

});
