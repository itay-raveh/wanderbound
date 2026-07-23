import { mount } from "@vue/test-utils";
import i18n from "@/i18n";
import UpgradeMatchDialog from "@/components/editor/UpgradeMatchDialog.vue";

function mountDialog() {
  return mount(UpgradeMatchDialog, {
    props: {
      modelValue: true,
      matched: 1,
      total: 1,
      unmatched: 0,
      alreadyUpgraded: 1,
      newThisRound: 1,
    },
    global: {
      plugins: [i18n],
      stubs: {
        PromptDialog: {
          props: ["body"],
          template: "<div>{{ body }}</div>",
        },
      },
    },
  });
}

describe("UpgradeMatchDialog", () => {
  afterEach(() => {
    i18n.global.locale.value = "en";
  });

  test("pluralizes every count in the English match summary", () => {
    i18n.global.locale.value = "en";

    expect(mountDialog().text()).toBe(
      "Matched 1 album file from 1 selected Google item. 1 was already at original quality.",
    );
  });

  test("pluralizes every count in the Hebrew match summary", () => {
    i18n.global.locale.value = "he";

    expect(mountDialog().text()).toBe(
      "נמצא קובץ אחד מהאלבום מתוך פריט אחד שנבחר ב-Google Photos. אחד מהם כבר היה באיכות המקורית.",
    );
  });
});
