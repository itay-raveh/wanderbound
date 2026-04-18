if (new URLSearchParams(location.search).has("error")) {
  document.getElementById("message").textContent =
    "Could not connect Google Photos. Close this tab and try again.";
} else {
  const channel = new BroadcastChannel("wanderbound-oauth");
  channel.postMessage({ type: "google-photos-connected" });
  channel.close();
}
