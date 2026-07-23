import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const garageOrigin = "http://localhost:3900";
const fixturePath = process.env.DIRECT_UPLOAD_FIXTURE;
const projectName = process.env.COMPOSE_PROJECT_NAME;
const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url));
const execFileAsync = promisify(execFile);

if (!fixturePath || !projectName) {
  throw new Error("direct upload integration environment is incomplete");
}

async function compose(...args: string[]): Promise<string> {
  const { stdout } = await execFileAsync(
    "docker",
    [
      "compose",
      "--project-name",
      projectName,
      "-f",
      `${repositoryRoot}/compose.yml`,
      "-f",
      `${repositoryRoot}/frontend/integration/compose.yml`,
      ...args,
    ],
    { cwd: repositoryRoot, env: process.env },
  );
  return stdout;
}

async function prepareDemoForUpload(userId: number): Promise<void> {
  const script = `
import asyncio
import sys
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.db import get_engine
from app.models.user import User

async def main():
    async with AsyncSession(get_engine()) as session:
        user = await session.get(User, int(sys.argv[1]))
        user.album_ids = []
        session.add(user)
        await session.commit()

asyncio.run(main())
`;
  await compose("exec", "-T", "app", "python", "-c", script, `${userId}`);
}

async function verifyTemporaryDataRemoved(uploadId: string): Promise<void> {
  const script = `
import sys
from app.core.config import get_settings
from app.services.upload_store import UploadStoreError, build_upload_store

settings = get_settings()
store = build_upload_store(settings)
try:
    store.head(f"uploads/{sys.argv[1]}.zip")
except UploadStoreError as exc:
    if exc.code not in {"404", "NoSuchKey", "NotFound"}:
        raise
else:
    raise RuntimeError("temporary object remains")
finally:
    store.close()

if (settings.DATA_FOLDER / "upload-work" / sys.argv[1]).exists():
    raise RuntimeError("local upload work remains")
`;
  await compose("exec", "-T", "app", "python", "-c", script, uploadId);
}

const developmentOrigins = [
  "http://localhost:8000",
  "http://127.0.0.1:8000",
  "http://localhost:5173",
] as const;

test("allows upload preflights from every development origin", async ({
  request,
}) => {
  for (const origin of developmentOrigins) {
    const response = await request.fetch(
      `${garageOrigin}/wanderbound-uploads/uploads/cors-check.zip`,
      {
        method: "OPTIONS",
        headers: {
          Origin: origin,
          "Access-Control-Request-Method": "PUT",
          "Access-Control-Request-Headers": "content-type,x-amz-content-sha256",
        },
      },
    );

    expect(response.status()).toBe(200);
    expect([origin, "*"]).toContain(
      response.headers()["access-control-allow-origin"],
    );
  }
});

test("uploads a multipart ZIP directly from the Vite origin", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const appOrigin = "http://localhost:5173";
  let directPartUploads = 0;
  page.on("request", (request) => {
    if (
      request.method() === "PUT" &&
      new URL(request.url()).origin === garageOrigin
    ) {
      directPartUploads += 1;
    }
  });

  const demo = await page.request.post(`${appOrigin}/api/v1/users/demo`);
  expect(demo.ok()).toBe(true);
  const demoUser = ((await demo.json()) as { user: { id: number } }).user;
  await prepareDemoForUpload(demoUser.id);
  await page.goto(`${appOrigin}/upload`);

  const created = page.waitForResponse(
    (response) =>
      response.status() === 201 &&
      new URL(response.url()).pathname === "/api/v1/users/uploads/s3/multipart",
  );

  const fileInput = page.locator('input[type="file"]');
  await expect(fileInput).toBeAttached();
  await fileInput.setInputFiles(fixturePath);
  const uploadId = ((await (await created).json()) as { uploadId: string })
    .uploadId;

  await expect(
    page.getByRole("heading", { name: "Choose albums" }),
  ).toBeVisible({ timeout: 90_000 });
  await page.getByLabel("Trip albums").click();
  await page.getByRole("option", { name: "trip-100" }).click();
  await page.getByRole("button", { name: "Import selected albums" }).click();
  await expect(fileInput).not.toBeAttached({ timeout: 90_000 });

  expect(directPartUploads).toBeGreaterThan(1);
  await verifyTemporaryDataRemoved(uploadId);
});
