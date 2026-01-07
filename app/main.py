import os
import asyncio
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright

# Correção para a biblioteca stealth
try:
    import playwright_stealth
except ImportError:
    playwright_stealth = None

app = FastAPI(title="MELI API")

# ---- CONFIGURAÇÕES GLOBAIS ----
API_KEY = os.getenv("API_KEY", "")
SESSION_DIR = os.getenv("SESSION_DIR", "/data")
STATE_PATH = os.path.join(SESSION_DIR, "storage_state.json")
LINKBUILDER_URL = "https://www.mercadolivre.com.br/afiliados/linkbuilder#hub"
MAX_BATCH = 30 

class ConvertRequest(BaseModel):
    links: List[str]
    link_type: str = "curto"
    batch_size: int = 30
    sleep_seconds: float = 1.0

# ---- ROTA DE SAÚDE (O seu erro está aqui se esta rota faltar) ----
@app.get("/health")
def health():
    return {
        "ok": True, 
        "has_session": os.path.exists(STATE_PATH),
        "session_path": STATE_PATH
    }

@app.get("/")
def home():
    return {"status": "online", "message": "Use a rota /health ou /convert"}

# ---- LÓGICA DE SCRAPING ----
async def build_links(batch_links: List[str]) -> str:
    if not os.path.exists(STATE_PATH):
        raise Exception("Ficheiro storage_state.json nao encontrado em /data")

    async with async_playwright() as p:
        # Aumentamos o timeout para servidores mais lentos
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STATE_PATH)
        page = await context.new_page()
        
        if playwright_stealth:
            await playwright_stealth.stealth_async(page)
        
        try:
            await page.goto(LINKBUILDER_URL, timeout=90000, wait_until="load")
            
            # Seletor genérico para o campo de texto
            await page.wait_for_selector("textarea", timeout=30000)
            await page.fill("textarea", "\n".join(batch_links))
            
            await page.click("button:has-text('Gerar')")
            
            # Espera pelo link gerado
            output_selector = "textarea#textfield-copyLink-1"
            await page.wait_for_selector(output_selector, timeout=60000)
            res = await page.input_value(output_selector)
            
            await browser.close()
            return res
        except Exception as e:
            await page.screenshot(path=os.path.join(SESSION_DIR, "erro_health.png"))
            await browser.close()
            raise Exception(f"Falha no browser: {str(e)}")

# ---- ROTA PARA O N8N ----
@app.post("/convert")
async def convert(req: ConvertRequest, x_api_key: Optional[str] = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Chave API invalida")
    
    try:
        # Processa apenas o primeiro lote para teste rápido
        links_para_processar = req.links[:MAX_BATCH]
        resultado = await build_links(links_para_processar)
        return {"success": True, "affiliate_link": resultado}
    except Exception as e:
        return {"success": False, "error": str(e)}
