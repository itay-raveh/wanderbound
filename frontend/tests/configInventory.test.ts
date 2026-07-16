import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const repositoryRoot = path.resolve(process.cwd(), "..");

describe("frontend configuration inventory", () => {
  it("is exhaustive only in operator values and Compose", () => {
    const example = readFileSync(
      path.join(repositoryRoot, ".env.example"),
      "utf8",
    );
    const names = new Set(
      [...example.matchAll(/^#?\s*(VITE_[A-Z0-9_]+)=/gm)].map(
        ([, name]) => name,
      ),
    );
    const grep = spawnSync("git", ["grep", "-Il", "-e", "VITE_"], {
      cwd: repositoryRoot,
      encoding: "utf8",
    });
    expect(grep.status).toBe(0);

    const exhaustiveFiles = grep.stdout
      .trim()
      .split("\n")
      .filter(Boolean)
      .filter((file) => {
        const source = readFileSync(path.join(repositoryRoot, file), "utf8");
        return [...names].every((name) => source.includes(name));
      })
      .sort();

    expect(exhaustiveFiles).toEqual([".env.example", "compose.yml"]);
  });
});
