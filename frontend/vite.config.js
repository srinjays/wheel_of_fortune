import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const backendOrigin = new URL(backendUrl).origin;

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: backendUrl,
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (proxyRequest, request) => {
            if (request.headers.origin) {
              proxyRequest.setHeader("origin", backendOrigin);
            }
          });
        },
      },
      "/socket.io": {
        target: backendUrl,
        ws: true,
      },
    },
  },
});
