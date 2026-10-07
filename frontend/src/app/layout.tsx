import type { Metadata, Viewport } from "next";
import { Inter, Instrument_Serif } from "next/font/google";
import { ToastProvider } from "@/components/ui";
import { Providers } from "./providers";
import "./globals.css";

const inter = Inter({
    subsets: ["latin"],
    variable: "--font-inter",
    display: "swap",
});

/** The display face: a text serif, 400 only, words at >=24px. Numbers,
 *  labels and container titles stay in Inter (see design/tokens.ts). */
const instrumentSerif = Instrument_Serif({
    weight: "400",
    subsets: ["latin"],
    variable: "--font-display",
    display: "swap",
});

/** Mirrors `landing/src/lib/site.ts` (`SITE.title`, `SITE.description`)
 *  verbatim. The two apps make one promise; edit there first, then here. */
export const metadata: Metadata = {
    title: "Tu estado de cuenta no lo lee nadie. Carguito sí.",
    description:
        "Sube el PDF de tu banco. Carguito saca cada movimiento, señala los cobros que se repiten y los que no cuadran, y desecha el archivo. Sin conectar cuentas, sin tu contraseña, sin capturar a mano.",
};

export const viewport: Viewport = {
    width: "device-width",
    initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="es-MX" className={`${inter.variable} ${instrumentSerif.variable}`}>
            <body className="font-sans">
                <ToastProvider>
                    <Providers>{children}</Providers>
                </ToastProvider>
            </body>
        </html>
    );
}
