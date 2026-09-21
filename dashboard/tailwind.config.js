/** @type {import('tailwindcss').Config} */

// ELMA admin — "сводка, а не приборная панель".
//
// The product sells calm: "интернет, который не играет на нервах". This console
// is read by one or two people, usually on a phone, to answer one question —
// идут ли деньги и что сделать прямо сейчас. So it is set like a quiet daily
// briefing: money large and in the reading flow, everything else recessive.
//
// The palette is ink-and-cloud, taken from the bot's own 💙 / ☁️ / 🤍 vocabulary.
// The dark tone is genuinely blue (#12202E) rather than a tinted near-black, and
// the brand blue leans to ink instead of the sky-cyan every admin panel uses.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Golos Text is drawn for Russian first — the right voice for a console
        // that is entirely in Russian, and not the Inter/Urbanist default.
        sans: ["Golos Text", "Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        // Mono is for real identifiers (telegram ids, tokens, promo codes) only,
        // never for decorative micro-labels.
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      colors: {
        bg: {
          DEFAULT: "#F6F8FB",
          subtle: "#EDF1F6",
          card: "#FFFFFF",
          elevated: "#E4EAF2",
        },
        border: { DEFAULT: "#DCE3EC", subtle: "#E9EEF4" },
        fg: { DEFAULT: "#12202E", muted: "#4A5B6E", subtle: "#7C8CA0" },
        // Brand azure: the primary action and "this is live". Nothing else — an
        // accent that appears everywhere stops meaning anything.
        accent: { DEFAULT: "#1857D6", hover: "#1246B4", dark: "#0D3488" },
        secondary: { DEFAULT: "#5C6F85", hover: "#4A5B6E" },
        // Money reads jade, not neon emerald: revenue should feel settled.
        success: "#17876B",
        danger: "#C4362F",
        warning: "#B8791C",
        info: { DEFAULT: "#1857D6", soft: "#4C86F0" },
        special: { DEFAULT: "#6B4BC7", soft: "#8A6FE0" },
      },
      borderRadius: {
        // Two radii, and they mean different things: controls you press vs
        // surfaces you read. One radius on everything is what makes a panel
        // look like a component kit.
        control: "10px",
        surface: "16px",
        xl2: "16px",
      },
      boxShadow: {
        paper: "0 1px 0 rgba(18,32,46,0.04), 0 1px 3px rgba(18,32,46,0.04)",
        lift: "0 6px 20px -10px rgba(18,32,46,0.22)",
        // Names the existing pages already reference.
        soft: "0 1px 0 rgba(18,32,46,0.04), 0 1px 3px rgba(18,32,46,0.04)",
        card: "0 1px 0 rgba(18,32,46,0.04), 0 1px 3px rgba(18,32,46,0.04)",
        glow: "0 6px 20px -10px rgba(18,32,46,0.22)",
        "glow-sm": "0 3px 10px -6px rgba(18,32,46,0.18)",
        cta: "0 6px 18px -8px rgba(24,87,214,0.45)",
        matte: "0 0 0 1px rgba(18,32,46,0.06), 0 10px 30px -14px rgba(18,32,46,0.25)",
      },
      keyframes: {
        // One orchestrated moment on load: the money figure settles in.
        settle: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        // Answers to a person's action.
        "sheet-up": {
          from: { transform: "translateY(12px)", opacity: "0" },
          to: { transform: "translateY(0)", opacity: "1" },
        },
        breathe: { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.35" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        ticker: { from: { transform: "translateX(0%)" }, to: { transform: "translateX(-50%)" } },
      },
      animation: {
        settle: "settle .5s cubic-bezier(.2,.7,.2,1) both",
        "sheet-up": "sheet-up .28s cubic-bezier(.2,.7,.2,1)",
        breathe: "breathe 2.4s ease-in-out infinite",
        shimmer: "shimmer 1.6s infinite",
        ticker: "ticker 40s linear infinite",
        // Aliases so existing markup keeps working after the rebrand.
        "fade-in": "settle .4s ease both",
        "fade-up": "settle .5s cubic-bezier(.2,.7,.2,1) both",
        "slide-up": "sheet-up .28s cubic-bezier(.2,.7,.2,1)",
        "pulse-live": "breathe 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
