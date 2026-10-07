const STEPS = [
    {
        title: "Subes el archivo",
        body: "El PDF de tu banco o el XML del SAT, arrastrado a la pantalla. Si el PDF trae contraseña, Carguito te la pide una vez para abrirlo y no la guarda. La de tu banca en línea no se pide nunca.",
    },
    {
        title: "Carguito lo lee y lo desecha",
        body: "Saca los movimientos, reconoce el banco, categoriza y desecha el archivo original. Solo quedan tus números.",
    },
    {
        title: "Ves tu dinero",
        body: "Gráficas, categorías y cobros que se repiten desde el primer documento, y mejores con cada corrección tuya. Con dos cuentas, Carguito empareja los pagos que coinciden entre ellas; los que no, los marcas tú para que no cuenten dos veces.",
    },
];

/**
 * Three steps on one rule: a timeline read left to right. Sits right under the
 * hero so "Cómo funciona" is the second thing anyone reads: a bold headline
 * provokes "how?", and this is the answer, in the product's mechanics.
 */
export function StepsB() {
    return (
        <section id="como-funciona" className="mx-auto w-full max-w-page scroll-mt-20 px-5 py-14 sm:px-8 sm:py-20">
            <p className="eyebrow">Cómo funciona</p>
            <h2 className="mt-3 max-w-[24ch] text-title-md sm:text-title-lg">Tres pasos. Ninguno es conectar tu banco.</h2>
            <ol className="relative mt-10 grid gap-8 sm:grid-cols-3 sm:gap-6">
                <span aria-hidden className="absolute left-0 right-0 top-[7px] hidden h-px bg-lineStrong sm:block" />
                {STEPS.map((s, i) => (
                    <li key={s.title} className="relative sm:pt-8">
                        <span
                            aria-hidden
                            className="absolute left-0 top-0 hidden h-[15px] w-[15px] rounded-full border-2 border-signal bg-night sm:block"
                        />
                        <span className="eyebrow">Paso {i + 1}</span>
                        <h3 className="mt-2 text-title-sm">{s.title}</h3>
                        <p className="mt-1.5 text-body-sm text-dust">{s.body}</p>
                    </li>
                ))}
            </ol>
        </section>
    );
}
