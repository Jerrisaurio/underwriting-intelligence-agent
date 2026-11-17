import pytest

from uw_agent.resolution.normalize import normalize_name


@pytest.mark.parametrize(
    ("raw", "core", "family", "has_cv"),
    [
        ("Tecnologías Bajío S.A. de C.V.", "TECNOLOGIAS BAJIO", "SA", True),
        ("TECNOLOGÍAS BAJÍO S.A. DE C.V.", "TECNOLOGIAS BAJIO", "SA", True),
        ("Tecnologías Bajío S.A. de C.V", "TECNOLOGIAS BAJIO", "SA", True),
        ("Tecnologías Bajío SACV", "TECNOLOGIAS BAJIO", "SA", True),
        ("Tecnologías Bajío SA de CV", "TECNOLOGIAS BAJIO", "SA", True),
        ("Tecnologías Bajío S.A.", "TECNOLOGIAS BAJIO", "SA", False),
        ("Desarrollos Mendoza S.A.P.I. de C.V.", "DESARROLLOS MENDOZA", "SAPI", True),
        ("Grupo Delta SAPI", "GRUPO DELTA", "SAPI", False),
        ("Cemex S.A.B. de C.V.", "CEMEX", "SAB", True),
        ("Comercializadora Lagunera S de RL de CV", "COMERCIALIZADORA LAGUNERA", "SRL", True),
        ("Constructora Lagunera SRL", "CONSTRUCTORA LAGUNERA", "SRL", False),
        ("Tecnologías Bajío S.C.", "TECNOLOGIAS BAJIO", "SC", False),
        ("Pascual Boing S.C.L.", "PASCUAL BOING", "SCL", False),
        ("Fresnillo plc", "FRESNILLO", "PLC", False),
        ("Banco Azteca S.A. Institución de Banca Múltiple", "BANCO AZTECA", "SA", False),
        ("PEMEX", "PEMEX", None, False),
    ],
)
def test_legal_form_is_split_from_core(raw, core, family, has_cv):
    n = normalize_name(raw)
    assert (n.core, n.legal_family, n.has_cv) == (core, family, has_cv)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("AT&T México", "ATT México"),
        ("C.F.E.", "CFE"),
        ("7-Eleven México", "7 Eleven México"),
        ("GF Inbursa", "Grupo Financiero Inbursa"),
        ("Org. Soriana", "Organización Soriana"),
        ("ORBIA ADVANCE CORP SAB", "Orbia Advance Corporation S.A.B. de C.V."),
    ],
)
def test_equivalent_spellings_share_core(a, b):
    assert normalize_name(a).core == normalize_name(b).core


def test_compact_form_ignores_spaces():
    assert normalize_name("VivaAerobus").compact == normalize_name("Viva Aerobus").compact


def test_word_ending_in_sa_is_not_a_legal_form():
    assert normalize_name("Mesa").core == "MESA"


def test_only_legal_form_leaves_empty_core():
    assert normalize_name("S.A. de C.V.").core == ""
