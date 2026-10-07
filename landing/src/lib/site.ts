/** Public URL of this landing — metadataBase and absolute OG links. */
export const SITE_URL =
    process.env.NEXT_PUBLIC_SITE_URL ??
    (process.env.VERCEL_PROJECT_PRODUCTION_URL
        ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
        : "http://localhost:3001");

/** Where every "Comenzar" sends people: the deployed Carguito app. */
export const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

/** Which button on the landing sent the visitor. Read by the app as `utm_content`. */
export type CtaPlacement = "nav" | "hero" | "band" | "footer" | "faq";

/**
 * The app URL stamped with where the click came from, so the dashboard can
 * tell a landing visitor from a returning user and which CTA converts.
 * Standard UTM names: `utm_source=landing`, `utm_medium=cta`,
 * `utm_content=<placement>`.
 */
export function appUrl(placement: CtaPlacement): string {
    const url = new URL(APP_URL);
    url.searchParams.set("utm_source", "landing");
    url.searchParams.set("utm_medium", "cta");
    url.searchParams.set("utm_content", placement);
    return url.toString();
}

/**
 * One promise, everywhere: the H1, the <title>, the share card, the meta
 * description and the dashboard's <title> (frontend/src/app/layout.tsx,
 * mirrored verbatim) all say the same thing. The headline is the product's
 * one opinion — statements are written not to be read — and its answer. No
 * "Carguito — " prefix on the title: the headline already names the brand.
 * See docs/voice-and-type.md.
 */
export const SITE = {
    name: "Carguito",
    headline: "Tu estado de cuenta no lo lee nadie. Carguito sí.",
    title: "Tu estado de cuenta no lo lee nadie. Carguito sí.",
    description:
        "Sube el PDF de tu banco. Carguito saca cada movimiento, señala los cobros que se repiten y los que no cuadran, y desecha el archivo. Sin conectar cuentas, sin tu contraseña, sin capturar a mano.",
} as const;
