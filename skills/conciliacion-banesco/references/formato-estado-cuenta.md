# Formato del estado de cuenta Banesco

Referencia para transcribir y leer el PDF "Estado de cuenta" de Banesco Banco Universal (cuenta corriente en bolívares). Esta descripción sale de estados de cuenta reales de 2026. Si un PDF trae otra estructura, no se adapta a la fuerza: se describe la diferencia en `Review_Notes`.

## Estructura de cada mes

1. **Portada del mes** (columna izquierda de la primera página):
   - Titular, dirección, correo y RIF del titular (al pie: `RIF: J-...`).
   - `No. de Cuenta` (20 dígitos; código de banco 0134) y `Período: MM-AAAA`.
   - **RESUMEN DE MOVIMIENTOS**: `Cheques Pagados`, `Otros Débitos`, `Depósitos`, `Otros Créditos`, cada uno con `Cantidad` y `Monto Total`.
   - **RESUMEN DE SALDOS**: `Inicial`, `Final`, `Promedio`.
2. **CHEQUES**: tabla `CHEQUE | DIA | MONTO`, a menudo vacía.
3. **DETALLE DE MOVIMIENTOS**: `DIA | REF. | CONCEPTO | CARGOS | ABONOS | SALDOS`. La primera fila es `SALDO MES ANTERIOR` (solo con saldo). Continúa en páginas con el título "DETALLE DE MOVIMIENTOS (continuación)", a veces en dos columnas por página.
4. Las últimas líneas del mes suelen ser `COM,SERV.MTTO CTA` y `EMISION DE ESTADO DE CUENTA`, con referencia `00000000000`.

Un PDF puede traer varios meses seguidos. Cada mes empieza con su portada.

## Cómo llenar el resumen

| Columna de `plantilla-resumen.csv` | Fuente en el PDF |
|---|---|
| `saldo_inicial` | RESUMEN DE SALDOS → Inicial |
| `saldo_final` | RESUMEN DE SALDOS → Final |
| `cant_debitos`, `total_debitos` | Otros Débitos + Cheques Pagados (cantidad y monto) |
| `cant_creditos`, `total_creditos` | Otros Créditos + Depósitos (cantidad y monto) |

Comprobación del propio resumen: `Inicial + créditos - débitos = Final`. En los estados revisados, la `Cantidad` coincide con el número de líneas de cargo y de abono del detalle.

## Números

- Formato venezolano: punto para los miles y coma para los decimales (`1.602.410,00`).
- El detalle no lleva signo: el monto va en la columna CARGOS (sale) o ABONOS (entra). Solo la columna SALDOS puede ser negativa (`-400,08`).
- En la transcripción se copia el monto tal cual. `banesco_parse.py` lo convierte.

## Trampas de lectura (escaneos y fotos)

- **Páginas fotografiadas o torcidas:** el encabezado "Banesco / Estado de cuenta" puede estar cortado, o faltar la portada del mes en la misma página. El período se toma de la portada anterior.
- **Dígitos que se confunden:** 3/8, 5/6, 1/7 y 0/8 en los decimales. El saldo corrido los detecta: si `saldo anterior + abono - cargo` no da el saldo impreso, alguno de los tres está mal leído.
- **Saldos borrosos al pie de la página:** se calculan desde la línea anterior y se confirman con el primer saldo de la página siguiente. Si no cuadra, renderizar a 400 dpi y releer.
- **Referencia con guion o punto inicial por suciedad del escaneo** (`-00012345678`): se transcribe sin ese carácter.
- **Marcas a mano** (tildes o rayas del cliente sobre las líneas): se ignoran, pero si tapan un dígito, se anota en `Review_Notes`.
- **Dos líneas iguales el mismo día** (p. ej. dos `TRANS,CTAS` del mismo monto con referencias distintas): son legítimas. No se borran como duplicadas.
