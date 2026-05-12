import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)


def _split_origins(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "20061104")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "campus_mental")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))

# 非空时允许 POST /api/v1/admin/register；须与前端提交的注册密钥一致（生产环境务必改为强随机串）
ADMIN_REGISTER_SECRET = os.getenv("ADMIN_REGISTER_SECRET", "").strip()

_cors = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS: list[str] = _split_origins(_cors) if _cors != "*" else ["*"]

# DeepSeek（云端，按量计费）
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

# Ollama（本机免费，无需 API Key）https://ollama.com
# LLM_PROVIDER: ollama（默认）| auto | deepseek
# - ollama：只用本机 Ollama（文档与课程演示推荐）
# - auto：有 DEEPSEEK_API_KEY 时优先 DeepSeek，否则 Ollama
# - deepseek：只用云端，须配置 DEEPSEEK_API_KEY
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b").strip()

# —— AI 生成速度与篇幅（可选调优）——
# max_tokens 越小通常越快、回复越短；测评长文默认 2000，树洞默认 1200。
LLM_EVAL_MAX_TOKENS = int(os.getenv("LLM_EVAL_MAX_TOKENS", "2000"))
LLM_CHAT_MAX_TOKENS = int(os.getenv("LLM_CHAT_MAX_TOKENS", "1200"))
LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "120"))
LLM_TEMP_EVAL = float(os.getenv("LLM_TEMP_EVAL", "0.65"))
LLM_TEMP_CHAT = float(os.getenv("LLM_TEMP_CHAT", "0.75"))

#仅 Ollama：限制上下文长度可缩短 prefill、加快首字（视模型与显存而定；不设置则由 Ollama 默认）
_ctx_raw = os.getenv("OLLAMA_NUM_CTX", "").strip()
OLLAMA_NUM_CTX: int | None = int(_ctx_raw) if _ctx_raw.isdigit() else None
