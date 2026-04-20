const params = new URLSearchParams(location.search);

if (params.has("error")) {
  document.getElementById("message").textContent =
    "Could not connect Google Photos. Close this tab and try again.";
} else {
  const nonce = params.get("nonce");
  if (nonce) {
    const channel = new BroadcastChannel(`wanderbound-oauth-${nonce}`);
    channel.postMessage({ type: "google-photos-connected" });
    channel.close();
  }
}
