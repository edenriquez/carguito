import type { Config } from "tailwindcss";
import {
    borderRadius,
    boxShadow,
    colors,
    fontFamily,
    fontSize,
    fontWeight,
    maxWidth,
    zIndex,
} from "./src/design/tokens";
import { dark } from "./src/design/dark";

/**
 * Same shape as frontend/tailwind.config.ts. `tokens.ts` is a verbatim copy
 * (npm run tokens:sync); the dark-surface additions the landing needs live in
 * `dark.ts` so the sync stays a plain overwrite.
 */
const config: Config = {
    content: ["./src/**/*.{ts,tsx}"],
    theme: {
        extend: {
            colors: { ...colors, ...dark.colors },
            /* The landing's display is a grotesque, not the dashboard's serif:
               same variable, a sans fallback chain (docs/voice-and-type.md §4). */
            fontFamily: {
                ...fontFamily,
                display: ["var(--font-display)", "ui-sans-serif", "system-ui", "sans-serif"],
            },
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            fontSize: fontSize as any,
            borderRadius: { ...borderRadius },
            maxWidth: { ...maxWidth },
            zIndex: Object.fromEntries(
                Object.entries(zIndex).map(([k, v]) => [k, String(v)])
            ),
        },
        /* Theme-level, not extend: the whole weight scale is these two. */
        fontWeight: { ...fontWeight },
        boxShadow: { ...boxShadow, ...dark.boxShadow },
    },
    plugins: [],
};

export default config;
