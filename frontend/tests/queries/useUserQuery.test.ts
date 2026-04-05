import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { BASE, defaultUser } from "../mocks/handlers";
import { withSetup } from "../helpers";
import { useUserQuery, KM_TO_MI } from "@/queries/useUserQuery";

describe("useUserQuery", () => {
  it("converts km to miles for formatDistance", async () => {
    server.use(
      http.get(`${BASE}/users`, () =>
        HttpResponse.json({ ...defaultUser, unit_is_km: false }),
      ),
    );

    const result = withSetup(() => useUserQuery());
    await flushPromises();

    // 100 km * 0.621371 = 62.1371 -> rounds to 62
    const expected = Math.round(100 * KM_TO_MI).toLocaleString("en-US");
    expect(result.formatDistance(100)).toBe(expected);
  });

  it("converts Celsius to Fahrenheit for formatTemp", async () => {
    server.use(
      http.get(`${BASE}/users`, () =>
        HttpResponse.json({
          ...defaultUser,
          temperature_is_celsius: false,
        }),
      ),
    );

    const result = withSetup(() => useUserQuery());
    await flushPromises();

    // 0 C -> 32 F
    expect(result.formatTemp(0)).toBe("32\u00B0");
    // 100 C -> 212 F
    expect(result.formatTemp(100)).toBe("212\u00B0");
  });

});
