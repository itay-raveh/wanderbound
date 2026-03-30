import OverviewPage from "@/components/album/overview/OverviewPage.vue";
import type { Album } from "@/client";
import { computed, ref } from "vue";
import { makeStep, makeSegmentOutline, mountWithPlugins } from "../helpers";

function makeAlbum(overrides: Partial<Album> = {}): Album {
  return {
    title: "My Trip",
    subtitle: "Europe 2024",
    excluded_steps: [],
    front_cover_photo: "cover.jpg",
    back_cover_photo: "back.jpg",
    uid: 1,
    id: "album-1",
    colors: { NL: "#ff6600", DE: "#000000" },
    ...overrides,
  } as Album;
}

// Mock useAlbum composable which uses provide/inject
vi.mock("@/composables/useAlbum", () => ({
  useAlbum: () => ({
    albumId: ref("album-1"),
    colors: computed(() => ({ NL: "#ff6600" })),
    media: computed(() => ({})),
    tripStart: computed(() => "2024-04-10"),
    totalDays: computed(() => 10),
  }),
}));

// Mock useUserQuery to avoid needing MSW / Pinia Colada query
vi.mock("@/queries/useUserQuery", () => ({
  useUserQuery: () => ({
    user: computed(() => null),
    locale: computed(() => "en"),
    isKm: computed(() => true),
    formatDistance: (km: number) => String(Math.round(km)),
    distanceUnit: computed(() => "Km"),
    countryName: (code: string, detail: string) => detail,
  }),
}));

function mountOverview(props: Record<string, unknown> = {}) {
  const steps = [
    makeStep({
      name: "Amsterdam",
      aid: "album-1",
      timestamp: 1712880000,
      timezone_id: "Europe/Amsterdam",
      location: { name: "Amsterdam", detail: "Netherlands", country_code: "NL", lat: 52.37, lon: 4.89 },
      pages: [["photo1.jpg", "photo2.jpg"]],
      datetime: "2024-04-10T10:00:00+02:00",
    }),
    makeStep({
      id: 2,
      name: "Berlin",
      aid: "album-1",
      datetime: "2024-04-15T10:00:00+02:00",
      location: { name: "Berlin", detail: "Germany", country_code: "DE", lat: 52.52, lon: 13.4 },
      pages: [["photo3.jpg"]],
    }),
  ];

  return mountWithPlugins(OverviewPage, {
    global: {
      stubs: {
        OverviewExtremes: { template: "<div class='stub-extremes' />" },
        OverviewFurthestPoint: { template: "<div class='stub-furthest' />" },
      },
    },
    props: {
      album: makeAlbum(),
      steps,
      segments: [makeSegmentOutline({
        start_time: 1712880000,
        end_time: 1712890000,
        kind: "walking",
        start_coord: [52.37, 4.89],
        end_coord: [52.39, 4.91],
      })],
      ...props,
    },
  });
}

describe("OverviewPage", () => {
  it("renders the page container", () => {
    const wrapper = mountOverview();
    expect(wrapper.find(".overview").exists()).toBe(true);
  });

  it("renders four stat items", () => {
    const wrapper = mountOverview();
    const stats = wrapper.findAll(".stat");
    expect(stats.length).toBe(4);
  });

  it("renders the days stat", () => {
    const wrapper = mountOverview();
    const statNumbers = wrapper.findAll(".stat-number");
    const statLabels = wrapper.findAll(".stat-label");

    // totalDays is mocked to return 10
    expect(statNumbers[0]!.text()).toBe("10");
    expect(statLabels[0]!.text()).toBe("Days");
  });

  it("renders the distance stat", () => {
    const wrapper = mountOverview();
    const statLabels = wrapper.findAll(".stat-label");
    // distanceUnit is mocked to "Km"
    expect(statLabels[1]!.text()).toBe("Km");
  });

  it("renders the photos stat with correct count", () => {
    const wrapper = mountOverview();
    const statNumbers = wrapper.findAll(".stat-number");
    const statLabels = wrapper.findAll(".stat-label");

    // Step 1 has 2 photos, Step 2 has 1 photo = 3 total
    expect(statNumbers[2]!.text()).toBe("3");
    expect(statLabels[2]!.text()).toBe("Photos");
  });

  it("renders the steps stat with correct count", () => {
    const wrapper = mountOverview();
    const statNumbers = wrapper.findAll(".stat-number");
    const statLabels = wrapper.findAll(".stat-label");

    // 2 steps
    expect(statNumbers[3]!.text()).toBe("2");
    expect(statLabels[3]!.text()).toBe("Steps");
  });

  it("renders country chips for each unique country", () => {
    const wrapper = mountOverview();
    const countryChips = wrapper.findAll(".country-chip");
    // Two unique countries: NL, DE
    expect(countryChips.length).toBe(2);
  });

  it("renders country names in the chips", () => {
    const wrapper = mountOverview();
    const countryNames = wrapper.findAll(".country-name");
    // countryName mock returns detail string
    expect(countryNames[0]!.text()).toBe("Netherlands");
    expect(countryNames[1]!.text()).toBe("Germany");
  });

  it("renders country flags with correct src", () => {
    const wrapper = mountOverview();
    const flags = wrapper.findAll(".country-flag");
    expect(flags[0]!.attributes("src")).toContain("nl.png");
    expect(flags[1]!.attributes("src")).toContain("de.png");
  });

  it("renders country accent bars with colors from album", () => {
    const wrapper = mountOverview();
    const accents = wrapper.findAll(".country-accent");
    // NL has #ff6600 from album.colors
    expect(accents[0]!.attributes("style")).toContain("#ff6600");
  });

  it("renders decorative SVGs (clouds and hills)", () => {
    const wrapper = mountOverview();
    expect(wrapper.find(".clouds").exists()).toBe(true);
    expect(wrapper.find(".hills").exists()).toBe(true);
  });

  it("renders stubbed child components", () => {
    const wrapper = mountOverview();
    expect(wrapper.find(".stub-extremes").exists()).toBe(true);
    // OverviewFurthestPoint only renders when user?.living_location exists
    // Our mock returns null for user, so it should not render
    expect(wrapper.find(".stub-furthest").exists()).toBe(false);
  });

  it("excludes countries with code '00' from the countries list", () => {
    const wrapper = mountOverview({
      steps: [
        makeStep({
          location: {
            name: "Unknown",
            detail: "Unknown",
            country_code: "00",
            lat: 0,
            lon: 0,
          },
        }),
        makeStep({
          id: 2,
          location: {
            name: "Berlin",
            detail: "Germany",
            country_code: "DE",
            lat: 52.52,
            lon: 13.4,
          },
        }),
      ],
    });
    const countryChips = wrapper.findAll(".country-chip");
    // Only DE should appear, not "00"
    expect(countryChips.length).toBe(1);
    expect(wrapper.find(".country-name").text()).toBe("Germany");
  });

  it("renders stat icons", () => {
    const wrapper = mountOverview();
    const icons = wrapper.findAll(".stat-watermark");
    expect(icons.length).toBe(4);
  });
});
