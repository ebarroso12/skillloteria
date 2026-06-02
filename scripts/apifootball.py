#!/usr/bin/env python3
"""
apifootball.py — Cliente do API-Football (api-sports.io) com CACHE AGRESSIVO.

Por que cache: o plano gratuito dá apenas 100 requisições/dia, zeradas à
00:00 UTC. Sem cache, uma única análise de confronto (escalação + eventos +
estatísticas + histórico dos dois times) já queima 6–10 requisições. O cache
guarda em disco tudo que foi buscado, com validade configurável, para não
desperdiçar a cota.

Honestidade de dados:
- O endpoint /status NÃO conta na cota; usamos para checar quota restante.
- Cobertura é desigual: respostas podem vir com results=0 (array vazio) sem
  erro. As funções retornam o que veio e sinalizam ausência, nunca inventam.
- xG é inconsistente no API-Football; o modelo trata como opcional.

Requer API_FOOTBALL_KEY no ambiente.
"""

from __future__ import annotations
import json
import os
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

BASE = "https://v3.football.api-sports.io"
CACHE_DIR = Path(os.environ.get("API_FOOTBALL_CACHE", str(Path.home() / ".cache" / "loto-copa")))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Validade padrão do cache por tipo de dado (segundos).
TTL = {
    "fixtures": 3600,        # jogos do dia mudam pouco
    "lineups": 1800,         # escalação confirma ~1h antes
    "events": 600,           # eventos ao vivo
    "statistics": 600,
    "teams": 7 * 86400,      # metadados quase estáticos
    "injuries": 6 * 3600,    # lesões
    "standings": 6 * 3600,
    "default": 3600,
}


def _key() -> str | None:
    return os.environ.get("API_FOOTBALL_KEY")


def _cache_path(endpoint: str, params: dict) -> Path:
    raw = endpoint + json.dumps(params, sort_keys=True)
    h = hashlib.sha256(raw.encode()).hexdigest()[:24]
    safe = endpoint.replace("/", "_")
    return CACHE_DIR / f"{safe}_{h}.json"


def _ttl_for(endpoint: str) -> int:
    for k, v in TTL.items():
        if k in endpoint:
            return v
    return TTL["default"]


def _read_cache(path: Path, ttl: int) -> dict | None:
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > ttl:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def get(endpoint: str, params: dict | None = None, force: bool = False) -> dict:
    """
    Chama um endpoint do API-Football, servindo do cache quando válido.
    Retorna o JSON cru da API ({get, parameters, errors, results, response}).
    Em erro de rede/quota, devolve dict com 'erro' em vez de lançar exceção.
    """
    params = params or {}
    key = _key()
    if not key:
        return {"erro": "API_FOOTBALL_KEY ausente. Crie uma chave gratuita em "
                        "dashboard.api-football.com e configure no ambiente/skills.entries."}

    path = _cache_path(endpoint, params)
    if not force:
        cached = _read_cache(path, _ttl_for(endpoint))
        if cached is not None:
            cached["_cache"] = "hit"
            return cached

    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}/{endpoint}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(url, headers={
        "x-apisports-key": key,
        "User-Agent": "loto-copa-analytics/1.1",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
            # remaining vem no header; anexa para o usuário monitorar a cota
            data["_quota_remaining"] = r.headers.get("x-ratelimit-requests-remaining")
            data["_cache"] = "miss"
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return {"erro": "Limite de requisições atingido (429). Cota diária esgotada "
                            "ou rajada rápida demais. Tente após 00:00 UTC."}
        return {"erro": f"HTTP {e.code} no API-Football."}
    except Exception as e:  # noqa: BLE001
        return {"erro": f"Falha de rede no API-Football: {e}"}

    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def quota() -> dict:
    """Consulta a cota restante. O endpoint /status NÃO conta na cota diária."""
    key = _key()
    if not key:
        return {"erro": "API_FOOTBALL_KEY ausente."}
    try:
        req = urllib.request.Request(f"{BASE}/status",
                                     headers={"x-apisports-key": key})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode("utf-8"))
        reqs = d.get("response", {}).get("requests", {})
        return {"usadas_hoje": reqs.get("current"), "limite_dia": reqs.get("limit_day")}
    except Exception as e:  # noqa: BLE001
        return {"erro": f"Falha ao consultar status: {e}"}


# ----------------------------------------------------------------------
# Helpers de alto nível — cada um é uma requisição (cuidado com a cota)
# ----------------------------------------------------------------------
def buscar_time(nome: str) -> dict:
    """Resolve nome -> id do time (1 requisição; cacheado por 7 dias)."""
    return get("teams", {"search": nome})


def ultimos_jogos(team_id: int, n: int = 10) -> dict:
    return get("fixtures", {"team": team_id, "last": n})


def jogos_entre(team1_id: int, team2_id: int, n: int = 10) -> dict:
    """Head-to-head: histórico de confrontos diretos."""
    return get("fixtures/headtohead", {"h2h": f"{team1_id}-{team2_id}", "last": n})


def estatisticas_fixture(fixture_id: int) -> dict:
    return get("fixtures/statistics", {"fixture": fixture_id})


def eventos_fixture(fixture_id: int) -> dict:
    return get("fixtures/events", {"fixture": fixture_id})


def escalacao_fixture(fixture_id: int) -> dict:
    return get("fixtures/lineups", {"fixture": fixture_id})


def lesoes(team_id: int, season: int) -> dict:
    return get("injuries", {"team": team_id, "season": season})


# ----------------------------------------------------------------------
# Endpoints focados na Copa do Mundo
# ----------------------------------------------------------------------
# No API-Football a Copa do Mundo é league=1. A temporada do torneio é o ano.
COPA_LEAGUE_ID = 1


def predicao_fixture(fixture_id: int) -> dict:
    """
    Predição estatística da PRÓPRIA API para um jogo (1 requisição).
    Traz percent (casa/empate/fora), advice, under/over, gols previstos e
    bloco comparison (ataque, defesa, Poisson, H2H). Calculada com 6
    algoritmos, atualizada de hora em hora. NÃO é odd de casa de aposta.
    """
    return get("predictions", {"fixture": fixture_id})


def coverage_copa(season: int) -> dict:
    """
    Quais dados existem para a Copa nesta temporada (events, lineups,
    statistics, injuries, predictions, odds...). Evita gastar requisições
    tentando dados que a competição não cobre. 1 requisição.
    """
    return get("leagues", {"id": COPA_LEAGUE_ID, "season": season})


def jogos_copa(season: int) -> dict:
    """Todos os jogos da Copa na temporada (1 requisição; cacheado 1h)."""
    return get("fixtures", {"league": COPA_LEAGUE_ID, "season": season})


def proximo_jogo_time_copa(team_id: int, season: int) -> dict:
    """Próximo jogo agendado de um time na Copa."""
    return get("fixtures", {"league": COPA_LEAGUE_ID, "season": season,
                            "team": team_id, "next": 1})


def parse_percent(valor) -> float | None:
    """Converte '45%' (ou 45 ou 0.45) em fração 0..1."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return valor / 100 if valor > 1 else float(valor)
    s = str(valor).strip().replace("%", "")
    try:
        v = float(s)
        return v / 100 if v > 1 else v
    except ValueError:
        return None
