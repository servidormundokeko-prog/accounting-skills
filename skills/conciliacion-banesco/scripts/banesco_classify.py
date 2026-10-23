"""
Clasifica los movimientos de un estado de cuenta Banesco y empareja comisiones.

Categorías (ver references/conceptos-banesco.md para el tratamiento contable):

  pago_movil                   Banesco Pago Movil (cobro si abono, pago si cargo)
  transferencia_inmediata      TRF CR INM <banco> <RIF/CI> <nombre>
  transferencia_cuentas        TRANS,CTAS
  transferencia_terceros       TRANS,CTAS. A TERCEROS BANESCO
  pago_seniat                  INCLUSION DE PLANILLA SENIAT C
  recaudacion_multipagos       RECAUDACION MULTIPAGOS <código>
  comision_pago_movil          Com, Banesco Pago Movil (o línea inferida, ver abajo)
  comision_transferencia       COM, TRF. CR.INM.OB
  comision_mantenimiento       COM,SERV.MTTO CTA
  comision_estado_cuenta       EMISION DE ESTADO DE CUENTA
  comision_sms                 Comision Servicio SMS
  comision_cajero              C.SERV.CAJERO AUT.
  otro                         cualquier otro concepto (p. ej. PPV ...) -> MANUAL_REVIEW_REQUIRED

Emparejamiento de comisiones: Banesco cobra la comisión en una línea aparte con
la MISMA referencia que la operación principal. El concepto no es confiable:
a veces dice "Com, Banesco Pago Movil" y a veces repite "Banesco Pago Movil".
Por eso, dentro de un período, se agrupan las líneas por referencia (excepto
referencias en cero) y:

  - el movimiento de mayor monto es la operación principal;
  - un cargo menor cuya relación con el principal sea <= RATIO_MAX_COMISION
    es su comisión. Confianza HIGH si el concepto empieza por "Com", MEDIUM si
    la comisión se infiere solo por referencia y monto.

La tasa observada (comisión / principal) se reporta por línea. No se asume
ninguna tarifa: se calcula la mediana observada por tipo de operación y se
señalan las comisiones que se apartan de ella para que el preparador las
compare con el tarifario vigente del banco.

Uso:
    from banesco_classify import clasificar, resumen_mensual
    clas = clasificar(movs)
"""
from __future__ import annotations

import re

import pandas as pd

from banesco_parse import movimientos

RATIO_MAX_COMISION = 0.05     # una "comisión" mayor al 5 % del principal no se empareja
DESVIO_TASA = 0.0005          # 0,05 puntos porcentuales sobre la mediana observada

REGLAS: list[tuple[str, re.Pattern]] = [
    ("comision_pago_movil", re.compile(r"^COM\W*BANESCO\s+PAGO\s+MOVIL", re.I)),
    ("comision_transferencia", re.compile(r"^COM\W*TRF\W*CR\W*INM", re.I)),
    ("comision_mantenimiento", re.compile(r"^COM\W*SERV\W*MTTO", re.I)),
    ("comision_estado_cuenta", re.compile(r"^EMISION\s+DE\s+ESTADO\s+DE\s+CUENTA", re.I)),
    ("comision_sms", re.compile(r"^COMISION\s+SERVICIO\s+SMS", re.I)),
    ("comision_cajero", re.compile(r"^C\W*SERV\W*CAJERO", re.I)),
    ("pago_seniat", re.compile(r"INCLUSION\s+DE\s+PLANILLA\s+SENIAT", re.I)),
    ("recaudacion_multipagos", re.compile(r"^RECAUDACION\s+MULTIPAGOS", re.I)),
    ("pago_movil", re.compile(r"^BANESCO\s+PAGO\s+MOVIL", re.I)),
    ("transferencia_inmediata", re.compile(r"^TRF\W*CR\W*INM", re.I)),
    ("transferencia_terceros", re.compile(r"^TRANS\W*CTAS\W*A\s+TERCEROS", re.I)),
    ("transferencia_cuentas", re.compile(r"^TRANS\W*CTAS", re.I)),
]

CATEGORIAS_GASTO_BANCARIO = {
    "comision_pago_movil",
    "comision_transferencia",
    "comision_mantenimiento",
    "comision_estado_cuenta",
    "comision_sms",
    "comision_cajero",
}

TRATAMIENTO = {
    "pago_movil": "Cobro a cliente (abono) o pago a proveedor/tercero (cargo). Identificar contraparte en libro.",
    "transferencia_inmediata": "Transferencia interbancaria. El concepto trae código de banco y RIF/CI de la contraparte.",
    "transferencia_cuentas": "Transferencia entre cuentas Banesco. Confirmar si es cuenta propia (traspaso) o de tercero.",
    "transferencia_terceros": "Transferencia a/desde tercero en Banesco. Identificar beneficiario en libro.",
    "pago_seniat": "Pago de planilla SENIAT. Requiere la planilla para saber qué impuesto liquida.",
    "recaudacion_multipagos": "Pago por recaudación Multipagos. Requiere soporte para identificar el servicio.",
    "comision_pago_movil": "Gasto bancario: comisión Pago Móvil.",
    "comision_transferencia": "Gasto bancario: comisión transferencia inmediata.",
    "comision_mantenimiento": "Gasto bancario: mantenimiento de cuenta.",
    "comision_estado_cuenta": "Gasto bancario: emisión de estado de cuenta.",
    "comision_sms": "Gasto bancario: servicio SMS.",
    "comision_cajero": "Gasto bancario: servicio de cajero automático.",
    "otro": "Concepto no catalogado. No se clasifica sin soporte.",
}


def categoria(concepto: str) -> str:
    c = str(concepto).strip()
    for nombre, patron in REGLAS:
        if patron.search(c):
            return nombre
    return "otro"


def _es_ref_nula(ref: str) -> bool:
    return not ref or set(ref) <= {"0"}


def clasificar(movs: pd.DataFrame) -> pd.DataFrame:
    df = movimientos(movs).reset_index(drop=True)
    df["sentido"] = ["abono" if a > 0 else "cargo" for a in df["abono"]]
    df["monto"] = df["abono"].where(df["abono"] > 0, df["cargo"])
    df["categoria"] = [categoria(c) for c in df["concepto"]]
    df["es_comision"] = df["categoria"].isin(CATEGORIAS_GASTO_BANCARIO)
    df["principal_linea"] = pd.NA
    df["principal_categoria"] = ""
    df["principal_sentido"] = ""
    df["tasa_observada"] = pd.NA
    df["confianza"] = ""

    for (_, ref), g in df.groupby(["periodo", "referencia"], sort=False):
        if _es_ref_nula(ref) or len(g) < 2:
            continue
        principal_idx = g["monto"].idxmax()
        principal = df.loc[principal_idx]
        for i, r in g.iterrows():
            if i == principal_idx or r["sentido"] != "cargo" or principal["monto"] <= 0:
                continue
            ratio = r["monto"] / principal["monto"]
            if ratio > RATIO_MAX_COMISION:
                continue
            explicita = str(r["concepto"]).strip().upper().startswith("COM")
            if not explicita:
                df.at[i, "categoria"] = (
                    "comision_transferencia" if principal["categoria"] == "transferencia_inmediata"
                    else "comision_pago_movil"
                )
            df.at[i, "es_comision"] = True
            df.at[i, "principal_linea"] = int(principal["linea"])
            df.at[i, "principal_categoria"] = principal["categoria"]
            df.at[i, "principal_sentido"] = principal["sentido"]
            df.at[i, "tasa_observada"] = round(ratio, 6)
            df.at[i, "confianza"] = "HIGH" if explicita else "MEDIUM"

    df["tratamiento"] = [TRATAMIENTO[c] for c in df["categoria"]]
    df["flag"] = ""
    # UNKNOWN como sub-estado siempre baja a MANUAL_REVIEW_REQUIRED (workpaper-standards)
    df.loc[df["categoria"] == "otro", "flag"] = "MANUAL_REVIEW_REQUIRED"
    df.loc[df["categoria"].isin(["pago_seniat", "recaudacion_multipagos"]), "flag"] = "NEEDS_CLARIFICATION"
    huerfanas = df["categoria"].isin(["comision_pago_movil", "comision_transferencia"]) & df["principal_linea"].isna()
    df.loc[huerfanas, "flag"] = "NEEDS_CLARIFICATION"
    df.loc[huerfanas, "tratamiento"] = df.loc[huerfanas, "tratamiento"] + " Sin operación principal con la misma referencia."
    _marcar_tasas_atipicas(df)
    return df


def _marcar_tasas_atipicas(df: pd.DataFrame) -> None:
    emparejadas = df.loc[df["tasa_observada"].notna()]
    if emparejadas.empty:
        return
    claves = ["principal_categoria", "principal_sentido"]
    medianas = emparejadas.groupby(claves)["tasa_observada"].median()
    df["tasa_mediana"] = pd.NA
    for i, r in emparejadas.iterrows():
        med = float(medianas.loc[(r["principal_categoria"], r["principal_sentido"])])
        df.at[i, "tasa_mediana"] = round(med, 6)
        if abs(float(r["tasa_observada"]) - med) > DESVIO_TASA:
            df.at[i, "flag"] = "NEEDS_CLARIFICATION"
            df.at[i, "tratamiento"] = (
                f"{df.at[i, 'tratamiento']} Tasa {float(r['tasa_observada']):.4%} se aparta de la mediana "
                f"{med:.4%}: comparar con tarifario del banco."
            )


def tabla_comisiones(clas: pd.DataFrame) -> pd.DataFrame:
    """Comisiones con su operación principal, para la pestaña Comisiones."""
    cols = [
        "periodo", "linea", "fecha", "referencia", "concepto", "monto", "categoria",
        "principal_linea", "principal_categoria", "principal_sentido",
        "tasa_observada", "tasa_mediana", "confianza", "flag", "tratamiento",
    ]
    out = clas.loc[clas["es_comision"]].copy()
    for c in cols:
        if c not in out.columns:
            out[c] = pd.NA
    return out[cols].reset_index(drop=True)


def resumen_mensual(clas: pd.DataFrame) -> pd.DataFrame:
    """Cantidad y monto por período, categoría y sentido."""
    g = clas.groupby(["periodo", "categoria", "sentido"], sort=True)["monto"]
    out = pd.DataFrame({"cantidad": g.size(), "monto": g.sum().round(2)}).reset_index()
    out["periodo"] = out["periodo"].astype(str)
    return out
