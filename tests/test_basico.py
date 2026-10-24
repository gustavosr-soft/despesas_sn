import pytest

from despesas import money
from despesas.config import ErroConfig, carregar


@pytest.mark.parametrize("texto,esperado", [
    ("30.000,00", 3_000_000), ("1.234,56", 123_456), ("1234,56", 123_456), ("1234.56", 123_456),
    ("0,5", 50), ("25", 2500), ("1.000", 100_000), ("12.5", 1250), ("R$ 6.000,00", 600_000),
    (" 50,00 ", 5000), ("0,01", 1),
])
def test_parse_valor_valido(texto, esperado):
    assert money.parse_valor(texto) == esperado


@pytest.mark.parametrize("texto", ["", "abc", "0", "0,00", "-5", "1,2,3", "1.2345", "1,234", "12,", ",50",
                                   "1..000", "10.00.00", "99999999999,00", "1e3", None])
def test_parse_valor_invalido(texto):
    with pytest.raises(ValueError):
        money.parse_valor(texto)


def test_formatar():
    assert money.formatar(3_000_000) == "30.000,00"
    assert money.formatar(5) == "0,05"
    assert money.formatar(7_837_500) == "78.375,00"
    assert money.formatar(0) == "0,00"
    assert money.para_campo(123_456) == "1234,56"


def test_config_padroes_e_caminhos(cfg):
    assert cfg.porta == 8099 and cfg.backup_manter == 3 and cfg.empresa == "Mercado Exemplo"
    assert cfg.db_path == cfg.base_dir / "dados" / "despesas.db"
    assert len(cfg.chave_secreta) >= 32
    assert carregar(cfg.arquivo).chave_secreta == cfg.chave_secreta  # chave estável entre reinícios


@pytest.mark.parametrize("trecho", ["[servidor]\nporta = 99999", "[servidor]\nporta = abc",
                                    "[backup]\nhora = 25:00", "[logs]\nnivel = XPTO",
                                    "[backup]\nativo = talvez"])
def test_config_invalida(tmp_path, trecho):
    ini = tmp_path / "c.ini"
    ini.write_text(trecho, encoding="utf-8")
    with pytest.raises(ErroConfig):
        carregar(ini)


def test_config_inexistente(tmp_path):
    with pytest.raises(ErroConfig):
        carregar(tmp_path / "nao_existe.ini")
