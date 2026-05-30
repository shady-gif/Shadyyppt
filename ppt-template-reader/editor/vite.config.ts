import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root,
  base: "/",
  plugins: [react()],
  build: {
    outDir: "../web",
    emptyOutDir: false,
    rollupOptions: {
      input: fileURLToPath(new URL("editor.html", import.meta.url)),
    },
  },
});
