import { appUrl } from "@/lib/site";
import { cn } from "@/lib/cn";
import { Button } from "./Button";
import type { Tone } from "./Wordmark";

/** The closing panel: the reader who reached the bottom is warm, so the
 *  headline is the old promise as an echo, not a new argument. */
export function CtaBand({ tone = "light" }: { tone?: Tone }) {
    const dark = tone === "dark";
    return (
        <section className="mx-auto w-full max-w-page px-5 pb-16 sm:px-8 sm:pb-24">
            <div
                className={cn(
                    "flex flex-wrap items-center gap-6 rounded-panel border p-6 sm:p-10",
                    dark ? "border-line bg-slate" : "border-mist bg-paper shadow-card"
                )}
            >
                <div className="min-w-[16rem] flex-1">
                    <h2 className="text-title-md sm:text-title-lg">Tu estado de cuenta, leído.</h2>
                    <p className={cn("mt-2 text-body-lg", dark ? "text-dust" : "text-graphite")}>
                        Un archivo basta. Carguito lo lee, lo desecha y te deja tus números.
                    </p>
                </div>
                <Button href={appUrl("band")} size="lg" tone={tone}>
                    Comenzar con un estado de cuenta
                </Button>
            </div>
        </section>
    );
}
