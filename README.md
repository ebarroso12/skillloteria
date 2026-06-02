# loto-copa-analytics 🎲⚽

Skill de **análise matemática honesta** para loterias da Caixa e futebol (incl. Copa do Mundo), com **dados ao vivo**. Formato AgentSkills — funciona em **OpenClaw**, **Claude Code** e **Codex** sem alteração.

## Resumo

Esta skill foi feita para responder perguntas quantitativas sobre loteria e futebol com foco em:
- probabilidade exata
- valor esperado
- fechamento/desdobramento
- jogos anti-divisão
- modelos estatísticos de futebol
- consulta de dados ao vivo quando houver fonte disponível

Ela **não** promete prever sorteios nem "quebrar a banca". O objetivo é orientar com matemática real e linguagem honesta.

Sem dependências externas: usa apenas a biblioteca padrão do Python 3 (`python3`). Isso é proposital — facilita a auditoria de segurança e evita falsos positivos em scanners de skills.

---

## O que ela faz (e o que não faz)

**Faz, e é matemática real:**
- Probabilidade exata de cada faixa de premiação (combinatória/hipergeométrica)
- Custo de apostas com mais dezenas e **valor esperado** vs. custo
- **Fechamentos/desdobramentos** (garantia condicional via cobertura de conjuntos)
- Jogos enviesados para **reduzir a chance de dividir o prêmio**
- Resultados **ao vivo** das loterias
- Futebol: Poisson + **Dixon-Coles**, **Elo**, **probabilidade implícita de odds** (remove a margem da casa), **value bets** e **Monte Carlo** de chaveamento

**Não faz, porque é impossível:**
- Prever números de loteria. Sorteios são independentes e sem memória. Qualquer "sistema" que prometa aumentar a chance de acerto é falso, e a skill diz isso ao usuário.

---

## Instalação

### OpenClaw
```bash
# Local (workspace atual)
openclaw skills install ./loto-copa-analytics --as loto-copa-analytics
# ou, se publicada no ClawHub:
openclaw skills install loto-copa-analytics
# Para futebol ao vivo, configure a chave em ~/.openclaw/openclaw.json:
#   skills.entries."loto-copa-analytics".env.FOOTBALL_DATA_TOKEN = "SUA_CHAVE"
openclaw skills verify loto-copa-analytics --card   # confere o Skill Card
```

### Claude Code
```bash
# copie a pasta para uma das raízes de skills do projeto ou pessoal:
cp -r loto-copa-analytics ~/.agents/skills/
# para futebol ao vivo:
export FOOTBALL_DATA_TOKEN="SUA_CHAVE"
```

### Codex (OpenAI)
```bash
cp -r loto-copa-analytics "$CODEX_HOME/skills/"   # normalmente ~/.codex/skills
export FOOTBALL_DATA_TOKEN="SUA_CHAVE"
```

A chave gratuita de futebol sai em https://www.football-data.org (plano free cobre a Copa do Mundo, competição `WC`).

---

## Uso rápido

```bash
cd loto-copa-analytics/scripts

python3 analisar.py loteria-prob megasena
python3 analisar.py loteria-ultimo megasena
python3 analisar.py loteria-ve megasena --marcadas 7 --premios "6:50000000,5:50000,4:1000"
python3 analisar.py loteria-ve-auto megasena --marcadas 7   # busca os prêmios ao vivo sozinho
python3 analisar.py fechamento --pool "1,5,12,23,33,42,51,60" --jogo 6 --garantia 4
python3 analisar.py anti-popular megasena --jogos 3

python3 analisar.py jogo-prob --casa-elo 1850 --fora-elo 1700 --mando 80
python3 analisar.py odds-valor --odds "2.10,3.40,3.60" --prob-modelo "0.52,0.27,0.21"
python3 analisar.py copa-monte-carlo --bracket "Brasil:2050,Argentina:2040,Franca:2010,Espanha:2000,Inglaterra:1980,Portugal:1970,Alemanha:1960,Holanda:1950" -n 20000
```

## Fontes de dados
- Loterias (sem chave): `loteriascaixa-api.herokuapp.com` com fallback para o JSON diário de `guilhermeasn/loteria.json` (GitHub Actions). Comunitárias, não oficiais — confira na Caixa antes de apostar.
- Futebol: `football-data.org` (requer `FOOTBALL_DATA_TOKEN`).

## Jogo responsável
Aposte só o que pode perder. Se virar problema, procure ajuda — no Brasil, CVV 188.

## Repositório

Fonte publicada em: `https://github.com/ebarroso12/skillloteria`
