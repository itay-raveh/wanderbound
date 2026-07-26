import { indexSteps } from "@/utils/steps";
import { makeStep } from "../helpers";

describe("indexSteps", () => {
  it("indexes steps and their ordered positions by ID", () => {
    const first = makeStep({ id: 42 });
    const second = makeStep({ id: 7 });

    const index = indexSteps([first, second]);

    expect(index.byId.get(7)).toBe(second);
    expect(index.positionById.get(42)).toBe(0);
    expect(index.positionById.get(7)).toBe(1);
    expect(index.byId.get(999)).toBeUndefined();
  });
});
