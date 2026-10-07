import { ShieldCheck } from "lucide-react";
import { appUrl, SITE } from "@/lib/site";
import { FIGURES } from "@/lib/data";
import { Button } from "@/components/shared/Button";
import { Highlight } from "@/components/shared/Highlight";
import { MeshGradient } from "./MeshGradient";

/**
 * The Stripe gesture on Carguito's terms: the opinion (statements are written
 * not to be read) and its answer in one line, one CTA, one trust line, and
 * below it one number set at 96px. The number is the proof: the
 * sub-headline's promise ("los cobros que se repiten") turned into a figure
 * a statement actually surfaced.
 */
export function HeroB() {
    return (
        <section className="relative isolate overflow-hidden">
            <MeshGradient />
            <div className="relative mx-auto w-full max-w-page px-5 pb-16 pt-20 sm:px-8 sm:pb-24 sm:pt-28">
                <p className="eyebrow rise">Finanzas personales para México</p>
                <h1 className="rise mt-4 max-w-[16ch] text-display sm:text-display-lg">
                    Tu estado de cuenta no lo lee nadie. <Highlight>Carguito sí</Highlight>.
                </h1>
                <p className="rise rise-2 mt-6 max-w-prose text-body-lg text-dust">{SITE.description}</p>
                <div className="rise rise-2 mt-8 flex flex-wrap items-center gap-4">
                    <Button href={appUrl("hero")} size="lg" tone="dark">
                        Comenzar con un estado de cuenta
                    </Button>
                    <a
                        href="#lecturas"
                        className="text-body text-dust underline decoration-lineStrong underline-offset-4 hover:text-bone"
                    >
                        Ver un ejemplo
                    </a>
                </div>
                <p className="rise rise-2 mt-4 flex items-center gap-1.5 text-body-sm text-dust">
                    <ShieldCheck size={14} aria-hidden className="text-signal" />
                    Carguito nunca pide la contraseña de tu banco. La del PDF, si trae una, la usa una vez y no la
                    guarda. Hoy no cobramos.
                </p>

                <div className="rise rise-3 mt-16 border-t border-line pt-8 sm:mt-24">
                    <p className="tabular text-bone">
                        <span className="text-metric-lg sm:text-metric-xl">{FIGURES.heroAmount}</span>
                        <span className="text-title-md text-dust sm:text-title-lg">{FIGURES.heroAmountUnit}</span>
                    </p>
                    <p className="mt-3 max-w-prose text-body-lg text-dust">{FIGURES.heroCaption}</p>
                </div>
            </div>
        </section>
    );
}
