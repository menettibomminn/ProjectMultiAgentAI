---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "security-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Auth Agent — MISTAKE

> **Questo file è append-only.** Ogni errore riscontrato aggiunge una nuova entry in fondo.
> Non cancellare o modificare entry precedenti. Ogni entry deve includere una remediation suggerita.

## Formato Entry

```markdown
## {timestamp} — Error in Task {task_id}
- **Error code:** {code}
- **Error message:** {message}
- **User/SA affected:** {user_id o service_account_id}
- **Stack/Context:** {stack trace o contesto dell'errore}
- **Impact:** {token non emesso | scope errati | auth flow interrotto}
- **Remediation:** {suggerimento per risolvere o prevenire in futuro}
- **Security alert:** yes | no
- **Resolved:** yes | no | pending
```

## Errori Comuni e Remediation

| Codice | Descrizione | Remediation Standard |
|---|---|---|
| `TOKEN_REFRESH_FAILED` | Refresh token non più valido | Utente deve ri-autenticarsi via OAuth flow |
| `SCOPE_VIOLATION` | Richiesta di scope superiori al permesso | Rifiutare richiesta; alertare security team |
| `VAULT_UNREACHABLE` | Vault locale non accessibile | Verificare permessi filesystem e stato OS keyring |
| `ENCRYPTION_ERROR` | Errore cifratura/decifratura token | Verificare master key in OS keyring; possibile corruzione |
| `SA_NOT_IN_ALLOWLIST` | Job richiede SA ma non è nella allowlist | Verificare infra/mcp_config.yml → service_account.allowed_jobs |
| `CONSENT_TIMEOUT` | Utente non ha completato il consent screen | Riprovare il flow OAuth; verificare redirect URI |

---

<!-- Append new error entries below this line -->
