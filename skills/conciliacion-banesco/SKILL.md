---
name: conciliacion-banesco
description: Conciliación bancaria de cuentas Banesco (Venezuela, bolívares) a partir del PDF "Estado de cuenta" de Banesco, incluso escaneado, contra el libro de banco o mayor de la cuenta. Usar cuando el usuario entrega estados de cuenta Banesco (uno o varios meses) y pide conciliar, validar el estado de cuenta, separar comisiones de Pago Móvil y transferencias, identificar partidas en tránsito o notas de débito/crédito no registradas, o preparar los asientos de gastos bancarios. Reconciles Banesco bank statements (Pago Móvil, TRF CR INM, SENIAT planillas) to the GL. Produce un libro de trabajo con validación línea por línea, clasificación, conciliación por cierre de mes, asientos propuestos y tabla de evidencia.
---

# Conciliación bancaria Banesco

Especialización de `bank-rec` para el formato de estado de cuenta de Banesco Banco Universal. Reutiliza su emparejador (`bank-rec/scripts/match_transactions.py`) y su antigüedad de partidas (`age_items.py`), y sigue `workpaper-standards` y `firm-config`. Instalar las cuatro skills juntas.

Moneda: bolívares (Bs., VES), expresión monetaria vigente desde 2021. El encabezado del libro de trabajo lo declara; no se convierte a USD salvo que el usuario dé la tasa y la fuente.

## Insumos

| Insumo | Obligatorio | Nota |
|---|---|---|
| Estado(s) de cuenta Banesco (PDF) | Sí | Uno o varios meses en un solo PDF. Suelen venir escaneados. |
| Libro de banco / mayor de la cuenta | Para conciliar | CSV/XLSX: fecha, descripción, referencia, monto con signo o debe/haber. |
| Saldo del libro al día anterior al primer mes | Para conciliar | Sin él no hay "saldo según libros". |
| Cuenta contable del banco y de gastos bancarios | Para asientos | De `firm-config/references/chart-of-accounts.csv`. |
| Partidas pendientes de la conciliación anterior | Si existen | Se incluyen en el libro con su fecha original. |
| Cómo registra el cliente el Pago Móvil | Sí | `bruto` (cobro y comisión por separado) o `neto`. Preguntar si no se sabe. |

Sin libro, la skill **valida y clasifica** el estado de cuenta y lo dice en la portada: "SIN LIBRO: conciliación incompleta". No se presenta como conciliado.

## Flujo

### 1. Pasar el PDF a la plantilla de transcripción

Probar primero con `python scripts/banesco_parse.py estado.pdf --out movimientos.csv`. Si el PDF tiene capa de texto, extrae las líneas y decide cargo o abono según cómo varía el saldo. Si responde "el PDF no tiene capa de texto", hay que transcribirlo:

- Leer las páginas con la herramienta de lectura de PDF, en bloques de pocas páginas. Para zonas borrosas, renderizar a 300-400 dpi (`pdftoppm -r 400`) y recortar la columna de interés.
- Llenar `references/plantilla-transcripcion.csv`: una fila por línea de DETALLE DE MOVIMIENTOS, en el orden en que aparecen, más la fila `SALDO MES ANTERIOR` al comienzo de cada mes. La referencia se copia como texto, con sus ceros a la izquierda.
- Llenar `references/plantilla-resumen.csv` con el bloque RESUMEN DE MOVIMIENTOS / RESUMEN DE SALDOS de cada mes.
- El formato, las páginas sin encabezado y las trampas de lectura están en `references/formato-estado-cuenta.md`.

### 2. Validar la transcripción (obligatorio)

```
python scripts/banesco_validate.py movimientos.csv --resumen resumen.csv
```

Verifica el saldo corrido línea por línea, los totales de débitos y créditos contra el resumen, los saldos inicial y final, la cantidad de líneas, la continuidad entre meses (el final de un mes es el inicial del siguiente) y los saldos negativos.

- `SALDO_CORRIDO` señala la primera línea donde el saldo deja de cuadrar. Releer esa línea y la anterior a mayor resolución, corregir y volver a validar.
- Un error de montos siempre se corrige releyendo el PDF. **Nunca se ajusta un monto para que cuadre.** Si una línea no se puede leer, se deja la diferencia y se reporta en `Review_Notes`.
- `SALDO_NEGATIVO` y `CANTIDAD` son observaciones, no errores, y van a preguntas para el cliente.

No se concilia hasta que no queden hallazgos `MANUAL_REVIEW_REQUIRED`. `conciliar_banesco.py` lo exige: si hay errores, escribe solo la pestaña `Validacion` y termina con código 1.

### 3. Conciliar

```
python scripts/conciliar_banesco.py --movimientos movimientos.csv --resumen resumen.csv \
    --libro libro.csv --saldo-inicial-libro "1.000,00" \
    --cuenta-banco 1010 --cuenta-gasto 6900 --comisiones bruto --out conciliacion.xlsx
```

El script:

1. **Clasifica** cada línea según `references/conceptos-banesco.md`: Pago Móvil, TRF CR INM, TRANS,CTAS, planillas SENIAT, Multipagos y comisiones.
2. **Empareja las comisiones por referencia.** Banesco cobra la comisión en otra línea con la misma referencia. A veces esa línea dice "Com, Banesco Pago Movil" (confianza `HIGH`) y a veces repite "Banesco Pago Movil": ahí se infiere por el monto (confianza `MEDIUM`). Calcula la tasa observada y marca las que se apartan de la mediana. **No asume tarifas:** el preparador las compara con el tarifario vigente del banco.
3. **Empareja banco contra libro** con `bank-rec` sobre todos los meses a la vez. Así, un depósito que el libro registró el 31 y el banco acreditó el 2 queda como partida en tránsito de ese cierre.
4. **Calcula cada cierre de mes:**

   ```
   Saldo según estado de cuenta
   + depósitos en tránsito               (libro sí, banco no)
   - cheques / pagos en tránsito         (libro sí, banco no)
   = saldo bancario conciliado
   Saldo según libro
   + notas de crédito no registradas     (banco sí, libro no)
   - notas de débito no registradas      (banco sí, libro no)
   = saldo libro ajustado
   Diferencia (debe ser 0 dentro de materiality.bank_rec_difference_tolerance)
   ```

   Si la diferencia no es cero, se informa su monto. **Nunca se fuerza el cuadre.**

5. **Propone asientos** (`JEs_Proposed`): un asiento por mes con las comisiones no registradas (débito a gasto bancario, crédito al banco). Estos asientos pasan por `je-review` antes de contabilizarse.

### 4. Revisar lo que el script no decide

- **Planillas SENIAT** (`INCLUSION DE PLANILLA SENIAT C`): el estado de cuenta no dice qué impuesto se pagó. Se emparejan con el libro por monto y fecha. Si no están en el libro, se pide la planilla y **no se propone una cuenta de impuesto**.
- **Notas de crédito no registradas** (cobros por Pago Móvil o TRF CR INM que no están en el libro): el concepto de TRF CR INM trae el código de banco y el RIF/CI del ordenante. Con eso se arma la pregunta al cliente. No se asignan a un cliente por suposición.
- **TRANS,CTAS**: confirmar si es un traspaso entre cuentas propias (debe aparecer en la otra cuenta con signo contrario) o un pago a un tercero.
- **Conceptos no catalogados** (p. ej. `PPV ...`): `MANUAL_REVIEW_REQUIRED`. No se clasifican sin soporte.
- **Saldos negativos** dentro del mes: preguntar al cliente si hubo sobregiro o si se debe al orden en que el banco registró las operaciones.

## Libro de trabajo

Pestañas: `Cover`, `Summary` (con fórmulas y una columna por mes), `Source_Bank`, `Validacion`, `Clasificacion`, `Comisiones`, `Resumen_Mensual`, `Source_GL`, `Matched`, `Probable_Matches`, `Unmatched_Bank`, `Unmatched_Book`, `Reconciling_Items` (por cierre, con antigüedad), `JEs_Proposed`, `Evidence`, `Review_Notes`.

`Resumen_Mensual` da, por mes, la cantidad y el monto de cada tipo de operación: total cobrado por Pago Móvil, comisiones, pagos al SENIAT, etc. Sirve para la nota a los estados financieros y para conversar con el cliente.

## Invariantes

- **Sin transcripción íntegra no hay conciliación.** El saldo corrido tiene que cuadrar en cada línea.
- **Las coincidencias probables y las comisiones inferidas (`MEDIUM`) no se confirman solas.** Van a revisión.
- **Una cuenta por libro de trabajo.** Si el cliente tiene varias cuentas Banesco, se corre una vez por cuenta.
- **No se inventan tarifas, impuestos ni contrapartes.** Lo que el estado de cuenta no dice se pregunta.
- Los flags siguen `workpaper-standards/references/review-flags.md`, sin crear flags nuevos.

## Cuándo decir "no sé"

- El número de cuenta del PDF no coincide con la cuenta del libro → detenerse y preguntar.
- Falta un mes intermedio (`CONTINUIDAD`) → pedir ese estado de cuenta. No se conciliarán los meses siguientes como si estuvieran completos.
- Una línea ilegible impide cuadrar el saldo corrido → informar la página, la línea y la diferencia, y pedir una copia más legible o el estado de cuenta digital.
- Más del 30 % de las partidas sin clasificar → probablemente el libro no es de esta cuenta o de este período. Informarlo en `Review_Notes`.
