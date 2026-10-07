import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * A reading card in the dashboard's order (EstadoView's `Card`): the title is
 * the finding, the chart is its proof, the foot says what it means or where
 * the number comes from. The eyebrow names the face or section it lives in.
 * The chart is an illustration of example figures, so it is hidden from
 * assistive tech; the title and the foot carry the words.
 */
export function BentoCard({
    eyebrow,
    title,
    foot,
    children,
    className,
    chartClassName,
}: {
    eyebrow: string;
    /** The finding, as the app words it. A card title, so no full stop. */
    title: string;
    foot: ReactNode;
    children: ReactNode;
    className?: string;
    chartClassName?: string;
}) {
    return (
        <article
            className={cn(
                "bento flex min-w-0 flex-col overflow-hidden rounded-panel border border-line bg-slate p-5 transition-transform duration-200 hover:-translate-y-0.5 sm:p-6",
                className
            )}
        >
            <p className="eyebrow">{eyebrow}</p>
            <h3 className="mt-2 text-body-lg font-medium">{title}</h3>
            <div aria-hidden className={cn("mt-5 flex flex-1 items-end", chartClassName)}>
                {children}
            </div>
            <div className="mt-5 border-t border-line pt-4 text-body-sm text-dust">{foot}</div>
        </article>
    );
}
