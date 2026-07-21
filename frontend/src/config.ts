import { publicConfig } from "@/client";
import { zPublicSettings } from "@/client/zod.gen";
import type { z } from "zod";

export type Settings = z.output<typeof zPublicSettings>;

let settings: Settings | undefined;
let loading: Promise<Settings> | undefined;

export function loadSettings(): Promise<Settings> {
  if (settings) return Promise.resolve(settings);
  loading ??= publicConfig().then(({ data }) => {
    if (!data) throw new Error("Public settings response was empty");
    settings = zPublicSettings.parse(data);
    return settings;
  });
  return loading;
}

export function getSettings(): Settings {
  if (!settings) throw new Error("Public settings are not loaded");
  return settings;
}
