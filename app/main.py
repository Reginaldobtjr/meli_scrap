import os
import asyncio
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI(title="MELI Affiliate Linkbuilder API")

# ---- Configurações ----
# Puxa a chave de API e caminhos das variáveis de ambiente do Easypanel
API_KEY = os.getenv("API_KEY", "")
SESSION_DIR = os.getenv("SESSION_DIR", "/data")
STATE_PATH = os.path.join(SESSION_DIR, "storage_state.json")

LINKBUILDER_URL = "https://www.mercadolivre.com.br/afiliados/linkbuilder#hub"
MAX_BATCH = 30

# ---- Seletores Estáveis ----
# Usamos texto e IDs específicos para maior durabilidade
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

# ---- Rotas de Monitorização ----

@app.get("/")
def home():
    """Rota para evitar loops de reinício no Easypanel."""
    return {"status": "online", "message": "MELI API operacional"}

@app.get("/health")
def health():
    """Verifica se o servidor está ativo e se a sessão existe."""
    return {"ok": True, "has_session": os.path.exists(STATE_PATH)}

# ---- Funções de Lógica e Segurança ----

def check_key(x_api_key: Optional[str]):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

def ensure_session_exists():
    if not os.path.exists(STATE_PATH):
        raise HTTPException(
            status_code=412,
            detail="Sem sessão salva. Verifique a pasta /data no volume do Easypanel."
        )

async def build_links(batch_links: List[str], link_type: str) -> str:
    ensure_session_exists()

    async with async_playwright() as p:
        # Headless=True é obrigatório para rodar em servidores sem monitor
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STATE_PATH)
        page = await context.new_page()

        print("A abrir o Linkbuilder...")
        # wait_until="load" garante um carregamento mais rápido no servidor
        await page.goto(LINKBUILDER_URL, timeout=60000, wait_until="load")

        # ESPERA EXPLÍCITA pelo campo de entrada para evitar erros de timeout
        try:
            print("A aguardar campo de entrada...")
            await page.wait_for_selector(INPUT_URLS, timeout=30000)
        except Exception:
            print("ERRO: Campo não encontrado. Possível redirecionamento para login.")
            await browser.close()
            raise HTTPException(
                status_code=503, 
                detail="Interface do Mercado Livre não carregou. Verifique a sessão."
            )

        # Lógica Resiliente para os botões de tipo de link
        radio_exists = await page.locator(RADIO_CURTO).is_visible()
        if radio_exists:
            print("Configurando tipo de link...")
            if link_type == "completo":
                await page.click(RADIO_COMPLETO)
            else:
                await page.click(RADIO_CURTO)

        # Preenchimento e Geração
        await page.fill(INPUT_URLS, "\n".join(batch_links))
        await page.click(BTN_GERAR)

        # Aguarda e captura o link final
        await page.wait_for_selector(OUTPUT_LINK, timeout=60000)
        affiliate_link = await page.input_value(OUTPUT_LINK)

        await browser.close()
        return affiliate_link

# ---- Rota Principal (Usada pelo n8n) ----

@app.post("/convert")
async def convert(req: ConvertRequest, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)

    batch_size = max(1, min(req.batch_size, MAX_BATCH))
    results = []
    failed = []

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
