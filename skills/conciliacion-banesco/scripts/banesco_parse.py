"""
Carga movimientos de un estado de cuenta Banesco (Venezuela) en un formato tabular.

Dos fuentes posibles:

  1. Transcripción CSV (caso normal: el PDF de Banesco suele venir escaneado,
     sin capa de texto). Una fila por línea de DETALLE DE MOVIMIENTOS, con el
     encabezado de `references/plantilla-transcripcion.csv`:

         periodo,pagina,dia,referencia,concepto,cargo,abono,saldo

     - periodo     MM-AAAA tal como aparece en "Período: 01-2026"
     - referencia  texto; se conservan los ceros a la izquierda
     - cargo/abono/saldo en formato venezolano (1.234.567,89) o con punto decimal
     - la fila "SALDO MES ANTERIOR" se transcribe con dia vacío y solo saldo

  2. PDF con capa de texto (`extract_text_pdf`). Banesco no imprime el signo:
     cargo vs abono se decide por la variación del saldo corrido.

Resumen por período (opcional pero recomendado) en otro CSV:

     periodo,saldo_inicial,saldo_final,cant_debitos,total_debitos,cant_creditos,total_creditos

Uso:
    from banesco_parse import load_transcripcion, load_resumen, to_bank_rec
    movs = load_transcripcion("movimientos.csv")
    bank = to_bank_rec(movs)      # date, description, amount, reference -> bank-rec

CLI:
    python banesco_parse.py movimientos.csv --out banco_normalizado.csv
    python banesco_parse.py estado.pdf --out movimientos.csv   # solo si el PDF tiene texto
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

TRANSCRIPCION_COLS = ("periodo", "pagina", "dia", "referencia", "concepto", "cargo", "abono", "saldo")
RESUMEN_COLS = (
    "periodo",
    "saldo_inicial",
    "saldo_final",
    "cant_debitos",
    "total_debitos",
    "cant_creditos",
    "total_creditos",
)
SALDO_ANTERIOR = "SALDO MES ANTERIOR"
AMOUNT_EPS = 0.005

_AMOUNT_RE = re.compile(r"^-?[\d.,]+$")


def parse_ve_amount(value) -> float | None:
    """'1.602.410,00' -> 1602410.0 ; '-400,08' -> -400.08 ; '' -> None.

    Acepta también punto decimal ('1602410.00') porque las transcripciones a
    veces mezclan formatos. Regla: una coma siempre es decimal (formato
    venezolano); un punto solo es decimal si es el último separador y lo
    siguen exactamente dos dígitos. Los demás separadores son de miles.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if pd.isna(value) else float(value)
    s = str(value).strip().replace(" ", "").replace("−", "-").replace("Bs.", "").replace("Bs", "")
    if not s:
        return None
    if not _AMOUNT_RE.match(s):
        raise ValueError(f"monto no reconocido: {value!r}")
    neg = s.startswith("-")
    s = s.lstrip("-")
    if s.count(",") > 1:
        raise ValueError(f"monto no reconocido: {value!r}")
    last = max(s.rfind(","), s.rfind("."))
    if last != -1 and (s[last] == "," or len(s) - last - 1 == 2):
        entero, dec = s[:last], s[last + 1 :]
    else:
        entero, dec = s, "0"
    entero = entero.replace(".", "").replace(",", "")
    out = float(f"{entero or '0'}.{dec}")
    return -out if neg else out


def parse_periodo(value) -> pd.Period:
    """'01-2026' o '2026-01' -> Period('2026-01', 'M')."""
    s = str(value).strip()
    m = re.fullmatch(r"(\d{1,2})[-/](\d{4})", s)
    if m:
        return pd.Period(year=int(m.group(2)), month=int(m.group(1)), freq="M")
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})", s)
    if m:
        return pd.Period(year=int(m.group(1)), month=int(m.group(2)), freq="M")
    raise ValueError(f"período no reconocido: {value!r} (use MM-AAAA)")


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str).fillna("")
    raise ValueError(f"tipo de archivo no soportado: {path.suffix}")


def load_transcripcion(source: Path | str | pd.DataFrame) -> pd.DataFrame:
    """Devuelve un DataFrame normalizado, una fila por línea del estado de cuenta.

    Columnas: periodo (Period), linea (orden dentro del período), pagina, fecha,
    referencia, concepto, cargo, abono, saldo, es_saldo_anterior.
    """
    raw = source.copy() if isinstance(source, pd.DataFrame) else _read_table(Path(source))
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    missing = [c for c in TRANSCRIPCION_COLS if c not in raw.columns and c != "pagina"]
    if missing:
        raise ValueError(f"transcripción sin columnas requeridas: {missing}")
    if "pagina" not in raw.columns:
        raw["pagina"] = ""

    rows = []
    for i, r in raw.iterrows():
        periodo = parse_periodo(r["periodo"])
        concepto = str(r["concepto"]).strip()
        es_ant = concepto.upper().startswith(SALDO_ANTERIOR)
        dia = str(r["dia"]).strip()
        fecha = pd.NaT
        if dia:
            try:
                fecha = pd.Timestamp(year=periodo.year, month=periodo.month, day=int(float(dia)))
            except ValueError as exc:
                raise ValueError(f"fila {i + 2}: día {dia!r} inválido para {periodo}") from exc
        elif not es_ant:
            raise ValueError(f"fila {i + 2}: falta el día del movimiento")
        cargo = parse_ve_amount(r["cargo"]) or 0.0
        abono = parse_ve_amount(r["abono"]) or 0.0
        rows.append(
            {
                "periodo": periodo,
                "pagina": str(r["pagina"]).strip(),
                "fecha": fecha,
                "referencia": str(r["referencia"]).strip(),
                "concepto": concepto,
                "cargo": abs(cargo),
                "abono": abs(abono),
                "saldo": parse_ve_amount(r["saldo"]),
                "es_saldo_anterior": es_ant,
            }
        )
    df = pd.DataFrame(rows)
    df["linea"] = df.groupby("periodo").cumcount() + 1
    return df


def load_resumen(source: Path | str | pd.DataFrame) -> pd.DataFrame:
    raw = source.copy() if isinstance(source, pd.DataFrame) else _read_table(Path(source))
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    missing = [c for c in RESUMEN_COLS if c not in raw.columns]
    if missing:
        raise ValueError(f"resumen sin columnas requeridas: {missing}")
    out = pd.DataFrame({"periodo": [parse_periodo(p) for p in raw["periodo"]]})
    for c in RESUMEN_COLS[1:]:
        if c.startswith("cant_"):
            out[c] = [int(float(v)) if str(v).strip() else None for v in raw[c]]
        else:
            out[c] = [parse_ve_amount(v) for v in raw[c]]
    return out


def movimientos(df: pd.DataFrame) -> pd.DataFrame:
    """Solo líneas de movimiento (sin la fila SALDO MES ANTERIOR)."""
    return df.loc[~df["es_saldo_anterior"]].copy()


def to_bank_rec(df: pd.DataFrame) -> pd.DataFrame:
    """Formato de entrada de bank-rec/scripts/match_transactions.py."""
    m = movimientos(df)
    return pd.DataFrame(
        {
            "date": m["fecha"],
            "description": m["concepto"],
            "amount": (m["abono"] - m["cargo"]).round(2),
            "reference": m["referencia"],
            "periodo": m["periodo"].astype(str),
            "linea": m["linea"],
        }
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# PDF con capa de texto
# ---------------------------------------------------------------------------

_PERIODO_RE = re.compile(r"Per[ií]odo:\s*(\d{2}-\d{4})")
_ANTERIOR_RE = re.compile(r"SALDO MES ANTERIOR\s+(-?[\d.]+,\d{2})")
_LINEA_RE = re.compile(
    r"^(?P<dia>\d{2})\s+(?P<ref>\d{6,14})\s+(?P<concepto>.+?)\s+"
    r"(?P<monto>[\d.]+,\d{2})\s+(?P<saldo>-?[\d.]+,\d{2})$"
)


def extract_text_pdf(path: Path | str) -> pd.DataFrame:
    """Extrae movimientos de un PDF de Banesco que tenga capa de texto.

    Lanza ValueError si el PDF está escaneado: en ese caso hay que transcribir
    las páginas a la plantilla CSV (ver SKILL.md, paso 1).
    """
    import pdfplumber  # import diferido: solo hace falta en este modo

    rows: list[dict] = []
    with pdfplumber.open(str(path)) as pdf:
        texto_total = 0
        periodo = None
        saldo_prev = None
        for n, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            texto_total += len(text.strip())
            for line in text.splitlines():
                line = line.strip()
                mp = _PERIODO_RE.search(line)
                if mp:
                    periodo = mp.group(1)
                ma = _ANTERIOR_RE.search(line)
                if ma and periodo:
                    saldo_prev = parse_ve_amount(ma.group(1))
                    rows.append(_fila(periodo, n, "", "", SALDO_ANTERIOR, "", "", ma.group(1)))
                    continue
                ml = _LINEA_RE.match(line)
                if not ml or periodo is None:
                    continue
                monto = parse_ve_amount(ml["monto"])
                saldo = parse_ve_amount(ml["saldo"])
                cargo, abono = "", ""
                if saldo_prev is not None and abs(saldo_prev + monto - saldo) < AMOUNT_EPS:
                    abono = ml["monto"]
                elif saldo_prev is not None and abs(saldo_prev - monto - saldo) < AMOUNT_EPS:
                    cargo = ml["monto"]
                else:
                    # sin saldo previo confiable: se deja para revisión manual
                    cargo = ml["monto"] if saldo_prev is None or saldo < saldo_prev else ""
                    abono = "" if cargo else ml["monto"]
                rows.append(_fila(periodo, n, ml["dia"], ml["ref"], ml["concepto"], cargo, abono, ml["saldo"]))
                saldo_prev = saldo
    if texto_total == 0:
        raise ValueError(
            "el PDF no tiene capa de texto (escaneado). Transcriba las páginas a "
            "references/plantilla-transcripcion.csv y valide con banesco_validate.py"
        )
    return pd.DataFrame(rows, columns=list(TRANSCRIPCION_COLS))


def _fila(periodo, pagina, dia, ref, concepto, cargo, abono, saldo) -> dict:
    return dict(
        periodo=periodo, pagina=pagina, dia=dia, referencia=ref,
        concepto=concepto, cargo=cargo, abono=abono, saldo=saldo,
    )


def _cli(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normaliza un estado de cuenta Banesco.")
    parser.add_argument("input", type=Path, help="Transcripción CSV/XLSX o PDF con texto")
    parser.add_argument("--out", type=Path, required=True, help="CSV de salida")
    args = parser.parse_args(argv)

    if args.input.suffix.lower() == ".pdf":
        try:
            df = extract_text_pdf(args.input)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        df.to_csv(args.out, index=False)
        print(f"{len(df)} líneas extraídas -> {args.out} (formato transcripción; valide antes de usar)")
        return 0

    bank = to_bank_rec(load_transcripcion(args.input))
    bank.to_csv(args.out, index=False)
    print(f"{len(bank)} movimientos normalizados -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
