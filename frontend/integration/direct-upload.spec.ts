import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const frontendOrigin = process.env.DIRECT_UPLOAD_BASE_URL;
const garageOrigin = process.env.UPLOAD_S3_BROWSER_ORIGIN;
const fixturePath = process.env.DIRECT_UPLOAD_FIXTURE;
const projectName = process.env.COMPOSE_PROJECT_NAME;
const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url));
const execFileAsync = promisify(execFile);

if (!frontendOrigin || !garageOrigin || !fixturePath || !projectName) {
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
  await compose("exec", "-T", "backend", "python", "-c", script, `${userId}`);
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
  await compose("exec", "-T", "backend", "python", "-c", script, uploadId);
}

test("uploads a multipart ZIP directly to Garage and imports it", async ({
  page,
}) => {
  test.setTimeout(120_000);
  let directPartUploads = 0;
  page.on("request", (request) => {
    if (
      request.method() === "PUT" &&
      new URL(request.url()).origin === garageOrigin
    ) {
      directPartUploads += 1;
    }
  });

  const demo = await page
    .context()
    .request.post(`${frontendOrigin}/api/v1/users/demo`);
  expect(demo.ok()).toBe(true);
  const demoUser = ((await demo.json()) as { user: { id: number } }).user;
  await prepareDemoForUpload(demoUser.id);
  await page.goto("/upload");

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

  await expect(fileInput).not.toBeAttached({ timeout: 90_000 });

  expect(directPartUploads).toBeGreaterThan(1);
  await verifyTemporaryDataRemoved(uploadId);
});
