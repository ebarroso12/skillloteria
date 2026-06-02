# TUTORIAL COMPLETO — loto-copa-analytics 🎲⚽

Guia único e definitivo: instalar, subir no GitHub, baixar em cada IA e
todos os comandos. Pré-requisito único: **python3** (confira: `python3 --version`).

> **Princípio da skill:** loteria é aleatória — nada prevê sorteio, e a skill
> diz isso. Futebol tem sinal real, mas o resultado é uma *probabilidade*,
> nunca certeza. Aposte só o que puder perder. CVV 188.

---

# PARTE 1 — BAIXAR E DESCOMPACTAR

1. Baixe `loto-copa-analytics.zip`.
2. Descompacte:
```bash
unzip loto-copa-analytics.zip
cd loto-copa-analytics
```

---

# PARTE 2 — SUBIR NO GITHUB

### 2.1 Criar o repositório
1. Acesse github.com → botão **New** (ou github.com/new).
2. Nome: `loto-copa-analytics`. Deixe **vazio** (sem README/licença — já temos).
3. Clique **Create repository**.

### 2.2 Enviar os arquivos (no terminal, dentro da pasta descompactada)
```bash
git init
git add .
git commit -m "skill loto-copa-analytics: análise de loterias e futebol"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/loto-copa-analytics.git
git push -u origin main
```
Se o GitHub pedir senha no push, use um **Personal Access Token** (Settings →
Developer settings → Tokens) no lugar da senha. O `.gitignore` já impede que a
chave de API e o cache subam junto.

### 2.3 (Opcional) Publicar no ClawHub
```bash
npm i -g clawhub        # se ainda não tiver o CLI
clawhub sync --all      # escaneia e publica
```

---

# PARTE 3 — INSTALAR EM CADA IA

## 3.1 OpenClaw
**A) Do GitHub (recomendado, depois de subir):**
```bash
openclaw skills install git:SEU_USUARIO/loto-copa-analytics@main
```
**B) Local (sem GitHub):**
```bash
openclaw skills install ./loto-copa-analytics --as loto-copa-analytics
```
**C) Do ClawHub (se publicou):**
```bash
openclaw skills install loto-copa-analytics
```
Conferir: `openclaw skills verify loto-copa-analytics --card`
Chave de futebol (opcional), em `~/.openclaw/openclaw.json`:
```json5
{ skills: { entries: { "loto-copa-analytics": { env: { API_FOOTBALL_KEY: "SUA_CHAVE" } } } } }
```

## 3.2 Claude Code
O Claude Code lê skills no formato AgentSkills. Basta copiar para uma raiz de skills:
```bash
# pessoal (todos os projetos):
cp -r loto-copa-analytics ~/.agents/skills/
# OU dentro de um projeto específico:
mkdir -p .agents/skills && cp -r loto-copa-analytics .agents/skills/
# futebol ao vivo:
export API_FOOTBALL_KEY="SUA_CHAVE"
```
Abra o Claude Code na pasta. A skill aparece como `/loto-copa-analytics`.

## 3.3 Codex (OpenAI)
```bash
cp -r loto-copa-analytics "${CODEX_HOME:-$HOME/.codex}/skills/"
export API_FOOTBALL_KEY="SUA_CHAVE"
```
Se usa o Codex via OpenClaw, prefira o método 3.1 (OpenClaw gerencia os skills).

### Chave gratuita de futebol
dashboard.api-football.com → cadastro → plano **Free** (100 req/dia). Sem ela,
as loterias e todos os modelos manuais de futebol funcionam normalmente; só os
comandos ao vivo de futebol (`confronto-auto`, `copa-*`, `quota`) precisam dela.

---

# PARTE 4 — TODOS OS COMANDOS

Sempre: `python3 scripts/analisar.py <comando> [opções]`

## LOTERIAS (sem chave)
Modalidades: `megasena lotofacil quina lotomania duplasena diadesorte supersete`

| Comando | O que faz |
|---|---|
| `loteria-prob megasena [--marcadas 8]` | Probabilidade exata de cada faixa + custo |
| `loteria-ultimo megasena` | Último resultado AO VIVO |
| `loteria-ve megasena --marcadas 7 --premios "6:50000000,5:50000,4:1000"` | Valor esperado (prêmios manuais) |
| `loteria-ve-auto megasena --marcadas 7` | Valor esperado buscando prêmios AO VIVO |
| `fechamento --pool "1,5,12,23,33,42,51,60" --jogo 6 --garantia 4` | Desdobramento com garantia condicional |
| `anti-popular megasena --jogos 3` | Gera jogos que evitam datas (<=31) |
| `loteria-uniforme megasena [--frequencia]` | Teste qui-quadrado: a loteria é justa? |
| `loteria-conferir megasena --jogo "1,3,15,25,45,52"` | Confere seu jogo contra o último sorteio |
| `loteria-divisao megasena [--apostas 40000000]` | Chance de dividir o prêmio se ganhar |

## FUTEBOL — modelos (sem chave, você fornece os números)
| Comando | O que faz |
|---|---|
| `jogo-prob --casa-elo 1850 --fora-elo 1700 [--mando 80]` | Probabilidade via Elo + Poisson/Dixon-Coles |
| `confronto --casa-nome X --fora-nome Y --casa-gm 2.1 --casa-gs 0.8 --fora-gm 1.9 --fora-gs 0.9 [--casa-forma "1,0.5,1,0,1"] [--casa-desfalques 0.3] [--casa-xg 1.8] [--casa-vermelhos 0.2]` | Modelo multifatorial completo |
| `penalti --conv-casa 0.85 --def-goleiro 0.20` | Probabilidade de um pênalti virar gol |
| `penalti --conv-casa 0.80 --conv-fora 0.72 --disputa` | Simula disputa de pênaltis (Monte Carlo) |
| `odds-valor --odds "2.10,3.40,3.60" [--prob-modelo "0.52,0.27,0.21"]` | Detecta value bet (remove margem da casa) |
| `copa-monte-carlo --bracket "Brasil:2050,Franca:2010,..." -n 20000` | Simula chaveamento e prob de título |

## FUTEBOL — ao vivo (precisa de API_FOOTBALL_KEY)
| Comando | O que faz |
|---|---|
| `quota` | Quanto resta da cota diária (não gasta cota) |
| `confronto-auto "Brasil" "Argentina"` | Monta forma/gols dos últimos 10 jogos sozinho |
| `copa-coverage [--season 2026]` | Quais dados a Copa cobre (lesões, predições...) |
| `copa-jogos [--season 2026]` | Lista jogos da Copa com fixture_id |
| `copa-confronto --fixture ID` | Cruza predição da API com nosso modelo (concordância/divergência) |

## Parâmetros úteis
- `--mando`: vantagem de casa. No `confronto` use ~1.12; em campo neutro/Copa, 1.0.
- `--casa-forma`: resultados recentes do mais novo p/ o antigo (1 vitória, 0.5 empate, 0 derrota).
- `--casa-desfalques`: peso 0..0.5 dos titulares ausentes (artilheiro fora ~0.25).
- `--casa-xg` / `--casa-fin`: gols esperados ou finalizações certas por jogo (estabiliza a estimativa).

---

# PARTE 5 — TESTE RÁPIDO (confirma que tudo funciona)
```bash
cd scripts
python3 analisar.py loteria-prob megasena
python3 analisar.py loteria-ultimo megasena
python3 analisar.py loteria-uniforme megasena
python3 analisar.py confronto --casa-nome Brasil --fora-nome Argentina --casa-gm 2.1 --casa-gs 0.8 --fora-gm 1.9 --fora-gs 0.9
# com chave:
python3 analisar.py quota
```

Pronto. Bom jogo — com a cabeça. 🦞
