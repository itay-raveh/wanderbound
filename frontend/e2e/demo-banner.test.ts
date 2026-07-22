import { expect, test } from "./fixtures";
import {
  mockAuthStateAuthenticated,
  mockUser,
} from "../tests/fixtures/mocks";

test("keeps the demo CTA visible while scrolling the album", async ({
  authedPage: page,
}) => {
  const demoUser = { ...mockUser, is_demo: true };
  await page.route("**/api/v1/auth/state", (route) =>
    route.fulfill({
      json: { ...mockAuthStateAuthenticated, user: demoUser },
    }),
  );
  await page.route("**/api/v1/users", (route) =>
    route.fulfill({ json: demoUser }),
  );
  await page.route("**/api/v1/users/demo", (route) =>
    route.fulfill({ status: 204, body: "" }),
  );
  await page.setViewportSize({ width: 1600, height: 500 });
  await page.goto("/editor");

  const cta = page.getByRole("button", { name: "Sign in with your own trip" });
  await expect(cta).toBeVisible({ timeout: 15_000 });
  const initialBox = await cta.boundingBox();
  expect(initialBox).not.toBeNull();

  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await expect
    .poll(() => page.evaluate(() => window.scrollY))
    .toBeGreaterThan(0);

  await expect(cta).toBeInViewport();
  const scrolledBox = await cta.boundingBox();
  expect(scrolledBox).not.toBeNull();
  expect(scrolledBox!.y).toBe(initialBox!.y);

  await cta.click();
  await expect(page).toHaveURL("/");
});
