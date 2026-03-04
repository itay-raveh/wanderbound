export let draggedPhoto: string | null = null;
export let draggedSourceCallback: (() => void) | null = null;

export function setDraggedPhoto(path: string, removeCb: () => void) {
  draggedPhoto = path;
  draggedSourceCallback = removeCb;
}

export function clearDraggedPhoto() {
  draggedPhoto = null;
  draggedSourceCallback = null;
}
