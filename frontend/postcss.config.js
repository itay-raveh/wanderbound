import rtlcss from "postcss-rtlcss";

// Wrap third-party CSS in rtl:ignore so postcss-rtlcss leaves it alone.
// Libraries like mapbox-gl rely on exact `left`/`right` positioning for
// canvas and markers — flipping them breaks the map entirely.
const skipVendorRtl = {
  postcssPlugin: "skip-vendor-rtl",
  Once(root, { Comment }) {
    const file = root.source?.input?.file ?? "";
    if (file.includes("node_modules")) {
      root.prepend(new Comment({ text: "rtl:begin:ignore" }));
      root.append(new Comment({ text: "rtl:end:ignore" }));
    }
  },
};

export default {
  plugins: [skipVendorRtl, rtlcss()],
};
