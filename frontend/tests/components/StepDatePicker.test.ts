import { flushPromises } from "@vue/test-utils";
import StepDatePicker from "@/components/editor/StepDatePicker.vue";
import { makeStep, mountWithPlugins } from "../helpers";

function mountDatePicker(props: Record<string, unknown> = {}) {
  const steps = [
    makeStep({ datetime: "2024-04-10T10:00:00+02:00" }),
    makeStep({
      datetime: "2024-04-12T10:00:00+02:00",
      location: { name: "Berlin", detail: "Germany", country_code: "DE", lat: 52.52, lon: 13.4 },
    }),
    makeStep({
      datetime: "2024-04-15T10:00:00+02:00",
      location: { name: "Paris", detail: "France", country_code: "FR", lat: 48.86, lon: 2.35 },
    }),
  ];

  return mountWithPlugins(StepDatePicker, {
    props: {
      steps,
      colors: { NL: "#ff6600", DE: "#000000", FR: "#0055a4" },
      ...props,
    },
  });
}

describe("StepDatePicker", () => {
  it("sets navigation bounds from step dates", () => {
    const wrapper = mountDatePicker();
    const qdate = wrapper.findComponent({ name: "QDate" });
    // Steps span April 2024
    expect(qdate.props("navigationMinYearMonth")).toBe("2024/04");
    expect(qdate.props("navigationMaxYearMonth")).toBe("2024/04");
  });

  it("provides events function that returns true for step dates", () => {
    const wrapper = mountDatePicker();
    const qdate = wrapper.findComponent({ name: "QDate" });
    const eventsFn = qdate.props("events") as (date: string) => boolean;

    // Step dates in QDate format (YYYY/MM/DD)
    expect(eventsFn("2024/04/10")).toBe(true);
    expect(eventsFn("2024/04/12")).toBe(true);
    expect(eventsFn("2024/04/15")).toBe(true);
    expect(eventsFn("2024/04/11")).toBe(false);
  });

  it("provides options function that filters to step dates only", () => {
    const wrapper = mountDatePicker();
    const qdate = wrapper.findComponent({ name: "QDate" });
    const optionsFn = qdate.props("options") as (date: string) => boolean;

    expect(optionsFn("2024/04/10")).toBe(true);
    expect(optionsFn("2024/04/12")).toBe(true);
    expect(optionsFn("2024/04/11")).toBe(false);
  });

  it("respects additional options filter from parent", () => {
    const wrapper = mountDatePicker({
      options: (date: string) => date !== "2024/04/12",
    });
    const qdate = wrapper.findComponent({ name: "QDate" });
    const optionsFn = qdate.props("options") as (date: string) => boolean;

    // 2024/04/12 is a step date but excluded by parent's options
    expect(optionsFn("2024/04/10")).toBe(true);
    expect(optionsFn("2024/04/12")).toBe(false);
  });

  it("injects a style element into the document head", async () => {
    const wrapper = mountDatePicker();
    await flushPromises();

    // The component appends a <style> element for country-colored event dots
    const styles = document.head.querySelectorAll("style");
    const hasInjectedStyle = Array.from(styles).some((s) =>
      s.textContent?.includes(".bg-cc"),
    );
    expect(hasInjectedStyle).toBe(true);

    wrapper.unmount();
  });

  it("removes the injected style element on unmount", async () => {
    const wrapper = mountDatePicker();
    await flushPromises();

    const styleCountBefore = document.head.querySelectorAll("style").length;
    wrapper.unmount();
    const styleCountAfter = document.head.querySelectorAll("style").length;

    expect(styleCountAfter).toBeLessThan(styleCountBefore);
  });
});
