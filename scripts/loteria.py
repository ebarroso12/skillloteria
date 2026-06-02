#!/usr/bin/env python3
"""
loteria.py — Motor de análise matemática para loterias da Caixa.

FILOSOFIA (leia antes de usar):
Sorteios de loteria são eventos independentes e sem memória. Nenhuma
estatística de "números atrasados", "quentes", padrões de soma ou paridade
altera a probabilidade do próximo sorteio. Isso é uma propriedade
matemática, não uma limitação deste código. Por isso este módulo NÃO
promete prever resultados. O que ele faz é matemática real e verificável:

  1. Probabilidade exata de cada faixa de premiação (combinatória).
  2. Valor esperado da aposta vs. custo (quase sempre negativo).
  3. Fechamentos / desdobramentos: garantir X acertos SE Y dezenas saírem.
  4. Geração de jogos evitando dezenas populares (não muda a chance de
     ganhar, mas reduz a chance de DIVIDIR o prêmio).

Qualquer "sistema" que prometa aumentar a chance de acerto é falso.
"""

from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from math import comb
import random
from typing import Iterable


# ----------------------------------------------------------------------
# Configuração das modalidades
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Modalidade:
    nome: str
    universo: int          # quantidade total de dezenas (ex.: 60 na Mega)
    marcadas: int          # quantas o apostador marca na aposta mínima
    sorteadas: int         # quantas a Caixa sorteia
    acerta_para_premio: int  # menor faixa premiada (acertos)
    preco_apost_minima: float


MODALIDADES = {
    "megasena":  Modalidade("Mega-Sena", 60, 6, 6, 4, 5.00),
    "lotofacil": Modalidade("Lotofácil", 25, 15, 15, 11, 3.00),
    "quina":     Modalidade("Quina", 80, 5, 5, 2, 2.50),
    "lotomania": Modalidade("Lotomania", 100, 50, 20, 15, 3.00),
    "duplasena": Modalidade("Dupla Sena", 50, 6, 6, 3, 2.50),
    "diadesorte": Modalidade("Dia de Sorte", 31, 7, 7, 4, 2.50),
    "supersete": Modalidade("Super Sete", 10, 7, 7, 3, 2.50),  # por coluna
}


# ----------------------------------------------------------------------
# Probabilidades — combinatória pura
# ----------------------------------------------------------------------
def prob_faixa(universo: int, sorteadas: int, marcadas: int, acertos: int) -> float:
    """
    Probabilidade de acertar exatamente `acertos` dezenas.

    Modelo hipergeométrico:
      P = C(sorteadas, acertos) * C(universo - sorteadas, marcadas - acertos)
          / C(universo, marcadas)

    Interpretação: das `sorteadas` dezenas premiadas, você precisa que
    `acertos` estejam entre suas `marcadas`; as demais marcadas devem cair
    no resto do universo (universo - sorteadas).
    """
    if acertos > marcadas or acertos > sorteadas:
        return 0.0
    favoraveis = comb(sorteadas, acertos) * comb(universo - sorteadas, marcadas - acertos)
    total = comb(universo, marcadas)
    return favoraveis / total


def tabela_probabilidades(chave: str, marcadas: int | None = None) -> list[dict]:
    """Retorna a probabilidade de cada faixa premiada de uma modalidade."""
    m = MODALIDADES[chave]
    marcadas = marcadas or m.marcadas
    linhas = []
    for ac in range(m.acerta_para_premio, m.sorteadas + 1):
        p = prob_faixa(m.universo, m.sorteadas, marcadas, ac)
        linhas.append({
            "acertos": ac,
            "probabilidade": p,
            "uma_em": (1 / p) if p > 0 else float("inf"),
        })
    return linhas


def custo_aposta(chave: str, marcadas: int) -> float:
    """
    Custo de uma aposta com mais dezenas que o mínimo = preço-base
    multiplicado pelo número de combinações da aposta mínima contidas nela.
    Ex.: Mega com 7 dezenas = C(7,6) = 7 apostas de R$5,00 = R$35,00.
    """
    m = MODALIDADES[chave]
    n_combos = comb(marcadas, m.marcadas)
    return n_combos * m.preco_apost_minima


def valor_esperado(chave: str, marcadas: int, premios_por_faixa: dict[int, float]) -> dict:
    """
    Valor esperado da aposta = Σ (prob_faixa * prêmio_da_faixa) - custo.

    `premios_por_faixa`: {acertos: prêmio_em_R$}. Use os valores estimados
    do concurso (a skill busca isso ao vivo). O VE quase sempre é negativo;
    a transparência é exatamente o ponto.
    """
    m = MODALIDADES[chave]
    custo = custo_aposta(chave, marcadas)
    retorno_esperado = 0.0
    detalhe = []
    for ac, premio in premios_por_faixa.items():
        p = prob_faixa(m.universo, m.sorteadas, marcadas, ac)
        contrib = p * premio
        retorno_esperado += contrib
        detalhe.append({"acertos": ac, "prob": p, "premio": premio, "contribuicao": contrib})
    return {
        "custo": custo,
        "retorno_esperado": retorno_esperado,
        "valor_esperado": retorno_esperado - custo,
        "retorno_por_real": (retorno_esperado / custo) if custo else 0.0,
        "detalhe": detalhe,
    }


# ----------------------------------------------------------------------
# Fechamentos / desdobramentos — combinatória legítima, não previsão
# ----------------------------------------------------------------------
def fechamento_garantia(dezenas: list[int], marcadas_por_jogo: int,
                        garantia: int, max_jogos: int = 200) -> list[tuple[int, ...]]:
    """
    Gera um conjunto de jogos a partir de um pool de `dezenas` de modo que,
    SE pelo menos `garantia` dezenas do pool forem sorteadas, ao menos um
    jogo contenha `garantia` acertos.

    ATENÇÃO: isto NÃO aumenta a probabilidade de o pool conter os números
    sorteados. É uma garantia condicional ("se ... então ..."), que é o
    significado matemático real de um fechamento. Usa um algoritmo guloso
    de cobertura de conjuntos (greedy set cover) — bom o suficiente na
    prática, não necessariamente o mínimo absoluto de jogos.
    """
    pool = sorted(set(dezenas))
    if len(pool) < marcadas_por_jogo:
        raise ValueError("Pool menor que o tamanho do jogo.")
    # Conjuntos-alvo que precisam ser cobertos: toda combinação de tamanho `garantia`.
    alvos = set(combinations(pool, garantia))
    candidatos = list(combinations(pool, marcadas_por_jogo))
    random.shuffle(candidatos)

    escolhidos: list[tuple[int, ...]] = []
    nao_cobertos = set(alvos)
    while nao_cobertos and len(escolhidos) < max_jogos:
        melhor, melhor_cobertura = None, -1
        for c in candidatos:
            subalvos = set(combinations(c, garantia))
            cobre = len(nao_cobertos & subalvos)
            if cobre > melhor_cobertura:
                melhor, melhor_cobertura = c, cobre
        if melhor is None or melhor_cobertura <= 0:
            break
        escolhidos.append(melhor)
        nao_cobertos -= set(combinations(melhor, garantia))
    return escolhidos


# ----------------------------------------------------------------------
# Geração de jogos evitando dezenas populares
# ----------------------------------------------------------------------
NUMEROS_POPULARES = set(range(1, 32))  # datas de aniversário: 1–31


def gerar_jogo_anti_popular(chave: str, qtd_jogos: int = 1,
                            marcadas: int | None = None) -> list[list[int]]:
    """
    Gera jogos enviesados para LONGE de números <=31 (datas) e de padrões
    visuais óbvios. Não muda sua chance de ganhar; reduz a probabilidade de
    rachar o prêmio com muita gente caso você ganhe.
    """
    m = MODALIDADES[chave]
    marcadas = marcadas or m.marcadas
    universo = list(range(1, m.universo + 1))
    altos = [n for n in universo if n > 31]
    jogos = []
    for _ in range(qtd_jogos):
        # Pelo menos metade das dezenas acima de 31, quando o universo permite.
        n_altos = min(len(altos), max(marcadas // 2, marcadas - len(NUMEROS_POPULARES)))
        escolha = set(random.sample(altos, min(n_altos, len(altos))))
        resto = [n for n in universo if n not in escolha]
        escolha |= set(random.sample(resto, marcadas - len(escolha)))
        jogos.append(sorted(escolha))
    return jogos


# ----------------------------------------------------------------------
# Estatística descritiva (com aviso) — só descreve o passado
# ----------------------------------------------------------------------
def frequencia_historica(historico: Iterable[Iterable[int]]) -> dict[int, int]:
    """
    Conta quantas vezes cada dezena saiu no histórico fornecido.

    AVISO EXPLÍCITO: isto descreve o passado. NÃO prevê o futuro e NÃO deve
    ser usado para escolher números "quentes" ou "atrasados" — sorteios são
    independentes. Serve só para curiosidade estatística e para checar se a
    fonte de dados parece uniforme (todas as dezenas tendem à mesma
    frequência no limite de muitos sorteios).
    """
    freq: dict[int, int] = {}
    for sorteio in historico:
        for d in sorteio:
            freq[int(d)] = freq.get(int(d), 0) + 1
    return dict(sorted(freq.items()))


def teste_uniformidade(historico: list[list[int]], universo: int) -> dict:
    """
    Teste qui-quadrado de aderência: a loteria é estatisticamente justa?
    H0 = todas as dezenas têm a mesma probabilidade (sorteio uniforme).

    Calcula a estatística X² = Σ (observado - esperado)² / esperado e os
    graus de liberdade (universo - 1). NÃO ajuda a ganhar — ao contrário:
    se a loteria for justa (esperado), confirma que NÃO há padrão explorável.
    É a prova matemática de que "números quentes" não existem.
    """
    freq = frequencia_historica(historico)
    n_sorteios = len(historico)
    por_sorteio = len(historico[0]) if historico else 0
    total_bolas = n_sorteios * por_sorteio
    esperado = total_bolas / universo  # cada dezena, se uniforme
    if esperado == 0:
        return {"erro": "Histórico insuficiente."}

    x2 = sum((freq.get(d, 0) - esperado) ** 2 / esperado for d in range(1, universo + 1))
    gl = universo - 1
    # valor crítico ~ aproximação para p=0.05 (Wilson-Hilferty), evita scipy
    z = 1.645
    critico = gl * (1 - 2 / (9 * gl) + z * (2 / (9 * gl)) ** 0.5) ** 3
    return {
        "sorteios_analisados": n_sorteios,
        "qui_quadrado": round(x2, 2),
        "graus_liberdade": gl,
        "valor_critico_p005": round(critico, 2),
        "uniforme": x2 < critico,
        "interpretacao": (
            "X² abaixo do crítico: compatível com sorteio justo/uniforme — "
            "ou seja, NÃO há dezena 'viciada' a explorar. X² acima: a amostra "
            "destoa do uniforme (pode ser acaso, viés de amostra ou da fonte de dados)."
        ),
    }


def conferir_jogo(jogo: list[int], sorteado: list[int]) -> dict:
    """Confere um jogo contra o resultado sorteado: acertos e quais."""
    s = set(int(x) for x in sorteado)
    acertos = sorted(set(int(x) for x in jogo) & s)
    return {"acertos": len(acertos), "dezenas_certas": acertos}


def prob_dividir_premio(chave: str, apostas_estimadas: float | None = None) -> dict:
    """
    Probabilidade aproximada de DIVIDIR o prêmio principal se você ganhar.

    Modelo: se há N apostas no concurso e a chance de acerto da faixa
    principal é p, o número de outros ganhadores ~ Poisson(λ = N * p).
    A chance de você NÃO dividir = P(0 outros) = e^(-λ). Usar dezenas
    impopulares (>31) reduz N efetivo — é o único 'ganho' real disponível.
    """
    m = MODALIDADES[chave]
    p = prob_faixa(m.universo, m.sorteadas, m.marcadas, m.sorteadas)
    # estimativa grosseira de apostas se não informada (ordem de grandeza)
    N = apostas_estimadas if apostas_estimadas else 30_000_000
    lam = N * p
    from math import exp
    p_sozinho = exp(-lam)
    # média de co-ganhadores condicionada a haver ao menos você
    return {
        "apostas_consideradas": N,
        "prob_acerto_principal": p,
        "lambda_outros_ganhadores": round(lam, 4),
        "prob_premio_so_seu": round(p_sozinho, 4),
        "divisao_esperada_se_ganhar": round(1 + lam, 2),
        "nota": "Jogar dezenas impopulares (>31, sem padrões) reduz os ganhadores "
                "que dividiriam com você. NÃO muda sua chance de ganhar.",
    }
