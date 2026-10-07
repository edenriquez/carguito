"use client";

import { useEffect, useState } from "react";
import { receiptsApi } from "@/lib/prices";

/**
 * How many tickets the account has. `null` while unknown.
 *
 * Documentos reads it to say how many tickets have been read, and where the
 * rest come from. A failed read is treated as zero: a note that appears
 * because the API blinked is worse than one that shows up a beat late.
 */
export function useReceiptCount(version = 0): number | null {
    const [count, setCount] = useState<number | null>(null);
    useEffect(() => {
        let stale = false;
        receiptsApi
            .list()
            .then((res) => !stale && setCount(res.total ?? res.items.length))
            .catch(() => !stale && setCount(0));
        return () => {
            stale = true;
        };
    }, [version]);
    return count;
}
