#!/usr/bin/env python3
"""
dados.py — Busca de dados AO VIVO, com fallback automático entre fontes.

LOTERIAS (sem chave de API):
  Primária : raw.githubusercontent.com/guilhermeasn/loteria.json
             (atualizado diariamente por GitHub Actions; muito estável)
  Fallback : loteriascaixa-api.herokuapp.com/api/<loteria>/latest

FUTEBOL (requer chave gratuita):
  football-data.org — defina FOOTBALL_DATA_TOKEN no ambiente.
  Sem token, as funções de futebol retornam erro explicativo em vez de
  inventar números.

Nenhuma fonte é oficial da Caixa/FIFA; são projetos comunitários. A skill
sempre informa a data do último concurso para o usuário conferir no site
oficial antes de apostar.
"""

from __future__ import annotations
import json
import os
import urllib.request
import urllib.error

TIMEOUT = 20
UA = {"User-Agent": "loto-copa-analytics/1.0 (+openclaw skill)"}

GITHUB_BASE = "https://raw.githubusercontent.com/guilhermeasn/loteria.json/master/data"
HEROKU_BASE = "https://loteriascaixa-api.herokuapp.com/api"
FOOTBALL_BASE = "https://api.football-data.org/v4"


def _get(url: str, headers: dict | None = None) -> dict | list:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


# ----------------------------------------------------------------------
# Loterias
# ----------------------------------------------------------------------
def ultimo_resultado_loteria(loteria: str) -> dict:
    """
    Retorna o resultado mais recente normalizado:
      {fonte, concurso, data, dezenas:[int], bruto:{...}}
    Tenta Heroku (já vem 'latest'); se falhar, usa o JSON do GitHub.
    """
    # Fonte 1: Heroku (entrega direto o último concurso)
    try:
        d = _get(f"{HEROKU_BASE}/{loteria}/latest")
        dezenas = [int(x) for x in d.get("dezenas", [])]
        return {
            "fonte": "loteriascaixa-api (heroku)",
            "concurso": d.get("concurso"),
            "data": d.get("data"),
            "dezenas": sorted(dezenas),
            "bruto": d,
        }
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        pass

    # Fonte 2: GitHub raw (dicionário {concurso: [dezenas...]})
    try:
        d = _get(f"{GITHUB_BASE}/{loteria}.json")
        ultimo = max(d.keys(), key=lambda k: int(k))
        return {
            "fonte": "guilhermeasn/loteria.json (github)",
            "concurso": int(ultimo),
            "data": None,
            "dezenas": sorted(int(x) for x in d[ultimo]),
            "bruto": {ultimo: d[ultimo]},
        }
    except Exception as e:  # noqa: BLE001 — última linha de defesa
        return {"erro": f"Nenhuma fonte de loteria respondeu: {e}"}


def _num(valor) -> float | None:
    """
    Converte premio em string ('R$ 1.566.871,70' ou '782,84') ou número
    para float. Retorna None se não der (ex.: '-' quando ninguém acertou).
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip()
    if not s or s in ("-", "R$ -"):
        return None
    s = s.replace("R$", "").strip()
    # formato brasileiro: ponto de milhar, vírgula decimal
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def premiacao_por_faixa(loteria: str) -> dict:
    """
    Extrai o prêmio (R$) e nº de ganhadores de CADA faixa do último concurso,
    direto da fonte ao vivo. Mapeia 'acertos' -> {premio, ganhadores}.
    Só funciona com a API do Heroku (o JSON do GitHub não traz premiação);
    se ela não responder, retorna erro explicativo.

    Também devolve `acumulada_prox` (prêmio estimado do próximo concurso),
    útil para estimar o valor esperado quando a faixa principal acumulou.
    """
    try:
        d = _get(f"{HEROKU_BASE}/{loteria}/latest")
    except Exception as e:  # noqa: BLE001
        return {"erro": f"Fonte de premiação (Heroku) indisponível: {e}. "
                        "O valor esperado precisa dos prêmios; passe-os manualmente "
                        "via 'loteria-ve --premios' ou tente mais tarde."}

    faixas = {}
    for p in d.get("premiacoes", []):
        # nº de acertos pode vir como 'faixa' (1=maior) ou em 'descricao'/'acertos'
        desc = str(p.get("descricao") or p.get("acertos") or "")
        digitos = "".join(ch for ch in desc if ch.isdigit())
        acertos = int(digitos) if digitos else None
        premio = _num(p.get("valorPremio") if "valorPremio" in p else p.get("premio"))
        ganh = p.get("ganhadores", p.get("vencedores"))
        try:
            ganh = int(str(ganh).replace(".", "")) if ganh not in (None, "") else None
        except ValueError:
            ganh = None
        if acertos is not None:
            faixas[acertos] = {"premio": premio, "ganhadores": ganh, "descricao": desc}

    return {
        "fonte": "loteriascaixa-api (heroku)",
        "concurso": d.get("concurso"),
        "data": d.get("data"),
        "acumulou": d.get("acumulou"),
        "acumulada_prox": _num(d.get("acumuladaProxConcurso")),
        "acumulada_prox_texto": d.get("acumuladaProxConcurso"),
        "prox_concurso": d.get("proximoConcurso", d.get("proxConcurso")),
        "data_prox": d.get("dataProximoConcurso", d.get("dataProxConcurso")),
        "faixas": faixas,
    }


def historico_loteria(loteria: str, limite: int | None = None) -> list[list[int]]:
    """
    Histórico completo de sorteios (lista de listas de dezenas), do JSON do
    GitHub. Use só para estatística descritiva — NÃO para prever sorteios.
    """
    d = _get(f"{GITHUB_BASE}/{loteria}.json")
    concursos = sorted(d.keys(), key=lambda k: int(k))
    if limite:
        concursos = concursos[-limite:]
    return [[int(x) for x in d[c]] for c in concursos]


# ----------------------------------------------------------------------
# Futebol
# ----------------------------------------------------------------------
def _football_token() -> str | None:
    return os.environ.get("FOOTBALL_DATA_TOKEN")


def proximos_jogos(competicao: str = "WC") -> dict:
    """
    Próximos jogos de uma competição (WC = Copa do Mundo no football-data.org).
    Requer FOOTBALL_DATA_TOKEN. Sem token, retorna instrução clara.
    """
    token = _football_token()
    if not token:
        return {"erro": "Defina API_FOOTBALL_KEY ou FOOTBALL_DATA_TOKEN "
                        "no skills.entries para dados de futebol ao vivo."}
    try:
        return _get(f"{FOOTBALL_BASE}/competitions/{competicao}/matches?status=SCHEDULED",
                    headers={"X-Auth-Token": token})
    except Exception as e:  # noqa: BLE001
        return {"erro": f"Falha ao consultar football-data.org: {e}"}


def historico_confrontos(time_id: int, limite: int = 20) -> dict:
    """Últimas partidas de um time (para alimentar Elo / médias de gols)."""
    token = _football_token()
    if not token:
        return {"erro": "FOOTBALL_DATA_TOKEN ausente."}
    try:
        return _get(f"{FOOTBALL_BASE}/teams/{time_id}/matches?status=FINISHED&limit={limite}",
                    headers={"X-Auth-Token": token})
    except Exception as e:  # noqa: BLE001
        return {"erro": f"Falha: {e}"}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(ultimo_resultado_loteria(sys.argv[1]), ensure_ascii=False, indent=2))
