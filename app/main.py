import os
import asyncio
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI(title="MELI Affiliate Linkbuilder API")

# ---- Config ----
API_KEY = os.getenv("API_KEY", "")
SESSION_DIR = os.getenv("SESSION_DIR", "/data")
STATE_PATH = os.path.join(SESSION_DIR, "storage_state.json")

LINKBUILDER_URL = "https://www.mercadolivre.com.br/afiliados/linkbuilder#hub"

MAX_BATCH = 30

# ---- Selectors (mais estáveis que XPATH absoluto) ----
INPUT_URLS = "textarea#url-0"
BTN_GERAR = "button:has-text('Gerar')"
OUTPUT_LINK = "textarea#textfield-copyLink-1"   # onde aparece o link curto no print
RADIO_CURTO = "label:has-text('Link curto')"
RADIO_COMPLETO = "label:has-text('Link completo')"

class ConvertRequest(BaseModel):
    links: List[str]
    link_type: str = "curto"       # "curto" ou "completo"
    batch_size: int = 30
    sleep_seconds: float = 1.0

def check_key(x_api_key: Optional[str]):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

def ensure_session_exists():
    if not os.path.exists(STATE_PATH):
        raise HTTPException(
            status_code=412,
            detail="Sem sessão salva. Gere e envie o arquivo storage_state.json para /data."
        )

@app.get("/")
def read_root():
    return {"status": "online", "message": "MELI Scraper API"}

@app.get("/health")
def health():
    return {"ok": True, "has_session": os.path.exists(STATE_PATH)}

async def build_links(batch_links: List[str], link_type: str) -> str:
    ensure_session_exists()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STATE_PATH)
        page = await context.new_page()

        await page.goto(LINKBUILDER_URL, timeout=60000)

        # Seleciona tipo de link
        if link_type == "completo":
            await page.click(RADIO_COMPLETO)
        else:
            await page.click(RADIO_CURTO)

        # Cola URLs (1 por linha)
        await page.fill(INPUT_URLS, "\n".join(batch_links))

        # Clica em Gerar
        await page.click(BTN_GERAR)

        # Espera o campo de saída aparecer e pega o valor
        await page.wait_for_selector(OUTPUT_LINK, timeout=60000)
        affiliate_link = await page.input_value(OUTPUT_LINK)

        await browser.close()
        return affiliate_link

@app.post("/convert")
async def convert(req: ConvertRequest, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)

    batch_size = max(1, min(req.batch_size, MAX_BATCH))
    results = []
    failed = []

    # O MELI parece retornar 1 link por execução (mesmo com 1 URL).
    # Se você mandar 30 URLs, pode voltar uma lista/área diferente.
    # Aqui eu retorno o output por batch e a gente ajusta se o MELI devolver múltiplos.
    for i in range(0, len(req.links), batch_size):
        batch = req.links[i:i + batch_size]
        try:
            out = await build_links(batch, req.link_type)
            results.append({
                "batch_index": i // batch_size,
                "input_count": len(batch),
                "affiliate_output": out
            })
        except Exception as e:
            failed.append({"batch_index": i // batch_size, "error": str(e)})

        if i + batch_size < len(req.links):
            await asyncio.sleep(req.sleep_seconds)
            

    return {"total": len(req.links), "batches": results, "failed": failed}
