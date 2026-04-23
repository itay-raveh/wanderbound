/** Abort-aware sleep. Resolves after `ms`, rejects if `signal` fires first. */
export function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason as Error);
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(timer);
      reject(signal.reason as Error);
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
}
