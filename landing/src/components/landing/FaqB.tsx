import { appUrl } from "@/lib/site";

/**
 * The six objections a first visitor actually has, answered in the order
 * they come up. Native <details>: no JS, keyboard-accessible, indexable. The
 * answers only say what the code does today — see docs/custody-plan.md and
 * the backend's statements blueprint before changing one.
 */
const FAQ: ReadonlyArray<{ q: string; a: string; href?: { label: string; to: string } }> = [
    {
        q: "¿Cuánto cuesta?",
        a: "Hoy nada: Carguito está en una fase temprana y no cobra. Si eso cambia, lo verás aquí y en el producto antes de que te afecte.",
    },
    {
        q: "¿Qué pasa con mi PDF y con mis datos?",
        a: "En la web, el PDF viaja, se lee en memoria y se desecha; no se guarda. Desde el celular, aún en pruebas, el archivo no sale del aparato: viaja solo el texto, cifrado. La foto de un ticket subida en la web se lee en el servidor y solo se guarda su texto. Lo que Carguito sí guarda son los movimientos que sacó (fecha, monto, descripción, categoría) para dibujar tus gráficas; tu ingreso y tus fijos se guardan en tu navegador. Eso significa que el servidor puede ver tus movimientos: no es cifrado de extremo a extremo, y no lo vamos a llamar así.",
        href: { label: "Leer la política de privacidad", to: "/privacidad" },
    },
    {
        q: "¿Qué bancos lee Carguito?",
        a: "Banamex y Banco Azteca con un lector dedicado, escrito para su formato. Nu, BBVA, Santander, Banorte y HSBC pasan por el lector genérico. También el XML del SAT.",
        href: { label: "Ver la lista completa", to: "#bancos" },
    },
    {
        q: "¿Necesito instalar una app?",
        a: "No. Todo funciona desde el navegador: subes el PDF, o la foto del ticket del súper, y ves tu dinero ahí mismo. La app del celular existe, pero hoy está en pruebas.",
    },
    {
        q: "¿De dónde salen las comparaciones con el país?",
        a: "De tablas públicas del INEGI: la ENIGH 2024 (gasto e ingreso por decil y por rubro), las líneas de pobreza por ingresos (la canasta alimentaria) y el INPC. Son cifras por hogar, no por persona, así que la comparación es aproximada, y cada lectura dice de qué tabla sale. Carguito no estima el lado del país: pone tus cargos junto a lo publicado.",
    },
    {
        q: "¿Y si mi PDF tiene contraseña?",
        a: "Carguito te la pide al subirlo: la del archivo, no la de tu banco. La usa una vez para abrir el PDF y la descarta con el resto de la petición; nunca la guarda ni la registra.",
    },
];

export function FaqB() {
    const jsonLd = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        mainEntity: FAQ.map((f) => ({
            "@type": "Question",
            name: f.q,
            acceptedAnswer: { "@type": "Answer", text: f.a },
        })),
    };
    return (
        <section id="preguntas" className="mx-auto w-full max-w-page scroll-mt-20 px-5 py-14 sm:px-8 sm:py-20">
            <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
            <p className="eyebrow">Preguntas</p>
            <h2 className="mt-3 max-w-[24ch] text-title-md sm:text-title-lg">Lo que vas a preguntar antes de subir nada.</h2>
            <p className="mt-3 max-w-prose text-body-sm text-dust">
                Respuestas contra el código que corre hoy, sin letra chiquita.
            </p>
            <div className="mt-8 max-w-prose divide-y divide-line border-y border-line">
                {FAQ.map((f) => (
                    <details key={f.q} className="faq group py-4">
                        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-display text-title-md text-bone">
                            {f.q}
                            <span
                                aria-hidden
                                className="shrink-0 text-dust transition-transform duration-200 group-open:rotate-45"
                            >
                                +
                            </span>
                        </summary>
                        <p className="mt-3 text-body text-dust">{f.a}</p>
                        {f.href && (
                            <a
                                href={f.href.to}
                                className="mt-2 inline-block text-body-sm text-bone underline decoration-lineStrong underline-offset-4 hover:text-signal"
                            >
                                {f.href.label}
                            </a>
                        )}
                    </details>
                ))}
            </div>
            <p className="mt-6 text-body-sm text-dust">
                ¿Otra duda? La respuesta más corta es probarlo:{" "}
                <a href={appUrl("faq")} className="text-bone underline decoration-lineStrong underline-offset-4 hover:text-signal">
                    sube un estado de cuenta
                </a>
                .
            </p>
        </section>
    );
}
