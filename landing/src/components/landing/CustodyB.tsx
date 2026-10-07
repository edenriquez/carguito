import { GraduationCap, ShieldCheck, Timer } from "lucide-react";

const CELLS = [
    {
        icon: GraduationCap,
        title: "Aprende de ti",
        body: "Renombra «POCK*SUPERLECLERC» a «Súper de la esquina» una vez: Carguito lo aplica a los parecidos y a cada estado de cuenta que subas después.",
    },
    {
        icon: ShieldCheck,
        title: "Ni una contraseña del banco",
        body: "Carguito no se conecta a tu banco, así que no hay nada que darle. En la web, el PDF viaja, se lee en memoria y se desecha. Desde el celular (en pruebas) ni siquiera sale del aparato: viaja solo el texto, cifrado.",
    },
    {
        icon: Timer,
        title: "Un archivo basta",
        body: "El primer estado de cuenta ya trae su lectura; las que comparan meses aparecen desde el segundo mes completo, y cada documento que sumes afina la historia. Abajo dice qué bancos lee Carguito y qué tan bien.",
    },
];

/**
 * The second opinion on the page: the practice of asking for a bank password,
 * never an app by name. The headline is the stance; the three cells are the
 * mechanics that back it (docs/custody-plan.md, F0 on the web).
 */
export function CustodyB() {
    return (
        <section id="custodia" className="mx-auto w-full max-w-page scroll-mt-20 px-5 py-10 sm:px-8 sm:py-14">
            <p className="eyebrow">Custodia</p>
            <h2 className="mt-3 max-w-[24ch] text-title-md sm:text-title-lg">
                Ninguna app debería pedirte la contraseña de tu banco.
            </h2>
            <div className="mt-8 grid gap-px overflow-hidden rounded-panel border border-line bg-line sm:grid-cols-3">
                {CELLS.map(({ icon: Icon, title, body }) => (
                    <div key={title} className="bg-night p-5 sm:p-6">
                        <Icon size={16} className="text-signal" aria-hidden />
                        <h3 className="mt-2.5 text-title-sm">{title}</h3>
                        <p className="mt-1.5 text-body-sm text-dust">{body}</p>
                    </div>
                ))}
            </div>
        </section>
    );
}
