import { flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { BASE, defaultAlbum, defaultSteps } from "../mocks/handlers";
import { deferred, withSetup } from "../helpers";
import { useStepsQuery } from "@/queries/queries";
import { useStepMutation } from "@/queries/useStepMutation";
import { useUndoStack } from "@/composables/useUndoStack";

const defaultStep = defaultSteps[0];

describe("useStepMutation", () => {
  beforeEach(() => {
    useUndoStack().clear();
  });

  function mountStepMutation() {
    const aid = ref<string | null>(defaultAlbum.id);
    return withSetup(() => {
      const query = useStepsQuery(aid);
      const mutation = useStepMutation(() => aid.value!);
      return { query, mutation };
    });
  }

  describe("optimistic update", () => {
    it("updates the matching step in cache immediately", async () => {
      const result = mountStepMutation();

      await flushPromises();
      expect(result.query.data.value?.[0]?.name).toBe("Amsterdam");

      const updateResponse = deferred<Response>();
      server.use(
        http.patch(
          `${BASE}/albums/:aid/steps/:sid`,
          () => updateResponse.promise,
        ),
      );

      result.mutation.mutate({ sid: 1, update: { name: "Rotterdam" } });
      await flushPromises();

      expect(result.query.data.value?.[0]?.name).toBe("Rotterdam");

      updateResponse.resolve(
        HttpResponse.json({ ...defaultStep, name: "Rotterdam" }),
      );
      await flushPromises();
    });

    it("only updates the targeted step, leaving others unchanged", async () => {
      const step2 = {
        ...defaultStep,
        id: 2,
        name: "Berlin",
      };
      const updatedStep1 = { ...defaultStep, name: "Utrecht" };

      let mutated = false;
      server.use(
        http.get(`${BASE}/albums/:aid/steps`, () =>
          HttpResponse.json(
            mutated ? [updatedStep1, step2] : [defaultStep, step2],
          ),
        ),
        http.patch(`${BASE}/albums/:aid/steps/:sid`, () => {
          mutated = true;
          return HttpResponse.json(updatedStep1);
        }),
      );

      const result = mountStepMutation();

      await flushPromises();
      expect(result.query.data.value).toHaveLength(2);

      result.mutation.mutate({ sid: 1, update: { name: "Utrecht" } });
      await flushPromises();

      expect(result.query.data.value?.[0]?.name).toBe("Utrecht");
      expect(result.query.data.value?.[1]?.name).toBe("Berlin");
    });

    it("sends explicit null cover in layout updates", async () => {
      let body: unknown;

      server.use(
        http.put(
          `${BASE}/albums/:aid/steps/:sid/media-layout`,
          async ({ request }) => {
            body = await request.json();
            return HttpResponse.json({ ...defaultStep, cover: null });
          },
        ),
      );

      const result = mountStepMutation();

      await flushPromises();

      result.mutation.mutate({ sid: 1, update: { cover: null } });
      await flushPromises();

      expect(body).toMatchObject({ cover: null });
    });
  });

  describe("undo stack", () => {
    it("stores step-specific before/after snapshots", async () => {
      const undoStack = useUndoStack();
      const stepMutator = vi.fn();
      undoStack.registerMutators(stepMutator, vi.fn());

      const result = mountStepMutation();

      await flushPromises();

      result.mutation.mutate({ sid: 1, update: { name: "New Name" } });
      await flushPromises();

      undoStack.undo();
      expect(stepMutator).toHaveBeenCalledWith(1, { name: "Amsterdam" });
    });

    it("does not push to undo stack if step is not found", async () => {
      const undoStack = useUndoStack();

      const result = mountStepMutation();

      await flushPromises();

      // Mutate a non-existent step id
      result.mutation.mutate({ sid: 999, update: { name: "Ghost" } });
      await flushPromises();

      expect(undoStack.canUndo.value).toBe(false);
    });
  });
});
