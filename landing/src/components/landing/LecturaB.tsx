import { Highlight } from "@/components/shared/Highlight";
import { cn } from "@/lib/cn";
import { INCOME, LECTURA, NO_CUADRA, mxn } from "@/lib/data";
import { ENIGH_MONTHLY, INPC_SOURCE } from "@/lib/pais";
import { BentoCard } from "./BentoCard";
import { CanastaChart, DecilChart, DiaCeroChart, DiasChart, InpcChart, NoCuadraList } from "./charts";

/**
 * The Lectura: the face the dashboard opens on after an upload
 * (frontend/src/components/estado/EstadoView.tsx). It is the product's
 * strongest proof, so it gets the first look after "Cómo funciona": the
 * statement held against the country's published tables, then against the
 * user's own income, then in time, then what does not add up. Titles are
 * the app's finding sentences filled with the example user's figures
 * (lib/data.ts); the country's figures are real (lib/pais.ts).
 */
export function LecturaB() {
    const { decil } = LECTURA;
    return (
        <section
            id="lecturas"
            aria-label="La lectura de tu estado de cuenta"
            className="mx-auto w-full max-w-page scroll-mt-20 px-5 py-10 sm:px-8 sm:py-14"
        >
            <p className="eyebrow">Lectura</p>
            <h2 className="mt-3 max-w-[22ch] text-title-md sm:text-title-lg">
                Tu estado de cuenta, leído <Highlight>contra el país</Highlight>.
            </h2>
            <p className="mt-3 max-w-prose text-body-sm text-dust">
                Lo primero que ves al subir tu PDF. Cada tarjeta es un hallazgo: el título lo dice, la gráfica lo prueba
                y la línea de abajo dice de dónde sale. Lo tuyo aquí son cifras de ejemplo; lo del país es lo publicado
                por el INEGI: la ENIGH 2024, las líneas de pobreza y el INPC.
            </p>

            <div className="mt-8 grid gap-4 lg:grid-cols-2">
                <article className="bento flex min-w-0 flex-col overflow-hidden rounded-panel border border-line bg-slate p-5 sm:p-6 lg:col-span-2 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,36rem)] lg:grid-rows-[auto_1fr_auto] lg:gap-x-12">
                    <div>
                        <p className="eyebrow">Contra el país</p>
                        <h3 className="mt-2 text-title-sm">{decil.title}</h3>
                    </div>
                    <Figures
                        className="mt-5 lg:col-start-1 lg:row-start-2 lg:self-center"
                        items={[
                            { label: "Tu gasto al mes", value: mxn(LECTURA.average), note: `promedio de ${LECTURA.months} meses`, on: true },
                            {
                                label: `Un hogar del decil ${decil.label}`,
                                value: mxn(ENIGH_MONTHLY.gasto[decil.index]!),
                                note: `gasta al mes; gana ${mxn(ENIGH_MONTHLY.ingreso[decil.index]!)}`,
                            },
                            { label: "Gastas como quien gana", value: `~${mxn(decil.equivalent)}`, note: "al mes, según la ENIGH" },
                            { label: "Tu ingreso", value: mxn(INCOME), note: `${mxn(decil.equivalent - INCOME)} menos que eso` },
                        ]}
                    />
                    <div aria-hidden className="mt-6 lg:col-start-2 lg:row-span-3 lg:row-start-1 lg:mt-0 lg:self-center">
                        <DecilChart />
                    </div>
                    <div className="mt-5 border-t border-line pt-4 text-body-sm text-dust lg:col-start-1 lg:row-start-3">
                        {decil.foot}
                    </div>
                </article>

                <BentoCard eyebrow="Contra el país" title={LECTURA.canasta.title} foot={LECTURA.canasta.foot} chartClassName="items-center">
                    <CanastaChart />
                </BentoCard>
                <BentoCard
                    eyebrow="Contra el país"
                    title={LECTURA.inpc.title}
                    foot={`Cada producto que compraste en más de un mes, contra el INPC de sus propios meses; por litro o kilo cuando el ticket dio tamaño. ${INPC_SOURCE}.`}
                >
                    <InpcChart />
                </BentoCard>
                <BentoCard eyebrow="Con tu ingreso" title={LECTURA.diaCero.title} foot={LECTURA.diaCero.foot}>
                    <DiaCeroChart />
                </BentoCard>
                <BentoCard eyebrow="En el tiempo" title={LECTURA.dias.title} foot={LECTURA.dias.foot}>
                    <DiasChart />
                </BentoCard>
                <BentoCard
                    className="lg:col-span-2"
                    eyebrow="Lo que no cuadra"
                    title={`${NO_CUADRA.length} cargos que no cuadran`}
                    foot="Carguito no adivina: tú dices si son tuyos."
                >
                    <NoCuadraList />
                </BentoCard>
            </div>

            <div className="mt-4 rounded-panel border border-line p-5 sm:p-6">
                <p className="eyebrow">En la misma lectura</p>
                <ul className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                    {LECTURA.more.map((m) => (
                        <li key={m.title} className="text-body-sm">
                            <span className="block text-label text-ash">{m.section}</span>
                            <span className="text-bone">{m.title}</span>
                        </li>
                    ))}
                </ul>
                <p className="mt-5 max-w-prose text-body-sm text-dust">
                    Las lecturas con tu ingreso esperan a que lo escribas una vez o etiquetes tu nómina en Plan: Carguito no
                    adivina cuánto entra. Las que comparan meses aparecen desde el segundo mes completo. Las de la ENIGH son
                    por hogar, no por persona, y Carguito lo dice en cada una. Base: los cargos de los últimos seis meses,
                    sin «Entre mis cuentas» ni excluidos.
                </p>
            </div>
        </section>
    );
}

/** The figures a feature card reads from, two by two — EstadoView's `Figures`. */
function Figures({ items, className }: { items: { label: string; value: string; note: string; on?: boolean }[]; className?: string }) {
    return (
        <dl className={cn("grid grid-cols-2 gap-x-6 gap-y-5", className)}>
            {items.map((f) => (
                <div key={f.label} className="min-w-0">
                    <dt className="text-label text-dust">{f.label}</dt>
                    <dd className={cn("mt-1 truncate tabular text-metric-sm", f.on ? "text-signal" : "text-bone")}>{f.value}</dd>
                    <dd className="mt-0.5 text-label text-ash">{f.note}</dd>
                </div>
            ))}
        </dl>
    );
}
