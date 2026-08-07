import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            "/health": "http://127.0.0.1:8080",
            "/map": "http://127.0.0.1:8080",
            "/cameras": "http://127.0.0.1:8080",
            "/crashes": "http://127.0.0.1:8080",
            "/risk": "http://127.0.0.1:8080"
        }
    }
});
