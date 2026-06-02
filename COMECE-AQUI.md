# COMECE AQUI 🦞 — guia rápido (passo a passo)

Tudo já está pronto. Baixe o `loto-copa-analytics.zip`, descompacte e siga o
caminho que você quiser. Leva 2 minutos.

---

## Passo 0 — Descompactar
```bash
unzip loto-copa-analytics.zip
cd loto-copa-analytics
```
Pré-requisito único: ter `python3` instalado. Confira com `python3 --version`.

---

## OPÇÃO A — Instalar no Claude Code (mais simples, sem GitHub)
```bash
cp -r ../loto-copa-analytics ~/.agents/skills/
```
Abra o Claude Code na sua pasta de trabalho. A skill já aparece.

## OPÇÃO B — Instalar no Codex (OpenAI)
```bash
cp -r ../loto-copa-analytics "${CODEX_HOME:-$HOME/.codex}/skills/"
```

## OPÇÃO C — Instalar no OpenClaw (local, sem GitHub)
```bash
openclaw skills install ./loto-copa-analytics --as loto-copa-analytics
openclaw skills verify loto-copa-analytics --card   # confere o Skill Card
```

---

## OPÇÃO D — Subir pro GitHub e instalar de lá (recomendado se for reaproveitar)
1. Crie um repositório vazio em github.com chamado `loto-copa-analytics`.
2. Na pasta descompactada:
```bash
git init
git add .
git commit -m "skill loto-copa-analytics"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/loto-copa-analytics.git
git push -u origin main
```
3. No OpenClaw, instale direto do repo:
```bash
openclaw skills install git:SEU_USUARIO/loto-copa-analytics@main
```

---

## Futebol ao vivo (opcional)
Pegue uma chave gratuita em https://dashboard.api-football.com e exporte:
```bash
export API_FOOTBALL_KEY="sua_chave"
```
No OpenClaw, em vez do export, configure em `~/.openclaw/openclaw.json`:
```json5
{ skills: { entries: { "loto-copa-analytics": { env: { API_FOOTBALL_KEY: "sua_chave" } } } } }
```
As loterias funcionam SEM chave nenhuma.

---

## Teste rápido (confirma que está tudo funcionando)
```bash
cd scripts
python3 analisar.py loteria-prob megasena          # probabilidades
python3 analisar.py loteria-ultimo megasena        # resultado ao vivo
python3 analisar.py loteria-ve-auto megasena --marcadas 7   # valor esperado automático
```

Pronto. Aposte com a cabeça — e lembre: na loteria a matemática é honesta,
nenhum sistema aumenta a chance de ganhar. CVV 188 se virar problema.
