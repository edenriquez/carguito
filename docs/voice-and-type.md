# Voz y tipografía de Carguito

Sustituye las decisiones tipográficas de `docs/redesign-plan.md` §6 y §10. 2026-09-05.

Aplica a la landing (`landing/`) y al dashboard (`frontend/`): una voz y un sistema tipográfico, con una excepción desde 2026-10-06: la cara display de la landing es otra (§4, «La display de la landing»). Los tokens viven en `frontend/src/design/tokens.ts` y se copian a la landing con `cd landing && npm run tokens:sync`; nunca se editan en `landing/src/design/tokens.ts`.

## 1. Manifiesto de voz

Carguito es audaz y tiene opinión. La opinión cabe en pocas frases y siempre trae su prueba al lado.

1. **Carguito tiene postura, no enemigos con nombre.** Opina sobre prácticas: el PDF que nadie puede leer, la app que pide la contraseña del banco, el número inventado. Nunca nombra a un banco ni a una app para criticarlos; los bancos aparecen solo en la lista de lo que Carguito sabe leer.
2. **Cada frase con filo trae su prueba al lado.** A un titular audaz lo sigue la mecánica: qué hace el código hoy. Sin cifras inventadas, testimonios, "IA", ni promesas fuera de producción. Las cifras de ejemplo se llaman así.
3. **El filo vive en pocos lugares.** Titulares y entradas de sección de la landing, onboarding, titulares del Plan, títulos de estado vacío. Etiquetas, columnas, números, toasts, errores, ajustes y textos legales son neutros.
4. **Quién habla.** El producto es Carguito, en tercera persona ("Carguito lo lee y lo desecha"). "Nosotros" solo firma compromisos de personas: privacidad, precio, reconocer un error. El usuario es "tú". Los controles hablan en la voz del usuario («Es entre mis cuentas»). El impersonal "se lee / se desecha" solo en chips de estado.
5. **Corto, concreto, en presente.** Verbos de acción (lee, señala, desecha, empareja); sustantivos del banco mexicano (cargo, abono, quincena, nómina, estado de cuenta); sin anglicismos de app (transacción, dashboard, ledger). Una idea por oración.
6. **Honesto hasta cuando duele.** Cuando Carguito no sabe, lo dice ("Carguito no adivina"); cuando algo falla, dice qué y qué hacer; cuando la lectura fue genérica, lo advierte. Un cero nunca es dato si es ausencia.
7. **Español de México.** Tú, celular, súper, ticket, quincena, nómina, banca en línea. Meses en minúscula; "$1,234.56"; "19%" pegado; siglas sin plural (los PDF, los CFDI).

### Las dos posturas

- **Contra el PDF que nadie lee.** Hero: "Tu estado de cuenta no lo lee nadie. Carguito sí." La prueba va inmediatamente debajo (qué saca, qué señala, qué desecha) y en "Cómo funciona".
- **Contra la app que pide la contraseña del banco.** Custodia: "Ninguna app debería pedirte la contraseña de tu banco." La prueba: Carguito no se conecta al banco; en la web el PDF viaja, se lee en memoria y se desecha; desde el celular (en pruebas) viaja solo el texto, cifrado.

Todo lo demás en la landing es prueba (la Lectura contra el país y las otras caras de Movimientos, Plan y Pagos, dibujadas como en el producto y con los títulos-hallazgo del producto; los comercios que nombra; los bancos que lee), objeción respondida (FAQ) o cierre ("Tu estado de cuenta, leído."). Cada gráfica de la landing corresponde a una que existe hoy en el dashboard: si la app quita o renombra una, la landing la quita o la renombra. Del lado del usuario las cifras son de ejemplo y se dicen así; del lado del país son las tablas publicadas del INEGI, copiadas en `landing/src/lib/pais.ts`.

## 2. Gramática y puntuación

- **Punto final.** Sí en H1/H2 que son oraciones y en párrafos. No en títulos de tarjeta, títulos de estado vacío, titulares del Plan, eyebrows, labels, botones, nav, títulos de sheet o diálogo. Las preguntas de la FAQ llevan ¿…?
- **Raya (—).** Un solo trabajo: el separador del `<title>` ("Carguito — …") y el dato ausente en tablas (`NO_DATE` en `frontend/src/lib/format.ts`). En prosa se usan comas, dos puntos o punto.
- **Comillas «».** Para citar lo que aparece en pantalla o en el renglón del banco («POCK*SUPERLECLERC», «Preguntar»).
- **Mayúsculas.** Tipo oración en todo. Los bancos como se escriben ellos (Banamex, Banco Azteca, Nu, BBVA). SAT, CFDI, PDF, XML, OCR en mayúsculas.
- **Cifras.** `mxn()` en titulares y tooltips ("$9,140"); `mxn2()` en renglones cotejables ("$1,412.60"); "~" para estimaciones ("~$70,139"); plural correcto con conteo ("1 cobro", "14 cobros").
- **Highlight.** Uno por titular, sobre la palabra que carga la promesa ("Carguito sí", "desecha", "estado de cuenta").

## 3. Glosario

| Concepto | Usar | Prohibido | Dónde |
|---|---|---|---|
| Renglón del estado | **movimiento** | transacción, operación, registro | tablas, conteos, nav |
| Sale dinero | **cargo** | gasto como renglón ("gasto por categoría" sí como agregado), pago (salvo "pago de tarjeta") | orientación, Plan, Atención |
| Entra dinero | **abono** | depósito, ingreso como renglón ("ingresos" sí como concepto de la cara) | Plan · Lo que entra, `AddIngresoSheet`, `PronosticoView` |
| Documento del banco | **estado de cuenta** completo | extracto, "estado", resumen | hero, onboarding, dropzone, FAQ, /privacidad |
| Estado o CFDI (paraguas) | **documento** | archivo en este sentido | nav, "Subir documento", Documentos |
| El archivo como archivo | **archivo** | documento en este sentido | "Elegir archivo", "el archivo se desecha", "contraseña del archivo" |
| Panel de Documentos | **"Todo lo leído"** | "Archivo" | `DocumentosView.tsx` |
| Cobro detectado que se repite | **cobro recurrente** / **cobro que se repite** | serie (en UI), sugerido como sustantivo, suscripción salvo que lo sea | Plan · Lo que se va, bento |
| Confirmado por el usuario | **fijo** / verbo **fijar** | fijo para no confirmados | "Fijar", "Quitar de fijos", "1 fijo" |
| Detectado sin confirmar | **por confirmar** | sugeridos, resto | título de sección de Fijos |
| Estimación de no confirmados | **sin confirmar ~$X** | resto recurrente | letra pequeña del titular de Fijos |
| Lo que Carguito produce | **lectura** (f.) → "ninguna" | vista, análisis, lens, workstation | bento, workspace, LecturasMenu, WorkspaceSidebar |
| Nivel de parser | **lector dedicado / lector genérico** | lectura dedicada/genérica, plantilla | `BanksB.tsx`, `ReviewStatement`, FAQ |
| Recibo del súper | **ticket** | recibo, tique, comprobante | Precios, Documentos, bento |
| Ingreso con ritmo / sin | **nómina** / **extra** | sueldo, salario, freelance | Plan · Lo que entra |
| Transferencia propia | control «Es entre mis cuentas»; estado "transferencia entre tus cuentas" | autotransferencia, traspaso | `TransactionEditor.tsx`, `DocumentosView.tsx` |
| Custodia web | "el PDF viaja, se lee en memoria y se desecha"; chip "Leído en el servidor y desechado" | encriptado, "seguro", "privado por diseño", cifrado de extremo a extremo | CustodyB, FAQ, /privacidad, chips |
| Custodia celular | "no sale de tu celular; viaja solo el texto, cifrado" | teléfono, dispositivo, móvil | igual + bento Precios |
| El aparato | **celular** | teléfono, móvil, smartphone | ambas apps |
| Guardar / eliminar | **guardar** datos; **eliminar** documentos; **desechar** solo el archivo | almacenar, borrar | /privacidad, dropzone, Documentos |
| Contraseñas | **contraseña del archivo/PDF** vs **contraseña de tu banco / banca en línea** | clave, password, credenciales | hero, diálogo, FAQ, onboarding |

## 4. Tipografía

### Pareja

- **Instrument Serif** (Google Fonts, `next/font/google`, `Instrument_Serif({ weight: "400", subsets: ["latin"], variable: "--font-display" })`). Un solo woff2 de ~15 KB servido por Next. Es la **cara de la opinión**: palabras a **24 px o más**. Su GSUB trae `ccmp`, `liga`, `locl`; **no trae `tnum`** y sus dígitos son proporcionales (nueve anchos distintos), así que nunca lleva números.
- **Inter** (variable, `--font-inter`). Texto, labels, celdas, títulos de contenedor y **todos los números**. Su GSUB trae `tnum`, `pnum`, `calt`, `frac`; el `body` activa `"tnum" 1, "lnum" 1` y desactiva `calt`/`liga` para que las cifras sean literales.
- Cadena de `display`: `var(--font-display), Georgia, "Times New Roman", serif`. Inter no está en la cadena a propósito: una serif que cayera a grotesca escondería una carga fallida.
- `lang="es-MX"` en ambas apps.

### La display de la landing

Desde 2026-10-06 la landing no usa Instrument Serif: su display es **Bricolage Grotesque** (`Bricolage_Grotesque({ subsets: ["latin"], axes: ["opsz"], variable: "--font-display" })` en `landing/src/app/layout.tsx`). El dashboard no cambia.

- **Por qué.** La landing vende y el dashboard se lee. Con el cambio a Carguito, y su marca de banquito sonriente, la serif condensada sonaba a periódico; una grotesca con carácter (tinta en las uniones, `g` y `ñ` de dibujo propio) grita sin gritar y sigue siendo de México y de dinero, no de app genérica. Es variable con eje de tamaño óptico (`opsz` 12–96): el hero a 72 px toma el corte apretado de display y las preguntas de la FAQ a 24 px el corte robusto de texto, sin tocar nada.
- **Español.** El subset `latin` trae á é í ó ú ü ñ ¿ ¡ « » completos.
- **Peso 500, tracking −0.022em.** Una grotesca a 400 sobre Night se ve tímida y a 0 de tracking se abre. Sigue habiendo solo dos pesos: la display de la landing usa 500 (`font-medium`), como los eyebrows y los títulos de tarjeta. Se aplica en `landing/src/app/globals.css` (`html :is(h1, h2, .font-display)`), no en los tokens, que siguen copiándose tal cual.
- **Cadena.** `landing/tailwind.config.ts` sobreescribe `fontFamily.display` a `var(--font-display), ui-sans-serif, system-ui, sans-serif`: una grotesca que cae a Georgia sería la carga fallida que sí se nota.
- **Números.** Siguen en Inter tabular. Bricolage no lleva cifras en la landing; las gráficas de ejemplo usan Inter y el ticket una monoespaciada.
- **La regla de 24 px se queda.** No por legibilidad (Bricolage aguanta 20 px) sino por sistema: bajo 24 px manda Inter en ambas apps, y así un título de tarjeta se ve igual en la landing que en el producto.
- La OG image pide a la API CSS de Google Fonts `Bricolage+Grotesque:opsz,wght@96,500`: Satori no lee fuentes variables, así que recibe la instancia estática.

### Pesos

Solo dos, definidos en `fontWeight` de los tokens y montados a nivel `theme` (no `extend`) en ambos `tailwind.config.ts`, así que `font-semibold` y `font-bold` no existen:

| Token | Valor | Uso |
|---|---|---|
| `font-normal` | 400 | todo, incluida la display del dashboard y las métricas |
| `font-medium` | 500 | wordmark, eyebrows, títulos de tarjeta de la landing (`h3`/`h4`), la display de la landing (`h1`/`h2`, FAQ), botones, énfasis puntual en cuerpo |

La opinión sale de las palabras, del contraste y del tamaño, nunca del peso. El 500 de la display de la landing no es énfasis: es el peso al que esa grotesca se ve como la serif a 400.

### La regla de 24 px

Instrument Serif es condensada y de alto contraste: bajo 24 px lee como una sans de 17 px y sus trazos finos se pierden sobre Night. Probado en la hoja de prueba (72/52/32/24 sobre `#141211`; 52/32/24 sobre `#fafaf9`): 24 es el piso, 20 ya se debilita. Por eso:

- El hero móvil arranca en `display` (52), nunca en `title-lg`.
- Los títulos de `EmptyState`, del dropzone y de los pasos del onboarding van en `title-md` (24).
- `title-sm` (20) **es Inter**: títulos de tarjeta (landing `h3`), títulos de contenedor (dashboard `h2` de tarjeta), títulos de sheet y diálogo.
- En el dashboard un heading no lleva `font-display` por defecto; los que cargan voz lo dicen en su clase. En la landing `h1`/`h2` son display y `h3`/`h4` son Inter 500.

### Escala

| Token | Tamaño / interlínea / tracking | Familia | Uso |
|---|---|---|---|
| `display-lg` | 72 / 1.04 / 0 | serif | H1 del hero en desktop |
| `display` | 52 / 1.08 / 0 | serif | H1 del hero en móvil, H1 de /privacidad y onboarding en desktop |
| `title-lg` | 32 / 1.15 / 0 | serif | H2 de sección en desktop, H1 de onboarding en móvil |
| `title-md` | 24 / 1.2 / 0 | serif | H2 de sección en móvil, preguntas de la FAQ, titulares del Plan, estados vacíos, dropzone |
| `title-sm` | 20 / 1.2 / -0.012em | Inter | títulos de tarjeta y contenedor, sheets, diálogos |
| `body-lg` | 16 / 1.69 | Inter | sub del hero, intros |
| `body` | 14 / 1.64 | Inter | el ritmo dominante; no romperlo |
| `body-sm` | 13 / 1.53 | Inter | cuerpos de tarjeta, notas |
| `label` | 12 / 1.33 | Inter | labels de formulario, ejes de gráfica |
| `caption` | 10 / 1.6 / 0.08em | Inter 500, mayúsculas | eyebrows; la clase `.eyebrow` existe en ambas apps y ya no añade tracking a mano |
| `metric-xl` | 96 / 1 / -0.035em | Inter tabular | la cifra del hero en desktop |
| `metric-lg` | 56 / 1 / -0.03em | Inter tabular | la cifra del hero en móvil |
| `metric` | 32 / 1.15 / -0.025em | Inter tabular | la cifra de una tarjeta |
| `metric-sm` | 20 / 1.2 / -0.015em | Inter tabular | cifras secundarias, celdas destacadas |

Los tokens `metric-*` son de números y los `display`/`title-*` de palabras; ninguno toma el lugar del otro. Las gráficas (ApexCharts) leen `fontSize.label`, `fontSize["body-sm"]` y `fontWeight.normal` de los mismos tokens.

### Verificación

- `npx tsc --noEmit` en `frontend/` y `landing/`; `npm run lint` solo en `landing/`. Nunca `next build` con los dev servers vivos.
- `grep -rn "font-display" frontend/src landing/src | grep -E "font-medium|metric|title-sm|body"` debe devolver nada fuera de `components/dev/`.
- `curl -s localhost:3001 | grep -o '/_next/static/media/[^"]*woff2'` debe listar dos archivos: Inter y Bricolage Grotesque (variable, `latin`). En `localhost:3000` siguen siendo Inter e Instrument Serif (~15 KB).
- La OG image (`landing/src/app/opengraph-image.tsx`) carga Bricolage Grotesque 500 desde la API CSS de Google Fonts en build; si la red falla, cae al sans del sistema sin romper el build.
