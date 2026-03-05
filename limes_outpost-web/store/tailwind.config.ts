import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans:  ["var(--font-syne)", "system-ui", "sans-serif"],
        mono:  ["var(--font-jetbrains)", "monospace"],
      },
      colors: {
        // Base surfaces
        canvas:   { DEFAULT: "#0a0b0e", 50: "#f8f9fa" },
        surface:  { DEFAULT: "#111318", light: "#f1f3f5" },
        elevated: { DEFAULT: "#1a1d24", light: "#ffffff" },
        border:   { DEFAULT: "#252830", light: "#e2e8f0" },

        // Brand accent — cold electric blue
        accent: {
          DEFAULT: "#3b82f6",
          dim:     "#1d4ed8",
          glow:    "#60a5fa",
          muted:   "#1e3a5f",
        },

        // Semantic status colors
        success: { DEFAULT: "#10b981", muted: "#064e3b" },
        warning: { DEFAULT: "#f59e0b", muted: "#451a03" },
        danger:  { DEFAULT: "#ef4444", muted: "#450a0a" },
        neutral: { DEFAULT: "#6b7280", muted: "#1f2937" },

        // Text hierarchy
        ink: {
          primary:   "#f1f5f9",
          secondary: "#94a3b8",
          muted:     "#475569",
          inverse:   "#0f172a",
        },
      },
      borderRadius: {
        sm:  "4px",
        md:  "6px",
        lg:  "10px",
        xl:  "14px",
        "2xl": "20px",
      },
      boxShadow: {
        "glow-accent": "0 0 20px rgba(59,130,246,0.25)",
        "glow-sm":     "0 0 8px rgba(59,130,246,0.15)",
        "elevated":    "0 4px 24px rgba(0,0,0,0.4)",
        "card":        "0 1px 3px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.2)",
      },
      animation: {
        "pulse-slow":    "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in":       "fadeIn 0.3s ease-out",
        "slide-up":      "slideUp 0.3s ease-out",
        "slide-in-left": "slideInLeft 0.25s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%":   { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideInLeft: {
          "0%":   { opacity: "0", transform: "translateX(-8px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
      },
      backgroundImage: {
        "grid-pattern": "linear-gradient(rgba(59,130,246,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(59,130,246,0.03) 1px, transparent 1px)",
      },
      backgroundSize: {
        "grid": "32px 32px",
      },
    },
  },
  plugins: [],
};

export default config;
