import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Inter } from "next/font/google";
import { SITE, SITE_URL } from "@/lib/site";
import "./globals.css";

const inter = Inter({
    subsets: ["latin"],
    variable: "--font-inter",
    display: "swap",
});

/** The landing's display face: a variable grotesque with an optical-size
 *  axis, so the 72px hero gets the tight display cut and the 24px FAQ
 *  questions the sturdier text cut on their own. Words at >=24px, weight 500
 *  only; numbers and card titles stay in Inter (docs/voice-and-type.md §4).
 *  The dashboard keeps Instrument Serif. */
const bricolage = Bricolage_Grotesque({
    subsets: ["latin"],
    axes: ["opsz"],
    variable: "--font-display",
    display: "swap",
});

export const metadata: Metadata = {
    metadataBase: new URL(SITE_URL),
    title: { default: SITE.title, template: `%s · ${SITE.name}` },
    description: SITE.description,
    robots: { index: true, follow: true },
    openGraph: {
        type: "website",
        locale: "es_MX",
        siteName: SITE.name,
        title: SITE.title,
        description: SITE.description,
    },
    twitter: { card: "summary_large_image" },
};

export const viewport: Viewport = {
    width: "device-width",
    initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="es-MX" className={`${inter.variable} ${bricolage.variable}`}>
            <body className="font-sans">{children}</body>
        </html>
    );
}
