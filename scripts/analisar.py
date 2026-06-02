#!/usr/bin/env python3
"""
analisar.py — CLI único da skill. O agente (OpenClaw / Claude Code / Codex)
chama este arquivo. Tudo sai em JSON para ser fácil de ler e repassar.

Exemplos:
  python analisar.py loteria-prob megasena
  python analisar.py loteria-prob megasena --marcadas 8
  python analisar.py loteria-ultimo megasena
  python analisar.py loteria-ve megasena --marcadas 7 --premios "6:50000000,5:50000,4:1000"
  python analisar.py fechamento --pool "1,5,12,23,33,42,51,60" --jogo 6 --garantia 4
  python analisar.py anti-popular megasena --jogos 3
  python analisar.py jogo-prob --casa-elo 1850 --fora-elo 1700
  python analisar.py odds-valor --odds "2.10,3.40,3.60" --prob-modelo "0.52,0.27,0.21"
  python analisar.py copa-monte-carlo --bracket "Brasil:2050,Franca:2010,..." -n 20000
"""

from __future__ import annotations
import argparse
import json
import sys

import loteria as L
import futebol as F
import dados as D
import modelo as M
import apifootball as AF


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_ve_auto(a):
    m = L.MODALIDADES[a.loteria]
    marcadas = a.marcadas or m.marcadas
    prem = D.premiacao_por_faixa(a.loteria)
    if "erro" in prem:
        _print(prem)
        return

    # Monta {acertos: premio} a partir da premiação real do concurso.
    premios = {}
    faixas = prem.get("faixas", {})
    for ac in range(m.acerta_para_premio, m.sorteadas + 1):
        info = faixas.get(ac)
        if info and info.get("premio") is not None:
            premios[ac] = info["premio"]
        elif ac == m.sorteadas:
            # faixa principal acumulou (premio '-'): usa o estimado do próximo concurso
            estimado = prem.get("acumulada_prox")
            if estimado:
                premios[ac] = estimado

    if not premios:
        _print({"erro": "Não foi possível obter prêmios desta fonte agora. "
                        "Use 'loteria-ve --premios' manualmente."})
        return

    ve = L.valor_esperado(a.loteria, marcadas, premios)
    _print({
        "modalidade": m.nome,
        "marcadas": marcadas,
        "concurso_referencia": prem.get("concurso"),
        "data": prem.get("data"),
        "acumulou_faixa_principal": prem.get("acumulou"),
        "premio_estimado_prox": prem.get("acumulada_prox_texto"),
        "premios_usados": premios,
        "fonte": prem.get("fonte"),
        **ve,
        "interpretacao": (
            "Prêmios buscados ao vivo do último concurso (a faixa principal usa o "
            "estimado do próximo se tiver acumulado). Valor esperado negativo = "
            "perda média no longo prazo, o que é normal em loterias. Confirme os "
            "valores no site oficial da Caixa antes de apostar."
        ),
    })


def _forma_from_kv(prefixo: str, a) -> M.FormaTime:
    """Monta FormaTime a partir de args --casa-* / --fora-*."""
    g = lambda s: getattr(a, f"{prefixo}_{s}")
    res = [float(x) for x in g("forma").split(",")] if g("forma") else []
    return M.FormaTime(
        nome=g("nome") or prefixo,
        gols_marcados=g("gm"), gols_sofridos=g("gs"),
        finalizacoes_certas=g("fin"), xg=g("xg"),
        resultados_recentes=res,
        cartoes_vermelhos=g("vermelhos"),
        peso_desfalques=g("desfalques"),
    )


def _confronto_saida(casa: M.FormaTime, fora: M.FormaTime, mando: float,
                     media_liga: float, rho: float, extra: dict | None = None):
    lam_c, lam_f = M.lambdas_confronto(casa, fora, media_liga, mando)
    matriz = F.matriz_placar_dc(lam_c, lam_f, rho=rho)
    probs = F.probs_1x2(matriz)
    probs = M.ajuste_risco_disciplina(probs, casa, fora)
    out = {
        "confronto": f"{casa.nome} x {fora.nome}",
        "lambda_casa": round(lam_c, 3),
        "lambda_fora": round(lam_f, 3),
        "fatores_aplicados": [
            "forca ataque/defesa", "forma recente (decaimento)",
            "desfalques", "mando", "ajuste fraco de disciplina",
        ],
        "resultado_1x2": {k: round(v, 4) for k, v in probs.items()},
        "ambos_marcam": round(sum(matriz[i][j] for i in range(1, len(matriz))
                                  for j in range(1, len(matriz[0]))), 4),
        "over_2_5": round(sum(matriz[i][j] for i in range(len(matriz))
                              for j in range(len(matriz[0])) if i + j >= 3), 4),
        "placares_provaveis": [(p, round(v, 4)) for p, v in F.placar_mais_provavel(matriz)],
        "aviso": "Distribuição de probabilidade, não previsão. Variância do futebol é alta; "
                 "cartões/expulsões/pênaltis são quase ruído em jogo único.",
    }
    if extra:
        out.update(extra)
    _print(out)


def cmd_copa_coverage(a):
    import datetime
    season = a.season or datetime.date.today().year
    r = AF.coverage_copa(season)
    if "erro" in r:
        _print(r); return
    resp = r.get("response", [])
    if not resp:
        _print({"erro": f"Copa (league=1) não encontrada para season={season}. "
                        "Confira o ano do torneio."}); return
    seasons = resp[0].get("seasons", [])
    atual = next((s for s in seasons if s.get("year") == season), seasons[-1] if seasons else {})
    _print({
        "competicao": resp[0].get("league", {}).get("name"),
        "season": season,
        "coverage": atual.get("coverage"),
        "quota_restante": r.get("_quota_remaining"),
        "nota": "Flag true = dado suportado, mas pode faltar jogo a jogo, "
                "sobretudo no início do torneio.",
    })


def cmd_copa_jogos(a):
    import datetime
    season = a.season or datetime.date.today().year
    r = AF.jogos_copa(season)
    if "erro" in r:
        _print(r); return
    jogos = []
    for j in r.get("response", []):
        fx = j.get("fixture", {}); tm = j.get("teams", {})
        jogos.append({
            "fixture_id": fx.get("id"),
            "data": fx.get("date"),
            "status": fx.get("status", {}).get("short"),
            "casa": tm.get("home", {}).get("name"),
            "fora": tm.get("away", {}).get("name"),
        })
    _print({"season": season, "total": len(jogos), "jogos": jogos,
            "quota_restante": r.get("_quota_remaining"),
            "dica": "Use o fixture_id em 'copa-confronto --fixture ID'."})


def cmd_copa_confronto(a):
    """
    Cruza a predição estatística da própria API-Football com o nosso modelo
    multifatorial, para o mesmo jogo. Concordância = mais confiança;
    divergência = cautela. Usa o bloco comparison/H2H da API e, se houver,
    as lesões reais para o fator de desfalques.
    """
    pred = AF.predicao_fixture(a.fixture)
    if "erro" in pred:
        _print(pred); return
    resp = pred.get("response", [])
    if not resp:
        _print({"erro": "Sem predição para este fixture (jogo distante ou sem cobertura)."}); return
    p = resp[0]
    percent = p.get("predictions", {}).get("percent", {})
    api_probs = {
        "casa": AF.parse_percent(percent.get("home")),
        "empate": AF.parse_percent(percent.get("draw")),
        "fora": AF.parse_percent(percent.get("away")),
    }
    comp = p.get("comparison", {})
    teams = p.get("teams", {})
    nome_casa = teams.get("home", {}).get("name", "Casa")
    nome_fora = teams.get("away", {}).get("name", "Fora")

    # Gols previstos pela API (quando presentes) alimentam nosso lambda como âncora
    goals = p.get("predictions", {}).get("goals", {})
    def _g(v):
        try: return abs(float(str(v).replace("-", "")))
        except (TypeError, ValueError): return None
    gca, gfa = _g(goals.get("home")), _g(goals.get("away"))

    # Monta FormaTime a partir do bloco comparison (força de ataque/defesa em %)
    def _frac(d, lado):
        return AF.parse_percent(d.get(lado)) if d else None
    atk_casa = _frac(comp.get("att", {}), "home")
    atk_fora = _frac(comp.get("att", {}), "away")

    casa = M.FormaTime(nome_casa,
                       gols_marcados=gca if gca else 1.3,
                       gols_sofridos=1.2)
    fora = M.FormaTime(nome_fora,
                       gols_marcados=gfa if gfa else 1.1,
                       gols_sofridos=1.3)
    # campo neutro na Copa -> mando 1.0
    lam_c, lam_f = M.lambdas_confronto(casa, fora, a.media_liga, mando=1.0)
    matriz = F.matriz_placar_dc(lam_c, lam_f, rho=a.rho)
    nosso = F.probs_1x2(matriz)

    # Concordância: distância entre as duas distribuições (quanto menor, melhor)
    div = None
    if all(v is not None for v in api_probs.values()):
        div = sum(abs(api_probs[k] - nosso[k]) for k in nosso) / 2  # distância L1/2 (0..1)

    _print({
        "confronto": f"{nome_casa} x {nome_fora}",
        "modelo_proprio_1x2": {k: round(v, 4) for k, v in nosso.items()},
        "api_football_1x2": {k: (round(v, 4) if v is not None else None) for k, v in api_probs.items()},
        "advice_api": p.get("predictions", {}).get("advice"),
        "under_over_api": p.get("predictions", {}).get("under_over"),
        "divergencia": round(div, 4) if div is not None else None,
        "leitura_divergencia": (
            None if div is None else
            "Forte concordância — mais confiança." if div < 0.10 else
            "Concordância moderada." if div < 0.20 else
            "Divergência relevante — trate com cautela, os modelos discordam."
        ),
        "comparison_api": comp,
        "quota_restante": pred.get("_quota_remaining"),
        "aviso": "Dois modelos estatísticos, não previsão. Em jogo único a variância manda.",
    })


def cmd_confronto(a):
    casa = _forma_from_kv("casa", a)
    fora = _forma_from_kv("fora", a)
    _confronto_saida(casa, fora, a.mando, a.media_liga, a.rho)


def cmd_penalti(a):
    if a.disputa:
        r = M.disputa_penaltis(a.conv_casa, a.conv_fora)
        _print({"prob_vencer_disputa": {k: round(v, 4) for k, v in r.items()},
                "aviso": "Simulação Monte Carlo; pênalti é alta variância."})
    else:
        p = M.prob_gol_penalti(a.conv_casa, a.def_goleiro)
        _print({"prob_gol_penalti": round(p, 4)})


def cmd_quota(a):
    _print(AF.quota())


def cmd_confronto_auto(a):
    """Monta o confronto automaticamente do API-Football. Gasta cota (~6-8 req)."""
    import datetime
    season = a.season or datetime.date.today().year
    t1 = AF.buscar_time(a.casa)
    t2 = AF.buscar_time(a.fora)
    for t, nome in ((t1, a.casa), (t2, a.fora)):
        if "erro" in t:
            _print(t); return
        if not t.get("response"):
            _print({"erro": f"Time '{nome}' não encontrado no API-Football."}); return
    id1 = t1["response"][0]["team"]["id"]
    id2 = t2["response"][0]["team"]["id"]
    nome1 = t1["response"][0]["team"]["name"]
    nome2 = t2["response"][0]["team"]["name"]

    def media_gols(fixtures_resp, team_id):
        jogos = fixtures_resp.get("response", [])
        gm = gs = 0; n = 0; res = []
        for j in jogos:
            g = j.get("goals", {})
            casa_id = j.get("teams", {}).get("home", {}).get("id")
            gc, gf = g.get("home"), g.get("away")
            if gc is None or gf is None:
                continue
            n += 1
            if casa_id == team_id:
                gm += gc; gs += gf
                res.append(1.0 if gc > gf else 0.5 if gc == gf else 0.0)
            else:
                gm += gf; gs += gc
                res.append(1.0 if gf > gc else 0.5 if gc == gf else 0.0)
        if n == 0:
            return None
        return {"gm": gm / n, "gs": gs / n, "res": res, "n": n}

    f1 = AF.ultimos_jogos(id1, 10); f2 = AF.ultimos_jogos(id2, 10)
    if "erro" in f1: _print(f1); return
    if "erro" in f2: _print(f2); return
    m1 = media_gols(f1, id1); m2 = media_gols(f2, id2)
    if not m1 or not m2:
        _print({"erro": "Cobertura insuficiente para estes times (API retornou poucos jogos). "
                        "Use o comando 'confronto' manual com os números que você tiver."})
        return

    casa = M.FormaTime(nome1, gols_marcados=m1["gm"], gols_sofridos=m1["gs"],
                       resultados_recentes=m1["res"])
    fora = M.FormaTime(nome2, gols_marcados=m2["gm"], gols_sofridos=m2["gs"],
                       resultados_recentes=m2["res"])
    _confronto_saida(casa, fora, a.mando, a.media_liga, a.rho, extra={
        "fonte": "API-Football (ultimos 10 jogos de cada)",
        "amostra": {nome1: m1["n"], nome2: m2["n"]},
        "quota_restante": f1.get("_quota_remaining"),
        "nota": "Auto usa só gols/forma. Para lesões, xG e disciplina, passe-os "
                "no comando 'confronto' manual (a cobertura gratuita desses é irregular).",
    })


def cmd_loteria_uniforme(a):
    hist = D.historico_loteria(a.loteria, a.limite)
    m = L.MODALIDADES[a.loteria]
    res = L.teste_uniformidade(hist, m.universo)
    res["modalidade"] = m.nome
    if a.frequencia:
        res["frequencia"] = L.frequencia_historica(hist)
    _print(res)


def cmd_loteria_conferir(a):
    jogo = [int(x) for x in a.jogo.split(",")]
    ult = D.ultimo_resultado_loteria(a.loteria)
    if "erro" in ult:
        _print(ult); return
    r = L.conferir_jogo(jogo, ult["dezenas"])
    r["concurso"] = ult.get("concurso")
    r["sorteado"] = ult["dezenas"]
    r["seu_jogo"] = sorted(jogo)
    _print(r)


def cmd_loteria_divisao(a):
    _print(L.prob_dividir_premio(a.loteria, a.apostas))


def cmd_loteria_prob(a):
    linhas = L.tabela_probabilidades(a.loteria, a.marcadas)
    m = L.MODALIDADES[a.loteria]
    _print({
        "modalidade": m.nome,
        "marcadas": a.marcadas or m.marcadas,
        "custo": L.custo_aposta(a.loteria, a.marcadas or m.marcadas),
        "faixas": linhas,
        "aviso": "Sorteios são independentes; nenhuma estratégia altera estas probabilidades.",
    })


def cmd_loteria_ultimo(a):
    _print(D.ultimo_resultado_loteria(a.loteria))


def cmd_loteria_ve(a):
    premios = {}
    for par in a.premios.split(","):
        ac, val = par.split(":")
        premios[int(ac)] = float(val)
    ve = L.valor_esperado(a.loteria, a.marcadas, premios)
    ve["interpretacao"] = (
        "Valor esperado negativo significa que, em média, a aposta perde "
        "dinheiro no longo prazo — normal em loterias."
    )
    _print(ve)


def cmd_fechamento(a):
    pool = [int(x) for x in a.pool.split(",")]
    jogos = L.fechamento_garantia(pool, a.jogo, a.garantia, a.max_jogos)
    _print({
        "pool": sorted(pool),
        "jogos_por_aposta": a.jogo,
        "garantia": f"{a.garantia} acertos SE {a.garantia}+ dezenas do pool saírem",
        "qtd_jogos": len(jogos),
        "jogos": [list(j) for j in jogos],
        "aviso": "Garantia condicional. NÃO aumenta a chance de o pool conter os sorteados.",
    })


def cmd_anti_popular(a):
    jogos = L.gerar_jogo_anti_popular(a.loteria, a.jogos, a.marcadas)
    _print({
        "jogos": jogos,
        "objetivo": "Reduzir a chance de dividir o prêmio (evita datas <=31).",
        "aviso": "NÃO aumenta a probabilidade de ganhar.",
    })


def cmd_jogo_prob(a):
    elo = F.Elo(ratings={"_casa": a.casa_elo, "_fora": a.fora_elo})
    lam_c, lam_f = elo.lambdas_estimados("_casa", "_fora",
                                         media_gols_liga=a.media_gols, mando=a.mando)
    matriz = F.matriz_placar_dc(lam_c, lam_f, rho=a.rho)
    _print({
        "lambda_casa": round(lam_c, 3),
        "lambda_fora": round(lam_f, 3),
        "resultado_1x2": {k: round(v, 4) for k, v in F.probs_1x2(matriz).items()},
        "placares_provaveis": [(p, round(v, 4)) for p, v in F.placar_mais_provavel(matriz)],
        "aviso": "Distribuição de probabilidade, não previsão. Modelos erram com frequência.",
    })


def cmd_odds_valor(a):
    odds = [float(x) for x in a.odds.split(",")]
    impl = F.implied_probs(odds)
    out = {"overround_casa": round(F.overround(odds), 4), "mercados": []}
    if a.prob_modelo:
        modelo = [float(x) for x in a.prob_modelo.split(",")]
        for i, (o, pm) in enumerate(zip(odds, modelo)):
            vb = F.value_bet(pm, o)
            vb["odd"] = o
            vb["prob_implicita_sem_vig"] = round(impl[i], 4)
            out["mercados"].append({k: (round(v, 4) if isinstance(v, float) else v)
                                    for k, v in vb.items()})
    else:
        out["prob_implicita_sem_vig"] = [round(p, 4) for p in impl]
    _print(out)


def cmd_copa(a):
    elo = F.Elo()
    bracket = []
    for item in a.bracket.split(","):
        nome, rating = item.split(":")
        elo.ratings[nome] = float(rating)
        bracket.append(nome)
    probs = F.simular_chaveamento(elo, bracket, n=a.n, mando=0.0)
    _print({
        "simulacoes": a.n,
        "prob_titulo": {k: round(v, 4) for k, v in probs.items()},
        "aviso": "Monte Carlo sobre ratings Elo; sensível aos ratings de entrada.",
    })


def main():
    p = argparse.ArgumentParser(description="Análise matemática de loterias e futebol.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("loteria-prob"); sp.add_argument("loteria"); sp.add_argument("--marcadas", type=int); sp.set_defaults(fn=cmd_loteria_prob)
    sp = sub.add_parser("loteria-ultimo"); sp.add_argument("loteria"); sp.set_defaults(fn=cmd_loteria_ultimo)
    sp = sub.add_parser("loteria-ve"); sp.add_argument("loteria"); sp.add_argument("--marcadas", type=int, required=True); sp.add_argument("--premios", required=True); sp.set_defaults(fn=cmd_loteria_ve)
    sp = sub.add_parser("loteria-ve-auto"); sp.add_argument("loteria"); sp.add_argument("--marcadas", type=int); sp.set_defaults(fn=cmd_ve_auto)
    sp = sub.add_parser("fechamento"); sp.add_argument("--pool", required=True); sp.add_argument("--jogo", type=int, required=True); sp.add_argument("--garantia", type=int, required=True); sp.add_argument("--max-jogos", type=int, default=200); sp.set_defaults(fn=cmd_fechamento)
    sp = sub.add_parser("anti-popular"); sp.add_argument("loteria"); sp.add_argument("--jogos", type=int, default=1); sp.add_argument("--marcadas", type=int); sp.set_defaults(fn=cmd_anti_popular)
    sp = sub.add_parser("loteria-uniforme"); sp.add_argument("loteria"); sp.add_argument("--limite", type=int, default=None); sp.add_argument("--frequencia", action="store_true"); sp.set_defaults(fn=cmd_loteria_uniforme)
    sp = sub.add_parser("loteria-conferir"); sp.add_argument("loteria"); sp.add_argument("--jogo", required=True, help="ex: 1,5,12,23,33,42"); sp.set_defaults(fn=cmd_loteria_conferir)
    sp = sub.add_parser("loteria-divisao"); sp.add_argument("loteria"); sp.add_argument("--apostas", type=float, default=None); sp.set_defaults(fn=cmd_loteria_divisao)
    sp = sub.add_parser("jogo-prob"); sp.add_argument("--casa-elo", type=float, required=True); sp.add_argument("--fora-elo", type=float, required=True); sp.add_argument("--media-gols", type=float, default=2.6); sp.add_argument("--mando", type=float, default=100.0); sp.add_argument("--rho", type=float, default=-0.13); sp.set_defaults(fn=cmd_jogo_prob)
    sp = sub.add_parser("odds-valor"); sp.add_argument("--odds", required=True); sp.add_argument("--prob-modelo"); sp.set_defaults(fn=cmd_odds_valor)
    sp = sub.add_parser("copa-monte-carlo"); sp.add_argument("--bracket", required=True); sp.add_argument("-n", type=int, default=10000); sp.set_defaults(fn=cmd_copa)

    # --- Confronto multifatorial (manual) ---
    sp = sub.add_parser("confronto")
    for lado in ("casa", "fora"):
        sp.add_argument(f"--{lado}-nome", default=None)
        sp.add_argument(f"--{lado}-gm", type=float, default=1.3, help="gols marcados/jogo")
        sp.add_argument(f"--{lado}-gs", type=float, default=1.3, help="gols sofridos/jogo")
        sp.add_argument(f"--{lado}-fin", type=float, default=None, help="finalizacoes certas/jogo")
        sp.add_argument(f"--{lado}-xg", type=float, default=None, help="xG/jogo (se tiver)")
        sp.add_argument(f"--{lado}-forma", default=None, help="ex: 1,0.5,1,0,1 (recente->antigo)")
        sp.add_argument(f"--{lado}-vermelhos", type=float, default=0.08, help="vermelhos/jogo")
        sp.add_argument(f"--{lado}-desfalques", type=float, default=0.0, help="peso 0..0.5 dos ausentes")
    sp.add_argument("--mando", type=float, default=1.12); sp.add_argument("--media-liga", type=float, default=1.35); sp.add_argument("--rho", type=float, default=-0.13)
    sp.set_defaults(fn=cmd_confronto)

    # --- Confronto automático (API-Football) ---
    sp = sub.add_parser("confronto-auto")
    sp.add_argument("casa"); sp.add_argument("fora")
    sp.add_argument("--season", type=int, default=None)
    sp.add_argument("--mando", type=float, default=1.12); sp.add_argument("--media-liga", type=float, default=1.35); sp.add_argument("--rho", type=float, default=-0.13)
    sp.set_defaults(fn=cmd_confronto_auto)

    # --- Pênaltis ---
    sp = sub.add_parser("penalti")
    sp.add_argument("--conv-casa", type=float, default=None); sp.add_argument("--conv-fora", type=float, default=None)
    sp.add_argument("--def-goleiro", type=float, default=None); sp.add_argument("--disputa", action="store_true")
    sp.set_defaults(fn=cmd_penalti)

    # --- Cota da API ---
    sp = sub.add_parser("quota"); sp.set_defaults(fn=cmd_quota)

    # --- Copa do Mundo (API-Football, league=1) ---
    sp = sub.add_parser("copa-coverage"); sp.add_argument("--season", type=int, default=None); sp.set_defaults(fn=cmd_copa_coverage)
    sp = sub.add_parser("copa-jogos"); sp.add_argument("--season", type=int, default=None); sp.set_defaults(fn=cmd_copa_jogos)
    sp = sub.add_parser("copa-confronto"); sp.add_argument("--fixture", type=int, required=True); sp.add_argument("--media-liga", type=float, default=1.35); sp.add_argument("--rho", type=float, default=-0.13); sp.set_defaults(fn=cmd_copa_confronto)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
