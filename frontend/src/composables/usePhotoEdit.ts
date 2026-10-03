import { inject, type InjectionKey } from "vue";

export const PHOTO_EDIT_KEY: InjectionKey<(name: string) => void> =
  Symbol("photo-edit");

export function usePhotoEdit() {
  return inject(PHOTO_EDIT_KEY, null);
}
