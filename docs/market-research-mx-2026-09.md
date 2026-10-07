# Investigación de mercado: finanzas personales en México

Consolidado de la conversación del 2026-09-08. Las cifras son de memoria (corte mediados de 2026) y hay que verificarlas antes de citarlas fuera del equipo.

## Hallazgo central

La educación financiera con datos propios funcionó como producto solo cuando estuvo atada a **una lección concreta o a un método**, no a "insights" generales. Todo producto gratuito de tablero terminó vendiendo crédito. En México, además, ningún B2C de finanzas personales encontró modelo porque dependía de conectores bancarios que nunca fueron estables.

## Antecedentes

| App | País | Qué hizo | Cómo le fue | Lección para Carguito |
|---|---|---|---|---|
| YNAB | EE. UU. | Método de cuatro reglas; la app existe para enseñarlo. Suscripción de pago desde el día uno. | Rentable y con comunidad fiel por más de una década, sin capital de riesgo. | La educación como método cobra. La gente paga por cambiar hábitos, no por ver gráficas. |
| Truebill / Rocket Money | EE. UU. | Una sola lección como cuña: cobros recurrentes que no recuerdas, cancelación en un toque. | Comprada por Rocket en 2021 por ~1,275 MUSD. | La lectura de recurrentes de Carguito es exactamente esa cuña. |
| Cleo | Reino Unido | Chat con personalidad sobre tus movimientos; el "modo regaño" es la función más querida. | Cientos de millones de ingresos anuales, usuarios jóvenes. | El tono es producto. El manifiesto de voz ya lo sabe. |
| Mint | EE. UU. | Agregación gratuita, categorías, consejos genéricos. Monetizó con ofertas de crédito. | Comprada por Intuit en 2009, cerrada en 2024. | El tablero gratuito no cambia hábitos y termina vendiendo crédito. |
| GuiaBolso | Brasil | Finanzas personales gratis con lectura del banco; millones de usuarios. | Pivotó a marketplace de préstamos; comprada por PicPay en 2021. | En Latinoamérica el negocio se fue al crédito y la educación se diluyó. |
| Fintonic, Finerio, Coru | España y México | Finanzas personales con alertas y clasificación vía scraping bancario. | Fintonic a préstamos; Finerio a B2B (open banking); Coru a marketplace de crédito. | El B2C de finanzas personales en México no encontró modelo. Advertencia principal. |
| Fetch, Ibotta | EE. UU. | Foto del ticket a cambio de recompensas; venden datos agregados a marcas. | Fetch supera decenas de millones de usuarios activos. | La gente fotografía tickets solo con premio inmediato. La comparación de precios sola (Basket) no retuvo. |

## Patrones de los que funcionaron

- **Una lección, no un tablero.** Truebill y YNAB ganaron con una idea que cabe en una frase.
- **Cobrar desde el inicio o resignarse al crédito.** Todos los gratuitos terminaron vendiendo préstamos, lo contrario de educar.
- **Personalidad con prueba.** Cleo regaña con tus números; la voz de Carguito ("opinión con su prueba al lado") es el mismo principio con más respeto.
- **El ticket necesita un premio en la misma foto.** "Esto te costó $38 más que en Chedraui."

## Por qué México es distinto

Fintonic, Finerio y Coru dependían de scraping con credenciales del usuario. En México eso nunca fue estable: los bancos cambian el portal, meten segundo factor y bloquean; las reglas secundarias de open finance de la Ley Fintech para datos transaccionales no aterrizaron. Cada caída del conector era un usuario perdido, y la app pedía la contraseña del banco, que es la desconfianza que la landing de Carguito nombra. El negocio se fue al crédito porque el producto base no se sostenía.

El estado de cuenta en PDF es la única entrada estable en México:

- **Todos los bancos lo emiten por obligación regulatoria.** Llega por correo cada mes y su formato cambia una vez al año, no cada semana. Un lector por banco es mantenimiento razonable; un scraper no.
- **Tiene ritmo mensual.** Es el ritmo del ciclo de aprendizaje: lección hoy, calificación con el estado del mes siguiente. Los hábitos no cambian en tiempo real.
- **No pide confianza que el usuario no quiere dar.** El PDF ya está en su correo. Reenviarlo (por ejemplo por WhatsApp) es un gesto que cualquiera entiende.

Segundo hueco que los productos extranjeros no ven: en México una parte grande del gasto es **efectivo**. El estado de cuenta solo registra el retiro en cajero. El ticket del súper es la única huella de ese efectivo; responde "en qué se fue lo que retiré", pregunta que ningún conector bancario contesta aunque existiera.

## Hueco que nadie cubre

Cerrar el círculo con el siguiente estado de cuenta: "hace un mes te mostramos $1,400 en gasto hormiga; este mes fueron $600". Ninguna de estas apps dice un mes después si la lección funcionó. En México y por WhatsApp, no existe.

## Implicaciones para Carguito

- Carguito como **curso que tu propio estado de cuenta te da**: lecciones con disparador computable (formato de `advisor-principles.md`).
- Tres cuñas candidatas: cobros que no recuerdas, tarjeta pagada al mínimo, lo que pagas de más en el súper.
- Canal de entrada más fácil que una web: reenviar el PDF por WhatsApp.
- **Decisión pendiente: cobrar por educar.** Los mexicanos que fracasaron no educaron mal; el gratis los obligó a vender crédito. Si Carguito educa, cobra por educar aunque sea poco, o encuentra quién pague sin ser un banco que presta.

## Pendientes de verificación

- Cifras de Rocket Money, Cleo, Fetch y fechas de GuiaBolso, Mint.
- Estado actual de Finerio, Coru y Fintonic en México.
- Estado real de las reglas secundarias de open finance (Ley Fintech) a 2026.
- Datos duros del mercado objetivo (ENIF/CNBV sobre uso de efectivo, tarjeta de crédito y pago mínimo) que no salieron en la conversación.
