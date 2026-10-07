import Link from "next/link";
import { cn } from "@/lib/cn";
import { BankMark } from "./BankMark";

export type Tone = "light" | "dark";

/** The smiling bank next to the wordmark — the product's logo. */
export function Wordmark({ tone = "light", className }: { tone?: Tone; className?: string }) {
    return (
        <Link
            href="/"
            className={cn(
                "inline-flex items-center gap-2 text-body font-medium",
                tone === "dark" ? "text-bone" : "text-ink",
                className
            )}
        >
            <BankMark size={20} />
            Carguito
        </Link>
    );
}
