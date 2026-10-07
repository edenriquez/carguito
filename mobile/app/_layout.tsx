import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

export default function RootLayout() {
    return (
        <SafeAreaProvider>
            <StatusBar style="light" />
            <Stack
                screenOptions={{
                    headerStyle: { backgroundColor: "#2563eb" },
                    headerTintColor: "#fff",
                    headerTitleStyle: { fontWeight: "700" },
                }}
            >
                <Stack.Screen name="index" options={{ title: "Carguito" }} />
                <Stack.Screen name="upload" options={{ title: "Subir Estado de Cuenta" }} />
                <Stack.Screen name="receipt" options={{ title: "Foto de un Ticket" }} />
                <Stack.Screen name="transactions" options={{ title: "Transacciones" }} />
            </Stack>
        </SafeAreaProvider>
    );
}
