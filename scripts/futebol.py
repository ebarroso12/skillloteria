#!/usr/bin/env python3
"""
futebol.py — Motor de modelagem probabilística para futebol (incl. Copa).

Aqui, ao contrário das loterias, existe sinal real: times têm forças
diferentes e os resultados não são uniformemente aleatórios. Mas o produto
final é sempre uma DISTRIBUIÇÃO DE PROBABILIDADE, nunca uma certeza. Mesmo
modelos bons erram muito, e lucro de longo prazo em apostas é difícil até
para profissionais.

Modelos implementados:
  1. Poisson independente para gols (base clássica).
  2. Ajuste Dixon-Coles para placares baixos (corrige 0-0,1-0,0-1,1-1).
  3. Rating Elo para estimar força relativa e converter em expectativa de gols.
  4. Probabilidade implícita a partir de odds, removendo a margem da casa
     ("vig"), para detectar value bets.
  5. Simulação de Monte Carlo de um mata-mata (chaveamento de Copa).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from math import exp, factorial
import random
from typing import Sequence


# ----------------------------------------------------------------------
# 1) Poisson
# ----------------------------------------------------------------------
def poisson_pmf(k: int, lam: float) -> float:
    """Probabilidade de exatamente k gols dado o número esperado lam."""
    return exp(-lam) * lam**k / factorial(k)


def matriz_placar(lam_casa: float, lam_fora: float, max_gols: int = 10) -> list[list[float]]:
    """Matriz P[i][j] = probabilidade de placar i (casa) x j (fora)."""
    return [[poisson_pmf(i, lam_casa) * poisson_pmf(j, lam_fora)
             for j in range(max_gols + 1)] for i in range(max_gols + 1)]


# ----------------------------------------------------------------------
# 2) Ajuste Dixon-Coles (1997) para placares baixos
# ----------------------------------------------------------------------
def _tau(i: int, j: int, lam: float, mu: float, rho: float) -> float:
    """Fator de correção de dependência para os quatro placares baixos."""
    if i == 0 and j == 0:
        return 1 - lam * mu * rho
    if i == 0 and j == 1:
        return 1 + lam * rho
    if i == 1 and j == 0:
        return 1 + mu * rho
    if i == 1 and j == 1:
        return 1 - rho
    return 1.0


def matriz_placar_dc(lam_casa: float, lam_fora: float,
                     rho: float = -0.13, max_gols: int = 10) -> list[list[float]]:
    """
    Matriz de placar com correção Dixon-Coles. rho negativo (~-0.13 típico)
    aumenta levemente a massa em empates baixos e 1x0/0x1, corrigindo a
    subestimação que o Poisson puro faz nesses placares.
    """
    base = matriz_placar(lam_casa, lam_fora, max_gols)
    for i in (0, 1):
        for j in (0, 1):
            base[i][j] *= _tau(i, j, lam_casa, lam_fora, rho)
    s = sum(sum(linha) for linha in base)
    return [[v / s for v in linha] for linha in base]  # renormaliza


def probs_1x2(matriz: list[list[float]]) -> dict[str, float]:
    """Converte a matriz de placar em P(casa), P(empate), P(fora)."""
    casa = empate = fora = 0.0
    for i, linha in enumerate(matriz):
        for j, p in enumerate(linha):
            if i > j:
                casa += p
            elif i == j:
                empate += p
            else:
                fora += p
    return {"casa": casa, "empate": empate, "fora": fora}


def placar_mais_provavel(matriz: list[list[float]], top: int = 5) -> list[tuple[str, float]]:
    """Top-N placares exatos mais prováveis."""
    chances = []
    for i, linha in enumerate(matriz):
        for j, p in enumerate(linha):
            chances.append((f"{i}-{j}", p))
    chances.sort(key=lambda x: x[1], reverse=True)
    return chances[:top]


# ----------------------------------------------------------------------
# 3) Rating Elo
# ----------------------------------------------------------------------
@dataclass
class Elo:
    ratings: dict[str, float] = field(default_factory=dict)
    base: float = 1500.0
    k: float = 32.0

    def get(self, time: str) -> float:
        return self.ratings.get(time, self.base)

    def esperado(self, a: str, b: str, mando: float = 100.0) -> float:
        """Probabilidade esperada de A vencer B (mando = vantagem de jogar em casa)."""
        ra, rb = self.get(a) + mando, self.get(b)
        return 1 / (1 + 10 ** ((rb - ra) / 400))

    def atualizar(self, a: str, b: str, placar_a: int, placar_b: int, mando: float = 100.0):
        """Atualiza ratings após uma partida (1 vitória A, 0.5 empate, 0 derrota)."""
        esp = self.esperado(a, b, mando)
        real = 1.0 if placar_a > placar_b else 0.5 if placar_a == placar_b else 0.0
        # margem de gols amplifica o ajuste (multiplicador clássico)
        margem = abs(placar_a - placar_b)
        mult = 1.0 if margem <= 1 else (1.5 if margem == 2 else (1.75 + (margem - 3) / 8))
        delta = self.k * mult * (real - esp)
        self.ratings[a] = self.get(a) + delta
        self.ratings[b] = self.get(b) - delta

    def lambdas_estimados(self, a: str, b: str, media_gols_liga: float = 2.6,
                          mando: float = 100.0) -> tuple[float, float]:
        """
        Converte diferença de Elo em gols esperados (lambdas) para alimentar
        o Poisson/Dixon-Coles. Heurística: divide a média de gols da liga
        entre os times proporcionalmente à força relativa.
        """
        p_a = self.esperado(a, b, mando)
        lam_a = media_gols_liga * p_a
        lam_b = media_gols_liga * (1 - p_a)
        return lam_a, lam_b


# ----------------------------------------------------------------------
# 4) Odds -> probabilidade implícita (removendo a margem da casa)
# ----------------------------------------------------------------------
def implied_probs(odds: Sequence[float]) -> list[float]:
    """
    Converte odds decimais em probabilidades implícitas normalizadas.
    A soma bruta de 1/odd passa de 100% (esse excesso é o 'vig'/overround,
    a margem da casa). Dividimos pela soma para remover a margem.
    """
    invs = [1 / o for o in odds]
    s = sum(invs)
    return [v / s for v in invs]


def overround(odds: Sequence[float]) -> float:
    """Margem embutida da casa (quanto a soma das probs passa de 1)."""
    return sum(1 / o for o in odds) - 1.0


def value_bet(prob_modelo: float, odd_oferecida: float) -> dict:
    """
    Detecta aposta de valor: se sua probabilidade estimada > probabilidade
    implícita na odd, o valor esperado é positivo. EV por R$1 apostado =
    prob_modelo * odd - 1.
    """
    ev = prob_modelo * odd_oferecida - 1
    return {
        "prob_modelo": prob_modelo,
        "prob_implicita": 1 / odd_oferecida,
        "ev_por_real": ev,
        "tem_valor": ev > 0,
    }


# ----------------------------------------------------------------------
# 5) Monte Carlo de mata-mata (chaveamento de Copa)
# ----------------------------------------------------------------------
def simular_confronto(elo: Elo, a: str, b: str, mando: float = 0.0) -> str:
    """Simula um jogo único de mata-mata (sem mando em Copa neutra)."""
    p_a = elo.esperado(a, b, mando)
    # empate no tempo normal -> decisão por pênaltis ~ moeda levemente
    # enviesada pela força; simplificação: usa p_a direto como prob de A passar.
    return a if random.random() < p_a else b


def simular_chaveamento(elo: Elo, bracket: list[str], n: int = 10000,
                        mando: float = 0.0) -> dict[str, float]:
    """
    `bracket`: lista de times em ordem de chaveamento (potência de 2:
    8, 16, 32...). Roda n simulações e retorna a probabilidade de cada time
    ser campeão. Monte Carlo: a lei dos grandes números faz a frequência
    convergir para a probabilidade real do modelo.
    """
    if len(bracket) & (len(bracket) - 1) != 0:
        raise ValueError("O número de times deve ser potência de 2 (8, 16, 32...).")
    titulos: dict[str, int] = {t: 0 for t in bracket}
    for _ in range(n):
        vivos = list(bracket)
        while len(vivos) > 1:
            prox = []
            for i in range(0, len(vivos), 2):
                prox.append(simular_confronto(elo, vivos[i], vivos[i + 1], mando))
            vivos = prox
        titulos[vivos[0]] += 1
    return {t: c / n for t, c in sorted(titulos.items(), key=lambda x: -x[1])}
