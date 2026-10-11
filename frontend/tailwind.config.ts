/** @type {import('tailwindcss').Config} */
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 600: "#1d4ed8", 700: "#1e40af" },
        // Zero-gravity tokens (dark space theme; see app/globals.css).
        void: "#04060f",
        abyss: "#0a0f24",
        nebula: {
          indigo: "#6366f1",
          violet: "#a78bfa",
          cyan: "#22d3ee",
        },
      },
      boxShadow: {
        glow: "0 0 24px -6px rgba(99, 102, 241, 0.55)",
        "glow-cyan": "0 0 24px -6px rgba(34, 211, 238, 0.45)",
        float: "0 18px 50px -12px rgba(0, 0, 0, 0.7)",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-6px)" },
        },
        rise: {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
        shimmer: {
          from: { backgroundPosition: "200% 0" },
          to: { backgroundPosition: "-200% 0" },
        },
        twinkle: {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
        drift: {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "50%": { transform: "translate(30px, -20px) scale(1.08)" },
        },
      },
      animation: {
        float: "float 7s ease-in-out infinite",
        rise: "rise 0.45s ease-out both",
        "pulse-soft": "pulse-soft 2.2s ease-in-out infinite",
        shimmer: "shimmer 1.6s linear infinite",
        twinkle: "twinkle 4s ease-in-out infinite",
        drift: "drift 18s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
