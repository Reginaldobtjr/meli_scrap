import os
import asyncio
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright
import playwright_stealth

app = FastAPI(title="MELI API Final")

# ---- CONFIGURAÇÕES ----
API_KEY = os.getenv("API_KEY", "")
SESSION_DIR = os.getenv("SESSION_DIR", "/data")
STATE_PATH = os.path.join(SESSION_DIR, "storage_state.json")
LINKBUILDER_URL = "https://www.mercadolivre.com.br/afiliados/linkbuilder#hub"
MAX_BATCH = 30 # Correção do NameError

# Seletores atualizados baseados na sua image_47986a.jpg
INPUT_URLS = "textarea" # Seletor genérico para o campo de URLs
BTN_GERAR = "button:has-text('Gerar')"
OUTPUT_LINK = "textarea#textfield-copyLink-1"

class ConvertRequest(BaseModel):
    links: List[str]
    link_type: str = "curto"
    batch_size: int = 30

@app.get("/")
def home(): return {"status": "online"}

async def build_links(batch_links: List[str]) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STATE_PATH)
        page = await context.new_page()
        
        try:
            await playwright_stealth.stealth_async(page)
            await page.goto(LINKBUILDER_URL, timeout=60000, wait_until="load")
            
            # Espera o textarea aparecer
            await page.wait_for_selector(INPUT_URLS, timeout=30000)
            
            # Preenche e gera
            await page.fill(INPUT_URLS, "\n".join(batch_links))
            await page.click(BTN_GERAR)
            
            # Espera o resultado
            await page.wait_for_selector(OUTPUT_LINK, timeout=60000)
            return await page.input_value(OUTPUT_LINK)
        except Exception as e:
            await page.screenshot(path=os.path.join(SESSION_DIR, "ultimo_erro.png"))
            await browser.close()
            raise Exception(f"Erro: {str(e)}")

@app.post("/convert")
async def convert(req: ConvertRequest, x_api_key: Optional[str] = Header(None)):
    if API_KEY and x_api_key != API_KEY: raise HTTPException(status_code=401)
    batch_size = max(1, min(req.batch_size, MAX_BATCH))
    # ... resto da lógica de batches ...
    out = await build_links(req.links[:batch_size])
    return {"affiliate_output": out}
