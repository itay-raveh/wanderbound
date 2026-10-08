import { mount } from "@vue/test-utils";
import { createI18n } from "vue-i18n";
import { AlbumMetaSchema } from "@/client/schemas.gen";
import type { AlbumMeta } from "@/client";
import openapi from "../../../backend/openapi.json";
import en from "@/i18n/locales/en.json";
import he from "@/i18n/locales/he.json";
import de from "@/i18n/locales/de.json";

vi.mock("@/queries/useAlbumMutation", () => ({
  useAlbumMutation: () => ({ mutateAsync: vi.fn() }),
}));

afterEach(() => {
  vi.doUnmock("@/client/schemas.gen");
  vi.resetModules();
});

it("retains backend numeric and cross-field constraints in the generated client", () => {
  const schema = openapi.components.schemas.AlbumMeta;
  expect(AlbumMetaSchema.properties.page_width_mm).toEqual(
    schema.properties.page_width_mm,
  );
  expect(AlbumMetaSchema.properties.page_height_mm).toEqual(
    schema.properties.page_height_mm,
  );
  expect(AlbumMetaSchema["x-page-aspect-ratio"]).toEqual(
    schema["x-page-aspect-ratio"],
  );
});

it("propagates changed schema bounds and defaults to validation, inputs and localized ranges", async () => {
  const schema = {
    ...AlbumMetaSchema,
    properties: {
      ...AlbumMetaSchema.properties,
      page_width_mm: {
        ...AlbumMetaSchema.properties.page_width_mm,
        minimum: 260,
        maximum: 400,
        default: 300,
      },
      page_height_mm: {
        ...AlbumMetaSchema.properties.page_height_mm,
        minimum: 190,
        maximum: 280,
        default: 220,
      },
    },
    "x-page-aspect-ratio": { minimum: 1.3, maximum: 1.7 },
  };
  vi.resetModules();
  vi.doMock("@/client/schemas.gen", () => ({ AlbumMetaSchema: schema }));
  const { albumPageSize, validatePageSize } = await import("@/utils/pageSize");
  expect(albumPageSize()).toEqual({ widthMm: 300, heightMm: 220 });
  expect(validatePageSize({ widthMm: 300, heightMm: 220 })).toBe(true);
  for (const [widthMm, heightMm] of [
    [255, 200],
    [270, 185],
    [410, 250],
    [400, 285],
    [300, 235],
    [380, 220],
    [NaN, 220],
    [300, Infinity],
  ]) {
    expect(validatePageSize({ widthMm, heightMm })).toBe(false);
  }
  const PageSizeSettings = (
    await import("@/components/editor/PageSizeSettings.vue")
  ).default;
  const i18n = createI18n({
    legacy: false,
    locale: "en",
    messages: { en, he, de },
  });
  const wrapper = mount(PageSizeSettings, {
    props: { album: { id: "schema-fixture" } as AlbumMeta },
    global: { plugins: [i18n] },
  });
  const [width, height] = wrapper.findAll("input[inputmode=decimal]");
  expect(width.element.value).toBe("300");
  expect(height.element.value).toBe("220");
  expect([
    width.attributes("min"),
    width.attributes("max"),
    height.attributes("min"),
    height.attributes("max"),
  ]).toEqual(["260", "400", "190", "280"]);
  await width.setValue("255");
  expect(wrapper.get('[role="alert"]').text()).toContain(
    "260–400 mm, height 190–280 mm",
  );
  expect(wrapper.get('[role="alert"]').text()).toContain("1.3–1.7");
  i18n.global.locale.value = "he";
  await wrapper.vm.$nextTick();
  expect(wrapper.get('[role="alert"]').text()).toContain("רוחב 260–400 mm");
  expect(wrapper.get('[role="alert"]').text()).toContain("1.3–1.7");
  i18n.global.locale.value = "de";
  await wrapper.vm.$nextTick();
  expect(wrapper.get('[role="alert"]').text()).toContain("Breite 260–400 mm");
  expect(wrapper.get('[role="alert"]').text()).toContain("1,3–1,7");
  await width.setValue("300,125");
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  i18n.global.locale.value = "en";
  await wrapper.vm.$nextTick();
  await width.setValue("255");
  await wrapper
    .findAll("button")
    .find((button) => button.text() === "in")!
    .trigger("click");
  expect(Number(width.attributes("min"))).toBeCloseTo(260 / 25.4);
  expect(wrapper.get('[role="alert"]').text()).toContain(
    "10.23622–15.748031 in",
  );
});
