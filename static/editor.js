/**
 * Manual Layout Editor for Polarsteps Album
 */

document.addEventListener("DOMContentLoaded", () => {
  initEditor();
});

function initEditor() {
  console.log("Initializing Editor Mode...");
  makePhotosDraggable();
  injectEditorUI();
}

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
  // Inject "Hidden Photos" bin or controls if we want them visible
  // For now, we'll keep hidden photos in a hidden div, so they are just removed from view.
  // To restore them, we'd need a "Manage Hidden" UI.
  // MVP: Context menu -> Hide. To restore, user must manually edit JSON or reset.

  // Global Save Control Panel
  const controlPanel = document.createElement("div");
  controlPanel.className = "editor-control-panel";
  controlPanel.innerHTML = `
        <div class="editor-status">Editor Mode</div>
        <div class="editor-actions">
           <button onclick="saveAllVisibleSteps()">Save Changes</button>
        </div>
    `;
  document.body.appendChild(controlPanel);

  // Inject styles for context menu
  const style = document.createElement("style");
  style.textContent = `
    .editor-context-menu {
        position: absolute;
        background: white;
        border: 1px solid #ccc;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.2);
        z-index: 10000;
        border-radius: 4px;
        overflow: hidden;
    }
    .menu-item {
        padding: 8px 12px;
        cursor: pointer;
        font-size: 14px;
        color: #333;
    }
    .menu-item:hover {
        background: #f0f0f0;
    }
    .is-dirty {
        border: 2px solid orange; /* Visual cue for modified steps */
    }
  `;
  document.head.appendChild(style);
}

// Drag & Drop Handlers
let draggedItem = null;

function handleDragStart(e) {
  draggedItem = this;
  this.classList.add("dragging");
  e.dataTransfer.effectAllowed = "move";
}

function handleDragEnd(e) {
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

function handleDragLeave(e) {
  this.classList.remove("drag-over");
}

function handleDrop(e) {
  e.stopPropagation();
  this.classList.remove("drag-over");

  if (draggedItem && this !== draggedItem.parentNode) {
    this.appendChild(draggedItem);
    // Find the step ID of this container
    const stepPage = this.closest(".step-page");
    if (stepPage) {
      const stepId = stepPage.dataset.stepId;
      markStepDirty(stepId);
    }
  }
  return false;
}

// Context Menu
function handleContextMenu(e) {
  e.preventDefault();
  const photoItem = this;
  const photoId = photoItem.dataset.photoId;

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
    if (confirm("Set this as cover?")) {
      saveStepLayout(stepId, { cover_photo_id: photoId }).then(() =>
        location.reload()
      );
    }
  };

  document.getElementById("ctx-hide").onclick = () => {
    const stepPage = photoItem.closest(".step-page");
    if (!stepPage) {
      console.error("Could not find parent .step-page for photo", photoItem);
      return;
    }
    const stepId = stepPage.dataset.stepId;
    console.log("Hiding photo", photoId, "for step", stepId);

    // Find the MAIN step page (not photo-page) which holds the hidden container
    const mainStepPage = document.querySelector(
      `.step-page[data-step-id="${stepId}"]:not(.photo-page)`
    );
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
        return;
      }
    }

    hiddenContainer.appendChild(photoItem);
    markStepDirty(stepId);
  };
}

// State Management
// State Management
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
    const btn = document.querySelector(".editor-actions button");
    if (btn) btn.innerText = "Save Changes *";
  }
}

async function saveStepLayout(stepId, overrides = {}) {
  if (!stepId) {
    console.error("saveStepLayout called with missing stepId");
    return null;
  }

  // Gather all photos for this step
  const stepPages = document.querySelectorAll(
    `.step-page[data-step-id="${stepId}"] .photo-page-container`
  );

  const pages = [];
  stepPages.forEach((container) => {
    const pagePhotos = [];
    container.querySelectorAll(".photo-item").forEach((item) => {
      pagePhotos.push(item.dataset.photoId);
    });
    if (pagePhotos.length > 0) {
      pages.push({ photos: pagePhotos });
    }
  });

  // Gather hidden photos
  const hiddenContainer = document.querySelector(
    `.step-page[data-step-id="${stepId}"] .hidden-photos-container`
  );
  const hiddenPhotos = [];
  if (hiddenContainer) {
    hiddenContainer.querySelectorAll(".photo-item").forEach((item) => {
      hiddenPhotos.push(item.dataset.photoId);
    });
  }

  // Gather Cover Photo ID
  const stepPage = document.querySelector(
    `.step-page[data-step-id="${stepId}"]`
  );
  let currentCoverId = null;
  if (stepPage) {
    const coverImg = stepPage.querySelector(".main-image");
    if (coverImg && coverImg.dataset.photoId) {
      currentCoverId = coverImg.dataset.photoId;
    }
  }

  const payload = {
    step_id: parseInt(stepId),
    pages: pages,
    hidden_photos: hiddenPhotos,
    cover_photo_id: currentCoverId,
    ...overrides,
  };

  console.log(`Saving layout for step ${stepId}:`, payload);

  return fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

window.saveAllVisibleSteps = async function () {
  if (dirtySteps.size === 0) {
    alert("No changes to save.");
    return;
  }

  const btn = document.querySelector(".editor-actions button");
  const originalText = btn.innerText;
  btn.innerText = "Saving...";
  btn.disabled = true;

  try {
    // Save sequentially to avoid race conditions in file writing
    for (const stepId of dirtySteps) {
      const response = await saveStepLayout(stepId);
      if (!response || !response.ok) {
        throw new Error(`Failed to save step ${stepId}`);
      }
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
    btn.innerText = originalText;
    btn.disabled = false;
  }
};
