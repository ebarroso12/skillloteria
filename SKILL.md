---
name: loto-copa-analytics
description: Análise matemática e estatística honesta de loterias da Caixa (Mega-Sena, Lotofácil, Quina, etc.) e de futebol/Copa do Mundo, com busca de dados ao vivo. Use quando o usuário pedir probabilidades de loteria, valor esperado de apostas, fechamentos/desdobramentos, geração de jogos, resultados recentes de sorteios, ou probabilidades de partidas, placares, value bets em odds e simulação de chaveamento de Copa. NÃO promete prever sorteios de loteria — eles são aleatórios — e deixa isso claro ao usuário.
homepage: https://clawhub.ai
metadata: { "openclaw": { "emoji": "🎲", "requires": { "bins": ["python3"] }, "primaryEnv": "API_FOOTBALL_KEY" } }
---

# loto-copa-analytics

Skill de análise quantitativa para **loterias da Caixa** e **futebol (incl. Copa do Mundo)**. Roda em OpenClaw, Claude Code e Codex (formato AgentSkills). Todos os comandos saem em JSON via um único CLI.

## Princípio inegociável (diga isto ao usuário quando relevante)

- **Loterias são aleatórias e sem memória.** Nenhuma análise de números "atrasados/quentes", soma, paridade ou padrão aumenta a chance de acerto. Isso é teorema, não opinião. Se o usuário pedir um "sistema que aumenta a chance de ganhar na loteria", explique gentilmente que isso é matematicamente impossível e ofereça o que é real: probabilidades exatas, valor esperado, fechamentos (garantia condicional) e jogos anti-divisão de prêmio.
- **Futebol tem sinal real**, mas o resultado é sempre uma *distribuição de probabilidade*, nunca certeza. Modelos erram com frequência. Nunca prometa lucro garantido.

## Como executar

Todos os comandos: `python3 {baseDir}/scripts/analisar.py <comando> [opções]`

### Loterias
- Probabilidades + custo: `loteria-prob <loteria> [--marcadas N]`
- Resultado AO VIVO: `loteria-ultimo <loteria>`
- Valor esperado: `loteria-ve <loteria> --marcadas N --premios "6:50000000,5:50000,4:1000"`
- **Valor esperado AUTOMÁTICO (busca prêmios ao vivo):** `loteria-ve-auto <loteria> [--marcadas N]`
- Fechamento/desdobramento: `fechamento --pool "1,5,12,23,33,42,51,60" --jogo 6 --garantia 4`
- Jogos anti-divisão de prêmio: `anti-popular <loteria> [--jogos N] [--marcadas N]`
- Teste de uniformidade (qui-quadrado, prova que não há número "quente"): `loteria-uniforme <loteria> [--frequencia]`
- Conferir jogo contra o último sorteio: `loteria-conferir <loteria> --jogo "1,3,15,25,45,52"`
- Probabilidade de dividir o prêmio: `loteria-divisao <loteria> [--apostas N]`

Loterias válidas: `megasena lotofacil quina lotomania duplasena diadesorte supersete`

### Futebol
- Probabilidade de jogo (Poisson + Dixon-Coles via Elo): `jogo-prob --casa-elo 1850 --fora-elo 1700 [--mando 80] [--media-gols 2.6]`
- **Confronto multifatorial (manual):** `confronto --casa-nome X --fora-nome Y --casa-gm 2.1 --casa-gs 0.8 --fora-gm 1.9 --fora-gs 0.9 [--casa-forma "1,0.5,1,0,1"] [--casa-desfalques 0.3] [--casa-xg 1.8] [--casa-fin 6] [--casa-vermelhos 0.2]`. Agrega força ataque/defesa, forma recente com decaimento, desfalques, mando, xG/finalizações e ajuste leve de disciplina. Saída: 1x2, ambos marcam, over 2.5, placares.
- **Confronto automático (API-Football):** `confronto-auto "Brasil" "Argentina" [--season 2026]`. Busca os últimos 10 jogos de cada time e monta forma/gols sozinho. Gasta ~6 requisições da cota.
- **Pênaltis:** `penalti --conv-casa 0.85 --def-goleiro 0.20` (um pênalti) ou `penalti --conv-casa 0.80 --conv-fora 0.72 --disputa` (disputa completa).
- **Cota da API:** `quota` (não consome cota).
- **Copa — o que existe:** `copa-coverage [--season 2026]` mostra quais dados a Copa cobre (lineups, injuries, predictions, etc.) sem desperdiçar requisições.
- **Copa — lista de jogos:** `copa-jogos [--season 2026]` lista os jogos com seus `fixture_id`.
- **Copa — confronto cruzado:** `copa-confronto --fixture ID` cruza a predição estatística da própria API-Football (calculada com 6 algoritmos) com o nosso modelo multifatorial. Reporta a divergência entre os dois: forte concordância = mais confiança; divergência relevante = cautela. Traz advice, under/over e o bloco comparison (ataque/defesa/Poisson/H2H) da API.
- Value bet em odds: `odds-valor --odds "2.10,3.40,3.60" [--prob-modelo "0.52,0.27,0.21"]`
- Simulação de Copa (Monte Carlo): `copa-monte-carlo --bracket "Brasil:2050,Franca:2010,..." -n 20000`

## Dados ao vivo

- **Loterias:** sem chave. Fonte primária `loteriascaixa-api` (Heroku), fallback automático para o JSON diário de `guilhermeasn/loteria.json` no GitHub. Sempre informe ao usuário o número/data do concurso e recomende conferir no site oficial da Caixa antes de apostar — as fontes são comunitárias, não oficiais.
- **Futebol:** o modelo multifatorial (`confronto`) e os de cálculo (`jogo-prob`, `odds-valor`, `copa`, `penalti`) funcionam SEM chave, com os números que o usuário fornecer. Para dados ao vivo de gols/forma (`confronto-auto`, `quota`), defina `API_FOOTBALL_KEY` (chave gratuita em dashboard.api-football.com) em `skills.entries.loto-copa-analytics.env`. O plano gratuito dá 100 requisições/dia (zera 00:00 UTC) e cobre todos os endpoints; a skill faz cache agressivo em disco para economizar a cota. Cobertura de xG/estatísticas avançadas é irregular no plano free — quando faltam, o modelo degrada para gols/finalizações em vez de inventar.

## Fluxo recomendado

1. Para perguntas de loteria, comece por `loteria-prob` para ancorar a conversa na realidade das probabilidades.
2. Se o usuário insistir em "melhorar as chances", ofereça `fechamento` (garantia condicional) e `anti-popular`, sempre repetindo que não muda a probabilidade de ganhar.
3. Para futebol, se houver `FOOTBALL_DATA_TOKEN`, busque ratings/médias reais; senão, peça os Elos ou odds ao usuário e rode os modelos.
4. Apresente sempre os avisos que o JSON traz no campo `aviso`.

## Jogo responsável

Se o usuário demonstrar gasto excessivo, perseguição de perdas ou sofrimento, pare a análise e oriente buscar apoio (no Brasil: CVV 188). Não incentive aumento de apostas.
