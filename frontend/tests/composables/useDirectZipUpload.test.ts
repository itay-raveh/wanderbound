import { completeIngestion, uploadProgress } from "@/client";
import { followUploadIngestion } from "@/composables/useDirectZipUpload";

vi.mock("@/client", () => ({
  completeIngestion: vi.fn(),
  uploadProgress: vi.fn(),
}));

const mockedCompleteIngestion = vi.mocked(completeIngestion);
const mockedUploadProgress = vi.mocked(uploadProgress);

afterEach(() => {
  vi.useRealTimers();
  vi.resetAllMocks();
});

async function* events(items: unknown[]) {
  for (const item of items) {
    await Promise.resolve();
    yield item;
  }
}

test("reconnects an interrupted ingestion stream before finalizing", async () => {
  mockedUploadProgress
    .mockResolvedValueOnce({
      stream: events([{ type: "phase", phase: "validating" }]),
    } as Awaited<ReturnType<typeof uploadProgress>>)
    .mockResolvedValueOnce({
      stream: events([{ type: "complete" }]),
    } as Awaited<ReturnType<typeof uploadProgress>>);
  const result = { user: { id: 42 }, trips: [] };
  mockedCompleteIngestion.mockResolvedValue({ data: result } as never);
  const onPhase = vi.fn();

  await expect(
    followUploadIngestion("upload-1", new AbortController().signal, onPhase),
  ).resolves.toBe(result);

  expect(mockedUploadProgress).toHaveBeenCalledTimes(2);
  expect(onPhase).toHaveBeenCalledWith("validating");
  expect(mockedCompleteIngestion).toHaveBeenCalledOnce();
});

test("retries the idempotent completion claim", async () => {
  vi.useFakeTimers();
  mockedUploadProgress.mockResolvedValue({
    stream: events([{ type: "complete" }]),
  } as Awaited<ReturnType<typeof uploadProgress>>);
  const result = { user: { id: 42 }, trips: [] };
  mockedCompleteIngestion
    .mockRejectedValueOnce(new Error("connection lost"))
    .mockResolvedValueOnce({ data: result } as never);

  const completed = followUploadIngestion(
    "upload-1",
    new AbortController().signal,
    vi.fn(),
  );
  const expectation = expect(completed).resolves.toBe(result);
  await vi.advanceTimersByTimeAsync(250);

  await expectation;
  expect(mockedCompleteIngestion).toHaveBeenCalledTimes(2);
});

test("stops after the SSE client exhausts a failed connection", async () => {
  mockedUploadProgress.mockImplementation(async (options) => {
    await Promise.resolve();
    options.onSseError?.(new Error("SSE failed: 401 Unauthorized"));
    return { stream: events([]) } as Awaited<
      ReturnType<typeof uploadProgress>
    >;
  });

  await expect(
    followUploadIngestion("upload-1", new AbortController().signal, vi.fn()),
  ).rejects.toThrow("SSE failed: 401 Unauthorized");
  expect(mockedUploadProgress).toHaveBeenCalledOnce();
});
