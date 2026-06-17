"""成员C：心灵树洞（AI 对话）"""
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

# 导入全局配置参数（如Token限制、温度、超时时间、模型地址等
from config import (
    DEEPSEEK_API_KEY, LLM_CHAT_MAX_TOKENS, LLM_PROVIDER,
    LLM_TEMP_CHAT, LLM_TIMEOUT_SEC, OLLAMA_BASE_URL, OLLAMA_MODEL,
)
# 导入依赖项：获取当前登录学生的 ID 和用户名
from deps import get_current_student_id, get_current_student_username
# 导入数据模型与统一响应格式工具
from llm_client import (
    build_companion_system_prompt, chat_available,
    iter_llm_chat_sse, llm_chat, ollama_effective_base_url,
)
# 导入数据模型与统一响应格式工具
from schemas import AiChatBody, ApiResponse, err, ok

# 创建路由器，并设置统一的 API 前缀
router = APIRouter(prefix="/api/v1")
_log = logging.getLogger(__name__)

"""
启发式检测：AI 是否发生了“指令泄露”（Prompt Injection/Leakage）。
部分开源小模型在对话时，可能会错误地将内部 messages 数组作为纯文本输出。
此函数通过检查前 280 个字符是否包含 '"messages"' 来进行快速拦截。
"""
def _looks_like_messages_json_echo(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 15 or not t.startswith("{"):
        return False
    return '"messages"' in t[:280].lower()

"""
    格式化 SSE (Server-Sent Events) 数据行。
    ensure_ascii=False 确保 JSON 中的中文不被转义为 Unicode 编码。
"""
def _ai_chat_sse_line(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

"""
    同步 AI 对话接口。等待大模型完整生成后，一次性返回全部文本。
"""
@router.post(
    "/ai/chat", response_model=ApiResponse,
    summary="心灵树洞多轮对话",
    description="请求体为 `messages`：OpenAI 风格对话数组，最后一项的 `role` 须为 `user`。",
)
def ai_chat(body: AiChatBody, username: str = Depends(get_current_student_username)):
    if body.messages[-1].role != "user":
        return err(400, "最后一条消息须来自用户")
    if not chat_available():
        return err(503, "当前为仅 DeepSeek 模式但未配置密钥。请在 .env 设置 DEEPSEEK_API_KEY，或设置 LLM_PROVIDER=ollama。")

    api_messages = [{"role": "system", "content": build_companion_system_prompt(username)}]
    for m in body.messages:
        api_messages.append({"role": m.role, "content": m.content.strip()})

    res = llm_chat(api_messages, max_tokens=LLM_CHAT_MAX_TOKENS, temperature=LLM_TEMP_CHAT, timeout=LLM_TIMEOUT_SEC)
    if not res.text:
        return err(503, res.user_hint or "AI 暂时无法响应，请稍后重试")
    if _looks_like_messages_json_echo(res.text):
        _log.warning("AI 回复疑似误输出 messages JSON 载荷")
        return err(503, "模型误把对话 JSON 当作内容输出。请重试；若反复出现请更换 Ollama 模型。")
    return ok({"reply": res.text, "llm_backend": res.backend}, "ok")


"""
    流式 AI 对话接口。采用 Server-Sent Events (SSE) 协议，逐字返回生成内容，
    极大提升用户在长文本生成时的交互体验。
"""
@router.post("/ai/chat/stream", summary="心灵树洞流式对话（SSE）")
def ai_chat_stream(body: AiChatBody, username: str = Depends(get_current_student_username)):
    if body.messages[-1].role != "user":
        return err(400, "最后一条消息须来自用户")
    if not chat_available():
        return err(503, "当前为仅 DeepSeek 模式但未配置密钥。请在 .env 设置 DEEPSEEK_API_KEY，或设置 LLM_PROVIDER=ollama。")

    api_messages = [{"role": "system", "content": build_companion_system_prompt(username)}]
    for m in body.messages:
        api_messages.append({"role": m.role, "content": m.content.strip()})

    def generate():
        acc: list[str] = []
        try:
            for item in iter_llm_chat_sse(
                api_messages, max_tokens=LLM_CHAT_MAX_TOKENS,
                temperature=LLM_TEMP_CHAT, timeout=LLM_TIMEOUT_SEC,
            ):
                ev = item.get("event")
                if ev == "chunk":
                    t = item.get("text") or ""
                    acc.append(t)
                    yield _ai_chat_sse_line({"type": "chunk", "text": t})
                elif ev == "done":
                    full = "".join(acc)
                    if _looks_like_messages_json_echo(full):
                        _log.warning("AI 流式回复疑似误输出 messages JSON 载荷")
                        yield _ai_chat_sse_line({"type": "error", "message": "模型误把对话 JSON 当作内容输出，请重试或更换模型。"})
                    else:
                        yield _ai_chat_sse_line({"type": "done", "llm_backend": item.get("llm_backend")})
                elif ev == "error":
                    yield _ai_chat_sse_line({"type": "error", "message": item.get("message") or "AI 暂时无法响应"})
        except Exception as e:
            _log.warning("ai/chat/stream: %s", e)
            yield _ai_chat_sse_line({"type": "error", "message": str(e)[:400]})

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

"""
    获取 AI 模块的公开配置状态。
    前端在初始化聊天界面时调用此接口，以决定展示“AI 聊天”还是“仅本地模式提示”。
"""
@router.get("/ai/public-config", response_model=ApiResponse)
def ai_public_config():
    return ok({
        "deepseek_configured": bool(DEEPSEEK_API_KEY), "llm_provider": LLM_PROVIDER,
        "ollama_model": OLLAMA_MODEL, "ollama_base_url": OLLAMA_BASE_URL,
        "ollama_effective_url": ollama_effective_base_url(),
        "chat_available": chat_available(),
        "free_local_tip": f"免费本机对话：安装 Ollama 后执行 ollama pull {OLLAMA_MODEL}，并设置 LLM_PROVIDER=ollama（或保持 auto 且不配置 DeepSeek 密钥）",
    }, "ok")
