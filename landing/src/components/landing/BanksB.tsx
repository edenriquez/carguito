import { BANKS } from "@/lib/data";

/**
 * The one checkable claim on the page: which statements Carguito reads and how
 * well. Two tiers plus the SAT, named plainly: no logos, no "y más". A bank
 * moves from "lector genérico" to "lector dedicado" when the backend gets a
 * parser for it. Honesty is the proof here, so nothing in it has an edge.
 */
export function BanksB() {
    const tiers = [
        {
            eyebrow: "Lector dedicado",
            names: BANKS.dedicated,
            body: "Un lector escrito para el formato de cada uno de estos bancos. Es la lectura más fiel.",
        },
        {
            eyebrow: "Lector genérico",
            names: BANKS.generic,
            body: "Carguito reconoce el banco y lee el PDF con el lector genérico. Lo que no cuadre, lo corriges ahí mismo.",
        },
        {
            eyebrow: "Facturas",
            names: [BANKS.sat],
            body: "El XML de tus facturas también entra: cada CFDI se vuelve un movimiento.",
        },
    ];
    return (
        <section id="bancos" className="mx-auto w-full max-w-page scroll-mt-20 px-5 py-14 sm:px-8 sm:py-20">
            <p className="eyebrow">Bancos</p>
            <h2 className="mt-3 max-w-[24ch] text-title-md sm:text-title-lg">Lo que Carguito sabe leer hoy.</h2>
            <div className="mt-8 grid gap-4 sm:grid-cols-3">
                {tiers.map((t) => (
                    <div key={t.eyebrow} className="rounded-panel border border-line bg-slate p-5 sm:p-6">
                        <p className="eyebrow">{t.eyebrow}</p>
                        <ul className="mt-3 flex flex-wrap gap-2">
                            {t.names.map((n) => (
                                <li
                                    key={n}
                                    className="rounded-control border border-lineStrong px-2.5 py-1 text-body-sm text-bone"
                                >
                                    {n}
                                </li>
                            ))}
                        </ul>
                        <p className="mt-4 text-body-sm text-dust">{t.body}</p>
                    </div>
                ))}
            </div>
            <p className="mt-6 max-w-prose text-body-sm text-dust">
                ¿Tu banco no aparece? Su PDF pasa por el lector genérico; qué tan bien salga depende de qué tan limpio
                venga el archivo. Los PDF escaneados pasan por OCR.
            </p>
        </section>
    );
}
