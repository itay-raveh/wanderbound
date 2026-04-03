/** Stable ref-callback cache: avoids creating new closures on each render while cleaning up on unmount. */
export function makeRefCache<T>() {
  const refs = new Map<string, T>();
  const fns = new Map<string, (el: unknown) => void>();
  function setter(key: string) {
    let fn = fns.get(key);
    if (!fn) {
      fn = (el: unknown) => {
        if (el) { refs.set(key, el as T); }
        else { refs.delete(key); fns.delete(key); }
      };
      fns.set(key, fn);
    }
    return fn;
  }
  return { refs, setter };
}
