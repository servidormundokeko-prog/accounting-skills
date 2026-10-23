# Conceptos del estado de cuenta Banesco

Catálogo que usa `scripts/banesco_classify.py`. Cada concepto tiene su categoría, lo que se puede afirmar sobre él solo con el estado de cuenta y lo que hace falta preguntar. Si aparece un concepto que no está aquí, cae en `otro` (`MANUAL_REVIEW_REQUIRED`). Se agrega a este catálogo solo después de confirmar con el cliente o con el banco qué significa.

| Concepto en el PDF | Categoría | Sentido | Qué se sabe | Qué falta |
|---|---|---|---|---|
| `Banesco Pago Movil` | `pago_movil` | abono o cargo | Abono: cobro recibido por Pago Móvil. Cargo: pago enviado. | Contraparte (cliente o proveedor): no aparece en el concepto. |
| `Com, Banesco Pago Movil` | `comision_pago_movil` | cargo | Comisión de la operación con la misma referencia. | — |
| `Banesco Pago Movil` (cargo pequeño, misma referencia que otra operación) | `comision_pago_movil` (inferida) | cargo | Comisión sin el prefijo "Com". Confianza `MEDIUM`. | Confirmación del preparador. |
| `TRF CR INM <banco> <RIF/CI> <nombre>` | `transferencia_inmediata` | abono o cargo | Transferencia de crédito inmediato. Trae el código del banco de la contraparte (0102, 0105, 0172...), su RIF o cédula y el inicio de su nombre. | Factura o documento que corresponde. |
| `COM, TRF. CR.INM.OB` | `comision_transferencia` | cargo | Comisión de la TRF CR INM con la misma referencia. | — |
| `TRANS,CTAS` | `transferencia_cuentas` | abono o cargo | Transferencia entre cuentas Banesco. | Si la cuenta es propia (traspaso) o de un tercero. |
| `TRANS,CTAS. A TERCEROS BANESCO` | `transferencia_terceros` | abono o cargo | Transferencia con un tercero en Banesco. | Beneficiario u ordenante. |
| `INCLUSION DE PLANILLA SENIAT C` | `pago_seniat` | cargo | Pago de una planilla al SENIAT. | La planilla: qué impuesto, qué período, si incluye multa o intereses. |
| `RECAUDACION MULTIPAGOS <código>` | `recaudacion_multipagos` | cargo | Pago por el servicio de recaudación Multipagos. | El servicio o ente que se pagó. |
| `COM,SERV.MTTO CTA` | `comision_mantenimiento` | cargo | Comisión de mantenimiento de la cuenta. | — |
| `EMISION DE ESTADO DE CUENTA` | `comision_estado_cuenta` | cargo | Comisión por emitir el estado de cuenta. | — |
| `Comision Servicio SMS` | `comision_sms` | cargo | Comisión por el servicio de mensajes de texto. | — |
| `C.SERV.CAJERO AUT.` | `comision_cajero` | cargo | Comisión por uso de cajero automático. | — |
| `PPV <RIF> <banco>` | `otro` | abono | No documentado en esta skill. | Preguntar al cliente o al banco. |

## Tasas de comisión

El estado de cuenta no imprime la tarifa. La skill solo calcula la **tasa observada** (comisión ÷ operación principal) y su mediana por tipo de operación. En los estados de enero de 2026 revisados, la mediana fue 1,5 % en los Pago Móvil recibidos y 0,3 % en los enviados. Es una observación, no una tarifa. Las tarifas cambian, así que cada tasa se compara con el tarifario vigente que publica el banco.

## Tratamiento contable sugerido (borrador para el preparador)

- **Comisiones:** débito a gasto bancario (`firm-config`, por defecto `6900`), crédito al banco. Se agrupan en un asiento por mes.
- **Cobros:** crédito a cuentas por cobrar del cliente identificado. Si no se identifica, queda como partida en conciliación; no se acredita a ingresos por defecto.
- **SENIAT:** contra la cuenta de impuesto que indique la planilla (p. ej. IVA por pagar, retenciones). La skill **no elige** esa cuenta.
- **Traspasos entre cuentas propias:** contra la otra cuenta bancaria. Se verifica que el monto aparezca con signo contrario en el estado de cuenta de esa cuenta.

Los asientos propuestos pasan por `je-review`.
