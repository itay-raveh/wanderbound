import { vi } from "vitest";

const mapOn = vi.fn();

const Map = vi.fn(() => ({
  on: mapOn,
  off: vi.fn(),
  once: vi.fn(),
  remove: vi.fn(),
  addControl: vi.fn(),
  removeControl: vi.fn(),
  addSource: vi.fn(),
  removeSource: vi.fn(),
  addLayer: vi.fn(),
  removeLayer: vi.fn(),
  getSource: vi.fn(),
  getLayer: vi.fn(),
  setLayoutProperty: vi.fn(),
  setPaintProperty: vi.fn(),
  flyTo: vi.fn(),
  fitBounds: vi.fn(),
  resize: vi.fn(),
  getCanvas: vi.fn(() => ({ style: {} })),
  getContainer: vi.fn(() => document.createElement("div")),
  loaded: vi.fn(() => true),
  isStyleLoaded: vi.fn(() => true),
}));

const NavigationControl = vi.fn();

const Marker = vi.fn(() => ({
  setLngLat: vi.fn().mockReturnThis(),
  addTo: vi.fn().mockReturnThis(),
  remove: vi.fn(),
  getElement: vi.fn(() => document.createElement("div")),
  getLngLat: vi.fn(() => ({ lng: 0, lat: 0 })),
  on: vi.fn().mockReturnThis(),
  setDraggable: vi.fn().mockReturnThis(),
}));

const Popup = vi.fn(() => ({
  setLngLat: vi.fn().mockReturnThis(),
  setHTML: vi.fn().mockReturnThis(),
  addTo: vi.fn().mockReturnThis(),
  remove: vi.fn(),
}));

export default { Map, NavigationControl, Marker, Popup, supported: () => true };
