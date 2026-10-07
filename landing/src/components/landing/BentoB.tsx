import { LO_QUE_ENTRA, LO_QUE_SE_VA, PAGOS, POR_CATEGORIA, POR_MES, PRECIOS, mxn2 } from "@/lib/data";
import { BentoCard } from "./BentoCard";
import { ComposicionChart, ContrasteChart, FijosChart, PagosChart, PorMesChart, PreciosChart } from "./charts";

/**
 * Everything past the Lectura, by where it lives in the dashboard: the other
 * faces of Movimientos (Por mes, Por categoría, Precios), Plan's two faces
 * (lo que se va, lo que entra) and the Pagos bell. Each title is that view's
 * own finding sentence with the example user's figures. Count and names
 * change together with the app's navigation
 * (frontend/src/components/movimientos/MovimientosHome.tsx), not here alone.
 */
export function BentoB() {
    const card = PAGOS.card;
    return (
        <section
            id="caras"
            aria-label="Movimientos, Plan y Pagos"
            className="mx-auto w-full max-w-page scroll-mt-20 px-5 py-10 sm:px-8 sm:py-14"
        >
            <p className="eyebrow">Lo que vas a ver</p>
            <h2 className="mt-3 max-w-[24ch] text-title-md sm:text-title-lg">
                El mismo PDF, por mes, por categoría y por lo que se repite.
            </h2>
            <p className="mt-3 max-w-prose text-body-sm text-dust">
                Las otras caras de Movimientos, el Plan y los Pagos. Cifras de ejemplo, dibujadas como las verás en el
                producto; las tuyas salen de tu estado de cuenta.
            </p>
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-12">
                <BentoCard
                    className="lg:col-span-7"
                    eyebrow="Movimientos · Por mes"
                    title={POR_MES.title}
                    foot="Una columna por mes y tu promedio como regla punteada. El mes en curso va aparte, «al 28», y no entra al promedio. Abre un mes y ves sus categorías."
                >
                    <PorMesChart />
                </BentoCard>
                <BentoCard
                    className="lg:col-span-5"
                    eyebrow="Movimientos · Por categoría"
                    title={POR_CATEGORIA.title}
                    foot="Cada categoría con su color de siempre. Debajo de la barra, cada una se abre hasta el cargo; lo que no tiene categoría va arriba, con su botón para revisarlo."
                >
                    <ComposicionChart />
                </BentoCard>
                <BentoCard
                    className="lg:col-span-4"
                    eyebrow="Plan · Lo que se va"
                    title={LO_QUE_SE_VA.title}
                    foot="Carguito encuentra los cobros que se repiten; tú fijas los que sí o sí llegan y agregas los que no vio, como la renta. Lo proyectado va aparte de lo medido."
                >
                    <FijosChart />
                </BentoCard>
                <BentoCard
                    className="lg:col-span-4"
                    eyebrow="Plan · Lo que entra"
                    title={LO_QUE_ENTRA.title}
                    foot="Etiqueta un abono como nómina o como extra una vez. Carguito no adivina lo que entra: cuenta solo lo que nombraste."
                >
                    <ContrasteChart />
                </BentoCard>
                <BentoCard
                    className="sm:col-span-2 lg:col-span-4"
                    eyebrow="Pagos"
                    title={`${card.bank} crédito: ${mxn2(card.amount)} antes del ${card.due}`}
                    foot="El pago de la tarjeta, como lo imprime tu estado de cuenta, y el mes con tus cargos fijos, bimestrales y semestrales. Una visita a la tienda, aunque se repita, no es un pago."
                >
                    <PagosChart />
                </BentoCard>
                <BentoCard
                    className="sm:col-span-2 lg:col-span-12"
                    eyebrow="Movimientos · Precios"
                    title={PRECIOS.title}
                    foot="Sube la foto del ticket del súper desde la web o desde la app del celular, que hoy está en pruebas. Carguito lo lee renglón por renglón, guarda solo el texto y sigue el precio de cada producto entre una compra y la siguiente."
                >
                    <PreciosChart />
                </BentoCard>
            </div>
        </section>
    );
}
