import { mount } from "@vue/test-utils";
import { createI18n } from "vue-i18n";
import { AlbumMetaSchema } from "@/client/schemas.gen";
import type { AlbumMeta } from "@/client";
import en from "@/i18n/locales/en.json";

const { mutateAsync } = vi.hoisted(() => ({ mutateAsync: vi.fn() }));
vi.mock("@/queries/useAlbumMutation", () => ({
  useAlbumMutation: () => ({ mutateAsync }),
}));

afterEach(() => {
  vi.doUnmock("@/client/schemas.gen");
  vi.resetModules();
});

it("rejects invalid dimensions under changed schema policy and saves localized decimals atomically", async () => {
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
  const PageSizeSettings = (
    await import("@/components/editor/PageSizeSettings.vue")
  ).default;
  const i18n = createI18n({
    legacy: false,
    locale: "en",
    messages: { en },
  });
  const wrapper = mount(PageSizeSettings, {
    props: { album: { id: "schema-fixture" } as AlbumMeta },
    global: { plugins: [i18n] },
  });
  const [width, height] = wrapper.findAll("input[inputmode=decimal]");
  const apply = () =>
    wrapper.findAll("button").find((button) => button.text() === "Apply")!;
  for (const [w, h] of [
    ["255", "200"],
    ["300", "185"],
    ["405", "250"],
    ["300", "285"],
    ["300", "235"],
    ["380", "220"],
    ["", "220"],
  ]) {
    await width.setValue(w);
    await height.setValue(h);
    expect(apply().attributes("disabled")).toBeDefined();
    await apply().trigger("click");
    expect(mutateAsync).not.toHaveBeenCalled();
  }
  await width.setValue("300,125");
  await height.setValue("220,25");
  await wrapper
    .findAll("button")
    .find((button) => button.text() === "in")!
    .trigger("click");
  await wrapper
    .findAll("button")
    .find((button) => button.text() === "mm")!
    .trigger("click");
  await apply().trigger("click");
  expect(mutateAsync).toHaveBeenCalledExactlyOnceWith({
    page_width_mm: 300.125,
    page_height_mm: 220.25,
  });
});
