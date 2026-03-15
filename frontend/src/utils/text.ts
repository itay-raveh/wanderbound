const RTL_PATTERN = /[\u0590-\u06FF]/;

export function chooseTextDir(text: string): "rtl" | "ltr" {
  return RTL_PATTERN.test(text) ? "rtl" : "ltr";
}
