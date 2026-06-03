import { expect, test } from "@playwright/test";

test("renders the landing page when the initial auth-state request fails", async ({
  page,
}) => {
  const routerFailures: string[] = [];
  page.on("console", (message) => {
    const text = message.text();
    if (text.includes("Vue Router")) routerFailures.push(text);
  });

  await page.route("**/api/v1/auth/state", (route) =>
    route.fulfill({ status: 500, json: { detail: "backend unavailable" } }),
  );

  await page.goto("/editor");
  await expect(
    page.getByRole("heading", { name: "Wanderbound" }),
  ).toBeVisible();
  expect(routerFailures).toEqual([]);
});
