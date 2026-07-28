import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Calm clinical palette — ink on paper, a single trustworthy blue accent.
        ink: {
          DEFAULT: "#12181f",
          soft: "#3a4652",
          muted: "#697684",
          faint: "#9aa5b1",
        },
        paper: {
          DEFAULT: "#ffffff",
          soft: "#f7f9fb",
          sunk: "#eef2f6",
        },
        line: {
          DEFAULT: "#e2e8f0",
          soft: "#eef2f6",
          strong: "#cbd5e1",
        },
        accent: {
          DEFAULT: "#1b64c9",
          soft: "#e8f0fb",
          ink: "#0f4a9c",
        },
        // Clinical status semantics
        danger: { DEFAULT: "#c0362c", soft: "#fbecea", ink: "#8f2018" },
        warn: { DEFAULT: "#b5730d", soft: "#fdf2e0", ink: "#7d4e05" },
        good: { DEFAULT: "#2f855a", soft: "#e7f4ec", ink: "#1e5e40" },
        info: { DEFAULT: "#1b64c9", soft: "#e8f0fb", ink: "#0f4a9c" },
        quiet: { DEFAULT: "#64748b", soft: "#f1f5f9", ink: "#475569" },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16, 24, 40, 0.04), 0 1px 3px rgba(16, 24, 40, 0.06)",
        pop: "0 4px 16px rgba(16, 24, 40, 0.10)",
        focus: "0 0 0 3px rgba(27, 100, 201, 0.18)",
      },
      borderRadius: {
        xl: "0.75rem",
      },
    },
  },
  plugins: [],
};

export default config;
