"""
Pruebas de integridad de un estado de cuenta Banesco ya transcrito.

Se corre ANTES de conciliar. Una transcripción que no pasa estas pruebas no
se concilia: primero se corrige la línea señalada releyendo la página.

Pruebas:

  SALDO_CORRIDO     saldo anterior + abono - cargo = saldo impreso, línea por línea.
                    Ubica errores de transcripción en la línea exacta.
  CARGO_Y_ABONO     una línea con cargo y abono a la vez, o sin ninguno.
  SALDO_INICIAL     SALDO MES ANTERIOR (o primera línea) vs "Inicial" del resumen.
  SALDO_FINAL       último saldo del detalle vs "Final" del resumen.
  TOTAL_DEBITOS     suma de cargos vs "Otros Débitos" + "Cheques Pagados" del resumen.
  TOTAL_CREDITOS    suma de abonos vs "Otros Créditos" + "Depósitos" del resumen.
  ECUACION_RESUMEN  Inicial + créditos - débitos = Final (el propio resumen cuadra).
  CANTIDAD          número de líneas vs "Cantidad" del resumen. Solo advertencia:
                    no está documentado cómo cuenta Banesco cada línea.
  CONTINUIDAD       saldo final del mes N = saldo inicial del mes N+1, y no
                    faltan meses intermedios.
  SALDO_NEGATIVO    el saldo corrido queda negativo (sobregiro o error). Observación.

Cada hallazgo usa el vocabulario de workpaper-standards: los errores de cuadre
son MANUAL_REVIEW_REQUIRED; las observaciones son NEEDS_CLARIFICATION.

Uso:
    from banesco_validate import validar
    hallazgos = validar(movs, resumen)      # DataFrame; vacío = transcripción íntegra

CLI:
    python banesco_validate.py movimientos.csv --resumen resumen.csv [--out hallazgos.csv]
    (código de salida 1 si hay errores de cuadre)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

from banesco_parse import load_resumen, load_transcripcion

TOLERANCIA = 0.01  # Bs.; reemplazar por materiality.bank_rec_difference_tolerance

ERROR = "MANUAL_REVIEW_REQUIRED"
OBSERVACION = "NEEDS_CLARIFICATION"

HALLAZGO_COLS = ("prueba", "flag", "periodo", "linea", "pagina", "esperado", "encontrado", "diferencia", "nota")


def _h(prueba, flag, periodo, linea=None, pagina="", esperado=None, encontrado=None, nota=""):
    dif = None
    if esperado is not None and encontrado is not None:
        dif = round(encontrado - esperado, 2)
    return {
        "prueba": prueba,
        "flag": flag,
        "periodo": str(periodo),
        "linea": linea,
        "pagina": pagina,
        "esperado": None if esperado is None else round(esperado, 2),
        "encontrado": None if encontrado is None else round(encontrado, 2),
        "diferencia": dif,
        "nota": nota,
    }


def _distinto(a: float, b: float, tol: float) -> bool:
    return abs(a - b) > tol + 1e-9


def validar(
    movs: pd.DataFrame, resumen: pd.DataFrame | None = None, tolerancia: float = TOLERANCIA
) -> pd.DataFrame:
    hallazgos: list[dict] = []
    res_by_p = {} if resumen is None else {r["periodo"]: r for _, r in resumen.iterrows()}

    for periodo, grupo in movs.groupby("periodo", sort=True):
        grupo = grupo.sort_values("linea")
        ant = grupo.loc[grupo["es_saldo_anterior"]]
        det = grupo.loc[~grupo["es_saldo_anterior"]]
        res = res_by_p.get(periodo)

        if not ant.empty:
            saldo = float(ant.iloc[0]["saldo"])
        elif res is not None and res["saldo_inicial"] is not None:
            saldo = float(res["saldo_inicial"])
        else:
            saldo = None
            hallazgos.append(
                _h("SALDO_INICIAL", ERROR, periodo,
                   nota="Sin fila SALDO MES ANTERIOR ni resumen: no se puede verificar el saldo corrido.")
            )

        if res is not None and not ant.empty and res["saldo_inicial"] is not None:
            if _distinto(float(ant.iloc[0]["saldo"]), float(res["saldo_inicial"]), tolerancia):
                hallazgos.append(
                    _h("SALDO_INICIAL", ERROR, periodo, esperado=float(res["saldo_inicial"]),
                       encontrado=float(ant.iloc[0]["saldo"]),
                       nota="SALDO MES ANTERIOR del detalle no coincide con 'Inicial' del resumen.")
                )

        for _, r in det.iterrows():
            if (r["cargo"] > 0) == (r["abono"] > 0):
                hallazgos.append(
                    _h("CARGO_Y_ABONO", ERROR, periodo, r["linea"], r["pagina"],
                       nota=f"Línea ref {r['referencia']} con cargo={r['cargo']} y abono={r['abono']}: debe tener solo uno.")
                )
            if saldo is None:
                saldo = r["saldo"]
                continue
            esperado = round(saldo + r["abono"] - r["cargo"], 2)
            if r["saldo"] is None:
                hallazgos.append(
                    _h("SALDO_CORRIDO", ERROR, periodo, r["linea"], r["pagina"], esperado=esperado,
                       nota=f"Línea ref {r['referencia']} sin saldo transcrito.")
                )
                saldo = esperado
                continue
            if _distinto(esperado, r["saldo"], tolerancia):
                hallazgos.append(
                    _h("SALDO_CORRIDO", ERROR, periodo, r["linea"], r["pagina"], esperado=esperado,
                       encontrado=r["saldo"],
                       nota=f"Releer línea ref {r['referencia']} ({r['concepto']}): monto o saldo mal transcrito, o falta una línea antes.")
                )
            if r["saldo"] < -tolerancia:
                hallazgos.append(
                    _h("SALDO_NEGATIVO", OBSERVACION, periodo, r["linea"], r["pagina"], encontrado=r["saldo"],
                       nota="Saldo corrido negativo en el estado de cuenta: confirmar con el cliente (sobregiro, orden de registro del banco).")
                )
            # se arrastra el saldo impreso para que un error no contamine las líneas siguientes
            saldo = r["saldo"]

        if res is None:
            continue
        total_cargos = round(float(det["cargo"].sum()), 2)
        total_abonos = round(float(det["abono"].sum()), 2)
        ultimo = float(det.iloc[-1]["saldo"]) if not det.empty and det.iloc[-1]["saldo"] is not None else None

        if res["saldo_final"] is not None and ultimo is not None and _distinto(ultimo, res["saldo_final"], tolerancia):
            hallazgos.append(
                _h("SALDO_FINAL", ERROR, periodo, esperado=float(res["saldo_final"]), encontrado=ultimo,
                   nota="Último saldo del detalle no coincide con 'Final' del resumen: faltan o sobran líneas al cierre.")
            )
        if res["total_debitos"] is not None and _distinto(total_cargos, res["total_debitos"], tolerancia):
            hallazgos.append(
                _h("TOTAL_DEBITOS", ERROR, periodo, esperado=float(res["total_debitos"]), encontrado=total_cargos,
                   nota="Suma de CARGOS del detalle vs Otros Débitos + Cheques Pagados del resumen.")
            )
        if res["total_creditos"] is not None and _distinto(total_abonos, res["total_creditos"], tolerancia):
            hallazgos.append(
                _h("TOTAL_CREDITOS", ERROR, periodo, esperado=float(res["total_creditos"]), encontrado=total_abonos,
                   nota="Suma de ABONOS del detalle vs Otros Créditos + Depósitos del resumen.")
            )
        if None not in (res["saldo_inicial"], res["saldo_final"], res["total_debitos"], res["total_creditos"]):
            calc = res["saldo_inicial"] + res["total_creditos"] - res["total_debitos"]
            if _distinto(calc, res["saldo_final"], tolerancia):
                hallazgos.append(
                    _h("ECUACION_RESUMEN", ERROR, periodo, esperado=round(calc, 2), encontrado=float(res["saldo_final"]),
                       nota="El resumen transcrito no cuadra consigo mismo: releer el bloque RESUMEN DE MOVIMIENTOS/SALDOS.")
                )
        n_cargos = int((det["cargo"] > 0).sum())
        n_abonos = int((det["abono"] > 0).sum())
        if res["cant_debitos"] is not None and n_cargos != res["cant_debitos"]:
            hallazgos.append(
                _h("CANTIDAD", OBSERVACION, periodo, esperado=float(res["cant_debitos"]), encontrado=float(n_cargos),
                   nota="Cantidad de líneas de cargo vs 'Otros Débitos' del resumen. Si los montos cuadran, puede ser criterio de conteo del banco.")
            )
        if res["cant_creditos"] is not None and n_abonos != res["cant_creditos"]:
            hallazgos.append(
                _h("CANTIDAD", OBSERVACION, periodo, esperado=float(res["cant_creditos"]), encontrado=float(n_abonos),
                   nota="Cantidad de líneas de abono vs 'Otros Créditos' del resumen. Si los montos cuadran, puede ser criterio de conteo del banco.")
            )

    hallazgos.extend(_continuidad(movs, resumen, tolerancia))
    return pd.DataFrame(hallazgos, columns=list(HALLAZGO_COLS))


def _saldos_por_periodo(movs: pd.DataFrame, resumen: pd.DataFrame | None) -> dict:
    out = {}
    for periodo, g in movs.groupby("periodo", sort=True):
        g = g.sort_values("linea")
        ant = g.loc[g["es_saldo_anterior"]]
        det = g.loc[~g["es_saldo_anterior"]]
        out[periodo] = {
            "inicial": float(ant.iloc[0]["saldo"]) if not ant.empty else None,
            "final": float(det.iloc[-1]["saldo"]) if not det.empty and det.iloc[-1]["saldo"] is not None else None,
        }
    if resumen is not None:
        for _, r in resumen.iterrows():
            d = out.setdefault(r["periodo"], {"inicial": None, "final": None})
            d["inicial"] = d["inicial"] if d["inicial"] is not None else r["saldo_inicial"]
            d["final"] = d["final"] if d["final"] is not None else r["saldo_final"]
    return out


def _continuidad(movs, resumen, tolerancia) -> list[dict]:
    saldos = _saldos_por_periodo(movs, resumen)
    periodos = sorted(saldos)
    out = []
    for prev, cur in zip(periodos, periodos[1:]):
        if (cur - prev).n != 1:
            out.append(
                _h("CONTINUIDAD", ERROR, cur,
                   nota=f"Falta al menos un estado de cuenta entre {prev} y {cur}.")
            )
            continue
        fin, ini = saldos[prev]["final"], saldos[cur]["inicial"]
        if fin is not None and ini is not None and _distinto(fin, ini, tolerancia):
            out.append(
                _h("CONTINUIDAD", ERROR, cur, esperado=fin, encontrado=ini,
                   nota=f"Saldo final de {prev} no es el saldo inicial de {cur}.")
            )
    return out


def hay_errores(hallazgos: pd.DataFrame) -> bool:
    return bool((hallazgos["flag"] == ERROR).any()) if not hallazgos.empty else False


def _cli(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida la transcripción de un estado de cuenta Banesco.")
    parser.add_argument("movimientos", type=Path)
    parser.add_argument("--resumen", type=Path)
    parser.add_argument("--tolerancia", type=float, default=TOLERANCIA)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    movs = load_transcripcion(args.movimientos)
    resumen = load_resumen(args.resumen) if args.resumen else None
    hallazgos = validar(movs, resumen, args.tolerancia)
    if args.out:
        hallazgos.to_csv(args.out, index=False)
    if hallazgos.empty:
        print("OK: la transcripción cuadra línea por línea y contra el resumen.")
        return 0
    with pd.option_context("display.max_colwidth", 90, "display.width", 200):
        print(hallazgos.to_string(index=False))
    return 1 if hay_errores(hallazgos) else 0


if __name__ == "__main__":
    sys.exit(_cli())
