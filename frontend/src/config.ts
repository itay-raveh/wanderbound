import { publicConfig } from "@/client";
import { zPublicSettings } from "@/client/zod.gen";
import type { z } from "zod";

export type RuntimeSettings = z.output<typeof zPublicSettings>;

let settings: RuntimeSettings | undefined;
let loading: Promise<RuntimeSettings> | undefined;

export function loadPublicSettings(): Promise<RuntimeSettings> {
  if (settings) return Promise.resolve(settings);
  loading ??= publicConfig().then(({ data }) => {
    if (!data) throw new Error("Public settings response was empty");
    settings = zPublicSettings.parse(data);
    return settings;
  });
  return loading;
}

export function getPublicSettings(): RuntimeSettings {
  if (!settings) throw new Error("Public settings are not loaded");
  return settings;
}
