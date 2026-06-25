import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "hsl(220 14% 8%)",
        card: "hsl(220 14% 12%)",
        border: "hsl(220 14% 18%)",
        muted: "hsl(220 6% 60%)",
        accent: "hsl(160 84% 50%)",
        danger: "hsl(0 84% 60%)",
        warning: "hsl(38 92% 60%)",
      },
    },
  },
  plugins: [typography],
};
export default config;
