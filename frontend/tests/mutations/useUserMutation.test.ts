import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { BASE, defaultUser } from "../mocks/handlers";
import { withSetup } from "../helpers";
import { useUserQuery } from "@/queries/useUserQuery";
import { useUserMutation } from "@/queries/useUserMutation";

describe("useUserMutation", () => {
  // ---------------------------------------------------------------------------
  // Optimistic update
  // ---------------------------------------------------------------------------

  describe("optimistic update", () => {
    it("updates cache immediately before server responds", async () => {
      const result = withSetup(() => {
        const query = useUserQuery();
        const mutation = useUserMutation();
        return { query, mutation };
      });

      await flushPromises();
      expect(result.query.user.value?.unit_is_km).toBe(true);

      server.use(
        http.patch(`${BASE}/users`, async () => {
          await new Promise((r) => setTimeout(r, 50));
          return HttpResponse.json({ ...defaultUser, unit_is_km: false });
        }),
      );

      result.mutation.mutate({ unit_is_km: false });
      await flushPromises();

      expect(result.query.user.value?.unit_is_km).toBe(false);

      await new Promise((r) => setTimeout(r, 100));
      await flushPromises();
    });

    it("merges only the updated fields", async () => {
      const updatedUser = { ...defaultUser, first_name: "New Name" };

      // Override both PATCH and GET so the refetch after onSettled also returns updated data
      server.use(
        http.patch(`${BASE}/users`, () => HttpResponse.json(updatedUser)),
        http.get(`${BASE}/users`, () => HttpResponse.json(updatedUser)),
      );

      const result = withSetup(() => {
        const query = useUserQuery();
        const mutation = useUserMutation();
        return { query, mutation };
      });

      await flushPromises();

      result.mutation.mutate({ first_name: "New Name" });
      await flushPromises();

      expect(result.query.user.value?.first_name).toBe("New Name");
      expect(result.query.user.value?.last_name).toBe("User");
      expect(result.query.user.value?.unit_is_km).toBe(true);
    });

    it("updates derived computeds after optimistic update", async () => {
      const result = withSetup(() => {
        const query = useUserQuery();
        const mutation = useUserMutation();
        return { query, mutation };
      });

      await flushPromises();
      expect(result.query.isKm.value).toBe(true);
      expect(result.query.isCelsius.value).toBe(true);

      const updatedUser = {
        ...defaultUser,
        unit_is_km: false,
        temperature_is_celsius: false,
      };

      server.use(
        http.patch(`${BASE}/users`, () => HttpResponse.json(updatedUser)),
        http.get(`${BASE}/users`, () => HttpResponse.json(updatedUser)),
      );

      result.mutation.mutate({
        unit_is_km: false,
        temperature_is_celsius: false,
      });
      await flushPromises();

      expect(result.query.isKm.value).toBe(false);
      expect(result.query.isCelsius.value).toBe(false);
    });
  });

  // ---------------------------------------------------------------------------
  // Error rollback
  // ---------------------------------------------------------------------------

  describe("error rollback", () => {
    it("reverts cache to previous value on error", async () => {
      server.use(
        http.patch(`${BASE}/users`, () =>
          HttpResponse.json({ detail: "Server error" }, { status: 500 }),
        ),
      );

      const result = withSetup(() => {
        const query = useUserQuery();
        const mutation = useUserMutation();
        return { query, mutation };
      });

      await flushPromises();
      expect(result.query.user.value?.first_name).toBe("Test");

      result.mutation.mutate({ first_name: "Will Fail" });
      await flushPromises();

      expect(result.query.user.value?.first_name).toBe("Test");
    });
  });

  // ---------------------------------------------------------------------------
  // API call
  // ---------------------------------------------------------------------------

  describe("API call", () => {
    it("sends the correct body to the API", async () => {
      let capturedBody: Record<string, unknown> | undefined;

      server.use(
        http.patch(`${BASE}/users`, async ({ request }) => {
          capturedBody = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({
            ...defaultUser,
            locale: "he-IL",
          });
        }),
      );

      const result = withSetup(() => {
        const query = useUserQuery();
        const mutation = useUserMutation();
        return { query, mutation };
      });

      await flushPromises();

      result.mutation.mutate({ locale: "he-IL" });
      await flushPromises();

      expect(capturedBody).toEqual({ locale: "he-IL" });
    });
  });

  // ---------------------------------------------------------------------------
  // Multiple mutations
  // ---------------------------------------------------------------------------

  describe("multiple mutations", () => {
    it("handles sequential mutations correctly", async () => {
      let callCount = 0;
      server.use(
        http.patch(`${BASE}/users`, async ({ request }) => {
          callCount++;
          const body = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({ ...defaultUser, ...body });
        }),
      );

      const result = withSetup(() => {
        const query = useUserQuery();
        const mutation = useUserMutation();
        return { query, mutation };
      });

      await flushPromises();

      result.mutation.mutate({ first_name: "Alice" });
      await flushPromises();

      result.mutation.mutate({ last_name: "Smith" });
      await flushPromises();

      expect(callCount).toBe(2);
    });
  });
});
