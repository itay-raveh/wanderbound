import { spawnSync } from "node:child_process";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import vm from "node:vm";

import { afterEach, describe, expect, it } from "vitest";

const script = path.resolve(process.cwd(), "nginx/40-wanderbound-config.sh");
const tempDirectories: string[] = [];

const baseEnvironment = {
  PATH: process.env.PATH ?? "/usr/bin:/bin",
  VITE_ENVIRONMENT: "production",
  VITE_FRONTEND_URL:
    "https://wanderbound.example.test/?one=\"%3C&two='unicode-שלום",
};

interface Fixture {
  runtimeRoot: string;
  builtIndex: string;
  nginxConfig: string;
}

function createFixture(): Fixture {
  const root = mkdtempSync(path.join(tmpdir(), "wanderbound-config-"));
  tempDirectories.push(root);
  const runtimeRoot = path.join(root, "runtime");
  const builtIndex = path.join(root, "built-index.html");
  const nginxConfig = path.join(root, "default.conf");
  mkdirSync(runtimeRoot);
  writeFileSync(
    builtIndex,
    '<meta property="og:url" content="__WANDERBOUND_FRONTEND_URL__/">\n' +
      '<link rel="canonical" href="__WANDERBOUND_FRONTEND_URL__/">\n',
  );
  writeFileSync(
    nginxConfig,
    "connect-src 'self' __WANDERBOUND_SENTRY_ORIGIN__;\n",
  );
  return { runtimeRoot, builtIndex, nginxConfig };
}

function runScript(
  fixture: Fixture,
  overrides: Record<string, string | undefined> = {},
) {
  const environment: Record<string, string> = { ...baseEnvironment };
  for (const [name, value] of Object.entries(overrides)) {
    if (value === undefined) delete environment[name];
    else environment[name] = value;
  }
  return spawnSync(
    "/bin/sh",
    [script, fixture.runtimeRoot, fixture.nginxConfig, fixture.builtIndex],
    { encoding: "utf8", env: environment },
  );
}

function readConfig(fixture: Fixture): Record<string, string> {
  const context = vm.createContext({});
  vm.runInContext(
    readFileSync(path.join(fixture.runtimeRoot, "config.js"), "utf8"),
    context,
  );
  return context.WANDERBOUND_CONFIG as Record<string, string>;
}

afterEach(() => {
  for (const directory of tempDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

describe("frontend container startup configuration", () => {
  it("serializes every VITE_ value into one runtime object", () => {
    const fixture = createFixture();
    const value = 'quoted " slash \\ newline\n<script> שלום';

    const result = runScript(fixture, {
      VITE_TEST_VALUE: value,
      DATABASE_PASSWORD: "must-not-be-public",
    });

    expect(result.status).toBe(0);
    expect(readConfig(fixture)).toMatchObject({
      VITE_ENVIRONMENT: "production",
      VITE_TEST_VALUE: value,
    });
    expect(readConfig(fixture)).not.toHaveProperty("DATABASE_PASSWORD");
  });

  it("applies the existing public defaults", () => {
    const fixture = createFixture();

    const result = runScript(fixture);

    expect(result.status).toBe(0);
    expect(readConfig(fixture)).toMatchObject({
      VITE_MAX_UPLOAD_GB: "4",
      VITE_SENTRY_TRACES_SAMPLE_RATE: "0.1",
    });
  });

  it("replaces installation-specific HTML metadata", () => {
    const fixture = createFixture();

    const result = runScript(fixture);

    expect(result.status).toBe(0);
    const index = readFileSync(
      path.join(fixture.runtimeRoot, "index.html"),
      "utf8",
    );
    expect(index).not.toContain("__WANDERBOUND_FRONTEND_URL__");
    expect(index.match(/https:\/\/wanderbound\.example\.test/g)).toHaveLength(
      2,
    );
    expect(index).toContain("&quot;%3C&amp;two=&apos;unicode-שלום");
  });

  it("adds only the Sentry DSN origin to the rendered CSP", () => {
    const fixture = createFixture();

    const result = runScript(fixture, {
      VITE_SENTRY_DSN:
        "https://public-key@errors.example.test:9443/42?ignored=yes#fragment",
    });

    expect(result.status).toBe(0);
    const nginxConfig = readFileSync(fixture.nginxConfig, "utf8");
    expect(nginxConfig).toContain("https://errors.example.test:9443");
    expect(nginxConfig).not.toContain("public-key");
    expect(nginxConfig).not.toContain("/42");
  });

  it("removes the Sentry CSP placeholder when the DSN is absent", () => {
    const fixture = createFixture();

    const result = runScript(fixture);

    expect(result.status).toBe(0);
    expect(readFileSync(fixture.nginxConfig, "utf8")).toBe(
      "connect-src 'self' ;\n",
    );
  });

  it.each([
    ["missing", undefined],
    ["invalid", "staging"],
  ])("rejects a %s environment", (_name, environment) => {
    const fixture = createFixture();

    const result = runScript(fixture, { VITE_ENVIRONMENT: environment });

    expect(result.status).not.toBe(0);
    expect(() =>
      readFileSync(path.join(fixture.runtimeRoot, "config.js")),
    ).toThrow();
    expect(result.stderr).not.toContain(environment ?? "undefined");
  });
});
