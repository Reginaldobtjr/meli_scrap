import os
import asyncio
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async  # <--- NOVA IMPORTAÇÃO

app = FastAPI(title="MELI Affiliate Linkbuilder API Stealth")

# ---- Configurações ----
API_KEY = os.getenv("API_KEY", "")
SESSION_DIR = os.getenv("SESSION_DIR", "/data")
STATE_PATH = os.path.join(SESSION_DIR, "storage_state.json")
LINKBUILDER_URL = "https://www.mercadolivre.com.br/afiliados/linkbuilder#hub"

# Seletores
INPUT_URLS = "textarea#url-0"
BTN_GERAR = "button:has-text('Gerar')"
OUTPUT_LINK = "textarea#textfield-copyLink-1"
RADIO_CURTO = "label:has-text('Link curto')"

class ConvertRequest(BaseModel):
    links: List[str]
    link_type: str = "curto"
    batch_size: int = 30
    sleep_seconds: float = 1.0

@app.get("/")
def home():
    return {"status": "online", "mode": "stealth"}

@app.get("/health")
def health():
    return {"ok": True, "has_session": os.path.exists(STATE_PATH)}

async def build_links(batch_links: List[str], link_type: str) -> str:
    async with async_playwright() as p:
        # Lançamento do browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STATE_PATH)
        page = await context.new_page()

        # ATIVA O MODO FURTIVO: Disfarça assinaturas de robô
        await stealth_async(page)

        try:
            await page.goto(LINKBUILDER_URL, timeout=60000, wait_until="networkidle")

            # Verifica campo de entrada
            await page.wait_for_selector(INPUT_URLS, timeout=30000)

            # Lógica de botões opcionais
            radio_exists = await page.locator(RADIO_CURTO).is_visible()
            if radio_exists:
                await page.click(RADIO_CURTO)

            # Preenchimento
            await page.fill(INPUT_URLS, "\n".join(batch_links))
            await page.click(BTN_GERAR)

            # Captura link final
            await page.wait_for_selector(OUTPUT_LINK, timeout=60000)
            affiliate_link = await page.input_value(OUTPUT_LINK)

            await browser.close()
            return affiliate_link

        except Exception as e:
            # Foto do erro para debug
            screenshot_path = os.path.join(SESSION_DIR, "erro_stealth.png")
            await page.screenshot(path=screenshot_path)
            await browser.close()
            raise HTTPException(status_code=503, detail=f"Erro na interface: {str(e)}")

@app.post("/convert")
async def convert(req: ConvertRequest, x_api_key: Optional[str] = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Lógica de processamento em lotes
    results = []
    for i in range(0, len(req.links), req.batch_size):
        batch = req.links[i:i + req.batch_size]
        try:
            out = await build_links(batch, req.link_type)
            results.append({"batch_index": i // req.batch_size, "affiliate_output": out})
        except Exception as e:
            results.append({"error": str(e)})
    return {"total": len(req.links), "batches": results}
