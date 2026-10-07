import { ImageResponse } from "next/og";
import { BankMark } from "@/components/ui/BankMark";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

/** Favicon: the smiling bank on a Paper tile, so its Soot face stays legible. */
export default function Icon() {
    return new ImageResponse(
        (
            <div
                style={{
                    width: 32,
                    height: 32,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: "#ffffff",
                    borderRadius: 8,
                }}
            >
                <BankMark size={28} />
            </div>
        ),
        size
    );
}
