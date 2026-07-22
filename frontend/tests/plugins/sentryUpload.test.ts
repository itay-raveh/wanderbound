import { isSensitiveUploadUrl } from "@/plugins/sentry";

it("recognizes upload bearer credentials without treating ordinary URLs as sensitive", () => {
  expect(
    isSensitiveUploadUrl(
      "https://objects.example/uploads/file.zip?X-Amz-Date=now&X-Amz-Signature=secret",
    ),
  ).toBe(true);
  expect(
    isSensitiveUploadUrl("/api/v1/users/uploads/id?key=uploads%2Fid.zip"),
  ).toBe(false);
});
