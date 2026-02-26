# PRD: Fix Incongruenze Documentazione Agenti

## Introduzione

La codebase ha accumulato incongruenze nella documentazione .md degli agenti: directory duplicate (kebab-case vs snake_case), file mancanti, formati disallineati, lingua mista e un agente sheets frammentato in due directory. Questo PRD definisce le fix necessarie per consolidare e standardizzare tutta la documentazione.

## Goals

- Eliminare tutte le directory kebab-case legacy (solo .md, zero codice)
- Consolidare sheets/ e sheets-agent/ in un unico sheets_agent/
- Garantire che ogni agente abbia lo stesso set di file .md
- Uniformare lingua (italiano), formato e convenzioni across all agents
- Zero regressioni: tutti i 259 test devono continuare a passare

## User Stories

### US-001: Consolidare sheets/ in sheets_agent/
**Descrizione:** Come sviluppatore, voglio un unico agente sheets con naming coerente (sheets_agent/) cosi da eliminare la confusione tra sheets/ e sheets-agent/.

**Acceptance Criteria:**
- [ ] Rinominare `Agents/sheets/` in `Agents/sheets_agent/`
- [ ] Aggiornare tutti gli import Python da `Agents.sheets` a `Agents.sheets_agent`
- [ ] Aggiornare `Agents/__init__.py` AVAILABLE_AGENTS: `"sheets"` -> `"sheets_agent"`
- [ ] Aggiornare `__main__.py` e `config.py` con i nuovi path
- [ ] Aggiornare i test (conftest, import) per usare `Agents.sheets_agent`
- [ ] Integrare le informazioni utili da `Agents/sheets-agent/CLAUDE.md` (skills, obiettivi, hooks) nel nuovo `sheets_agent/CLAUDE.md`
- [ ] Riscrivere `sheets_agent/CLAUDE.md` in italiano come tutti gli altri agenti
- [ ] Eliminare `Agents/sheets-agent/` (dir kebab legacy)
- [ ] Eliminare `Agents/sheets/` (vecchio path)
- [ ] Aggiornare `.github/workflows/ci.yml` se referenzia `Agents/sheets`
- [ ] Tutti i 41 test sheets passano con i nuovi path
- [ ] `python -m Agents.sheets_agent --run-once` funziona correttamente

### US-002: Eliminare directory kebab-case legacy
**Descrizione:** Come sviluppatore, voglio rimuovere le directory duplicate kebab-case che contengono solo .md senza codice, consolidando i docs nelle dir snake_case.

**Acceptance Criteria:**
- [ ] Per ogni agente (auth, backend, frontend, metrics): fare merge dei .md da kebab-case a snake_case
- [ ] Regola merge: se un .md esiste in entrambe le dir, il contenuto della dir snake_case ha priorita (e piu recente); integrare info utili dal kebab-case
- [ ] Eliminare `Agents/auth-agent/`
- [ ] Eliminare `Agents/backend-agent/`
- [ ] Eliminare `Agents/frontend-agent/`
- [ ] Eliminare `Agents/metrics-agent/`
- [ ] Verificare che nessun file Python referenzi path kebab-case
- [ ] Aggiornare eventuali riferimenti nei CLAUDE.md (es. `ASSERT file_exists("agents/sheets-agent/CLAUDE.md")`)

### US-003: Creare file .md mancanti
**Descrizione:** Come sviluppatore, voglio che ogni agente abbia lo stesso set di file .md per coerenza e completezza.

**Acceptance Criteria:**
- [ ] Set standard di file .md per ogni agente: CLAUDE.md, CHANGELOG.md, HEALTH.md, MISTAKE.md, TODO.md, ARCHITECTURE.md
- [ ] Creare `Agents/auth_agent/TODO.md` seguendo il formato degli altri agenti
- [ ] Creare `Agents/auth_agent/ARCHITECTURE.md` seguendo il formato degli altri agenti
- [ ] Creare `Agents/metrics_agent/TODO.md` seguendo il formato degli altri agenti
- [ ] Creare `Agents/metrics_agent/ARCHITECTURE.md` seguendo il formato degli altri agenti
- [ ] Creare `Agents/teams/sheets-team/TODO.md` seguendo il formato degli altri agenti
- [ ] Tutti i nuovi file devono avere il frontmatter YAML standard (version, last_updated, owner, project)

### US-004: Standardizzare formato e lingua dei .md
**Descrizione:** Come sviluppatore, voglio che tutti i file .md usino lo stesso formato e la stessa lingua (italiano) per facilitare la manutenzione.

**Acceptance Criteria:**
- [ ] Tutti i .md in italiano (tradurre quelli in inglese in `sheets_agent/`)
- [ ] Fix typo ricorrente: `"Questo file e append-only"` -> `"Questo file è append-only"` (in tutti i file sheets)
- [ ] CHANGELOG.md: formato uniforme con Task ID, Status, Summary, Artifacts, Metrics
- [ ] HEALTH.md: schema JSON nel frontmatter + tabella aggiornamenti coerente
- [ ] TODO.md: formato `- [x] PREFIX-NNN — Titolo — Priorita — Data — depends: [] — DONE data`
- [ ] MISTAKE.md: tutti devono includere tabella severita (critical/high/medium/low) come frontend-agent
- [ ] Unificare prefissi task ID sheets: usare `sh-` (non `sw-`) coerente con CLAUDE.md
- [ ] Hook naming: usare `pre_hook`, `post_hook`, `error_hook` (non "Pre-processing" etc.)
- [ ] Aggiornare `last_updated` a `2026-02-24` in tutti i frontmatter

### US-005: Allineare requirements.txt
**Descrizione:** Come sviluppatore, voglio che il version pinning sia coerente tra tutti gli agenti.

**Acceptance Criteria:**
- [ ] Adottare upper bounds per tutti: `jsonschema>=4.20,<5`, `portalocker>=2.8,<3`, `pydantic>=2.5,<3`
- [ ] Allineare versioni dev deps: `pytest>=7.4,<9`, `pytest-cov>=4.1,<6`, `flake8>=7.0,<8`, `mypy>=1.8,<2`
- [ ] Verificare che `pip install -r requirements.txt` funzioni per ogni agente
- [ ] Tutti i 259 test passano dopo l'allineamento

## Requisiti Funzionali

- FR-1: Il sistema deve avere un'unica directory per agente, in snake_case
- FR-2: Ogni agente deve avere esattamente 6 file .md: CLAUDE, CHANGELOG, HEALTH, MISTAKE, TODO, ARCHITECTURE
- FR-3: Tutti i file .md devono essere in italiano con frontmatter YAML standard
- FR-4: Gli import Python devono usare solo path snake_case (`Agents.sheets_agent`, non `Agents.sheets`)
- FR-5: Il CI (.github/workflows/ci.yml) deve testare tutti gli agenti con i path corretti
- FR-6: Nessuna regressione nei test (259 test, 0 failures)

## Non-Goals

- Non implementare nuove funzionalita per nessun agente
- Non modificare la logica Python (solo import path e config)
- Non creare un requirements.txt root aggregato (fuori scope)
- Non rinominare `Agents/teams/sheets-team/` (il team e diverso dagli agenti)
- Non toccare `Agents/sheets_team_lead/` (gia corretto)

## Considerazioni Tecniche

- Il rename `sheets/` -> `sheets_agent/` richiede aggiornamento di TUTTI gli import
- Il CI in `.github/workflows/ci.yml` referenzia `Agents/sheets` — va aggiornato
- `__init__.py` root definisce `AVAILABLE_AGENTS` — va aggiornato
- Il comando di lancio cambia: `python -m Agents.sheets_agent --run-once`
- I test usano `from Agents.sheets.*` — tutti da aggiornare

## Metriche di Successo

- 0 directory kebab-case residue in `Agents/`
- 6 agenti x 6 file .md = 36 file .md totali (+ team docs)
- Tutti i 259+ test passano
- `flake8` e `mypy` passano senza errori
- Lingua uniforme italiano in tutti i .md

## Domande Aperte

- Nessuna — tutte le decisioni sono state prese con il product owner.
