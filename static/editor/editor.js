document.addEventListener("DOMContentLoaded", () => initEditor());

function toggleVideo(overlay) {
    const wrapper = overlay.parentElement;
    const video = wrapper.querySelector("video");

    video.classList.add("active");
    video.play().then(() => video.focus());
    overlay.style.display = "none";
}

async function videoSetFrame(btn, stepId, videoSrc) {
    const wrapper = btn.parentElement;
    const video = wrapper.querySelector("video");

    if (!video) return;

    // If video is not active (user hasn't played it), we can't get a new frame easily unless we force load.
    // Assuming user played -> paused -> set frame.
    const timestamp = video.currentTime;

    btn.textContent = "Setting...";
    btn.disabled = true;

    try {
        const response = await fetch("/api/video", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                id: parseInt(stepId),
                video_src: videoSrc,
                timestamp: timestamp,
            }),
        });

        const data = await response.json();
        if (data.success) {
            btn.textContent = "Saved!";
            setTimeout(() => {
                btn.textContent = "Set Frame";
                btn.disabled = false;
                // Reload to see the new frame immediately
                window.location.reload();
            }, 1000);
        } else {
            alert("Failed to set frame: " + (data.error || "Unknown error"));
            btn.disabled = false;
            btn.textContent = "Set Frame";
        }
    } catch (e) {
        console.error(e);
        alert("Error setting frame");
        btn.disabled = false;
        btn.textContent = "Set Frame";
    }
}

function initEditor() {
    document.body.classList.add("is-editing");
    makePhotosDraggable();

    // Bind Save Button
    const saveBtn = document.getElementById("save-btn");
    if (saveBtn) {
        saveBtn.addEventListener("click", () => saveAllVisibleSteps());
    }

    // Keyboard Shortcuts for Video Scrubbing
    document.addEventListener("keydown", (e) => {
        // Only works if a video player is the focused element
        if (document.activeElement?.tagName !== "VIDEO") return;
        const activeVideo = document.activeElement;

        const FRAME_STEP = 0.04; // ~1 frame at 25fps

        switch (e.key) {
            case ",": // Frame back
            case "<":
                activeVideo.currentTime = Math.max(
                    0,
                    activeVideo.currentTime - FRAME_STEP
                );
                activeVideo.pause(); // Ensure we pause to see the frame
                break;
            case ".": // Frame forward
            case ">":
                activeVideo.currentTime = Math.min(
                    activeVideo.duration,
                    activeVideo.currentTime + FRAME_STEP
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
}

window.addPhotoPage = function (stepId, btn) {
    // Determine where to insert: before the button container
    const btnContainer = btn.closest(".add-page-container");

    // Create new page structure
    const newPage = document.createElement("div");
    newPage.className = "step-page photo-page page-container";
    newPage.dataset.stepId = stepId;

    newPage.innerHTML = `
        <div class="photo-page-container">
            <!-- Photos drop here -->
        </div>
    `;

    // Insert
    btnContainer.insertAdjacentElement("beforebegin", newPage);

    // Attach listeners
    const container = newPage.querySelector(".photo-page-container");
    container.addEventListener("dragover", handleDragOver);
    container.addEventListener("drop", handleDrop);
    container.addEventListener("dragleave", handleDragLeave);

    // Scroll to new page ?
    newPage.scrollIntoView({behavior: "smooth"});
};

function makePhotosDraggable() {
    const photoItems = document.querySelectorAll(".photo-item");
    const containers = document.querySelectorAll(".photo-page-container");

    photoItems.forEach((item) => {
        // item.draggable is now set in HTML
        item.addEventListener("dragstart", handleDragStart);
        item.addEventListener("dragend", handleDragEnd);

        // Add context menu for "Set Cover"
        item.addEventListener("contextmenu", handleContextMenu);
    });

    containers.forEach((container) => {
        container.addEventListener("dragover", handleDragOver);
        container.addEventListener("drop", handleDrop);
        container.addEventListener("dragleave", handleDragLeave);
    });
}

// Drag & Drop Handlers
let draggedItem = null;
let draggedSourceStepId = null;
let draggedSourceStepName = null;

function handleDragStart(e) {
    draggedItem = this;
    const stepPage = this.closest(".step-page");
    draggedSourceStepId = stepPage ? stepPage.dataset.stepId : null;
    draggedSourceStepName = stepPage ? stepPage.dataset.stepName : null;

    this.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
}

function handleDragEnd(_) {
    this.classList.remove("dragging");
    draggedItem = null;

    // Remove drag-over classes
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

async function handleDrop(e) {
    e.stopPropagation();
    this.classList.remove("drag-over");

    const itemToMove = draggedItem;
    if (
        itemToMove &&
        (this.contains(itemToMove) || this !== itemToMove.parentNode)
    ) {
        // Determine Destination Step
        const destStepPage = this.closest(".step-page");
        const destStepId = destStepPage ? destStepPage.dataset.stepId : null;

        // Standard Drop Logic (Reordering or Appending)
        // Advanced Drop: Reorder support
        // Check if we dropped ON TOP of another photo item
        const targetPhoto = e.target.closest(".photo-item");

        if (
            targetPhoto &&
            targetPhoto !== itemToMove &&
            this.contains(targetPhoto)
        ) {
            // Determine insertion direction based on mouse position
            const rect = targetPhoto.getBoundingClientRect();
            const midX = rect.left + rect.width / 2;

            if (e.clientX < midX) {
                targetPhoto.parentNode.insertBefore(itemToMove, targetPhoto);
            } else {
                targetPhoto.parentNode.insertBefore(
                    itemToMove,
                    targetPhoto.nextSibling
                );
            }
        } else {
            // Appended to container (empty space)
            this.appendChild(itemToMove);
        }

        // Find the step ID of this container (dest) and mark dirty
        if (destStepId) {
            markStepDirty(destStepId);
        }
    }
    return false;
}

// Context Menu
function handleContextMenu(e) {
    e.preventDefault();
    const photoItem = this;
    const photoPath = photoItem.dataset.photoPath;

    // Create simple custom menu

    const menu = document.createElement("div");
    menu.className = "editor-context-menu";
    menu.style.left = e.pageX + "px";
    menu.style.top = e.pageY + "px";

    menu.innerHTML = `
        <div class="menu-item" id="ctx-cover">Set as Cover</div>
        <div class="menu-item" id="ctx-hide">Hide Photo</div>
    `;

    document.body.appendChild(menu);

    // Close menu on click anywhere
    const closeMenu = () => {
        menu.remove();
        document.removeEventListener("click", closeMenu);
    };
    setTimeout(() => document.addEventListener("click", closeMenu), 0);

    // Actions
    document.getElementById("ctx-cover").onclick = () => {
        const stepPage = photoItem.closest(".step-page");
        const stepId = stepPage.dataset.stepId;
        updateStepCover(stepId, photoPath).then(() => location.reload());
    };

    document.getElementById("ctx-hide").onclick = () => {
        try {
            const stepPage = photoItem.closest(".step-page");
            if (!stepPage) {
                console.error("Could not find parent .step-page for photo", photoItem);
                return;
            }
            const stepId = stepPage.dataset.stepId;
            console.log("Hiding photo", photoPath, "for step", stepId);

            // Find the MAIN step page (not photo-page) which holds the hidden container
            const mainStepPage = document.querySelector(
                `.step-page[data-step-id="${stepId}"]:not(.photo-page)`
            );
            let hiddenContainer = null;

            if (mainStepPage) {
                hiddenContainer = mainStepPage.querySelector(
                    ".hidden-photos-container"
                );
            }

            if (!hiddenContainer) {
                // Fallback: create in main page if possible, or just append to main page
                if (mainStepPage) {
                    hiddenContainer = document.createElement("div");
                    hiddenContainer.className = "hidden-photos-container";
                    mainStepPage.appendChild(hiddenContainer);
                } else {
                    console.error("Could not find main step page for id", stepId);
                    alert("Error: Could not find main step page. Check console.");
                    return;
                }
            }

            hiddenContainer.appendChild(photoItem);
            console.log("Moved photo to hidden container");
            markStepDirty(stepId);
            console.log("Marked step dirty");
        } catch (e) {
            console.error("Error hiding photo:", e);
            alert("Error hiding photo: " + e.message);
        }
    };
}

const dirtySteps = new Set();

function markStepDirty(stepId) {
    if (!stepId) {
        console.warn("Attempted to mark undefined step as dirty");
        return;
    }
    if (!dirtySteps.has(stepId)) {
        dirtySteps.add(stepId);
        // Visual feedback
        const step = document.querySelector(`.step-page[data-step-id="${stepId}"]`);
        if (step) step.classList.add("is-dirty");

        // Enable Save button state if needed
        const btn = document.querySelector(".save-btn");
        btn.disabled = false;
    }
}

function collectStepLayout(stepId, overrides = {}) {
    if (!stepId) return null;

    // Gather all photos for this step
    const stepPages = document.querySelectorAll(
        `.step-page[data-step-id="${stepId}"] .photo-page-container`
    );

    const pages = [];
    stepPages.forEach((container) => {
        const pagePhotos = [];
        container.querySelectorAll(".photo-item").forEach((item) => {
            pagePhotos.push(JSON.parse(item.dataset.photo));
        });
        if (pagePhotos.length > 0) {
            pages.push({photos: pagePhotos});
        }
    });

    // Gather hidden photos
    const hiddenContainer = document.querySelector(
        `.step-page[data-step-id="${stepId}"]:not(.photo-page) .hidden-photos-container`
    );
    const hiddenPhotos = [];
    if (hiddenContainer) {
        hiddenContainer.querySelectorAll(".photo-item").forEach((item) => {
            hiddenPhotos.push(item.dataset.photoPath);
        });
    }

    // Gather Cover Photo ID
    const stepPage = document.querySelector(
        `.step-page[data-step-id="${stepId}"]`
    );

    return {
        id: parseInt(stepId),
        name: stepPage?.dataset.stepName,
        cover: stepPage?.dataset.stepCover,
        pages: pages,
        hidden_photos: hiddenPhotos,
        ...overrides,
    };
}

async function updateStepCover(stepId, cover) {
    try {
        const response = await fetch("/api/cover", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id: stepId, cover}),
        });

        const result = await response.json();
        if (!result.success) {
            throw new Error(result.error || "Cover update failed");
        }
    } catch (err) {
        console.error(err);
        alert(`Error saving: ${err.message}`);
    }
}

window.saveAllVisibleSteps = async function () {
    if (dirtySteps.size === 0) {
        alert("No changes to save.");
        return;
    }

    const btn = document.querySelector(".save-btn");
    btn.disabled = true;

    try {
        const allUpdates = [];
        for (const stepId of dirtySteps) {
            const data = collectStepLayout(stepId);
            if (data) allUpdates.push(data);
        }

        const response = await fetch("/api/layout", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({updates: allUpdates}),
        });

        const result = await response.json();
        if (!result.success) {
            throw new Error(result.error || "Layout update failed");
        }

        // Clear dirty state
        dirtySteps.clear();
        document
            .querySelectorAll(".is-dirty")
            .forEach((el) => el.classList.remove("is-dirty"));

        // Reload to see changes
        location.reload();
    } catch (err) {
        console.error(err);
        alert(`Error saving: ${err.message}`);
        btn.disabled = false;
    }
};
