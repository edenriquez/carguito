import { ImageResponse } from "next/og";
import { SITE } from "@/lib/site";
import { BankMark } from "@/components/shared/BankMark";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = SITE.title;

/**
 * The share card. Soot ground, the wordmark, one headline with the highlight
 * pill — the same typographic move as the pages, in the same display face.
 * Bricolage Grotesque is fetched at build from the Google Fonts CSS API as a
 * static 500 instance at the 96 optical size (Satori cannot read a variable
 * font), subset to the characters the card uses; if that fetch fails the card
 * falls back to Satori's system sans rather than failing the build.
 */
/** SITE.headline split around the highlight. Word groups wrap as units in Satori, so the first half is two. */
const HEADLINE = { before: ["Tu estado de cuenta", "no lo lee nadie."], highlight: "Carguito sí", after: "." };

async function loadDisplayFont(text: string): Promise<ArrayBuffer | null> {
    try {
        const css = await fetch(
            `https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@96,500&text=${encodeURIComponent(text)}`,
            // An unrecognised UA gets TTF, which Satori can read; a browser UA gets woff2, which it cannot.
            { headers: { "User-Agent": "curl/8" } }
        ).then((r) => r.text());
        const url = css.match(/src:\s*url\(([^)]+)\)/)?.[1];
        if (!url) return null;
        return await fetch(url).then((r) => r.arrayBuffer());
    } catch {
        return null;
    }
}

export default async function OpenGraphImage() {
    const text = `${SITE.name} ${HEADLINE.before.join(" ")} ${HEADLINE.highlight} ${HEADLINE.after} ${SITE.description}`;
    const data = await loadDisplayFont(text);
    const fontFamily = data ? "Bricolage Grotesque" : "sans-serif";
    return new ImageResponse(
        (
            <div
                style={{
                    width: "100%",
                    height: "100%",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    padding: 72,
                    background: "#1c1917",
                    color: "#e7e5e4",
                    fontFamily,
                    letterSpacing: "-0.02em",
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 30 }}>
                    <BankMark size={40} />
                    {SITE.name}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
                    <div style={{ display: "flex", flexWrap: "wrap", fontSize: 76, lineHeight: 1.08 }}>
                        {/* Word spacing as margin: Satori drops a trailing &nbsp; inside a span. */}
                        {HEADLINE.before.map((chunk) => (
                            <span key={chunk} style={{ marginRight: "0.24em" }}>
                                {chunk}
                            </span>
                        ))}
                        <span
                            style={{
                                background: "rgba(51,152,225,0.22)",
                                color: "#c1e1f7",
                                borderRadius: 10,
                                padding: "0 18px",
                            }}
                        >
                            {HEADLINE.highlight}
                        </span>
                        {/* Tuck the period against the pill, as the page's .highlight does with its negative inline margin. */}
                        <span style={{ marginLeft: -10 }}>{HEADLINE.after}</span>
                    </div>
                    <div style={{ fontSize: 30, lineHeight: 1.3, color: "#a8a29e", maxWidth: 900 }}>
                        {SITE.description}
                    </div>
                </div>
            </div>
        ),
        {
            ...size,
            fonts: data ? [{ name: "Bricolage Grotesque", data, weight: 500, style: "normal" }] : undefined,
        }
    );
}
