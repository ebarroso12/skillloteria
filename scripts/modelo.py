#!/usr/bin/env python3
"""
modelo.py — Modelo multifatorial de confronto, construído sobre futebol.py.

Refina a estimativa dos gols esperados (lambdas) combinando vários sinais,
cada um com peso e justificativa estatística explícita. A saída final ainda
passa pelo Poisson/Dixon-Coles de futebol.py para virar probabilidades de
resultado e placar.

HONESTIDADE SOBRE CADA FATOR (peso reflete o poder preditivo real):
  ALTO sinal em jogo único:
    - Força ofensiva/defensiva (gols marcados/sofridos ajustados)
    - Forma recente com decaimento temporal
    - Mando de campo
    - Desfalques de titulares-chave (lesão/suspensão)
  MÉDIO sinal:
    - Finalizações certas (proxy de xG quando xG não vem)
    - Head-to-head (pequena amostra; estilo de confronto)
  BAIXO sinal / quase-ruído em jogo único (NÃO inflar):
    - Cartões, expulsões, "descontrole": afetam o jogo mas são raros e
      mal previsíveis. Entram só como leve ajuste de risco, nunca como
      preditor forte.
    - Conversão de pênaltis: relevante só SE houver pênalti; modelado à parte.

Estilo de dados: cada função recebe dicionários simples (já extraídos da API
ou montados à mão). Se um fator faltar, o modelo o ignora e segue com os
demais — degrada com elegância, não inventa.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from math import exp


# ----------------------------------------------------------------------
# Estrutura de entrada de um time
# ----------------------------------------------------------------------
@dataclass
class FormaTime:
    nome: str
    # médias por jogo (do período recente analisado):
    gols_marcados: float = 1.3
    gols_sofridos: float = 1.3
    finalizacoes_certas: float | None = None   # proxy de xG se xG ausente
    xg: float | None = None                    # opcional; usado se presente
    # forma recente: lista de resultados mais recentes -> antigos (1 vit, 0.5 emp, 0 der)
    resultados_recentes: list[float] = field(default_factory=list)
    # disciplina (médias por jogo) — sinal fraco, usado só como ajuste de risco
    cartoes_amarelos: float = 2.0
    cartoes_vermelhos: float = 0.08
    # desfalques: peso somado dos titulares ausentes (0..1 cada; ver abaixo)
    peso_desfalques: float = 0.0
    elo: float | None = None


# ----------------------------------------------------------------------
# Componentes do modelo
# ----------------------------------------------------------------------
def fator_forma(resultados: list[float], meia_vida: float = 5.0) -> float:
    """
    Forma recente com DECAIMENTO EXPONENCIAL: jogos mais recentes pesam mais.
    Retorna um multiplicador em torno de 1.0 (acima = boa fase).

    meia_vida = nº de jogos para o peso cair pela metade. A média ponderada
    fica em [0,1]; converto para multiplicador suave [~0.85, ~1.15].
    """
    if not resultados:
        return 1.0
    pesos = [exp(-i / meia_vida) for i in range(len(resultados))]
    media = sum(r * w for r, w in zip(resultados, pesos)) / sum(pesos)
    # 0.5 (forma neutra) -> 1.0; bom desvio de ±0.3 vira ±~0.15
    return 1.0 + (media - 0.5) * 0.6


def ataque_defesa_lambda(atk: FormaTime, dfd: FormaTime,
                         media_liga: float = 1.35) -> float:
    """
    Gols esperados do time `atk` contra `dfd`, no modelo clássico de força
    relativa (Maher/Dixon-Coles):
      lambda = media_liga * forca_ataque(atk) * forca_defesa(dfd)
    onde forca_ataque = gols_marcados/media_liga e
          forca_defesa = gols_sofridos/media_liga.

    Se houver xG (ou finalizações certas), faz uma média com os gols para
    estabilizar a estimativa (xG é menos ruidoso que gols brutos).
    """
    base_atk = atk.gols_marcados
    sinal = atk.xg if atk.xg is not None else (
        atk.finalizacoes_certas * 0.33 if atk.finalizacoes_certas is not None else None)
    if sinal is not None:
        base_atk = 0.6 * sinal + 0.4 * atk.gols_marcados  # xG pesa mais (menos ruído)

    forca_atk = base_atk / media_liga
    forca_def = dfd.gols_sofridos / media_liga
    return media_liga * forca_atk * forca_def


def ajuste_desfalques(lam: float, peso_desfalques: float) -> float:
    """
    Reduz os gols esperados conforme a importância dos ausentes.
    `peso_desfalques` é a soma das importâncias (0..1) dos titulares fora;
    cap em 0.5 para não zerar o ataque. Ex.: artilheiro fora ~0.25.
    """
    fator = max(0.55, 1.0 - min(peso_desfalques, 0.5))
    return lam * fator


def ajuste_risco_disciplina(probs: dict[str, float], casa: FormaTime,
                            fora: FormaTime) -> dict[str, float]:
    """
    Ajuste FRACO de risco por indisciplina. Um time com expulsões muito acima
    da média tem leve aumento na chance de não-vitória (jogar com 10 piora o
    resultado esperado). O efeito é propositalmente pequeno: expulsão é rara
    e mal previsível em jogo único — tratar como preditor forte seria desonesto.
    """
    # diferença de propensão a vermelho (média liga ~0.08/jogo)
    extra_casa = max(0.0, casa.cartoes_vermelhos - 0.08)
    extra_fora = max(0.0, fora.cartoes_vermelhos - 0.08)
    # cada 0.1 de vermelho extra desloca ~1.5% de prob da vitória para empate/derrota
    desloc = (extra_casa - extra_fora) * 0.15
    p = dict(probs)
    transf = max(-0.04, min(0.04, desloc))  # cap rígido em ±4 pontos percentuais
    p["casa"] = max(0.0, p["casa"] - transf)
    p["fora"] = max(0.0, p["fora"] + transf * 0.6)
    p["empate"] = max(0.0, 1.0 - p["casa"] - p["fora"])
    s = sum(p.values())
    return {k: v / s for k, v in p.items()}


def lambdas_confronto(casa: FormaTime, fora: FormaTime,
                      media_liga: float = 1.35, mando: float = 1.12) -> tuple[float, float]:
    """
    Combina todos os fatores de ataque/defesa, forma e desfalques nos dois
    lambdas finais (gols esperados casa e fora). `mando` é o multiplicador de
    vantagem de jogar em casa (~1.12 típico; use 1.0 em campo neutro/Copa).
    """
    lam_casa = ataque_defesa_lambda(casa, fora, media_liga)
    lam_fora = ataque_defesa_lambda(fora, casa, media_liga)

    lam_casa *= fator_forma(casa.resultados_recentes)
    lam_fora *= fator_forma(fora.resultados_recentes)

    lam_casa = ajuste_desfalques(lam_casa, casa.peso_desfalques)
    lam_fora = ajuste_desfalques(lam_fora, fora.peso_desfalques)

    lam_casa *= mando
    lam_fora /= mando ** 0.5  # mando ajuda o mandante e atrapalha um pouco o visitante

    # piso para evitar lambdas absurdamente baixos
    return max(0.15, lam_casa), max(0.15, lam_fora)


# ----------------------------------------------------------------------
# Módulo de pênaltis — separado, porque só importa SE houver pênalti
# ----------------------------------------------------------------------
def prob_gol_penalti(conversao_batedor: float | None = None,
                     defesa_goleiro: float | None = None,
                     media_liga: float = 0.78) -> float:
    """
    Probabilidade de um pênalti virar gol. Média histórica ~0.75–0.79.
    Combina taxa de conversão do batedor e taxa de defesa do goleiro, se
    fornecidas; senão usa a média da liga. Modelo log-odds simples.
    """
    if conversao_batedor is None and defesa_goleiro is None:
        return media_liga
    c = conversao_batedor if conversao_batedor is not None else media_liga
    g = defesa_goleiro if defesa_goleiro is not None else (1 - media_liga)
    # média geométrica entre "bateu bem" e "goleiro não defende"
    return max(0.5, min(0.95, (c + (1 - g)) / 2))


def disputa_penaltis(p_casa: float = 0.78, p_fora: float = 0.78,
                     simulacoes: int = 20000) -> dict[str, float]:
    """
    Simula uma disputa de pênaltis (5 cobranças + alternadas na morte súbita),
    dada a prob de conversão de cada lado. Útil para mata-mata. Monte Carlo.
    """
    import random
    vit_casa = 0
    for _ in range(simulacoes):
        gc = gf = 0
        # 5 cobranças cada
        for _ in range(5):
            gc += random.random() < p_casa
            gf += random.random() < p_fora
        # morte súbita
        while gc == gf:
            a = random.random() < p_casa
            b = random.random() < p_fora
            gc += a; gf += b
            if a != b:
                break
        if gc > gf:
            vit_casa += 1
    pc = vit_casa / simulacoes
    return {"casa": pc, "fora": 1 - pc}
