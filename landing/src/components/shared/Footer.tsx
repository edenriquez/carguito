import Link from "next/link";
import { appUrl } from "@/lib/site";
import { cn } from "@/lib/cn";
import type { Tone } from "./Wordmark";

/**
 * The links a visitor looks for at the bottom, and only those: no contact
 * address because there is no real one to give yet. Anchors are absolute
 * (`/#…`) so the same footer works from `/privacidad`.
 */
const LINKS = [
    { label: "Cómo funciona", href: "/#como-funciona" },
    { label: "Bancos", href: "/#bancos" },
    { label: "Preguntas", href: "/#preguntas" },
    { label: "Privacidad", href: "/privacidad" },
];

export function Footer({ tone = "light" }: { tone?: Tone }) {
    const dark = tone === "dark";
    const link = cn(
        "text-body-sm underline-offset-4 hover:underline",
        dark ? "text-dust hover:text-bone" : "text-ash hover:text-ink"
    );
    return (
        <footer className={cn("border-t py-8", dark ? "border-line" : "border-mist")}>
            <div className="mx-auto flex w-full max-w-page flex-col gap-4 px-5 sm:flex-row sm:items-center sm:justify-between sm:px-8">
                <p className={cn("text-body-sm", dark ? "text-dust" : "text-ash")}>
                    Carguito. Finanzas personales para México.
                </p>
                <nav aria-label="Pie de página" className="flex flex-wrap gap-x-5 gap-y-2">
                    {LINKS.map((l) => (
                        <Link key={l.href} href={l.href} className={link}>
                            {l.label}
                        </Link>
                    ))}
                    <a href={appUrl("footer")} className={link}>
                        Comenzar
                    </a>
                </nav>
            </div>
        </footer>
    );
}
