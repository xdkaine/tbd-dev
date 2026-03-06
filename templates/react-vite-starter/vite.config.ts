import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const port = parseInt(process.env.PORT || "3000", 10);

export default defineConfig({
  plugins: [react()],
  server: {
    port,
  },
  preview: {
    port,
    host: "0.0.0.0",
  },
});
