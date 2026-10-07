import { FIGURES } from "@/lib/data";
import { DARK } from "@/components/shared/mock/palette";
import { ScatterMock } from "@/components/shared/mock/ScatterMock";
import { AttentionMock } from "@/components/shared/mock/AttentionMock";
import { StackMock } from "@/components/shared/mock/StackMock";
import { CalendarMock } from "@/components/shared/mock/CalendarMock";
import { ForecastMock } from "@/components/shared/mock/ForecastMock";
import { TicketMock } from "@/components/shared/mock/TicketMock";
import { BentoCard } from "./BentoCard";

/**
 * The product as six readings, in the order of the dashboard's navigation
 * (docs/audit/2026-09-05, IA decision): Movimientos, Atención, Categorías,
 * Plan (lo que se va / lo que entra), Precios. Custody is not a reading — it
 * has its own strip, the FAQ and /privacidad. Count and names change together
 * with the app's IA, not here alone.
 */
export function BentoB() {
    return (
        <section
            id="lecturas"
            aria-label="Lo que vas a ver"
            className="mx-auto w-full max-w-page scroll-mt-20 px-5 py-10 sm:px-8 sm:py-14"
        >
            <p className="eyebrow">Lo que vas a ver</p>
            <h2 className="mt-3 max-w-[22ch] text-title-md sm:text-title-lg">
                Seis lecturas de un solo PDF.
            </h2>
            <p className="mt-3 max-w-prose text-body-sm text-dust">
                Cifras de ejemplo, dibujadas como las verás en el producto. Las tuyas salen de tu estado de cuenta.
            </p>
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-12">
                <BentoCard
                    className="lg:col-span-7"
                    eyebrow="Movimientos"
                    metric={String(FIGURES.movements)}
                    title="Cada movimiento, dibujado"
                    body="Un punto por cargo, en el tiempo, con lo que salió en el periodo. Tócalo y edítalo ahí mismo."
                    mock={<ScatterMock p={DARK} />}
                    mockClassName="sm:h-52"
                />
                <BentoCard
                    className="lg:col-span-5"
                    eyebrow="Atención"
                    metric={String(FIGURES.attentionCount)}
                    title="Lo que llama la atención"
                    body="Cargos inusuales, duplicados y comercios nuevos, señalados antes de que los busques."
                    mock={<AttentionMock p={DARK} />}
                    mockClassName="sm:h-52"
                />
                <BentoCard
                    className="lg:col-span-4"
                    eyebrow="Categorías"
                    metric={`${FIGURES.categoriesTop} ${FIGURES.categoriesTopShare}`}
                    title="Cada mes, por categoría"
                    body="Columnas apiladas que dicen cuánto costó cada mes y en qué."
                    mock={<StackMock p={DARK} />}
                />
                <BentoCard
                    className="lg:col-span-4"
                    eyebrow="Plan · Lo que se va"
                    metric={`${FIGURES.fixedMonthly}/mes`}
                    title="Los cobros que se repiten"
                    body={`Carguito los encuentra solo; aquí, ${FIGURES.fixedCount} ${FIGURES.fixedCaption}. Tú fijas los que sí o sí se cobran, y quedan con su ritmo y su próxima fecha.`}
                    mock={<CalendarMock p={DARK} />}
                />
                <BentoCard
                    className="lg:col-span-4"
                    eyebrow="Plan · Lo que entra"
                    metric={FIGURES.forecastNeed}
                    title="Lo que necesitas antes de la quincena"
                    body="Etiqueta un abono como nómina una vez. Desde ahí, Carguito contrasta lo que te entra con lo que ya está comprometido."
                    mock={<ForecastMock p={DARK} />}
                />
                <BentoCard
                    className="sm:col-span-2 lg:col-span-12"
                    eyebrow="Precios · desde el celular"
                    metric={FIGURES.ticketDelta}
                    title={FIGURES.ticketLine}
                    body="El ticket del súper, leído renglón por renglón: Carguito sigue el precio de cada producto entre una compra y la siguiente. Los tickets entran con la app del celular, que hoy está en pruebas."
                    mock={<TicketMock p={DARK} className="h-full w-full max-w-[200px]" />}
                    mockClassName="h-32 items-center justify-center sm:h-36"
                />
            </div>
        </section>
    );
}
