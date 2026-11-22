import type { Config } from "tailwindcss";

// Flat colours only: CLAUDE.md section 11 forbids gradients and UI libraries.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#2f5bea", dark: "#2447bd", soft: "#e8eefd" },
      },
    },
  },
  plugins: [],
};

export default config;
