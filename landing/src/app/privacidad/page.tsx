import type { Metadata, Viewport } from "next";
import { Nav } from "@/components/shared/Nav";
import { Footer } from "@/components/shared/Footer";
import { Highlight } from "@/components/shared/Highlight";
import "../landing.css";

export const metadata: Metadata = {
    title: "Privacidad",
    description:
        "Qué recibe Carguito, qué guarda y qué no puede prometer. El PDF se lee y se desecha; los movimientos se guardan; el servidor los puede ver.",
    alternates: { canonical: "/privacidad" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#141211" };

/**
 * The custody promise written down, no more and no less than what the code
 * does today (docs/custody-plan.md, F0 on the web). Anything here that the
 * backend stops doing must change on the same day.
 */
const SECTIONS: ReadonlyArray<{ title: string; items: string[] }> = [
    {
        title: "Qué recibimos",
        items: [
            "El PDF de tu estado de cuenta o el XML de tus facturas del SAT, cuando tú lo subes desde el navegador. Viaja cifrado en tránsito (TLS).",
            "Si el PDF está protegido, la contraseña del archivo. Se usa una vez para abrirlo y se descarta con el resto de la petición; no se guarda ni se registra en logs.",
            "Nunca la contraseña ni el usuario de tu banca en línea. Carguito no se conecta a tu banco.",
        ],
    },
    {
        title: "Qué hacemos con el archivo",
        items: [
            "Se lee en memoria: extraemos el texto (con OCR si es un PDF escaneado), detectamos el banco y separamos los movimientos.",
            "El archivo original se desecha al terminar. No se guarda en disco ni se conserva una copia. Eso quiere decir que, en la web, el servidor sí ve el PDF mientras lo lee.",
            "Desde el celular (en pruebas) el archivo no sale del aparato: el celular extrae el texto y lo envía cifrado con una llave de un solo uso; el servidor lo descifra en memoria y sigue el mismo camino.",
            "Guardamos una huella (hash) del archivo para no procesar dos veces el mismo estado de cuenta.",
        ],
    },
    {
        title: "Qué guardamos",
        items: [
            "Los movimientos extraídos: fecha, monto, descripción tal como venía en el estado y la categoría que Carguito les asignó.",
            "Los datos del estado de cuenta que hacen falta para ordenarlos: banco, tipo de cuenta y periodo.",
            "Lo que tú le enseñas: nombres que renombras, etiquetas, correcciones y cobros fijos que registras.",
        ],
    },
    {
        title: "Qué no podemos prometer hoy",
        items: [
            "No es cifrado de extremo a extremo. Para calcular tus gráficas el servidor necesita leer tus movimientos, así que puede verlos. Lo decimos aquí porque prometer lo contrario sería falso.",
            "El chat del dashboard y la lectura de tickets usan un modelo de lenguaje externo. Reciben tu pregunta y los movimientos necesarios para responderla, o los renglones del ticket. El archivo original nunca pasa por ahí.",
        ],
    },
    {
        title: "Eliminar",
        items: [
            "Puedes eliminar cualquier documento desde el producto; sus movimientos se van con él.",
        ],
    },
];

export default function Privacidad() {
    return (
        <main data-theme="dark" className="min-h-dvh bg-night text-dust">
            <Nav tone="dark" />
            <article className="mx-auto w-full max-w-page px-5 pb-16 pt-16 sm:px-8 sm:pb-24 sm:pt-24">
                <p className="eyebrow">Privacidad</p>
                <h1 className="mt-4 max-w-[18ch] text-title-lg sm:text-display">
                    Carguito lee tu archivo y lo <Highlight>desecha</Highlight>. Tus números se quedan.
                </h1>
                <p className="mt-6 max-w-prose text-body-lg text-dust">
                    Esta página dice exactamente qué recibe Carguito, qué guarda y qué no puede prometer todavía. Está
                    escrita contra el código que corre hoy, no contra un plan.
                </p>
                <div className="mt-12 grid gap-10 sm:mt-16 sm:grid-cols-[minmax(0,220px)_minmax(0,640px)] sm:gap-x-12">
                    {SECTIONS.map((s) => (
                        <section key={s.title} className="contents">
                            <h2 className="text-title-md">{s.title}</h2>
                            <ul className="-mt-6 space-y-3 sm:mt-0">
                                {s.items.map((it) => (
                                    <li key={it} className="flex gap-3 text-body text-dust">
                                        <span aria-hidden className="mt-[0.7em] h-1 w-1 shrink-0 rounded-full bg-signal" />
                                        <span>{it}</span>
                                    </li>
                                ))}
                            </ul>
                        </section>
                    ))}
                </div>
                <p className="mt-12 max-w-prose text-body-sm text-dust">
                    Actualizado el 5 de septiembre de 2026. Si cambia lo que el producto hace con tus datos, cambia
                    esta página el mismo día.
                </p>
            </article>
            <Footer tone="dark" />
        </main>
    );
}
