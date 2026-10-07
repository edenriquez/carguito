import type { Viewport } from "next";
import { Nav } from "@/components/shared/Nav";
import { LogoMarquee } from "@/components/shared/LogoMarquee";
import { CtaBand } from "@/components/shared/CtaBand";
import { Footer } from "@/components/shared/Footer";
import { HeroB } from "@/components/landing/HeroB";
import { StepsB } from "@/components/landing/StepsB";
import { LecturaB } from "@/components/landing/LecturaB";
import { BentoB } from "@/components/landing/BentoB";
import { CustodyB } from "@/components/landing/CustodyB";
import { BanksB } from "@/components/landing/BanksB";
import { FaqB } from "@/components/landing/FaqB";
import "./landing.css";

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#141211" };

/**
 * The landing — "Señal oscura". One dark root via data-theme (see
 * globals.css): Night ground, a drifting cyan mesh in the hero, the product
 * drawn as the dashboard draws it: the Lectura, then the other faces.
 *
 * The order is the argument: the opinion and its answer (hero) → how it
 * works (three steps, `#como-funciona`) → proof (the Lectura against the
 * country, `#lecturas`; Movimientos, Plan and Pagos, `#caras`; the merchants
 * it names) → the second opinion (custody) → honesty as proof
 * (which banks, how well) → objections (FAQ) → the close as an echo.
 * Voice and glossary: docs/voice-and-type.md.
 */
export default function Landing() {
    return (
        <main data-theme="dark" className="min-h-dvh bg-night text-dust">
            <Nav tone="dark" />
            <HeroB />
            <StepsB />
            <LecturaB />
            <BentoB />
            <LogoMarquee
                tone="dark"
                label="Reconoce a quien te cobra"
                note="A estos Carguito ya los nombra desde el renglón crudo del banco. Los que no conoce llegan como vienen en el estado de cuenta: los nombras una vez y Carguito los aprende."
            />
            <CustodyB />
            <BanksB />
            <FaqB />
            <CtaBand tone="dark" />
            <Footer tone="dark" />
        </main>
    );
}
