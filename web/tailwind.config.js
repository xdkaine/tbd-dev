/** @type {import('tailwindcss').Config} */
const defaultTheme = require("tailwindcss/defaultTheme");

module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-geist-sans)", ...defaultTheme.fontFamily.sans],
        mono: ["var(--font-mono)", ...defaultTheme.fontFamily.mono],
      },
      colors: {
        brand: {
          50: "#edfff6",
          100: "#d5ffeb",
          200: "#aeffd8",
          300: "#70ffbc",
          400: "#2bff99",
          500: "#00d68f",
          600: "#00ad73",
          700: "#008a5c",
          800: "#006d4a",
          900: "#005a3e",
          950: "#003322",
        },
      },
    },
  },
  plugins: [],
};
