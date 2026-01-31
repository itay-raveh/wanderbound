document.addEventListener("DOMContentLoaded", () => initEditor());

// --- API Helper ---
async function apiCall(endpoint, body) {
    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body),
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || `Request failed (${response.status})`);
        }
        return response;
    } catch (err) {
        console.error(err);
        alert(err.message);
        throw err; // Re-throw so caller can handle UI state
    }
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
    const wrapper = btn.parentElement;
    const video = wrapper.querySelector("video");
    if (!video) return;

    // Assuming user played -> paused -> set frame.
    const timestamp = video.currentTime;

    btn.textContent = "Setting...";
    btn.disabled = true;

    try {
        await apiCall("/api/video", {
            id: parseInt(stepId),
            src,
            timestamp,
        });

        btn.textContent = "Saved!";
        setTimeout(() => {
            btn.textContent = "Set Frame";
            btn.disabled = false;
            window.location.reload();
        }, 1000);
    } catch (e) {
        btn.disabled = false;
        btn.textContent = "Set Frame";
    }
}

// --- Initialization & Event Delegation ---
function initEditor() {
    setupGlobalListeners();

    // Bind Save Button
    const saveBtn = document.getElementById("save-btn");
    if (saveBtn) {
        saveBtn.addEventListener("click", () => saveAllVisibleSteps());
    }
}

function setupGlobalListeners() {
    // Keyboard Shortcuts for Video
    document.addEventListener("keydown", (e) => {
        if (document.activeElement?.tagName !== "VIDEO") return;
        const activeVideo = document.activeElement;
        const FRAME_STEP = 0.04; // ~1 frame at 25fps

        switch (e.key) {
            case ",":
            case "<":
                activeVideo.currentTime = Math.max(0, activeVideo.currentTime - FRAME_STEP);
                activeVideo.pause();
                break;
            case ".":
            case ">":
                activeVideo.currentTime = Math.min(activeVideo.duration, activeVideo.currentTime + FRAME_STEP);
                activeVideo.pause();
                break;
            case "Enter":
                e.preventDefault();
                const setFrameBtn = activeVideo.parentElement.querySelector(".set-frame-btn");
                if (setFrameBtn) setFrameBtn.click();
                break;
        }
    });

    // Drag & Drop Delegation
    document.addEventListener("dragstart", (e) => {
        if (e.target.matches(".photo-item")) handleDragStart.call(e.target, e);
        // Also handle images inside photo-item if they are the drag target
        else if (e.target.closest(".photo-item")) handleDragStart.call(e.target.closest(".photo-item"), e);
    });

    document.addEventListener("dragend", (e) => {
        if (draggedItem) handleDragEnd.call(draggedItem, e);
    });

    document.addEventListener("dragover", (e) => {
        const container = e.target.closest(".photo-page-container");
        if (container) handleDragOver.call(container, e);
    });

    document.addEventListener("dragleave", (e) => {
        const container = e.target.closest(".photo-page-container");
        if (container) handleDragLeave.call(container, e);
    });

    document.addEventListener("drop", (e) => {
        const container = e.target.closest(".photo-page-container");
        if (container) handleDrop.call(container, e);
    });

    // Context Menu Delegation
    document.addEventListener("contextmenu", (e) => {
        const photoItem = e.target.closest(".photo-item");
        if (photoItem) handleContextMenu.call(photoItem, e);
    });
}

window.addPhotoPage = function (stepId, btn) {
    const btnContainer = btn.closest(".add-page-container");
    const newPage = document.createElement("div");
    newPage.className = "step-page photo-page page-container";
    newPage.dataset.stepId = stepId;

    newPage.innerHTML = `
        <div class="photo-page-container">
            <!-- Photos drop here -->
        </div>
    `;

    btnContainer.insertAdjacentElement("beforebegin", newPage);
    newPage.scrollIntoView({behavior: "smooth"});
    // No need to attach listeners manually thanks to delegation!
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
    document.querySelectorAll(".photo-page-container").forEach((c) => c.classList.remove("drag-over"));
}

function handleDragOver(e) {
    e.preventDefault();
    this.classList.add("drag-over");
    return false;
}

function handleDragLeave(_) {
    this.classList.remove("drag-over");
}

async function handleDrop(e) {
    e.stopPropagation();
    this.classList.remove("drag-over");

    const itemToMove = draggedItem;
    if (itemToMove && (this.contains(itemToMove) || this !== itemToMove.parentNode)) {
        const destStepPage = this.closest(".step-page");
        const destStepId = destStepPage ? destStepPage.dataset.stepId : null;
        const targetPhoto = e.target.closest(".photo-item");

        if (targetPhoto && targetPhoto !== itemToMove && this.contains(targetPhoto)) {
            const rect = targetPhoto.getBoundingClientRect();
            const midX = rect.left + rect.width / 2;
            if (e.clientX < midX) {
                targetPhoto.parentNode.insertBefore(itemToMove, targetPhoto);
            } else {
                targetPhoto.parentNode.insertBefore(itemToMove, targetPhoto.nextSibling);
            }
        } else {
            this.appendChild(itemToMove);
        }

        if (destStepId) markStepDirty(destStepId);
    }
    return false;
}

// --- Context Menu ---
function handleContextMenu(e) {
    e.preventDefault();
    const photoItem = this;
    const photoPath = photoItem.dataset.photoPath;

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

    document.getElementById("ctx-cover").onclick = () => {
        const stepPage = photoItem.closest(".step-page");
        const stepId = stepPage.dataset.stepId;
        updateStepCover(stepId, photoPath).then(() => location.reload());
    };

    document.getElementById("ctx-hide").onclick = () => {
        const stepPage = photoItem.closest(".step-page");
        if (!stepPage) return;
        const stepId = stepPage.dataset.stepId;

        const mainStepPage = document.querySelector(`.step-page[data-step-id="${stepId}"]:not(.photo-page)`);
        let hiddenContainer = mainStepPage?.querySelector(".hidden-photos-container");

        if (!hiddenContainer && mainStepPage) {
            hiddenContainer = document.createElement("div");
            hiddenContainer.className = "hidden-photos-container";
            mainStepPage.appendChild(hiddenContainer);
        }

        if (hiddenContainer) {
            hiddenContainer.appendChild(photoItem);
            markStepDirty(stepId);
        } else {
            alert("Error: Could not find main step page.");
        }
    };
}

// --- State Management ---
const dirtySteps = new Set();

function markStepDirty(stepId) {
    if (!stepId) return;
    if (!dirtySteps.has(stepId)) {
        dirtySteps.add(stepId);
        document.querySelector(`.step-page[data-step-id="${stepId}"]`)?.classList.add("is-dirty");
        document.querySelector(".save-btn").disabled = false;
    }
}

function collectStepLayout(stepId) {
    if (!stepId) return null;
    const stepPages = document.querySelectorAll(`.step-page[data-step-id="${stepId}"] .photo-page-container`);
    const pages = [];
    stepPages.forEach((container) => {
        const pagePhotos = [];
        container.querySelectorAll(".photo-item").forEach((item) => {
            pagePhotos.push(JSON.parse(item.dataset.photo));
        });
        if (pagePhotos.length > 0) pages.push({photos: pagePhotos});
    });

    const hiddenContainer = document.querySelector(`.step-page[data-step-id="${stepId}"]:not(.photo-page) .hidden-photos-container`);
    const hiddenPhotos = [];
    if (hiddenContainer) {
        hiddenContainer.querySelectorAll(".photo-item").forEach((item) => {
            hiddenPhotos.push(item.dataset.photoPath);
        });
    }

    const stepPage = document.querySelector(`.step-page[data-step-id="${stepId}"]`);
    return {
        id: parseInt(stepId),
        name: stepPage?.dataset.stepName,
        cover: stepPage?.dataset.stepCover,
        pages: pages,
        hidden_photos: hiddenPhotos,
    };
}

async function updateStepCover(stepId, cover) {
    await apiCall("/api/cover", {id: stepId, cover});
}

window.saveAllVisibleSteps = async function () {
    if (dirtySteps.size === 0) return alert("No changes to save.");

    const btn = document.querySelector(".save-btn");
    btn.disabled = true;

    try {
        const allUpdates = Array.from(dirtySteps).map(id => collectStepLayout(id)).filter(Boolean);
        await apiCall("/api/layout", {updates: allUpdates});

        dirtySteps.clear();
        document.querySelectorAll(".is-dirty").forEach((el) => el.classList.remove("is-dirty"));
        location.reload();
    } catch (err) {
        btn.disabled = false;
    }
};

// Force load lazy images before print
window.onbeforeprint = () => {
    document.querySelectorAll('img[loading="lazy"]').forEach((img) => img.loading = "eager");
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
    return Math.atan2(dy, dx) * 180 / Math.PI;
}

// Global Map Initialization Logic
window.initMapLogic = function (containerId, segments, steps) {
    const ICON_SIZE = containerId === "map-main" ? 20 : 60;
    const LINE_WEIGHT = containerId === "map-main" ? 1 : 2;
    const PADDING = 100;

    console.log("Initializing Map Logic for", containerId);
    const mapContainer = document.getElementById(containerId);
    if (!mapContainer) return;

    const loadingText = mapContainer.parentElement.querySelector('.map-loading-text');

    if (typeof L === 'undefined') {
        if (loadingText) loadingText.textContent = "Error: Leaflet JS (L) is not defined.";
        return;
    }

    try {
        const map = L.map(containerId, {
            zoomSnap: 0, zoomDelta: 0.1, preferCanvas: true, zoomControl: false,
            attributionControl: false, dragging: false, touchZoom: false,
            scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false, keyboard: false
        });

        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {}).addTo(map);
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {}).addTo(map);

        if (loadingText) loadingText.textContent = "Map Loading... Tiles";
        // Hide loading text after delay/load
        setTimeout(() => { if (loadingText) loadingText.style.display = 'none'; }, 2000);
        setTimeout(() => map.invalidateSize(), 500);

        const createIcon = (url) => {
            if (url && url !== 'None' && url !== '') {
                return L.divIcon({
                    className: `step-marker-${containerId}`,
                    html: `<div class="custom-marker-inner" style="background-image: url('${url}');"></div>`,
                    iconSize: [ICON_SIZE, ICON_SIZE],
                    iconAnchor: [ICON_SIZE / 2, ICON_SIZE / 2],
                    popupAnchor: [0, -ICON_SIZE / 2]
                });
            }
            return L.divIcon({ className: 'step-marker-icon', iconSize: [12, 12], iconAnchor: [6, 6] });
        };

        const bounds = [];
        segments.forEach(segment => {
            const segPoints = segment.points.map(p => [p.lat, p.lon]);
            bounds.push(segPoints);

            if (!segment.is_flight) {
                L.polyline(segPoints, { color: '#ffffff', weight: LINE_WEIGHT * 2 }).addTo(map);
            } else {
                const pStart = segPoints[0];
                const pEnd = segPoints[segPoints.length - 1];
                const control = getControlPoint(pStart, pEnd, 0.5);
                const curvePoints = [];
                for (let i = 0; i <= 100; i++) {
                    curvePoints.push(getBezierPoint(i / 100, pStart, control, pEnd));
                }
                L.polyline(curvePoints, { color: '#ffffff', weight: LINE_WEIGHT, dashArray: '1, 5', lineCap: 'round' }).addTo(map);

                // Plane Icon
                const midT = 0.55;
                const midPos = getBezierPoint(midT, pStart, control, pEnd);
                const posPlus = getBezierPoint(midT + 0.01, pStart, control, pEnd);
                const angle = getAngle(midPos, posPlus);
                const planeIcon = L.divIcon({
                    className: 'plane-icon-container',
                    html: `<img src="https://cdn.prod.polarsteps.com/65969828189e33620c7fe02b236c1f2734e312df/assets/airplane-marker.png" style="transform: rotate(${-angle}deg); display: block;" alt="Airplane Icon">`,
                    iconSize: [16, 15],
                });
                L.marker(midPos, {icon: planeIcon, zIndexOffset: -1000}).addTo(map);
            }
        });

        if (bounds.length) map.fitBounds(bounds, { padding: [PADDING, PADDING], maxZoom: 18 });

        steps.forEach(step => {
            L.marker([step.lat_val, step.lon_val], {
                icon: createIcon(step.cover_photo),
                zIndexOffset: 1000
            }).addTo(map);
        });

        console.log("Map initialized successfully for", containerId);
    } catch (e) {
        console.error("Map initialization error:", e);
        if (loadingText) {
            loadingText.textContent = "Error loading map: " + e.message;
            loadingText.style.color = "red";
        }
    }
};
