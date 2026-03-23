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

  it("handles full drag lifecycle: start -> end", () => {
    const isDragging = useDragState();
    isDragging.value = false;

    document.dispatchEvent(new Event("dragstart"));
    expect(isDragging.value).toBe(true);

    document.dispatchEvent(new Event("dragend"));
    expect(isDragging.value).toBe(false);
  });

  it("handles full drag lifecycle: start -> drop", () => {
    const isDragging = useDragState();
    isDragging.value = false;

    document.dispatchEvent(new Event("dragstart"));
    expect(isDragging.value).toBe(true);

    document.dispatchEvent(new Event("drop"));
    expect(isDragging.value).toBe(false);
  });

  it("handles multiple drag cycles", () => {
    const isDragging = useDragState();
    isDragging.value = false;

    // First cycle
    document.dispatchEvent(new Event("dragstart"));
    expect(isDragging.value).toBe(true);
    document.dispatchEvent(new Event("dragend"));
    expect(isDragging.value).toBe(false);

    // Second cycle
    document.dispatchEvent(new Event("dragstart"));
    expect(isDragging.value).toBe(true);
    document.dispatchEvent(new Event("drop"));
    expect(isDragging.value).toBe(false);
  });
});
