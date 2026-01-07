import os
import asyncio
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright

# Correção de compatibilidade para a biblioteca stealth
try:
    from playwright_stealth import stealth_async as stealth
except ImportError:
    try:
        from playwright_stealth import stealth
    except ImportError:
        stealth = None

app = FastAPI(title="MELI Affiliate API - Versão Final")

# ---- CONFIGURAÇÕES GLOBAIS (Onde estava o erro) ----
API_KEY = os.getenv("API_KEY", "")
SESSION_DIR = os.getenv("SESSION_DIR", "/data")
STATE_PATH = os.path.join(SESSION_DIR, "storage_state.json")

LINKBUILDER_URL = "https://www.mercadolivre.com.br/afiliados/linkbuilder#hub"
MAX_BATCH = 30  # <--- DEFINIDO AQUI PARA CORRIGIR O NAMEERROR

# ---- SELETORES ----
INPUT_URLS = "textarea#url-0"
BTN_GERAR = "button:has-text('Gerar')"
OUTPUT_LINK = "textarea#textfield-copyLink-1"
RADIO_CURTO = "label:has-text('Link curto')"
RADIO_COMPLETO = "label:has-text('Link completo')"

class ConvertRequest(BaseModel):
    links: List[str]
    link_type: str = "curto"
    batch_size: int = 30
    sleep_seconds: float = 1.0

# ---- ROTAS DE SAÚDE ----

@app.get("/")
def home():
    return {"status": "online", "message": "API operacional"}

@app.get("/health")
def health():
    return {"ok": True, "has_session": os.path.exists(STATE_PATH)}

# ---- LÓGICA DE SCRAPING ----

async def build_links(batch_links: List[str], link_type: str) -> str:
    if not os.path.exists(STATE_PATH):
        raise HTTPException(status_code=412, detail="Sessão não encontrada.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STATE_PATH)
        page = await context.new_page()

        # Aplica o modo furtivo se a biblioteca estiver disponível
        if stealth:
            try:
                await stealth(page)
            except Exception:
                pass

        try:
            await page.goto(LINKBUILDER_URL, timeout=60000, wait_until="load")
            await page.wait_for_selector(INPUT_URLS, timeout=30000)

            # Lógica para os botões de tipo de link
            radio_exists = await page.locator(RADIO_CURTO).is_visible()
            if radio_exists:
                if link_type == "completo":
                    await page.click(RADIO_COMPLETO)
                else:
                    await page.click(RADIO_CURTO)

            await page.fill(INPUT_URLS, "\n".join(batch_links))
            await page.click(BTN_GERAR)

            await page.wait_for_selector(OUTPUT_LINK, timeout=60000)
            affiliate_link = await page.input_value(OUTPUT_LINK)

            await browser.close()
            return affiliate_link

        except Exception as e:
            # Tira print do erro para debug no servidor
            screenshot_path = os.path.join(SESSION_DIR, "ultimo_erro.png")
            await page.screenshot(path=screenshot_path)
            await browser.close()
            raise Exception(f"Erro na interface: {str(e)}")

# ---- ROTA PRINCIPAL (POST /convert) ----

@app.post("/convert")
async def convert(req: ConvertRequest, x_api_key: Optional[str] = Header(None)):
    # Validação da chave de API
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Define o tamanho do lote respeitando o máximo global
    batch_size = max(1, min(req.batch_size, MAX_BATCH))
    
    results = []
    failed = []

    # Processamento em lotes
    for i in range(0, len(req.links), batch_size):
        batch = req.links[i:i + batch_size]
        try:
            out = await build_links(batch, req.link_type)
            results.append({
                "batch_index": i // batch_size,
                "affiliate_output": out
            })
        except Exception as e:
            failed.append({
                "batch_index": i // batch_size,
                "error": str(e)
            })

        # Pausa opcional entre lotes
        if i + batch_size < len(req.links):
            await asyncio.sleep(req.sleep_seconds)

    return {
        "total_links": len(req.links),
        "batches_success": results,
        "failed": failed
    }
