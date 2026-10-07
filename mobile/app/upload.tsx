import { useEffect, useRef, useState } from "react";
import {
    ActivityIndicator,
    Alert,
    Modal,
    ScrollView,
    Share,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    View,
} from "react-native";
import * as DocumentPicker from "expo-document-picker";
import * as Linking from "expo-linking";
import { api } from "@/lib/api";
import {
    ExtractedPayload,
    ExtractionError,
    extractDocument,
    extractionMessage,
} from "@/lib/extract";
import {
    AlreadyProcessedError,
    IngestResponse,
    KeyPinMismatchError,
    sendExtracted,
    trustServerKey,
} from "@/lib/secure-transport";
import {
    forgetStatement,
    listStatements,
    markProcessed,
    markUnprocessed,
    storeStatement,
    StoredStatement,
} from "@/lib/storage";

type UploadResult = {
    filename: string;
    template: string;
    transactionsCreated: number;
    dashboardUrl: string;
};

export default function UploadScreen() {
    const [items, setItems] = useState<StoredStatement[]>([]);
    const [phase, setPhase] = useState<string | null>(null);
    const [status, setStatus] = useState<string | null>(null);
    const [result, setResult] = useState<UploadResult | null>(null);
    /** Ids ticked in selection mode. A non-null set *is* selection mode. */
    const [selected, setSelected] = useState<Set<string> | null>(null);
    /**
     * Set when an encrypted PDF needs a password. `wrong` distinguishes the
     * first ask from a retry after the PDF rejected one. The password itself
     * lives in `password` and is dropped as soon as extraction finishes — it is
     * never written to the index or put in the payload.
     */
    const [passwordFor, setPasswordFor] = useState<{
        stored: StoredStatement;
        wrong: boolean;
    } | null>(null);
    const [password, setPassword] = useState("");

    /** Kept so a key-rotation prompt can resume the send without re-reading. */
    const pending = useRef<{ payload: ExtractedPayload; storedId: string } | null>(null);

    async function refresh() {
        setItems(await listStatements());
    }

    useEffect(() => {
        refresh();
    }, []);

    async function pickAndProcess() {
        const picked = await DocumentPicker.getDocumentAsync({
            type: ["application/pdf", "text/xml", "application/xml"],
            copyToCacheDirectory: true,
        });
        if (picked.canceled) return;

        const asset = picked.assets[0];
        setResult(null);
        setStatus(null);

        // 1. The durable copy lands on the phone first, and stays there.
        setPhase("Guardando en tu teléfono…");
        const stored = await storeStatement(
            asset.uri,
            asset.name,
            asset.mimeType ?? "application/octet-stream"
        );
        await refresh();

        // 2. The custody beat: extraction happens here, not on a server.
        await extractAndSend(stored);
    }

    /**
     * Extraction + send for a file already stored on the phone. Split out of
     * `pickAndProcess` so an encrypted PDF can be retried with a password
     * without asking the user to pick the file again — the durable copy is
     * already in the custody boundary.
     */
    async function extractAndSend(stored: StoredStatement, pdfPassword?: string) {
        setPhase("Leyendo en tu teléfono…");
        let payload: ExtractedPayload;
        try {
            payload = await extractDocument(
                stored.localUri,
                stored.name,
                stored.mimeType,
                pdfPassword
            );
        } catch (e) {
            setPhase(null);
            const code = e instanceof ExtractionError ? e.code : null;
            if (code === "password_required" || code === "password_incorrect") {
                setPassword("");
                setPasswordFor({ stored, wrong: code === "password_incorrect" });
                return;
            }
            setStatus(extractionMessage(e));
            return;
        }

        await sealAndSend(payload, stored.id, stored.name);
    }

    function submitPassword() {
        if (!passwordFor || password.length === 0) return;
        const { stored } = passwordFor;
        const entered = password;
        setPasswordFor(null);
        setPassword("");
        extractAndSend(stored, entered);
    }

    function cancelPassword() {
        setPasswordFor(null);
        setPassword("");
        setStatus("Guardado en tu teléfono, sin leer. Necesita la contraseña del PDF.");
    }

    async function sealAndSend(payload: ExtractedPayload, storedId: string, filename: string) {
        pending.current = { payload, storedId };
        setPhase("Enviando cifrado…");
        try {
            const res: IngestResponse = await sendExtracted(payload);
            await markProcessed(storedId, res.statement_id);
            await refresh();
            setPhase(null);
            setStatus(null);
            setResult({
                filename,
                template: res.template,
                transactionsCreated: res.transactions_created,
                dashboardUrl: res.dashboard_url,
            });
            pending.current = null;
        } catch (e) {
            setPhase(null);
            console.error(
                `[DBG] sealAndSend failed: name=${(e as Error)?.name} message=${(e as Error)?.message} status=${(e as { status?: number })?.status}\n${(e as Error)?.stack ?? "(no stack)"}`
            ); // TEMP DEBUG
            if (e instanceof KeyPinMismatchError) {
                promptKeyRotation(e, filename);
                return;
            }
            if (e instanceof AlreadyProcessedError) {
                setStatus("Este archivo ya estaba procesado. No se envió nada nuevo.");
                pending.current = null;
                return;
            }
            setStatus(`Guardado en tu teléfono. No se pudo enviar: ${(e as Error).message}`);
        }
    }

    function promptKeyRotation(error: KeyPinMismatchError, filename: string) {
        setStatus(
            "La llave pública del servidor cambió. No envié nada: así se ve un intento de intercepción."
        );
        Alert.alert(
            "La llave del servidor cambió",
            `Tenía fijada la llave "${error.pinned.key_id}" desde ${new Date(
                error.pinned.pinned_at
            ).toLocaleDateString()} y ahora el servidor ofrece "${error.offered.key_id}".\n\n` +
                "Si no esperabas una rotación de llaves, cancela: alguien podría estar en medio.",
            [
                { text: "Cancelar", style: "cancel" },
                {
                    text: "Confiar en la nueva llave",
                    style: "destructive",
                    onPress: async () => {
                        await trustServerKey(error.offered);
                        const job = pending.current;
                        if (job) await sealAndSend(job.payload, job.storedId, filename);
                    },
                },
            ]
        );
    }

    async function openDashboard(url: string) {
        try {
            await Linking.openURL(url);
        } catch {
            setStatus(`No pude abrir el link. Cópialo a mano: ${url}`);
        }
    }

    async function shareDashboard(res: UploadResult) {
        try {
            await Share.share({
                message: `${res.transactionsCreated} movimientos de ${res.filename} en Carguito: ${res.dashboardUrl}`,
                url: res.dashboardUrl,
            });
        } catch {
            /* user dismissed the sheet */
        }
    }

    function confirmDelete(item: StoredStatement) {
        Alert.alert(
            "Eliminar del servidor",
            `Se borraran los movimientos extraidos de "${item.name}". El archivo se queda en tu telefono.`,
            [
                { text: "Cancelar", style: "cancel" },
                {
                    text: "Eliminar",
                    style: "destructive",
                    onPress: () => deleteRemote(item),
                },
            ]
        );
    }

    /* ---------------------------------------------------------------- */
    /* Selection mode                                                     */
    /* ---------------------------------------------------------------- */

    function toggleSelection(id: string) {
        setSelected((current) => {
            const next = new Set(current ?? []);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }

    function selectAll() {
        setSelected(new Set(items.map((item) => item.id)));
    }

    const selectedItems = items.filter((item) => selected?.has(item.id));
    /** Only these have server-side data; the rest were never processed. */
    const selectedWithRemote = selectedItems.filter((item) => item.remoteId);

    /**
     * Says out loud what each side loses before anything is destroyed. The two
     * consequences are genuinely different — the phone copy is gone for good,
     * while the server data can be rebuilt by uploading the file again — so the
     * message names them separately instead of saying "delete N items".
     */
    function confirmDeleteSelected() {
        const count = selectedItems.length;
        if (count === 0) return;

        const remote = selectedWithRemote.length;
        const detail =
            remote > 0
                ? `Se borrarán ${count} archivo(s) de este teléfono, y los movimientos de ${remote} de ellos desaparecerán también de tu dashboard.\n\n` +
                  "El archivo del teléfono no se puede recuperar: si lo quieres de vuelta, tendrás que subirlo otra vez."
                : `Se borrarán ${count} archivo(s) de este teléfono.\n\n` +
                  "Ninguno llegó a procesarse, así que tu dashboard no cambia. El archivo no se puede recuperar.";

        Alert.alert(`Eliminar ${count} archivo(s)`, detail, [
            { text: "Cancelar", style: "cancel" },
            { text: "Eliminar", style: "destructive", onPress: deleteSelected },
        ]);
    }

    /**
     * Deletes server-side data first, then the local copy. That order matters:
     * if the network call fails we still hold the file, so the user can retry.
     * Doing it the other way round could leave transactions on the server with
     * nothing on the phone to point at them.
     */
    async function deleteSelected() {
        const targets = selectedItems;
        setSelected(null);
        setStatus(null);

        let filesDeleted = 0;
        let transactionsDeleted = 0;
        const failures: string[] = [];

        for (const item of targets) {
            setPhase(`Eliminando ${filesDeleted + failures.length + 1} de ${targets.length}…`);
            try {
                if (item.remoteId) {
                    const res = await api.deleteStatement(item.remoteId);
                    transactionsDeleted += res.transactions_deleted;
                }
                await forgetStatement(item.id);
                filesDeleted++;
            } catch (e) {
                failures.push(`${item.name}: ${(e as Error).message}`);
            }
        }

        await refresh();
        setPhase(null);

        // The result card can point at a statement that no longer exists.
        if (result && targets.some((item) => item.name === result.filename)) setResult(null);

        const parts = [`Eliminados ${filesDeleted} archivo(s) de tu teléfono`];
        if (transactionsDeleted > 0) parts.push(`${transactionsDeleted} movimientos del servidor`);
        const summary = `${parts.join(" y ")}.`;
        setStatus(
            failures.length > 0
                ? `${summary} No se pudo con ${failures.length}: ${failures.join(" · ")}`
                : summary
        );
    }

    async function deleteRemote(item: StoredStatement) {
        if (!item.remoteId) return;
        setPhase("Eliminando del servidor…");
        try {
            const res = await api.deleteStatement(item.remoteId);
            await markUnprocessed(item.id);
            await refresh();
            setPhase(null);
            setStatus(`Eliminados ${res.transactions_deleted} movimientos del servidor.`);
        } catch (e) {
            setPhase(null);
            setStatus(`No se pudo eliminar: ${(e as Error).message}`);
        }
    }

    return (
        <ScrollView style={styles.screen} contentContainerStyle={{ padding: 16 }}>
            <Text style={styles.subtle}>
                Tu archivo se queda en el teléfono. Aquí mismo se lee y solo el texto extraído
                viaja, cifrado de punta a punta con la llave del servidor. El PDF nunca sale.
            </Text>

            <Modal
                visible={passwordFor !== null}
                transparent
                animationType="fade"
                onRequestClose={cancelPassword}
            >
                <View style={styles.modalBackdrop}>
                    <View style={styles.modalCard}>
                        <Text style={styles.modalTitle}>Este PDF pide contraseña</Text>
                        <Text style={styles.subtle}>
                            {passwordFor?.stored.name}
                        </Text>
                        <Text style={styles.modalNote}>
                            Se usa aquí para abrir el archivo y no se guarda ni viaja a ningún
                            lado.
                        </Text>

                        <TextInput
                            style={[styles.input, passwordFor?.wrong ? styles.inputError : null]}
                            value={password}
                            onChangeText={setPassword}
                            placeholder="Contraseña del PDF"
                            secureTextEntry
                            autoFocus
                            autoCapitalize="none"
                            autoCorrect={false}
                            onSubmitEditing={submitPassword}
                            returnKeyType="go"
                        />
                        {passwordFor?.wrong && (
                            <Text style={styles.inputErrorText}>
                                Esa contraseña no abrió el PDF.
                            </Text>
                        )}

                        <TouchableOpacity
                            style={[
                                styles.primaryBtn,
                                password.length === 0 ? styles.primaryBtnDisabled : null,
                            ]}
                            onPress={submitPassword}
                            disabled={password.length === 0}
                        >
                            <Text style={styles.primaryBtnText}>Abrir</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.secondaryBtn} onPress={cancelPassword}>
                            <Text style={styles.secondaryBtnText}>Cancelar</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            </Modal>

            <TouchableOpacity
                style={[styles.primaryBtn, phase ? styles.primaryBtnDisabled : null]}
                onPress={pickAndProcess}
                disabled={phase !== null}
            >
                <Text style={styles.primaryBtnText}>Seleccionar PDF o XML (SAT)</Text>
            </TouchableOpacity>

            {phase && (
                <View style={styles.phaseRow}>
                    <ActivityIndicator size="small" color="#2563eb" />
                    <Text style={styles.phaseText}>{phase}</Text>
                </View>
            )}

            {status && <Text style={styles.status}>{status}</Text>}

            {result && (
                <View style={styles.resultCard}>
                    <Text style={styles.resultTitle}>Listo</Text>
                    <Text style={styles.resultBig}>{result.transactionsCreated} movimientos</Text>
                    <Text style={styles.subtle}>
                        {result.filename} · formato {result.template}
                    </Text>
                    <Text style={styles.custodyNote}>
                        El archivo original sigue solo en este teléfono.
                    </Text>

                    <TouchableOpacity
                        style={styles.primaryBtn}
                        onPress={() => openDashboard(result.dashboardUrl)}
                    >
                        <Text style={styles.primaryBtnText}>Ver en tu dashboard</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.secondaryBtn} onPress={() => shareDashboard(result)}>
                        <Text style={styles.secondaryBtnText}>Compartir link</Text>
                    </TouchableOpacity>
                </View>
            )}

            <View style={styles.sectionHeader}>
                <Text style={styles.sectionTitle}>Archivos guardados</Text>
                {items.length > 0 &&
                    (selected ? (
                        <View style={styles.headerActions}>
                            <TouchableOpacity onPress={selectAll}>
                                <Text style={styles.headerAction}>Todos</Text>
                            </TouchableOpacity>
                            <TouchableOpacity onPress={() => setSelected(null)}>
                                <Text style={styles.headerAction}>Cancelar</Text>
                            </TouchableOpacity>
                        </View>
                    ) : (
                        <TouchableOpacity
                            onPress={() => setSelected(new Set())}
                            disabled={phase !== null}
                        >
                            <Text
                                style={[
                                    styles.headerAction,
                                    phase ? styles.headerActionDisabled : null,
                                ]}
                            >
                                Seleccionar
                            </Text>
                        </TouchableOpacity>
                    ))}
            </View>

            {items.map((s) => {
                const isSelected = selected?.has(s.id) ?? false;
                const row = (
                    <View style={[styles.fileRow, isSelected ? styles.fileRowSelected : null]}>
                        {selected && (
                            <View style={[styles.checkbox, isSelected ? styles.checkboxOn : null]}>
                                {isSelected && <Text style={styles.checkboxTick}>✓</Text>}
                            </View>
                        )}
                        <View style={{ flex: 1 }}>
                            <Text style={styles.fileName}>{s.name}</Text>
                            <Text style={styles.subtle}>
                                {new Date(s.storedAt).toLocaleString()}
                            </Text>
                        </View>
                        <Text style={s.processed ? styles.done : styles.pending}>
                            {s.processed ? "Procesado" : "Pendiente"}
                        </Text>
                        {/* The per-row action deletes only the server copy and keeps the
                            file, which is a different promise from the bulk delete; it
                            would be ambiguous to offer both at once. */}
                        {!selected && s.remoteId && (
                            <TouchableOpacity
                                style={styles.deleteBtn}
                                onPress={() => confirmDelete(s)}
                                accessibilityLabel={`Eliminar ${s.name} del servidor`}
                            >
                                <Text style={styles.deleteBtnText}>Eliminar</Text>
                            </TouchableOpacity>
                        )}
                    </View>
                );

                return selected ? (
                    <TouchableOpacity
                        key={s.id}
                        onPress={() => toggleSelection(s.id)}
                        accessibilityRole="checkbox"
                        accessibilityState={{ checked: isSelected }}
                        accessibilityLabel={s.name}
                    >
                        {row}
                    </TouchableOpacity>
                ) : (
                    <View key={s.id}>{row}</View>
                );
            })}
            {items.length === 0 && <Text style={styles.subtle}>Aun no hay archivos.</Text>}

            {selected && (
                <TouchableOpacity
                    style={[
                        styles.destructiveBtn,
                        selectedItems.length === 0 ? styles.primaryBtnDisabled : null,
                    ]}
                    onPress={confirmDeleteSelected}
                    disabled={selectedItems.length === 0 || phase !== null}
                >
                    <Text style={styles.destructiveBtnText}>
                        {selectedItems.length === 0
                            ? "Selecciona archivos para eliminar"
                            : `Eliminar ${selectedItems.length} archivo(s)`}
                    </Text>
                </TouchableOpacity>
            )}
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    screen: { flex: 1, backgroundColor: "#f8fafc" },
    subtle: { color: "#64748b", fontSize: 13 },
    primaryBtn: {
        backgroundColor: "#2563eb",
        borderRadius: 12,
        padding: 14,
        alignItems: "center",
        marginTop: 16,
    },
    primaryBtnDisabled: { opacity: 0.5 },
    primaryBtnText: { color: "#fff", fontWeight: "600" },
    secondaryBtn: {
        borderRadius: 12,
        padding: 12,
        alignItems: "center",
        marginTop: 8,
        borderWidth: 1,
        borderColor: "#cbd5e1",
    },
    secondaryBtnText: { color: "#334155", fontWeight: "600" },
    phaseRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 12 },
    phaseText: { color: "#0f172a" },
    status: { marginTop: 12, color: "#0f172a" },
    resultCard: {
        backgroundColor: "#fff",
        borderRadius: 16,
        padding: 16,
        marginTop: 16,
        borderWidth: 1,
        borderColor: "#bbf7d0",
    },
    resultTitle: { color: "#059669", fontWeight: "700", fontSize: 13 },
    resultBig: { fontSize: 24, fontWeight: "700", marginTop: 2 },
    custodyNote: { color: "#059669", fontSize: 12, marginTop: 8 },
    sectionTitle: { fontWeight: "700", fontSize: 16 },
    sectionHeader: {
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "space-between",
        marginTop: 24,
        marginBottom: 8,
    },
    headerActions: { flexDirection: "row", gap: 16 },
    headerAction: { color: "#2563eb", fontWeight: "600", fontSize: 14 },
    headerActionDisabled: { opacity: 0.4 },
    checkbox: {
        width: 22,
        height: 22,
        borderRadius: 6,
        borderWidth: 1,
        borderColor: "#cbd5e1",
        marginRight: 12,
        alignItems: "center",
        justifyContent: "center",
    },
    checkboxOn: { backgroundColor: "#2563eb", borderColor: "#2563eb" },
    checkboxTick: { color: "#fff", fontSize: 13, fontWeight: "700" },
    fileRowSelected: { borderColor: "#2563eb", backgroundColor: "#eff6ff" },
    destructiveBtn: {
        backgroundColor: "#dc2626",
        borderRadius: 12,
        padding: 14,
        alignItems: "center",
        marginTop: 8,
    },
    destructiveBtnText: { color: "#fff", fontWeight: "600" },
    modalBackdrop: {
        flex: 1,
        backgroundColor: "rgba(15, 23, 42, 0.45)",
        justifyContent: "center",
        padding: 24,
    },
    modalCard: { backgroundColor: "#fff", borderRadius: 16, padding: 20 },
    modalTitle: { fontWeight: "700", fontSize: 17, marginBottom: 4 },
    modalNote: { color: "#059669", fontSize: 12, marginTop: 10 },
    input: {
        borderWidth: 1,
        borderColor: "#cbd5e1",
        borderRadius: 10,
        padding: 12,
        marginTop: 12,
        fontSize: 16,
    },
    inputError: { borderColor: "#dc2626" },
    inputErrorText: { color: "#dc2626", fontSize: 12, marginTop: 6 },
    fileRow: {
        flexDirection: "row",
        alignItems: "center",
        backgroundColor: "#fff",
        borderRadius: 12,
        padding: 12,
        marginBottom: 8,
        borderWidth: 1,
        borderColor: "#e2e8f0",
    },
    fileName: { fontWeight: "600" },
    done: { color: "#059669", fontSize: 12 },
    pending: { color: "#94a3b8", fontSize: 12 },
    deleteBtn: {
        marginLeft: 12,
        paddingVertical: 6,
        paddingHorizontal: 10,
        borderRadius: 8,
        borderWidth: 1,
        borderColor: "#fecaca",
        backgroundColor: "#fef2f2",
    },
    deleteBtnText: { color: "#dc2626", fontSize: 12, fontWeight: "600" },
});
