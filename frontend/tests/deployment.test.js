import assert from "node:assert/strict";
import test from "node:test";

test("Vite development proxy uses BACKEND_URL or the Render default", async () => {
  const previousBackendUrl = process.env.BACKEND_URL;

  try {
    delete process.env.BACKEND_URL;
    const defaultConfig = (await import("../vite.config.js?default-backend")).default;
    assert.equal(
      defaultConfig.server.proxy["/api"].target,
      "https://egneema-1.onrender.com",
    );

    process.env.BACKEND_URL = "https://render.example.test";
    const customConfig = (await import("../vite.config.js?custom-backend")).default;
    assert.equal(customConfig.server.proxy["/api"].target, "https://render.example.test");
  } finally {
    if (previousBackendUrl === undefined) delete process.env.BACKEND_URL;
    else process.env.BACKEND_URL = previousBackendUrl;
  }
});

test("Vercel rewrites API traffic to Render instead of defining API functions", async () => {
  const vercelConfig = await import("../vercel.json", { with: { type: "json" } });

  assert.deepEqual(vercelConfig.default.rewrites, [
    {
      source: "/api/:path*",
      destination: "https://egneema-1.onrender.com/api/:path*",
    },
  ]);
});
