"""Valores em reais: guardados como centavos inteiros; entrada/saída no padrão brasileiro."""
from __future__ import annotations

import re

MAXIMO_CENTAVOS = 99_999_999_999  # 999.999.999,99


def parse_valor(texto: str) -> int:
    """Converte '1.234,56', '1234,56', '1234.56', '30.000' etc. em centavos.

    Regras: com vírgula, a vírgula é o separador decimal e o ponto, de milhar.
    Sem vírgula, 'ddd.ddd' (grupos de 3) é milhar e 'd.dd' é decimal.
    """
    erro = ValueError("Valor inválido. Use o formato 1.234,56.")
    if texto is None:
        raise erro
    t = str(texto).strip().replace("R$", "").replace(" ", "").replace(" ", "")
    if not t or not re.fullmatch(r"[\d.,]+", t):
        raise erro
    milhar = r"\d{1,3}(\.\d{3})+"
    if "," in t:
        inteiro, _, dec = t.rpartition(",")
        if not (re.fullmatch(milhar, inteiro) or re.fullmatch(r"\d+", inteiro)):
            raise erro
        if not re.fullmatch(r"\d{1,2}", dec):
            raise erro
        inteiro = inteiro.replace(".", "")
    elif "." in t:
        if re.fullmatch(milhar, t):
            inteiro, dec = t.replace(".", ""), "00"
        elif re.fullmatch(r"\d+\.\d{1,2}", t):
            inteiro, dec = t.split(".")
        else:
            raise erro
    else:
        inteiro, dec = t, "00"
    centavos = int(inteiro) * 100 + int(dec.ljust(2, "0"))
    if centavos <= 0:
        raise ValueError("O valor deve ser maior que zero.")
    if centavos > MAXIMO_CENTAVOS:
        raise ValueError("Valor acima do máximo permitido (999.999.999,99).")
    return centavos


def formatar(centavos: int | None) -> str:
    """30000_00 -> '30.000,00'."""
    c = int(centavos or 0)
    sinal = "-" if c < 0 else ""
    c = abs(c)
    return f"{sinal}{c // 100:,}".replace(",", ".") + f",{c % 100:02d}"


def para_campo(centavos: int) -> str:
    """Valor para preencher um campo de formulário (sem separador de milhar)."""
    return f"{centavos // 100},{centavos % 100:02d}"
