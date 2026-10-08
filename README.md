# agents-wrapper

> Ollama-kompatibilis API átjáró és middleware réteg Google Antigravity és OpenAI Codex CLI ágensekhez.


A kérések előtt és után tetszőleges **bővíthető rétegek (Layers / Interceptors)** futtathatók (pl. Security Guardrails, Prompt Sanitizer, Audit Logger, 3rd-party RAG / Webhook hook).

---

## Főbb funkciók

- **Teljes Ollama API kompatibilitás:**
  - `GET /` & `GET /api/version`: Open WebUI liveness és handshake támogatás.
  - `GET /api/tags`: Dinamikusan felderített és konfigurált modellek listázása.
  - `POST /api/chat`: Valós idejű NDJSON streamelés (`stream: true`) és egybefüggő válasz (`stream: false`).
  - `POST /api/generate`: Nyers prompt kiegészítés.
  - `POST /api/show`: Modell metaadatok és paraméterek megjelenítése.
- **Dinamikus modellfelismerés:**
  - Automatikusan lekérdezi az elérhető modelleket a helyi CLI-ből (`agy models`).
  - Dinamikus modellnevek az Open WebUI-ban:
    - `agy`: Alapértelmezett Antigravity CLI futtatás.
    - `agy:gemini-3.8-flash-high`, `agy:claude-sonnet-4-6`, `agy:gpt-oss-120b-medium`: Dinamikusan kiválasztott háttérmodellek.
    - `agy:plan`: Antigravity tervezési (plan) módban.
    - `codex`: Codex CLI futtatás.
    - `codex:readonly`, `codex:workspace-write`: Különböző sandbox szintekkel.
    - `mock`: Villámgyors tesztelő modell a rétegek ellenőrzésére.
- **Pluggable Layer / Middleware Rendszer:**
  - **Security Layer:**
    - Prompt Injection és Jailbreak kísérletek felismerése és blokkolása.
    - Titkos adatok és API kulcsok szivárgásának (AWS, OpenAI, GitHub PAT, Private Keys) blokkolása.
    - Veszélyes és destruktív parancsok (pl. `rm -rf /`, `mkfs`, fork bombák) blokkolása.
  - **Prompt Sanitizer & Formatter Layer:**
    - Az Open WebUI-ból érkező kontextus (RAG dokumentumok, előzmények) tiszta formázása a CLI-k számára.
  - **Audit Logger Layer:**
    - Hívások, válaszidők és méretek strukturált naplózása (`audit.log`).
  - **External Hook Layer (opcionális):**
    - Külső HTTP Webhook hívása 3rd-party RAG szolgáltatásokhoz.

---

## Telepítés és Indítás

### 1. Előfeltételek
- Python 3.10+
- Helyileg telepített `agy` (és/vagy `codex`) CLI.

### 2. Indítás
Egyszerűen futtasd az indító scriptet:
```bash
./run.sh
```
Ez automatikusan létrehozza a `.venv` környezetet, feltelepíti a minimális függőségeket (FastAPI, Uvicorn, Pydantic, PyYAML), és elindítja a szervert a **11434**-es porton (az Ollama alapértelmezett portja).

Egyedi port vagy host megadása:
```bash
./run.sh --port 11434 --host 0.0.0.0
```

---

## Használat Open WebUI-val

1. Indítsd el a wrappert: `./run.sh`
2. Nyisd meg az **Open WebUI** felületét.
3. Menj a **Settings > Admin Settings > Connections** menüpontba.
4. Add meg az Ollama API URL-t:
   ```text
   http://localhost:11434
   ```
   *(Dockerből futó Open WebUI esetén használd a `http://host.docker.internal:11434` címet!)*
5. Kattints a frissítés / mentés gombra. Az Open WebUI azonnal zöldre vált, és megjeleníti a modelleket (pl. `agy:latest`, `agy:gemini-3.8-flash-high`, `codex:latest`).
6. A csevegésben használd az Open WebUI beépített **Dokumentum / RAG** funkcióit bátran: az Open WebUI automatikusan beilleszti a releváns szövegrészleteket a kontextusba, a wrapper pedig biztonsági ellenőrzés után továbbítja azt az ágensnek!

---

## Konfiguráció (`config.yaml`)

A `config.yaml` fájlban egyszerűen be- és kikapcsolhatók a rétegek, illetve egyedi profilok hozhatók létre:

```yaml
server:
  host: "0.0.0.0"
  port: 11434

backends:
  agy:
    binary_path: "agy"
    default_model: "gemini-3.8-flash-high"
    auto_discover_models: true

pipeline:
  layers:
    - name: "security_check"
      enabled: true
      config:
        block_on_prompt_injection: true
        block_on_secret_leak: true
        block_on_destructive_commands: true

    - name: "prompt_sanitizer"
      enabled: true

    - name: "audit_logger"
      enabled: true
      config:
        log_file: "audit.log"
```

---

## Saját Layer hozzáadása

Új réteget a `BaseLayer` osztályból örököltetve hozhatsz létre:

```python
from src.pipeline.base import BaseLayer
from src.pipeline.context import PipelineContext

class MyCustomLayer(BaseLayer):
    async def pre_process(self, ctx: PipelineContext) -> PipelineContext:
        # Kérés előtti logika (pl. prompt módosítás, külső ellenőrzés)
        if "tiltott_kifejezes" in ctx.prompt_text:
            ctx.abort("Egyedi tiltási ok")
        return ctx

    async def post_process_chunk(self, chunk: str, ctx: PipelineContext) -> str:
        # Streamelt kimenet valós idejű maszkolása
        return chunk
```

A réteget regisztrálhatod a `PipelineRunner.register_layer_class("my_layer", MyCustomLayer)` hívással, és bekapcsolhatod a `config.yaml`-ban!

---

## Tesztek futtatása

A csomag teljes tesztlefedettséggel rendelkezik a végpontokra, streamelésre és a security blokkolásra:

```bash
PYTHONPATH=. ./.venv/bin/pytest tests/test_api.py -v
```

Valós `agy` CLI hívás tesztelése (ha elérhető a rendszereden):
```bash
PYTHONPATH=. ./.venv/bin/pytest tests/test_agy_live.py -v -s
```
