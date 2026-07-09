import { nextTick } from "vue";
import { mountWithPlugins, makeStep } from "../helpers";
import NavChapterGroup from "@/components/editor/nav/NavChapterGroup.vue";
import type { ChapterVisit } from "@/components/editor/nav/types";

const group: ChapterVisit = {
  key: "chapter-1",
  name: "South America",
  chapterIndex: 0,
  chapter: {
    id: "chapter-1",
    title: "South America",
    subtitle: "",
    front_cover_photo: "",
    back_cover_photo: "",
    step_ids: [1, 2],
  },
  headerItems: [],
  countries: [],
  stepIds: [1, 2],
  dateRange: "Jan 1 - Jan 2",
};

function mountChapterGroup(mergeTarget: "previous" | "next") {
  return mountWithPlugins(NavChapterGroup, {
    props: {
      group,
      open: false,
      openCountryKey: null,
      activeStepId: null,
      activeSectionKey: null,
      hiddenSet: new Set<number>(),
      hiddenHeaderSet: new Set<string>(),
      steps: [makeStep({ id: 1 }), makeStep({ id: 2 })],
      colors: {},
      formatMapRange: () => "",
      canDelete: true,
      canSplit: true,
      mergeTarget,
      startOptions: [],
      startStepId: null,
    },
    attachTo: document.body,
  });
}

describe("NavChapterGroup", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("labels first-chapter removal as a merge with the next chapter", async () => {
    const wrapper = mountChapterGroup("next");

    await wrapper.get('button[aria-label="Chapter actions"]').trigger("click");
    await nextTick();

    expect(document.body.textContent).toContain("Merge with next chapter");
    expect(document.body.textContent).not.toContain("Delete chapter");
  });

  it("labels later chapter removal as a merge with the previous chapter", async () => {
    const wrapper = mountChapterGroup("previous");

    await wrapper.get('button[aria-label="Chapter actions"]').trigger("click");
    await nextTick();

    expect(document.body.textContent).toContain("Merge with previous chapter");
    expect(document.body.textContent).not.toContain("Delete chapter");
  });
});
