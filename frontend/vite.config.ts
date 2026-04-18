import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "src"),
    },
    dedupe: ["react", "react-dom"],
  },
  root: path.resolve(import.meta.dirname),
  build: {
    outDir: path.resolve(import.meta.dirname, "dist"),
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    // Fail loud if 5173 is already taken rather than silently jumping
    // to 5174 (which strands the browser on a stale HMR port and
    // produces "WebSocket closed without opened" in the console).
    strictPort: true,
    // Bind to both IPv4 *and* IPv6 via ``true``. ``0.0.0.0`` alone
    // only listens on IPv4 and Firefox (which resolves ``localhost``
    // to ``::1`` first) then fails to establish the HMR WebSocket.
    host: true,
    // Let Vite infer the WS host/port from window.location — this
    // works whether the app is served over http or an HTTPS reverse
    // proxy and avoids the Firefox ``::1`` vs ``127.0.0.1`` mismatch
    // we were papering over with the explicit ``localhost`` pin.
    hmr: {
      clientPort: 5173,
    },
    proxy: {
      "/api/v1": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        // Proxy the HiTL live-stream WebSocket (``/api/v1/hitl/threads/
        // {id}/live``) to the FastAPI backend. Without ``ws: true`` the
        // upgrade request gets handed to Vite's own HMR endpoint and
        // closes before opening — you'll see "WebSocket closed without
        // opened" in the browser console.
        ws: true,
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4173,
    host: "0.0.0.0",
  },
});
