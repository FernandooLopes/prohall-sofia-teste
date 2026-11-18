import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

MODELO_GEMINI = "gemini-3.8-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODELO_GEMINI}:generateContent"
)

CAMINHO_CATALOGO = RAIZ / "data" / "catalogo.json"
PASTA_STATIC = RAIZ / "static"

PIX_VALIDADE_PADRAO = 15 * 60


def chave_gemini():
    return os.getenv("GEMINI_API_KEY", "").strip()


def nivel_raciocinio():
    nivel = os.getenv("GEMINI_THINKING_LEVEL", "low").strip().lower()
    return nivel if nivel in ("low", "medium", "high") else "low"


def validade_pix():
    try:
        segundos = int(os.getenv("PIX_VALIDADE_SEGUNDOS", ""))
    except ValueError:
        return PIX_VALIDADE_PADRAO
    return segundos if segundos > 0 else PIX_VALIDADE_PADRAO
