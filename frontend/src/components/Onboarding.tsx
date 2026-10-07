"use client";

import { useEffect, useState } from "react";
import type { UploadResult } from "@/lib/api";
import { BankMark } from "@/components/ui";
import { track } from "@/lib/telemetry";
import { StatementDropzone } from "@/components/StatementDropzone";
import { ReviewStatement } from "@/components/onboarding/ReviewStatement";
import { UploadStory } from "@/components/onboarding/UploadStory";

/**
 * The doing page: the visitor already said yes on the landing site, so no
 * sales copy survives here — an instruction, the dropzone, and an honest
 * answer to the one question somebody about to hand over a bank statement is
 * actually holding. Two steps on one screen:
 *
 * 1. upload — the dropzone owns the viewport;
 * 2. review — the OCR shows its work (`ReviewStatement`) before the app opens.
 *
 * Two things this screen used to get wrong:
 *
 * - **It spoke in a voice the app does not have.** A 52px Instrument Serif
 *   hero, then an app that is Inter from edge to edge. The first screen should
 *   sound like the product it opens, so the type here is the app's type.
 * - **It explained the pipeline in three paragraphs.** "Carguito lo lee y lo
 *   desecha" is a claim about custody, and a paragraph making that claim is
 *   just a paragraph. The scene below shows it: the file travels once, it
 *   dissolves at the processor, and only data continues to the charts. The
 *   words under it are labels for what is moving, not a second telling.
 *
 * Someone who lands here cold (a shared link, a bookmark) gets one quiet way
 * back to the pitch; the pitch itself is not repeated.
 */
const LANDING_URL = process.env.NEXT_PUBLIC_LANDING_URL ?? "http://localhost:3001";

/** One label per beat of the scene above, left to right: your phone, the
 *  processor, the charts. Kept to a line each — anything longer stops being a
 *  caption and starts competing with the animation it is captioning. */
const BEATS = [
    {
        title: "Tu archivo",
        body: "Sale de tu carpeta de descargas una sola vez.",
    },
    {
        title: "Carguito lo lee y lo borra",
        body: "Saca los movimientos. El PDF no se guarda en ningún lado.",
    },
    {
        title: "Quedan tus números",
        body: "Categorías, los cobros que se repiten y qué se va fijo cada mes.",
    },
];

export function Onboarding({
    onComplete,
    fromLanding = false,
}: {
    onComplete?: () => void;
    /** The visitor clicked a CTA on the landing: their click should end in an
     *  action, not in more reading. The dropzone's button takes focus. */
    fromLanding?: boolean;
}) {
    const [result, setResult] = useState<UploadResult | null>(null);

    useEffect(() => {
        track("onboarding.view", { from_landing: fromLanding });
    }, [fromLanding]);

    return (
        // dvh, not vh: on a phone, 100vh hides the bottom of the page behind
        // the browser's collapsing toolbar.
        <main className="flex min-h-dvh flex-col">
            <header className="mx-auto w-full max-w-page px-5 pt-6 sm:px-8 sm:pt-8">
                <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-2 text-body font-medium text-ink">
                        <BankMark size={20} />
                        Carguito
                    </div>
                    <a
                        href={LANDING_URL}
                        onClick={() => track("onboarding.to_landing")}
                        className="text-body-sm text-graphite underline decoration-mist underline-offset-4 transition-colors duration-100 hover:text-ink"
                    >
                        ¿Qué es Carguito?
                    </a>
                </div>
            </header>

            <div className="mx-auto w-full max-w-page flex-1 px-5 py-8 sm:px-8 sm:py-10">
                {result ? (
                    <div className="mx-auto max-w-xl">
                        <ReviewStatement result={result} onDone={() => onComplete?.()} />
                    </div>
                ) : (
                    <>
                        <div className="max-w-prose">
                            {/* The app's face, at the app's weight. The
                                tracking is the one hand-set value on the page:
                                the size tokens are cut for the serif and carry
                                tracking 0, which Inter does not want at 32px. */}
                            <h1 className="text-title-md font-normal -tracking-[0.015em] text-ink sm:text-title-lg">
                                Empieza por el PDF que ya tienes.
                            </h1>
                            <p className="mt-2 max-w-prose text-body text-graphite">
                                El estado de cuenta que tu banco ya te mandó. Sin conectar
                                cuentas, sin tu contraseña de banca en línea, sin capturar
                                nada a mano.
                            </p>
                        </div>

                        <StatementDropzone
                            className="mt-6 sm:mt-8"
                            autoFocus={fromLanding}
                            onResult={(r) =>
                                track("onboarding.uploaded", {
                                    template: r.template,
                                    transactions: r.transactions_created,
                                })
                            }
                            onSettled={(results) => {
                                // The review step confirms *one* parse. With a
                                // batch there is no one parse to confirm, and
                                // showing the first of five would be an
                                // arbitrary sample — so a batch opens the app,
                                // where Documentos lists every file and
                                // Movimientos holds every movement.
                                if (results.length === 1) setResult(results[0]!);
                                else if (results.length > 1) onComplete?.();
                            }}
                        />

                        <section className="mt-8 sm:mt-10">
                            <h2 className="eyebrow">Qué pasa con tu archivo</h2>
                            <UploadStory className="mx-auto mt-3 max-w-lg" />
                            {/* Three columns under a three-beat scene: each
                                label sits roughly under the thing it names —
                                phone, processor, charts. Stacked on a phone,
                                where three columns of text is not a legend. */}
                            <ol className="mx-auto mt-1 grid max-w-2xl gap-4 sm:grid-cols-3 sm:gap-5">
                                {BEATS.map((beat) => (
                                    <li key={beat.title} className="sm:text-center">
                                        <h3 className="text-body font-medium text-ink">
                                            {beat.title}
                                        </h3>
                                        <p className="mt-1 text-body-sm text-graphite">
                                            {beat.body}
                                        </p>
                                    </li>
                                ))}
                            </ol>
                            <p className="mx-auto mt-6 max-w-prose border-t border-mist pt-4 text-label text-graphite sm:text-center">
                                Si tu PDF viene con contraseña, Carguito te la pide solo para
                                abrirlo y no la guarda. Nunca es la contraseña de tu banca
                                en línea.
                            </p>
                        </section>
                    </>
                )}
            </div>
        </main>
    );
}
