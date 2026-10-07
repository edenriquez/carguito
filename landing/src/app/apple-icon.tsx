import { ImageResponse } from "next/og";
import { BankMark } from "@/components/shared/BankMark";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
    return new ImageResponse(
        (
            <div
                style={{
                    width: 180,
                    height: 180,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: "#ffffff",
                }}
            >
                <BankMark size={132} />
            </div>
        ),
        size
    );
}
