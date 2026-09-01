import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * There is no dev proxy, on purpose.
 *
 * This app is a standalone client of the Candidate Search API, not one half of a
 * monorepo. It reaches the API over the network by its URL - the same way in
 * development as in production, and the same way any other client would. That
 * keeps one code path instead of two, and means a request that works here works
 * when deployed.
 *
 * The one thing it costs is that development is cross-origin, so the API must
 * list this dev server's origin in CORS_ORIGINS.
 */
export default defineConfig(({ mode }) => {
  // A config file does not get .env values through `process.env` - Vite loads
  // them into `import.meta.env` for client code only. loadEnv is how the config
  // itself reads them, and it also picks up real environment variables carrying
  // the prefix, which is how the container build supplies this value.
  const env = loadEnv(mode, import.meta.dirname, "VITE_");

  if (!env.VITE_API_BASE_URL) {
    // Fail here rather than let a bundle be built that cannot reach anything.
    // Checked at config time so `npm run build` in CI stops too, not just the
    // browser at run time.
    throw new Error(
      "VITE_API_BASE_URL is not set.\n\n" +
        "This app reaches the Candidate Search API over the network and has no " +
        "default. Copy .env.example to .env for local development, or pass the " +
        "value as a build argument when building the container.\n\n" +
        "Include the API prefix, for example: http://localhost:8000/api",
    );
  }

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": path.resolve(import.meta.dirname, "./src") },
    },
    server: {
      port: 5173,
      // Refuse to start rather than quietly moving to 5174 when the port is
      // busy. The API allows this origin by name, so a silently different port
      // would look like a broken app: every request blocked by the browser, and
      // nothing at all in the API logs. Being told the port is taken is far
      // easier to fix.
      strictPort: true,
    },
  };
});
