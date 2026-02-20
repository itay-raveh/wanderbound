// noinspection TypeScriptUMDGlobal

async function apiCall(endpoint, body) {
  try {
    const response = await fetch("/api/" + endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      // noinspection ExceptionCaughtLocallyJS
      throw new Error(data.detail || `Request failed (${response.status})`);
    }
  } catch (err) {
    console.error(err);
    alert(err.message);
    throw err;
  }
}

function collectStepLayout(stepId) {
  const stepPhotoPages = document.querySelectorAll(
    `.step-page[data-step-id="${stepId}"] .photo-page-container`,
  );

  const pages = [];
  stepPhotoPages.forEach((container) => {
    const pagePhotos = [];

    container.querySelectorAll(".photo-item").forEach((item) => {
      pagePhotos.push(JSON.parse(item.dataset.photo));
    });

    if (pagePhotos.length > 0) pages.push({ photos: pagePhotos });
  });

  const hiddenContainer = document.querySelector(
    `.step-page[data-step-id="${stepId}"]:not(.photo-page) .hidden-photos-container`,
  );
  const hiddenPhotos = [];
  hiddenContainer.querySelectorAll(".photo-item").forEach((item) => {
    hiddenPhotos.push(item.dataset.photoPath);
  });

  const stepPage = document.querySelector(
    `.step-page[data-step-id="${stepId}"]`,
  );

  return {
    id: parseInt(stepId),
    name: stepPage.dataset.stepName,
    cover: stepPage.dataset.stepCover,
    pages,
    hidden_photos: hiddenPhotos,
  };
}

function updateStepCover(id, cover) {
  apiCall("cover", { id, cover }).then(location.reload);
}

function updateStepLayout(id) {
  apiCall("layout", collectStepLayout(id)).then(location.reload);
}

// --- Video Logic ---
function toggleVideo(overlay) {
  const wrapper = overlay.parentElement;
  const video = wrapper.querySelector("video");

  video.classList.add("active");
  video.play().then(() => video.focus());
  overlay.style.display = "none";
}

async function videoSetFrame(btn, stepId, src) {
  btn.textContent = "Setting...";
  btn.disabled = true;

  try {
    await apiCall("video", {
      id: parseInt(stepId),
      src,
      timestamp: btn.parentElement.querySelector("video").currentTime,
    });

    location.reload();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Set Frame";
  }
}

const FRAME_STEP = 1 / 30; // 1 frame at 30fps

// --- Initialization & Event Delegation ---
document.addEventListener("DOMContentLoaded", () => {
  // Keyboard Shortcuts for Video
  document.addEventListener("keydown", (e) => {
    const activeVideo = document.activeElement;
    if (activeVideo?.tagName !== "VIDEO") return;

    switch (e.key) {
      case ",":
      case "<":
        activeVideo.currentTime = Math.max(
          0,
          activeVideo.currentTime - FRAME_STEP,
        );
        activeVideo.pause();
        break;
      case ".":
      case ">":
        activeVideo.currentTime = Math.min(
          activeVideo.duration,
          activeVideo.currentTime + FRAME_STEP,
        );
        activeVideo.pause();
        break;
      case "Enter":
        e.preventDefault();
        const setFrameBtn =
          activeVideo.parentElement.querySelector(".set-frame-btn");
        if (setFrameBtn) setFrameBtn.click();
        break;
    }
  });

  // Drag & Drop Delegation
  document.addEventListener("dragstart", (e) => {
    if (e.target.matches(".photo-item")) handleDragStart.call(e.target, e);
    // Also handle images inside photo-item if they are the drag target
    else if (e.target.closest(".photo-item"))
      handleDragStart.call(e.target.closest(".photo-item"), e);
  });

  document.addEventListener("dragend", (e) => {
    if (draggedItem) handleDragEnd.call(draggedItem, e);
  });

  document.addEventListener("dragover", (e) => {
    const container = e.target.closest(".photo-page-container");
    if (container) handleDragOver.call(container, e);

    const addPageContainer = e.target.closest(".add-page-container");
    if (addPageContainer) handleDragOver.call(addPageContainer, e);
  });

  document.addEventListener("dragleave", (e) => {
    const container = e.target.closest(".photo-page-container");
    if (container) handleDragLeave.call(container, e);

    const addPageContainer = e.target.closest(".add-page-container");
    if (addPageContainer) handleDragLeave.call(addPageContainer, e);
  });

  document.addEventListener("drop", (e) => {
    const container = e.target.closest(".photo-page-container");
    if (container) handleDrop.call(container, e);

    const addPageContainer = e.target.closest(".add-page-container");
    if (addPageContainer) handleAddPageDrop.call(addPageContainer, e);
  });

  // Context Menu Delegation
  document.addEventListener("contextmenu", (e) => {
    const photoItem = e.target.closest(".photo-item");
    if (photoItem) handleContextMenu.call(photoItem, e);
  });
});

window.addPhotoPage = function (stepId, btn) {
  const newPage = document.createElement("div");
  newPage.className = "step-page photo-page page-container";
  newPage.dataset.stepId = stepId;
  newPage.innerHTML = `
        <div class="photo-page-container">
            <!-- Photos drop here -->
        </div>
    `;

  const btnContainer = btn.closest(".add-page-container");
  btnContainer.insertAdjacentElement("beforebegin", newPage);

  newPage.scrollIntoView({ behavior: "smooth" });
  return newPage;
};

// --- Drag & Drop Logic ---
let draggedItem = null;

function handleDragStart(e) {
  draggedItem = this;
  this.classList.add("dragging");
  e.dataTransfer.effectAllowed = "move";
}

function handleDragEnd(_) {
  this.classList.remove("dragging");
  draggedItem = null;
  document
    .querySelectorAll(".photo-page-container")
    .forEach((c) => c.classList.remove("drag-over"));
}

function handleDragOver(e) {
  e.preventDefault();
  this.classList.add("drag-over");
  return false;
}

function handleDragLeave(_) {
  this.classList.remove("drag-over");
}

function handleDrop(e) {
  e.stopPropagation();
  this.classList.remove("drag-over");

  // If no item is dragged, or it's not one of our children, return
  if (
    !draggedItem ||
    !(this.contains(draggedItem) || this !== draggedItem.parentNode)
  )
    return;

  const oldParent = draggedItem.parentNode;

  // If the item was dropped over another photo
  const targetPhoto = e.target.closest(".photo-item");
  if (
    targetPhoto &&
    targetPhoto !== draggedItem &&
    this.contains(targetPhoto)
  ) {
    // Check if it was dropped closer to the left side or right side of the other photo
    const rect = targetPhoto.getBoundingClientRect();
    const midX = rect.left + rect.width / 2;
    // And insert the item before or after the other photo respectively
    targetPhoto.parentNode.insertBefore(
      draggedItem,
      e.clientX < midX ? targetPhoto : targetPhoto.nextSibling,
    );
  } else {
    // Otherwise, `this` is simply a photo page
    this.appendChild(draggedItem);
  }

  // If the old parent is now empty and was a photo page (not the main step page), remove it
  if (
    oldParent !== this &&
    oldParent.closest(".photo-page") &&
    oldParent.querySelectorAll(".photo-item").length === 0
  ) {
    oldParent.closest(".step-page").remove();
  }

  // Update the layout
  updateStepLayout(this.closest(".step-page").dataset.stepId);
}

function handleAddPageDrop(e) {
  e.stopPropagation();
  this.classList.remove("drag-over");

  if (!draggedItem) return;

  // Find stepId
  // Previous sibling should be a step-page belonging to the same step
  const stepPage = this.previousElementSibling;

  // If the previous element is not a step page (e.g. at the very top?), try next sibling if it exists, or just fail safely
  const stepId = stepPage?.dataset?.stepId;
  if (!stepId) return;

  // Create the new page
  // We pass `this` as the button, since it's the container and addPhotoPage handles `closest('.add-page-container')`
  const newPage = window.addPhotoPage(parseInt(stepId), this);

  // Move the photo to the new page
  const newContainer = newPage.querySelector(".photo-page-container");
  handleDrop.call(newContainer, e);
}

// --- Context Menu ---
function handleContextMenu(e) {
  e.preventDefault();

  // Create menu
  const menu = document.createElement("div");
  menu.className = "editor-context-menu";
  menu.style.left = e.pageX + "px";
  menu.style.top = e.pageY + "px";
  menu.innerHTML = `
        <div class="menu-item" id="ctx-cover">Set as Cover</div>
        <div class="menu-item" id="ctx-hide">Hide Photo</div>
    `;
  document.body.appendChild(menu);
  const closeMenu = () => {
    menu.remove();
    document.removeEventListener("click", closeMenu);
  };
  setTimeout(() => document.addEventListener("click", closeMenu), 0);

  // "Set as Cover" action
  document.getElementById("ctx-cover").onclick = () => {
    updateStepCover(
      this.closest(".step-page").dataset.stepId,
      this.dataset.photoPath,
    );
  };

  // "Hide photo" action
  document.getElementById("ctx-hide").onclick = () => {
    const stepId = this.closest(".step-page").dataset.stepId;
    document
      .querySelector(
        `.step-page[data-step-id="${stepId}"]:not(.photo-page) .hidden-photos-container`,
      )
      .appendChild(this);
    updateStepLayout(stepId);
  };
}

// Force load lazy images before print
window.onbeforeprint = () => {
  document
    .querySelectorAll('img[loading="lazy"]')
    .forEach((img) => (img.loading = "eager"));
};

// --- Map Helpers ---
function getBezierPoint(t, p0, p1, p2) {
  const x = (1 - t) * (1 - t) * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0];
  const y = (1 - t) * (1 - t) * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1];
  return [x, y];
}

function getControlPoint(p0, p1, offsetScale) {
  const mid = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2];
  const dx = p1[0] - p0[0];
  const dy = p1[1] - p0[1];
  const nx = -dy;
  const ny = dx;
  const k = offsetScale * 0.2;
  return [mid[0] + nx * k, mid[1] + ny * k];
}

function getAngle(p0, p1) {
  const dy = p1[0] - p0[0];
  const dx = p1[1] - p0[1];
  return (Math.atan2(dy, dx) * 180) / Math.PI;
}

const PADDING = 100;

// Global Map Initialization Logic
window.initMapLogic = (containerId, segments, steps) => {
  const map = L.map(containerId, {
    zoomSnap: 0,
    zoomDelta: 0.1,
    preferCanvas: true,
    zoomControl: false,
    attributionControl: false,
    dragging: false,
    touchZoom: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    boxZoom: false,
    keyboard: false,
  });

  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  ).addTo(map);
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
  ).addTo(map);
  setTimeout(() => map.invalidateSize(), 500);

  const lineWeight = 3 - steps.length / 100;

  const bounds = [];
  segments.forEach((segment) => {
    const segPoints = segment.points.map((p) => [p.lat, p.lon]);
    bounds.push(segPoints);

    if (!segment.is_flight) {
      L.polyline(segPoints, {
        color: "#ffffff",
        weight: lineWeight * 2,
      }).addTo(map);
    } else {
      const pStart = segPoints[0];
      const pEnd = segPoints[segPoints.length - 1];
      const control = getControlPoint(pStart, pEnd, 0.5);
      const curvePoints = [];
      for (let i = 0; i <= 100; i++) {
        curvePoints.push(getBezierPoint(i / 100, pStart, control, pEnd));
      }
      L.polyline(curvePoints, {
        color: "#ffffff",
        weight: lineWeight,
        dashArray: "1, 5",
        lineCap: "round",
      }).addTo(map);

      // Plane Icon
      const midT = 0.55;
      const midPos = getBezierPoint(midT, pStart, control, pEnd);
      const posPlus = getBezierPoint(midT + 0.01, pStart, control, pEnd);
      const angle = getAngle(midPos, posPlus);
      L.marker(midPos, {
        icon: L.divIcon({
          className: "plane-icon-container",
          html: `<img src="https://cdn.prod.polarsteps.com/65969828189e33620c7fe02b236c1f2734e312df/assets/airplane-marker.png" style="transform: rotate(${-angle}deg); display: block;" alt="Airplane Icon">`,
          iconSize: [16, 15],
        }),
      }).addTo(map);
    }
  });

  map.fitBounds(bounds, { padding: [PADDING, PADDING], maxZoom: 18 });

  const iconSize = 60 - steps.length / 5;

  steps.forEach((step) => {
    L.marker([step.lat_val, step.lon_val], {
      icon: L.divIcon({
        className: "step-marker-icon",
        html: `<div class="custom-marker-inner" style="background-image: url('${step.cover_photo}')"></div>`,
        iconSize: [iconSize, iconSize],
        iconAnchor: [iconSize / 2, iconSize / 2],
        popupAnchor: [0, -iconSize / 2],
      }),
    }).addTo(map);
  });
};
