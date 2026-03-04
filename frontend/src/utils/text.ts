export function chooseTextDir(text: string): "rtl" | "ltr" {
  //  Hebrew                            Arabic
  if (/[\u0590-\u05ff]/.test(text) || /[\u0600-\u06ff]/.test(text))
    return "rtl";

  return "ltr";
}
