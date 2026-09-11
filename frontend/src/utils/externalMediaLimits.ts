import { zBodyAddDevice, zUpgradeRequest } from "@/client/zod.gen";
import { z } from "zod";

export const EXTERNAL_MEDIA_IMPORT_MAX_ITEMS = z.toJSONSchema(
  zBodyAddDevice.shape.files,
).maxItems!;
export const GOOGLE_REPLACEMENT_MAX_ITEMS = 1;
export const GOOGLE_UPGRADE_MAX_SESSION_IDS = z.toJSONSchema(
  zUpgradeRequest.shape.session_ids,
).maxItems!;
