import pandas as pd
import pytest

from banesco_classify import clasificar
from banesco_parse import load_resumen, load_transcripcion, parse_ve_amount, to_bank_rec
from banesco_validate import hay_errores, validar
from conciliar_banesco import conciliar

COLS = ["periodo", "pagina", "dia", "referencia", "concepto", "cargo", "abono", "saldo"]

MOVS = [
    ["01-2026", 1, "", "", "SALDO MES ANTERIOR", "", "", "1.000,00"],
    ["01-2026", 1, "02", "00000000111", "Banesco Pago Movil", "", "10.000,00", "11.000,00"],
    ["01-2026", 1, "02", "00000000111", "Com, Banesco Pago Movil", "150,00", "", "10.850,00"],
    ["01-2026", 1, "05", "24000000001", "Banesco Pago Movil", "2.000,00", "", "8.850,00"],
    ["01-2026", 1, "05", "24000000001", "Banesco Pago Movil", "6,00", "", "8.844,00"],
    ["01-2026", 1, "10", "02600000001", "INCLUSION DE PLANILLA SENIAT C", "3.000,00", "", "5.844,00"],
    ["01-2026", 1, "15", "03500000001", "TRANS,CTAS", "500,00", "", "5.344,00"],
    ["01-2026", 1, "31", "00000000000", "COM,SERV.MTTO CTA", "8,00", "", "5.336,00"],
    ["01-2026", 1, "31", "00000000000", "EMISION DE ESTADO DE CUENTA", "8,00", "", "5.328,00"],
    ["02-2026", 2, "", "", "SALDO MES ANTERIOR", "", "", "5.328,00"],
    ["02-2026", 2, "03", "00000000222", "Banesco Pago Movil", "", "4.000,00", "9.328,00"],
    ["02-2026", 2, "03", "00000000222", "Com, Banesco Pago Movil", "60,00", "", "9.268,00"],
    ["02-2026", 2, "28", "00000000000", "COM,SERV.MTTO CTA", "8,00", "", "9.260,00"],
]

RESUMEN = pd.DataFrame(
    [
        ["01-2026", "1.000,00", "5.328,00", 7, "5.672,00", 1, "10.000,00"],
        ["02-2026", "5.328,00", "9.260,00", 2, "68,00", 1, "4.000,00"],
    ],
    columns=["periodo", "saldo_inicial", "saldo_final", "cant_debitos", "total_debitos", "cant_creditos", "total_creditos"],
)

LIBRO = pd.DataFrame(
    [
        ["02/01/2026", "Cobro cliente A", "00000000111", "10.000,00", ""],
        ["05/01/2026", "Pago proveedor B", "", "", "2.000,00"],
        ["10/01/2026", "Pago IVA SENIAT", "", "", "3.000,00"],
        ["15/01/2026", "Traspaso a cuenta nómina", "", "", "500,00"],
        ["30/01/2026", "Cheque 101", "101", "", "700,00"],
        ["31/01/2026", "Depósito cliente C", "", "4.000,00", ""],
    ],
    columns=["fecha", "descripcion", "referencia", "debe", "haber"],
)


@pytest.fixture
def movs():
    return load_transcripcion(pd.DataFrame(MOVS, columns=COLS))


@pytest.fixture
def resumen():
    return load_resumen(RESUMEN)


@pytest.mark.parametrize(
    "raw, esperado",
    [("1.602.410,00", 1602410.0), ("-400,08", -400.08), ("8,00", 8.0), ("1602410.00", 1602410.0),
     ("1.602.410", 1602410.0), ("12,5", 12.5), ("", None)],
)
def test_parse_ve_amount(raw, esperado):
    assert parse_ve_amount(raw) == esperado


def test_transcripcion_integra(movs, resumen):
    hallazgos = validar(movs, resumen)
    assert not hay_errores(hallazgos), hallazgos.to_string()
    assert to_bank_rec(movs)["amount"].sum() == pytest.approx(10000 + 4000 - 5672 - 68)


def test_saldo_corrido_ubica_linea_mal_transcrita(resumen):
    malos = [list(r) for r in MOVS]
    malos[3][5] = "2.200,00"  # se leyó 2.200 en vez de 2.000
    h = validar(load_transcripcion(pd.DataFrame(malos, columns=COLS)), resumen)
    corrido = h.loc[h["prueba"] == "SALDO_CORRIDO"]
    assert list(corrido["linea"]) == [4]
    assert corrido.iloc[0]["diferencia"] == pytest.approx(200.0)
    assert "TOTAL_DEBITOS" in set(h["prueba"])


def test_continuidad_entre_meses(resumen):
    malos = [list(r) for r in MOVS]
    malos[9][7] = "5.000,00"
    h = validar(load_transcripcion(pd.DataFrame(malos, columns=COLS)))
    assert "CONTINUIDAD" in set(h["prueba"])


def test_saldo_negativo_es_observacion():
    filas = [
        ["03-2026", 1, "", "", "SALDO MES ANTERIOR", "", "", "100,00"],
        ["03-2026", 1, "02", "1", "TRANS,CTAS", "500,00", "", "-400,00"],
        ["03-2026", 1, "02", "2", "Banesco Pago Movil", "", "600,00", "200,00"],
    ]
    h = validar(load_transcripcion(pd.DataFrame(filas, columns=COLS)))
    assert list(h["prueba"]) == ["SALDO_NEGATIVO"]
    assert not hay_errores(h)


def test_comisiones_emparejadas_por_referencia(movs):
    clas = clasificar(movs).set_index("linea")
    enero = clas.loc[clas["periodo"] == pd.Period("2026-01", "M")]
    explicita, inferida = enero.loc[3], enero.loc[5]
    assert explicita["confianza"] == "HIGH" and explicita["principal_linea"] == 2
    assert explicita["tasa_observada"] == pytest.approx(0.015)
    # mismo concepto "Banesco Pago Movil", pero es la comisión del pago saliente
    assert inferida["categoria"] == "comision_pago_movil"
    assert inferida["confianza"] == "MEDIUM" and inferida["principal_linea"] == 4
    assert enero.loc[6, "categoria"] == "pago_seniat" and enero.loc[6, "flag"] == "NEEDS_CLARIFICATION"


def test_conciliacion_cuadra_con_partidas_en_transito(tmp_path, movs):
    pd.DataFrame(MOVS, columns=COLS).to_csv(tmp_path / "movs.csv", index=False)
    RESUMEN.to_csv(tmp_path / "resumen.csv", index=False)
    LIBRO.to_csv(tmp_path / "libro.csv", index=False)
    out = tmp_path / "rec.xlsx"
    rc = conciliar(tmp_path / "movs.csv", tmp_path / "resumen.csv", out, tmp_path / "libro.csv",
                   saldo_inicial_libro=1000.0, cuenta_banco="1010")
    assert rc == 0
    items = pd.read_excel(out, sheet_name="Reconciling_Items")
    enero = items.loc[items["cierre"] == "2026-01-31"]
    assert set(enero.loc[enero["lado"] == "libro", "estado_rec"]) == {"DEPOSIT_IN_TRANSIT", "OUTSTANDING_CHECK"}
    assert enero.loc[enero["estado_rec"] == "BANK_FEE_NOT_BOOKED", "amount"].sum() == pytest.approx(-172.0)
    jes = pd.read_excel(out, sheet_name="JEs_Proposed")
    assert list(jes.groupby("JE_ID")["Debit"].sum()) == pytest.approx([172.0, 68.0])
    assert (jes.groupby("JE_ID")["Debit"].sum() == jes.groupby("JE_ID")["Credit"].sum()).all()
    ev = pd.read_excel(out, sheet_name="Evidence")
    dif = ev.loc[ev["Concepto"] == "Diferencia no conciliada", "Valor"]
    assert list(dif) == pytest.approx([0.0, 0.0])


def test_no_concilia_si_la_transcripcion_no_cuadra(tmp_path):
    malos = [list(r) for r in MOVS]
    malos[3][5] = "2.200,00"
    pd.DataFrame(malos, columns=COLS).to_csv(tmp_path / "movs.csv", index=False)
    RESUMEN.to_csv(tmp_path / "resumen.csv", index=False)
    rc = conciliar(tmp_path / "movs.csv", tmp_path / "resumen.csv", tmp_path / "rec.xlsx")
    assert rc == 1
    assert "Validacion" in pd.ExcelFile(tmp_path / "rec.xlsx").sheet_names


def test_modo_neto_empareja_cobro_neto_de_comision(tmp_path):
    pd.DataFrame(MOVS, columns=COLS).to_csv(tmp_path / "movs.csv", index=False)
    libro = LIBRO.copy()
    libro.loc[0, "debe"] = "9.850,00"  # el cliente registra el Pago Móvil neto de comisión
    libro.to_csv(tmp_path / "libro.csv", index=False)
    out = tmp_path / "rec.xlsx"
    conciliar(tmp_path / "movs.csv", None, out, tmp_path / "libro.csv", saldo_inicial_libro=1000.0,
              modo_comisiones="neto")
    matched = pd.read_excel(out, sheet_name="Matched")
    assert 9850.0 in set(matched["bank_amount"].round(2))
