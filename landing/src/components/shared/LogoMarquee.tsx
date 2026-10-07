/* eslint-disable @next/next/no-img-element */
import { cn } from "@/lib/cn";
import type { Tone } from "./Wordmark";

const LOGOS = [
    "oxxo", "cfe", "telcel", "rappi", "didi", "netflix", "spotify", "uber",
    "amazon", "mercado-libre", "totalplay", "izzi", "starbucks", "soriana",
    "chedraui", "mercado-pago",
];

/**
 * "Reconoce a quien te cobra": the merchants Carguito already names from a raw
 * statement line (every slug here is in frontend/src/lib/merchants.ts). Pure
 * CSS loop over a duplicated track; pauses on hover and under reduced motion.
 * Plain <img>: 16 tiny PNGs don't need the optimizer. `note` scopes the
 * promise: these are named; the rest you name once.
 */
export function LogoMarquee({ tone = "light", label, note }: { tone?: Tone; label: string; note?: string }) {
    const dark = tone === "dark";
    return (
        <section aria-label={label} className="mx-auto w-full max-w-page px-5 py-10 sm:px-8 sm:py-14">
            <p className="eyebrow text-center">{label}</p>
            <div className="marquee mt-6 overflow-hidden">
                <div className="marquee-track items-center">
                    {[...LOGOS, ...LOGOS].map((slug, i) => (
                        <img
                            key={`${slug}-${i}`}
                            src={`/logos/${slug}.png`}
                            alt={i < LOGOS.length ? slug.replace(/-/g, " ") : ""}
                            aria-hidden={i >= LOGOS.length || undefined}
                            width={40}
                            height={40}
                            loading="lazy"
                            className={cn(
                                "h-8 w-8 shrink-0 rounded-[6px] object-contain sm:h-10 sm:w-10",
                                dark ? "opacity-75 grayscale" : "opacity-90"
                            )}
                        />
                    ))}
                </div>
            </div>
            {note && (
                <p className={cn("mx-auto mt-6 max-w-prose text-center text-body-sm", dark ? "text-dust" : "text-ash")}>
                    {note}
                </p>
            )}
        </section>
    );
}
