import { colors } from "@/design/tokens";
import { BankMark } from "@/components/ui";

/**
 * What happens to your file, as one looping scene.
 *
 * It was written for the landing banner and deleted with it; the keyframes
 * outlived the component in globals.css. It belongs here more than it ever
 * belonged there: on the landing it illustrated a promise, and on this screen
 * it answers the question somebody is actually holding — "I am about to hand
 * a bank statement to a website, what happens to it?" — before they hand it
 * over. It replaced three paragraphs that made the same claim in words.
 *
 * The story it must tell, in order: the file lives on the PHONE → one
 * transient copy travels to the processor → the FILE dissolves there (it is
 * discarded, never stored) → only structured DATA continues into the charts →
 * the custody seal settles back on the phone. That last beat is the product's
 * long game — today the backend does the parsing, but the phone as custodian
 * is the architecture — so the seal lands on the phone, not on the server.
 *
 * Pure SVG + the `story-*` keyframes in globals.css. Every element's static
 * style IS the composed final scene, which is what reduced-motion users see.
 */
export function UploadStory({ className }: { className?: string }) {
    return (
        <div className={className}>
            <svg
                viewBox="0 0 560 300"
                role="img"
                aria-label="Tu archivo viaja del teléfono al procesador, se desecha, y solo tus datos llegan a las gráficas; la custodia queda en tu teléfono."
                className="h-auto w-full"
            >
                {/* ---- Rails: the journey, always faintly in motion -------- */}
                <path
                    d="M 150 150 H 244"
                    fill="none"
                    stroke={colors.muted}
                    strokeWidth="1.5"
                    className="story-dash"
                />
                <path
                    d="M 316 150 H 396"
                    fill="none"
                    stroke={colors.muted}
                    strokeWidth="1.5"
                    className="story-dash"
                />

                {/* ---- The phone: origin and custodian --------------------- */}
                <g>
                    <rect
                        x="58"
                        y="52"
                        width="92"
                        height="196"
                        rx="16"
                        fill={colors.paper}
                        stroke={colors.mist}
                        strokeWidth="1.5"
                    />
                    {/* speaker slit */}
                    <rect x="92" y="64" width="24" height="3" rx="1.5" fill={colors.mist} />
                    {/* screen hairlines: the ledger living on the device */}
                    <rect x="72" y="84" width="46" height="4" rx="2" fill={colors.mist} />
                    <rect x="72" y="98" width="62" height="4" rx="2" fill={colors.fog} />
                    <rect x="72" y="112" width="54" height="4" rx="2" fill={colors.fog} />
                    <rect x="72" y="126" width="60" height="4" rx="2" fill={colors.fog} />

                    {/* The transient copy: a small document that makes the trip
                        and dissolves at the processor. */}
                    <g className="story-doc" style={{ opacity: 0 }}>
                        <rect
                            x="80"
                            y="168"
                            width="44"
                            height="56"
                            rx="6"
                            fill={colors.paper}
                            stroke={colors.ash}
                            strokeWidth="1.5"
                        />
                        <path
                            d="M 112 168 v 10 h 12"
                            fill="none"
                            stroke={colors.ash}
                            strokeWidth="1.5"
                        />
                        <rect x="88" y="186" width="24" height="3" rx="1.5" fill={colors.ash} />
                        <rect x="88" y="196" width="28" height="3" rx="1.5" fill={colors.mist} />
                        <rect x="88" y="206" width="20" height="3" rx="1.5" fill={colors.mist} />
                    </g>

                    {/* The custody seal: it lands on the PHONE. */}
                    <g className="story-seal">
                        <circle
                            cx="150"
                            cy="70"
                            r="14"
                            fill={colors.canvas}
                            stroke={colors.edge}
                            strokeWidth="1.5"
                        />
                        <path
                            d="M 150 61.5 l 7 3 v 5 c 0 4.5 -3 7.5 -7 9 c -4 -1.5 -7 -4.5 -7 -9 v -5 z"
                            fill={colors.signal}
                            opacity="0.15"
                            stroke={colors.signal}
                            strokeWidth="1.2"
                        />
                        <path
                            d="M 146.5 70 l 2.5 2.5 l 5 -5.5"
                            fill="none"
                            stroke={colors.signal}
                            strokeWidth="1.6"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        />
                    </g>
                </g>

                {/* ---- The processor: reads, keeps nothing ------------------ */}
                <g>
                    <circle
                        cx="280"
                        cy="150"
                        r="30"
                        fill={colors.paper}
                        stroke={colors.mist}
                        strokeWidth="1.5"
                    />
                    {/* pulse when the file arrives and dissolves */}
                    <circle
                        cx="280"
                        cy="150"
                        r="30"
                        fill="none"
                        stroke={colors.signal}
                        strokeWidth="1.5"
                        className="story-node-ring"
                        style={{ opacity: 0, transformBox: "fill-box", transformOrigin: "center" }}
                    />
                    {/* the bank mark — Carguito doing the reading */}
                    <BankMark size={28} x={266} y={136} />

                    {/* Data packets: what actually continues — not the file. */}
                    <g className="story-packet-a" style={{ opacity: 0 }}>
                        <rect x="312" y="138" width="9" height="9" rx="2.5" fill={colors.soot} />
                    </g>
                    <g className="story-packet-b" style={{ opacity: 0 }}>
                        <rect x="312" y="152" width="9" height="9" rx="2.5" fill={colors.signal} />
                    </g>
                </g>

                {/* ---- The charts: where the data ends up ------------------- */}
                <g>
                    <rect
                        x="396"
                        y="70"
                        width="130"
                        height="160"
                        rx="12"
                        fill={colors.paper}
                        stroke={colors.mist}
                        strokeWidth="1.5"
                    />
                    <rect x="410" y="86" width="52" height="5" rx="2.5" fill={colors.mist} />
                    {/* bars grow when the packets land */}
                    <g>
                        <rect className="story-bar" x="412" y="150" width="16" height="60" rx="2" fill={colors.soot} opacity="0.85" />
                        <rect className="story-bar" x="436" y="170" width="16" height="40" rx="2" fill={colors.ash} />
                        <rect className="story-bar" x="460" y="136" width="16" height="74" rx="2" fill={colors.soot} opacity="0.65" />
                        <rect className="story-bar" x="484" y="158" width="16" height="52" rx="2" fill={colors.ash} />
                    </g>
                    {/* the net line draws itself over the bars */}
                    <path
                        className="story-line"
                        d="M 412 140 L 444 126 L 468 132 L 500 108"
                        fill="none"
                        stroke={colors.signal}
                        strokeWidth="2"
                        strokeLinecap="round"
                    />
                    <line x1="410" y1="212" x2="512" y2="212" stroke={colors.mist} strokeWidth="1.5" />
                </g>
            </svg>
        </div>
    );
}
