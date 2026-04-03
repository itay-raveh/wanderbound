import EditableText from "@/components/album/EditableText.vue";
import JustifiedText from "@/components/album/JustifiedText.vue";
import type { JustifiedLine } from "@/composables/useTextLayout";
import { mountWithPlugins } from "../helpers";

vi.mock("@/composables/usePrintReady", () => ({
  usePrintMode: () => false,
}));

function mountEditableText(props: Record<string, unknown> = {}) {
  return mountWithPlugins(EditableText, {
    props: { modelValue: "Hello World", ...props },
  });
}

function line(text: string): JustifiedLine {
  return { text };
}

// ---------------------------------------------------------------------------
// Single-line mode (contenteditable)
// ---------------------------------------------------------------------------

describe("EditableText single-line", () => {
  it("emits update:modelValue on blur with changed text", async () => {
    const wrapper = mountEditableText({ modelValue: "Original" });
    const el = wrapper.find(".editable-display");

    await el.trigger("focus");
    (el.element as HTMLElement).innerText = "Changed";
    await el.trigger("blur");

    expect(wrapper.emitted("update:modelValue")).toBeTruthy();
    expect(wrapper.emitted("update:modelValue")![0]).toEqual(["Changed"]);
  });

  it("does not emit update:modelValue on blur when text is unchanged", async () => {
    const wrapper = mountEditableText({ modelValue: "Same" });
    const el = wrapper.find(".editable-display");

    await el.trigger("focus");
    (el.element as HTMLElement).innerText = "Same";
    await el.trigger("blur");

    expect(wrapper.emitted("update:modelValue")).toBeFalsy();
  });

  it("trims whitespace on commit", async () => {
    const wrapper = mountEditableText({ modelValue: "Original" });
    const el = wrapper.find(".editable-display");

    await el.trigger("focus");
    (el.element as HTMLElement).innerText = "  Trimmed  ";
    await el.trigger("blur");

    expect(wrapper.emitted("update:modelValue")![0]).toEqual(["Trimmed"]);
  });
});

// ---------------------------------------------------------------------------
// Multiline mode (display → textarea swap)
// ---------------------------------------------------------------------------

describe("EditableText multiline", () => {
  const sampleLines = [line("First line"), line("Second line")];

  it("renders JustifiedText when lines are provided", () => {
    const wrapper = mountEditableText({
      modelValue: "Full text here",
      multiline: true,
      lines: sampleLines,
    });
    expect(wrapper.findComponent(JustifiedText).exists()).toBe(true);
    expect(wrapper.find("textarea").exists()).toBe(false);
  });

  it("renders raw modelValue when lines is null", () => {
    const wrapper = mountEditableText({
      modelValue: "Raw text",
      multiline: true,
      lines: null,
    });
    expect(wrapper.findComponent(JustifiedText).exists()).toBe(false);
    expect(wrapper.find(".editable-display").text()).toBe("Raw text");
  });

  it("switches to textarea on click", async () => {
    const wrapper = mountEditableText({
      modelValue: "Editable",
      multiline: true,
      lines: sampleLines,
    });

    await wrapper.find(".editable-display").trigger("click");
    const textarea = wrapper.find("textarea");
    expect(textarea.exists()).toBe(true);
    expect((textarea.element as HTMLTextAreaElement).value).toBe("Editable");
  });

  it("switches back to display on blur and emits when changed", async () => {
    const wrapper = mountEditableText({
      modelValue: "Original",
      multiline: true,
      lines: sampleLines,
    });

    // Enter edit mode
    await wrapper.find(".editable-display").trigger("click");
    const textarea = wrapper.find("textarea");

    // Change value and blur
    await textarea.setValue("Modified");
    await textarea.trigger("blur");

    expect(wrapper.find("textarea").exists()).toBe(false);
    expect(wrapper.findComponent(JustifiedText).exists()).toBe(true);
    expect(wrapper.emitted("update:modelValue")![0]).toEqual(["Modified"]);
  });

  it("does not emit when text unchanged after edit", async () => {
    const wrapper = mountEditableText({
      modelValue: "Same text",
      multiline: true,
      lines: sampleLines,
    });

    await wrapper.find(".editable-display").trigger("click");
    // Don't change the value, just blur
    await wrapper.find("textarea").trigger("blur");

    expect(wrapper.emitted("update:modelValue")).toBeFalsy();
  });

  it("strips leading/trailing newlines on commit", async () => {
    const wrapper = mountEditableText({
      modelValue: "Original",
      multiline: true,
      lines: sampleLines,
    });

    await wrapper.find(".editable-display").trigger("click");
    await wrapper.find("textarea").setValue("\n\nContent\n\n");
    await wrapper.find("textarea").trigger("blur");

    expect(wrapper.emitted("update:modelValue")![0]).toEqual(["Content"]);
  });

  it("preserves internal newlines (paragraph breaks)", async () => {
    const wrapper = mountEditableText({
      modelValue: "Original",
      multiline: true,
      lines: sampleLines,
    });

    await wrapper.find(".editable-display").trigger("click");
    await wrapper.find("textarea").setValue("First paragraph\n\nSecond paragraph");
    await wrapper.find("textarea").trigger("blur");

    expect(wrapper.emitted("update:modelValue")![0]).toEqual([
      "First paragraph\n\nSecond paragraph",
    ]);
  });

  it("reverts on Escape without emitting", async () => {
    const wrapper = mountEditableText({
      modelValue: "Original",
      multiline: true,
      lines: sampleLines,
    });

    await wrapper.find(".editable-display").trigger("click");
    await wrapper.find("textarea").setValue("Changed");
    await wrapper.find("textarea").trigger("keydown", { key: "Escape" });

    expect(wrapper.emitted("update:modelValue")).toBeFalsy();
    expect(wrapper.find("textarea").exists()).toBe(false);
  });

  it("has no contenteditable elements in multiline mode", () => {
    const wrapper = mountEditableText({
      modelValue: "Text",
      multiline: true,
      lines: sampleLines,
    });
    expect(wrapper.find("[contenteditable]").exists()).toBe(false);
  });
});
