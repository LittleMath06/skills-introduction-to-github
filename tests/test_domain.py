"""Testes unitários das regras de negócio (sem banco, sem rede)."""
from __future__ import annotations

import pytest

from prospeccao.domain import cnpj, query_parser, scoring
from prospeccao.domain.fiscal import infer_icms
from prospeccao.domain.regions import normalize_uf, region_of
from prospeccao.domain.segments import DEFAULT_SEGMENTS, SegmentRule, classify
from prospeccao.domain.text import (
    is_free_email,
    normalize_email,
    normalize_phone,
    tokens,
)

# ---------------------------------------------------------------- CNPJ


@pytest.mark.parametrize("value", ["11.222.333/0001-81", "11222333000181", 11222333000181])
def test_cnpj_valid(value):
    assert cnpj.is_valid(value)
    assert cnpj.validate(value) == "11222333000181"


@pytest.mark.parametrize("value", ["11.222.333/0001-82", "00000000000000", "11111111111111",
                                   "123", "", None, "abc", "112223330001811"])
def test_cnpj_invalid(value):
    assert not cnpj.is_valid(value)
    with pytest.raises(cnpj.InvalidCNPJ):
        cnpj.validate(value)


def test_cnpj_alfanumerico_exemplo_oficial():
    # Exemplo publicado pela Receita Federal para o CNPJ alfanumérico: 12.ABC.345/01DE-35
    assert cnpj.compute_check_digits("12ABC34501DE") == "35"
    assert cnpj.is_valid("12.ABC.345/01DE-35")
    assert not cnpj.is_valid("12.ABC.345/01DE-36")


def test_cnpj_spreadsheet_number_lost_zeros():
    # Planilha converteu "01.234.567/0001-95" em número
    valid = "0123456700" + "01"
    full = valid + cnpj.compute_check_digits(valid)
    assert cnpj.clean(int(full)) == full
    assert cnpj.clean(f"{int(full)}.0") == full


def test_cnpj_format_and_parts():
    assert cnpj.format_cnpj("11222333000181") == "11.222.333/0001-81"
    assert cnpj.basico("11.222.333/0001-81") == "11222333"
    assert cnpj.is_matriz("11222333000181")
    assert not cnpj.is_matriz("11222333000262")


# ---------------------------------------------------------------- textos e contatos


def test_phone_normalization():
    assert normalize_phone("011", "3333-4444") == "1133334444"
    assert normalize_phone("11", "98888-7777") == "11988887777"
    assert normalize_phone("", "123") is None
    assert normalize_phone("11", "00000000") is None


def test_email_rules():
    assert normalize_email(" Contato@Empresa.com.BR ") == "contato@empresa.com.br"
    assert normalize_email("invalido@") is None
    assert is_free_email("fulano@gmail.com")
    assert not is_free_email("vendas@empresa.com.br")


def test_tokens_remove_stopwords_and_accents():
    assert tokens("Instalações Elétricas LTDA de São Paulo") == ["instalacoes", "eletricas", "paulo"]


def test_regions():
    assert region_of("sp") == "Sudeste"
    assert region_of("MT") == "Centro-Oeste"
    assert region_of(None) is None
    assert normalize_uf("São Paulo") == "SP"
    assert normalize_uf("mg") == "MG"
    assert normalize_uf("Narnia") is None


# ---------------------------------------------------------------- segmentos


@pytest.fixture
def rules():
    return [SegmentRule(i, s["name"], tuple(s["cnae_prefixes"]), tuple(s["keywords"]),
                        s.get("is_fallback", False)) for i, s in enumerate(DEFAULT_SEGMENTS, 1)]


@pytest.mark.parametrize("cnae_code,expected", [
    ("4321500", "Instaladores"), ("4673700", "Distribuidores"), ("4742300", "Varejo"),
    ("7112000", "Engenharia"), ("4221902", "Energia"), ("4221904", "Telecomunicações"),
    ("4211101", "Infraestrutura"), ("4120400", "Construção Civil"), ("2733300", "Fabricantes"),
    ("0115600", "Agrobusiness"), ("2512800", "Indústria"), ("3321000", "Automação"),
])
def test_classify_by_cnae(rules, cnae_code, expected):
    result = classify(rules, cnae_code)
    assert result.segment_name == expected
    assert result.method == "cnae"
    assert 0 < result.confidence <= 0.95


def test_classify_most_specific_prefix_wins(rules):
    # 4221902 casa com "42" (Infraestrutura) e "4221902" (Energia) → Energia
    assert classify(rules, "4221902").segment_name == "Energia"


def test_classify_by_keyword_when_cnae_generic(rules):
    result = classify(rules, "8299799", [], "SOLAR FOTOVOLTAICA INTEGRADORA LTDA")
    assert result.segment_name == "Integradores"
    assert result.method == "palavra-chave"


def test_classify_fallback(rules):
    result = classify(rules, "9602501", [], "SALAO DE BELEZA")
    assert result.segment_name == "Outros"
    assert result.method == "fallback"
    assert result.confidence == 0.2


def test_classify_secondary_cnae(rules):
    result = classify(rules, "9602501", ["4321500"])
    assert result.segment_name == "Instaladores"
    assert "secundário" in result.explanation


# ---------------------------------------------------------------- similaridade e potencial


def _profile():
    customers = [scoring.CompanyFeatures("4321500", [], "Instaladores", "SP", "03",
                                         "instalacoes eletricas prediais") for _ in range(6)]
    customers += [scoring.CompanyFeatures("4673700", [], "Distribuidores", "PR", "05",
                                          "distribuidora material eletrico") for _ in range(3)]
    customers += [scoring.CompanyFeatures("0115600", [], "Agrobusiness", "MT", "05", "fazenda")]
    return scoring.Profile.build(customers)


def test_similarity_without_customers_is_zero_and_explained():
    result = scoring.similarity(scoring.Profile(), scoring.CompanyFeatures("4321500"), {})
    assert result["score"] == 0
    assert "não importada" in result["note"]


def test_similarity_exact_match_is_high_and_explained():
    profile = _profile()
    c = scoring.CompanyFeatures("4321500", [], "Instaladores", "SP", "03", "instalacoes eletricas")
    result = scoring.similarity(profile, c, {})
    assert result["score"] >= 90
    assert result["similar_customers"] == 6
    keys = {cr["key"] for cr in result["criteria"]}
    assert keys == {"cnae", "segmento", "palavras", "localizacao", "porte"}
    cnae_cr = next(cr for cr in result["criteria"] if cr["key"] == "cnae")
    assert "6 cliente" in cnae_cr["explanation"]


def test_similarity_orders_candidates_sensibly():
    profile = _profile()
    same = scoring.similarity(profile, scoring.CompanyFeatures("4321500", [], "Instaladores", "SP"), {})
    group = scoring.similarity(profile, scoring.CompanyFeatures("4322301", [], "Instaladores", "RJ"), {})
    unrelated = scoring.similarity(profile, scoring.CompanyFeatures("5611201", [], "Outros", "AM"), {})
    assert same["score"] > group["score"] > unrelated["score"]


def test_similarity_region_fallback_when_uf_absent():
    profile = _profile()
    r = scoring.similarity(profile, scoring.CompanyFeatures("4321500", uf="RJ"), {})
    loc = next(cr for cr in r["criteria"] if cr["key"] == "localizacao")
    assert 0 < loc["value"] <= 0.5 and "Sudeste" in loc["explanation"]


def test_weights_are_configurable_and_normalized():
    profile = _profile()
    c = scoring.CompanyFeatures("5611201", [], "Outros", "SP", "03")
    only_location = scoring.similarity(profile, c, {"cnae": 0, "segmento": 0, "palavras": 0,
                                                    "localizacao": 5, "porte": 0})
    assert only_location["score"] == 100.0
    w = scoring.normalize_weights({"cnae": 2, "porte": 2}, scoring.DEFAULT_SIMILARITY_WEIGHTS)
    assert abs(sum(w.values()) - 1) < 1e-9


def test_profile_roundtrip():
    p = _profile()
    q = scoring.Profile.from_dict(p.to_dict())
    assert q.n == p.n and q.cnae[7] == p.cnae[7] and q.uf == p.uf


def test_potential_zero_for_inactive_company():
    r = scoring.potential(95, "Instaladores", 100, "08", 10)
    assert r["score"] == 0 and "Baixada" in r["note"]


def test_potential_combines_criteria():
    high = scoring.potential(90, "Instaladores", 90, "02", 10)
    low = scoring.potential(90, "Outros", 20, "02", 0.5)
    assert high["score"] > low["score"]
    assert {c["key"] for c in high["criteria"]} == set(scoring.DEFAULT_POTENTIAL_WEIGHTS)


def test_completeness():
    assert scoring.completeness({}) == 0
    full = {k: True for k in ["razao_social", "nome_fantasia", "cnae_principal", "endereco",
                              "municipio", "uf", "telefone", "email", "site", "porte",
                              "data_abertura"]}
    assert scoring.completeness(full) == 100


# ---------------------------------------------------------------- fiscal


def test_icms_inference_is_only_probable():
    inf = infer_icms("4673700")
    assert inf["level"] == "provavel" and inf["confidence"] < 1
    assert "Não constitui aconselhamento" in inf["notes"]
    assert infer_icms("7112000") is None  # serviço de engenharia (ISS)


# ---------------------------------------------------------------- pesquisa livre


def test_parse_engineering_sao_paulo():
    p = query_parser.parse("Encontrar empresas de engenharia elétrica em São Paulo")
    assert (p.segment, p.uf, p.terms) == ("Engenharia", "SP", ["eletrica"])


def test_parse_agro_centro_oeste():
    p = query_parser.parse("Encontrar empresas do agronegócio no Centro-Oeste")
    assert (p.segment, p.region, p.uf) == ("Agrobusiness", "Centro-Oeste", None)


def test_parse_similar_to_customers():
    p = query_parser.parse("Encontrar empresas semelhantes aos meus clientes atuais")
    assert p.similar_to_customers and p.terms == []
    assert p.as_filters()["sort"] == "similarity"


def test_parse_uf_abbreviation_and_city():
    p = query_parser.parse("instaladores em MG", known_cities={"Uberlandia"})
    assert (p.segment, p.uf) == ("Instaladores", "MG")
    p = query_parser.parse("distribuidores uberlandia", known_cities={"UBERLANDIA"})
    assert p.city == "UBERLANDIA"


def test_parse_does_not_confuse_words_with_uf():
    # "de" / "es" minúsculos no meio da frase não viram UF
    p = query_parser.parse("fabricantes de cabos especiais")
    assert p.uf is None and p.segment == "Fabricantes"


def test_parse_mato_grosso_do_sul_before_mato_grosso():
    assert query_parser.parse("agro em mato grosso do sul").uf == "MS"
