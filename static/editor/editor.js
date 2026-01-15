/**
 * Manual Layout Editor for Polarsteps Album
 */

document.addEventListener("DOMContentLoaded", () => initEditor());

function initEditor() {
    makePhotosDraggable();
    injectEditorUI();
    injectAddPageButtons();
}

function injectAddPageButtons() {
    // Find all step groupings.
    // We can assume steps are sequential blocks defined by data-step-id.
    const steps = new Set();
    document.querySelectorAll(".step-page[data-step-id]").forEach((el) => steps.add(el.dataset.stepId));

    steps.forEach((stepId) => {
        // Find the last visible element for this step to append the button after
        const stepPages = document.querySelectorAll(`.step-page[data-step-id="${stepId}"]`);
        const lastPage = stepPages[stepPages.length - 1];

        if (lastPage) {
            const btnContainer = document.createElement("div");
            btnContainer.className = "add-page-container";
            btnContainer.innerHTML = `<button class="add-page-btn" title="Add Photo Page" onclick="addPhotoPage('${stepId}', this)">+</button>`;
            lastPage.insertAdjacentElement("afterend", btnContainer);
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
        item.draggable = true;
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

function injectEditorUI() {
    const saveBtn = document.createElement("button");
    saveBtn.className = "save-btn";
    saveBtn.innerHTML = "SAVE"
    saveBtn.addEventListener("click", () => saveAllVisibleSteps());
    saveBtn.disabled = true;
    document.body.appendChild(saveBtn);
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
    if (itemToMove && (this.contains(itemToMove) || this !== itemToMove.parentNode)) {
        // Determine Destination Step
        const destStepPage = this.closest(".step-page");
        const destStepId = destStepPage ? destStepPage.dataset.stepId : null;

        // Standard Drop Logic (Reordering or Appending)
        // Advanced Drop: Reorder support
        // Check if we dropped ON TOP of another photo item
        const targetPhoto = e.target.closest(".photo-item");

        if (targetPhoto && targetPhoto !== itemToMove && this.contains(targetPhoto)) {
            // Determine insertion direction based on mouse position
            const rect = targetPhoto.getBoundingClientRect();
            const midX = rect.left + rect.width / 2;

            if (e.clientX < midX) {
                targetPhoto.parentNode.insertBefore(itemToMove, targetPhoto);
            } else {
                targetPhoto.parentNode.insertBefore(itemToMove, targetPhoto.nextSibling);
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
            const mainStepPage = document.querySelector(`.step-page[data-step-id="${stepId}"]:not(.photo-page)`);
            let hiddenContainer = null;

            if (mainStepPage) {
                hiddenContainer = mainStepPage.querySelector(".hidden-photos-container");
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
    const stepPages = document.querySelectorAll(`.step-page[data-step-id="${stepId}"] .photo-page-container`);

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
    const hiddenContainer = document.querySelector(`.step-page[data-step-id="${stepId}"]:not(.photo-page) .hidden-photos-container`);
    const hiddenPhotos = [];
    if (hiddenContainer) {
        hiddenContainer.querySelectorAll(".photo-item").forEach((item) => {
            hiddenPhotos.push(item.dataset.photoPath);
        });
    }

    // Gather Cover Photo ID
    const stepPage = document.querySelector(`.step-page[data-step-id="${stepId}"]`);

    return {
        id: parseInt(stepId),
        name: stepPage?.dataset.stepName,
        cover: stepPage?.dataset.stepCover,
        pages: pages,
        hidden_photos: hiddenPhotos, ...overrides,
    };
}

async function updateStepCover(stepId, cover) {
    try {
        const response = await fetch("/api/cover", {
            method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: stepId, cover}),
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
            method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({updates: allUpdates}),
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
