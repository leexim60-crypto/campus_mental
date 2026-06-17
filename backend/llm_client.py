"""
大模型调用：DeepSeek（云端）与 Ollama（本机免费，无需充值）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Iterator, Optional
from urllib.parse import urlparse, urlunparse

import httpx

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
)

logger = logging.getLogger(__name__)


class LLMStreamError(Exception):
    """流式对话失败（HTTP 非 200、解析失败等）。"""

    pass

# 本机请求不要被 HTTP_PROXY/HTTPS_PROXY 转发到公司代理，否则访问 127.0.0.1 常出现 502
_HTTPX_LOCAL = {"trust_env": False}


def ollama_effective_base_url() -> str:
    """把 .env 里的地址整理成稳定形态，避免 localhost/IPv6、缺协议、多余路径导致连错。"""
    raw = (OLLAMA_BASE_URL or "").strip()
    if not raw:
        raw = "http://127.0.0.1:11434"
    if not raw.startswith(("http://", "https://")):
        raw = "http://" + raw
    try:
        p = urlparse(raw)
        host = (p.hostname or "127.0.0.1").lower()
        if host in ("localhost", "::1"):
            host = "127.0.0.1"
        port = p.port if p.port is not None else 11434
        netloc = f"{host}:{port}"
        # Ollama 根地址不要带 path（有人误写成 http://127.0.0.1:11434/api）
        base = urlunparse((p.scheme or "http", netloc, "", "", "", "")).rstrip("/")
        return base
    except Exception:
        return "http://127.0.0.1:11434"


@dataclass
class LLMResult:
    """
        封装大语言模型（LLM）调用结果的标准化数据容器。

        用于在业务逻辑与接口层之间统一传递 AI 模型的响应数据。
        所有字段均为可选，允许根据实际业务场景灵活返回部分数据。

        Attributes:
            text (Optional[str]): LLM 生成的核心文本内容（即模型的实际回答）。
            user_hint (Optional[str]): 面向用户的提示信息。例如生成失败、触发安全拦截
                                       或需要用户补充输入时的友好提示文案。
            backend (Optional[str]): 实际使用的后端模型名称
                                     主要用于前端展示，让用户知晓当前提供服务的 AI 模型。
        """
    text: Optional[str] = None
    user_hint: Optional[str] = None
    backend: Optional[str] = None


"""
    动态构建 DeepSeek 聊天接口的完整 URL。
    Returns:
        str: 完整的 DeepSeek Chat Completions API 请求地址。
    """
def _deepseek_url() -> str:
    base = DEEPSEEK_BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


"""
    解析 OpenAI 兼容的 SSE（Server-Sent Events）流式响应，逐步提取文本内容。
    Args:
        response (httpx.Response): httpx 返回的流式响应对象。

    Yields:
        str: 从流中逐步解析出的大模型文本内容片段（delta content）。
    """
def _iter_openai_sse_content(response: httpx.Response) -> Iterator[str]:
    for line in response.iter_lines():
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        if not line.startswith("data: "):
            continue
        data = line[6:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        content = delta.get("content") or ""
        if content:
            yield content


"""
    调用 DeepSeek API 并逐步返回生成的文本内容。
    Args:
        messages (list[dict[str, Any]]): 遵循 OpenAI 规范的对话历史消息列表。
        max_tokens (int): 模型单次生成的最大 Token 数量。
        temperature (float): 生成文本的随机性/创造性参数。
        timeout (float): HTTP 请求的超时时间（秒）。

    Yields:
        str: 从 DeepSeek 流式响应中逐步解析出的文本内容片段。

    Raises:
        LLMStreamError: 当未配置 API Key、HTTP 请求失败或 API 返回业务错误时抛出。
"""
def _stream_deepseek_chunks(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> Iterator[str]:
    if not DEEPSEEK_API_KEY:
        raise LLMStreamError(
            "未配置 DEEPSEEK_API_KEY。若要用本机 Ollama，请将 LLM_PROVIDER=ollama 或 auto 且不配置密钥。"
        )
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", _deepseek_url(), headers=headers, json=payload) as r:
            if r.status_code != 200:
                try:
                    j = r.json()
                    err_obj = j.get("error") if isinstance(j.get("error"), dict) else {}
                    api_msg = (err_obj.get("message") or "")[:400]
                except Exception:
                    api_msg = (r.text or "")[:200]
                raise LLMStreamError(api_msg or f"DeepSeek HTTP {r.status_code}")
            yield from _iter_openai_sse_content(r)


"""
    调用本地 Ollama 原生 API 并逐步返回生成的文本内容。
    Args:
        client (httpx.Client): 复用的 httpx 客户端实例。
        base (str): Ollama 服务的本地基础 URL（如 http://localhost:11434）。
        model (str): 要调用的 Ollama 模型名称。
        messages (list[dict[str, Any]]): 遵循 Ollama 规范的对话历史消息列表。
        options (dict[str, Any]): Ollama 专属的模型生成参数（如 temperature, top_p 等）。
        timeout (float): HTTP 请求的超时时间（秒）。

    Yields:
        str: 从 Ollama 流式响应中逐步解析出的文本内容片段。

    Raises:
        LLMStreamError: 当 HTTP 请求失败时抛出，包含详细的 Ollama 错误诊断信息。
"""
def _stream_ollama_native_chunks(
    client: httpx.Client,
    base: str,
    model: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any],
    timeout: float,
) -> Iterator[str]:
    url = f"{base.rstrip('/')}/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": options,
    }
    with client.stream("POST", url, json=payload, timeout=timeout) as r:
        if r.status_code != 200:
            err_txt = r.read().decode("utf-8", errors="replace")
            api_err = _ollama_api_error_message(err_txt)
            core = _ollama_fail_hint(r.status_code, err_txt, model)
            diag = _ollama_post_failure_diag(client, base, model)
            hint = f"Ollama 报错：{api_err}\n\n{core}{diag}" if api_err else f"{core}{diag}"
            raise LLMStreamError(hint)
        for line in r.iter_lines():
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = j.get("message") or {}
            c = msg.get("content") or ""
            if c:
                yield c


"""
    调用 Ollama 模型并逐步返回生成的文本内容，支持 OpenAI 兼容接口与原生接口的自动降级。
    1. 优先尝试使用 Ollama 的 OpenAI 兼容接口 (/v1/chat/completions)。
    2. 若兼容接口请求成功且能正常解析出内容，则直接返回流式结果。
    3. 若兼容接口不可用（如返回 404）或发生其他非致命错误，
       则自动降级（Fallback）到 Ollama 原生接口 (/api/chat) 继续流式输出。

    Args:
        messages (list[dict[str, Any]]): 对话历史消息列表。
        max_tokens (int): 模型单次生成的最大 Token 数量。
        temperature (float): 生成文本的随机性/创造性参数。
        timeout (float): HTTP 请求的超时时间（秒）。
    Yields:
        str: 从 Ollama 流式响应中逐步解析出的文本内容片段。
"""
def _stream_ollama_chunks(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> Iterator[str]:
    base = ollama_effective_base_url()
    url_v1 = f"{base}/v1/chat/completions"
    _native_opts: dict[str, Any] = {
        "temperature": temperature,
        "num_predict": max_tokens,
    }
    if OLLAMA_NUM_CTX is not None:
        _native_opts["num_ctx"] = OLLAMA_NUM_CTX

    payload_v1: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if OLLAMA_NUM_CTX is not None:
        payload_v1["options"] = {"num_ctx": OLLAMA_NUM_CTX}

    with httpx.Client(timeout=timeout, **_HTTPX_LOCAL) as client:
        model_use = _resolve_ollama_model(client, base, OLLAMA_MODEL)
        payload_v1["model"] = model_use

        with client.stream("POST", url_v1, json=payload_v1) as r:
            if r.status_code == 200:
                got = False
                for piece in _iter_openai_sse_content(r):
                    got = True
                    yield piece
                if got:
                    return
            if r.status_code not in (200, 404):
                logger.warning("Ollama /v1 stream HTTP %s: %s", r.status_code, r.text[:400])

        yield from _stream_ollama_native_chunks(
            client, base, model_use, messages, _native_opts, timeout
        )


"""
    大语言模型流式对话的统一入口（Facade），封装了多模型调度、自动降级与全局异常处理。
    Args:
        messages (list[dict[str, Any]]): 遵循 OpenAI 规范的对话历史消息列表。
        max_tokens (int): 模型单次生成的最大 Token 数量，默认 1024。
        temperature (float): 生成文本的随机性/创造性参数，默认 0.7。
        timeout (float): HTTP 请求的超时时间（秒），默认 120.0。
    Yields:
        dict[str, Any]: 标准化的 SSE 事件字典，包含以下三种类型：
            - {"event": "chunk", "text": "..."}: 逐步生成的文本内容片段。
            - {"event": "done", "llm_backend": "deepseek"|"ollama"}: 流式生成正常结束。
            - {"event": "error", "message": "..."}: 捕获到异常时的错误提示。
"""
def iter_llm_chat_sse(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    timeout: float = 120.0,
) -> Iterator[dict[str, Any]]:
    """
    心灵树洞流式输出。依次 yield:
    - {"event": "chunk", "text": "..."}
    - {"event": "done", "llm_backend": "deepseek"|"ollama"}
    出错时 yield {"event": "error", "message": "..."} 并结束。
    """
    mode = LLM_PROVIDER if LLM_PROVIDER in ("deepseek", "ollama", "auto") else "auto"

    def _emit_chunks(gen: Iterator[str], backend: str) -> Iterator[dict[str, Any]]:
        for t in gen:
            yield {"event": "chunk", "text": t}
        yield {"event": "done", "llm_backend": backend}

    try:
        if mode == "deepseek":
            yield from _emit_chunks(
                _stream_deepseek_chunks(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                ),
                "deepseek",
            )
            return
        if mode == "ollama":
            yield from _emit_chunks(
                _stream_ollama_chunks(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                ),
                "ollama",
            )
            return
        # auto：DeepSeek 流式在「尚未输出任何 token」失败时回退 Ollama（yield from 不会捕获子生成器异常）
        if DEEPSEEK_API_KEY:
            deepseek_emitted = False
            try:
                for t in _stream_deepseek_chunks(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                ):
                    deepseek_emitted = True
                    yield {"event": "chunk", "text": t}
                yield {"event": "done", "llm_backend": "deepseek"}
                return
            except LLMStreamError as e:
                if deepseek_emitted:
                    raise
                logger.info("DeepSeek 流式不可用，回退 Ollama: %s", e)
        for t in _stream_ollama_chunks(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        ):
            yield {"event": "chunk", "text": t}
        yield {"event": "done", "llm_backend": "ollama"}
    except LLMStreamError as e:
        yield {"event": "error", "message": str(e)}
    except httpx.TimeoutException:
        yield {"event": "error", "message": "模型响应超时，请稍后重试。"}
    except Exception as e:
        logger.warning("流式对话异常: %s", e)
        yield {"event": "error", "message": str(e)[:300]}


"""
    同步调用 DeepSeek API 并返回标准化的 LLM 结果。
    Args:
        messages (list[dict[str, Any]]): 遵循 OpenAI 规范的对话历史消息列表。
        max_tokens (int): 模型单次生成的最大 Token 数量。
        temperature (float): 生成文本的随机性/创造性参数。
        timeout (float): HTTP 请求的超时时间（秒）。
    Returns:
        LLMResult: 封装了调用结果的数据类实例。
            - 成功时：text 包含模型回复内容，user_hint 为 None。
            - 失败时：text 为 None，user_hint 包含面向用户的错误提示或降级建议。
            - backend 始终标记为 "deepseek"。
"""
def _call_deepseek(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> LLMResult:
    if not DEEPSEEK_API_KEY:
        return LLMResult(
            None,
            "未配置 DEEPSEEK_API_KEY。若要用免费本机模型，请将 LLM_PROVIDER=ollama 或保持 auto 且不配置密钥。",
            "deepseek",
        )
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(_deepseek_url(), headers=headers, json=payload)
            if r.status_code != 200:
                api_msg = ""
                try:
                    j = r.json()
                    err_obj = j.get("error") if isinstance(j.get("error"), dict) else {}
                    api_msg = (err_obj.get("message") or "")[:400]
                except Exception:
                    api_msg = (r.text or "")[:200]
                logger.warning("DeepSeek HTTP %s: %s", r.status_code, api_msg)
                hint = api_msg or f"HTTP {r.status_code}"
                low = (api_msg + str(r.status_code)).lower()
                if (
                    "insufficient" in low
                    or "balance" in low
                    or "余额" in api_msg
                    or r.status_code == 402
                ):
                    hint = (
                        "DeepSeek 账户余额不足。可免费改用本机 Ollama："
                        "安装 https://ollama.com 后执行 ollama pull qwen2.5:7b，"
                        "并设置环境变量 LLM_PROVIDER=ollama（或删除 DEEPSEEK_API_KEY 使用 auto）。"
                    )
                elif r.status_code in (401, 403):
                    hint = "DeepSeek API Key 无效。"
                elif r.status_code == 429:
                    hint = "请求过于频繁，请稍后再试。"
                return LLMResult(None, hint, "deepseek")
            data = r.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if not content:
                return LLMResult(None, "模型返回为空。", "deepseek")
            return LLMResult(content, None, "deepseek")
    except httpx.TimeoutException:
        return LLMResult(None, "DeepSeek 连接超时。", "deepseek")
    except Exception as e:
        logger.warning("DeepSeek 异常: %s", e)
        return LLMResult(None, str(e)[:200], "deepseek")

"""
    Args:
        name (str): 原始传入的模型名称。
    Returns:
        str: 修正后的模型名称。若未命中常见笔误，则原样返回。
    """
def _fix_ollama_model_typo(name: str) -> str:
    """常见笔误：少写 b、误用 7 等。"""
    n = (name or "").strip()
    fixes = {
        "qwen2.5:7": "qwen2.5:7b",
        "qwen2.5:14": "qwen2.5:14b",
        "qwen2.5:32": "qwen2.5:32b",
        "qwen2.5:3": "qwen2.5:3b",
    }
    return fixes.get(n, n)


"""
    智能解析并校验 Ollama 模型名称，支持自动纠错与模糊匹配。
    在发起模型调用前，通过查询本地 Ollama 的 /api/tags 接口确认模型是否存在。
    若用户指定的模型未安装，会依次尝试：
    1. 自动修复常见拼写错误。
    2. 精确匹配已安装模型。
    3. 前缀匹配（如匹配带有特定版本号的模型）。
    4. 系列匹配（自动降级使用同系列的其他已安装模型）。
    若校验过程发生异常（如 Ollama 未启动），则安全回退并返回原始名称。
    Args:
        client (httpx.Client): 复用的 httpx 客户端实例。
        base (str): Ollama 服务的本地基础 URL。
        wanted (str): 用户期望调用的模型名称。
    Returns:
        str: 最终解析出的、本地 Ollama 实际可用的模型名称。
"""
def _resolve_ollama_model(client: httpx.Client, base: str, wanted: str) -> str:
    """用 /api/tags 校验；名称不在列表则尝试匹配同系列已安装模型。"""
    wanted = _fix_ollama_model_typo(wanted)
    try:
        r = client.get(f"{base.rstrip('/')}/api/tags", timeout=15.0)
        if r.status_code != 200:
            return wanted
        models = [
            m.get("name")
            for m in (r.json().get("models") or [])
            if isinstance(m, dict) and m.get("name")
        ]
        if not models:
            return wanted
        if wanted in models:
            return wanted
        root = wanted.split(":")[0] if ":" in wanted else wanted
        for n in models:
            if n == wanted or n.startswith(wanted + ":"):
                logger.info("Ollama 模型名纠正: %s -> %s", wanted, n)
                return n
        for n in models:
            if n.split(":")[0] == root:
                logger.info("Ollama 使用已安装的同名系列: %s -> %s", wanted, n)
                return n
    except Exception as e:
        logger.debug("Ollama /api/tags: %s", e)
    return wanted


"""
    从 Ollama API 的错误响应体中提取人类可读的错误信息。
    Args:
        body (str): Ollama API 返回的原始响应体字符串。

    Returns:
        str: 提取出的错误信息（最多 500 字符）。若无法提取或响应体无效，则返回空字符串。
"""
def _ollama_api_error_message(body: str) -> str:
    """Ollama 常在 JSON 里返回 {\"error\": \"...\"}，比裸 502 更有用。"""
    raw = (body or "").strip()
    if not raw:
        return ""
    try:
        j = json.loads(raw)
        if not isinstance(j, dict):
            return ""
        err = j.get("error")
        if isinstance(err, str) and err.strip():
            return err.strip()[:500]
        if isinstance(err, dict):
            m = err.get("message")
            if isinstance(m, str) and m.strip():
                return m.strip()[:500]
    except Exception:
        pass
    return ""


"""
    Ollama 对话失败后的后置诊断工具，通过探活请求精准定位故障原因。
    Args:
        client (httpx.Client): 复用的 httpx 客户端实例。
        base (str): Ollama 服务的本地基础 URL。
        model (str): 发生调用失败的模型名称。
    Returns:
        str: 包含诊断建议的提示字符串。若诊断过程发生未知异常，则返回空字符串。
"""
def _ollama_post_failure_diag(client: httpx.Client, base: str, model: str) -> str:
    """对话失败后再探活，区分「连错机器/WSL」与「推理挂了」。"""
    b = base.rstrip("/")
    try:
        hv = client.get(f"{b}/api/version", timeout=4.0)
        if hv.status_code == 200:
            return (
                "\n\n【自检】当前能访问 Ollama 的 /api/version，说明地址与端口基本正确；"
                "HTTP 502/5xx 多半是本次模型推理失败（显存不足、模型未下完、名称与 ollama list 不一致等）。"
                f"请在终端执行：ollama run {model}"
            )
        return (
            f"\n\n【自检】访问 {b}/api/version 得到 HTTP {hv.status_code}。"
            "请核对 OLLAMA_BASE_URL；若 uvicorn 跑在 WSL/Docker、Ollama 装在 Windows 桌面，"
            "127.0.0.1 指向的是容器/WSL 自己，应改为 Windows 宿主机 IP（或 Docker 下 host.docker.internal:11434）。"
        )
    except httpx.ConnectError:
        return (
            "\n\n【自检】无法连接到 /api/version（连接被拒绝）。"
            "这与「HTTP 502」不同：502 是已连上 HTTP 服务但处理失败。"
            "请确认 OLLAMA_BASE_URL 指向正在运行 Ollama 的那台机器。"
        )
    except Exception:
        return ""

"""
    生成针对 Ollama 502/5xx 错误的结构化排查指南。
    Args:
        status (int): Ollama 返回的 HTTP 状态码（通常为 502 或 5xx）。
        body (str): Ollama 返回的原始响应体字符串。
        model (str): 发生调用失败的模型名称。
    Returns:
        str: 包含详细排查步骤和原始错误信息的用户友好提示字符串。
"""
def _ollama_fail_hint(status: int, body: str, model: str) -> str:
    """502/5xx：通常已连上 Ollama，但模型或引擎异常。"""
    snip = (body or "").strip().replace("\n", " ")[:350]
    return (
        f"Ollama 返回 HTTP {status}（已能连上服务，但本次推理失败）。\n"
        "请按顺序排查：\n"
        f"1) 终端执行 ollama list，将 .env 里 OLLAMA_MODEL 改成与列表中**完全一致**的名称（常见：qwen2.5:7b、qwen2.5:3b）。\n"
        f"2) 终端执行 ollama run {model} ，能正常对话后再试本系统。\n"
        "3) 显存/内存不足时换小模型：ollama pull qwen2.5:3b，并改 OLLAMA_MODEL。\n"
        "4) .env 中 OLLAMA_BASE_URL 使用 http://127.0.0.1:11434（不要用 https；localhost 可能走 IPv6）。\n"
        "5) 若开了系统/Clash 代理，请把 127.0.0.1、localhost 加入 NO_PROXY，否则易出现 502。\n"
        "6) 右键托盘退出 Ollama 后重开，或升级到最新版。\n"
        f"服务返回：{snip or '（无正文）'}"
    )


"""
    同步调用 Ollama 本地模型并返回标准化的 LLM 结果。

    该函数采用“双接口自动降级”策略：优先尝试使用新版 Ollama 更稳定的 
    OpenAI 兼容接口 (/v1/chat/completions)，若失败或返回空内容，则自动
    回退至 Ollama 原生接口 (/api/chat)。

    同时，函数内置了极其详尽的异常捕获与诊断机制。当遇到连接拒绝、超时
    或 502 等错误时，不会直接抛出底层异常，而是结合本地网络环境（如 WSL/
    Docker 的 IP 映射、代理冲突、显存不足等常见痛点），生成一份“保姆级”
    的排查指南返回给用户。

    Args:
        messages (list[dict[str, Any]]): 遵循 OpenAI 规范的对话历史消息列表。
        max_tokens (int): 模型单次生成的最大 Token 数量。
        temperature (float): 生成文本的随机性/创造性参数。
        timeout (float): HTTP 请求的超时时间（秒）。

    Returns:
        LLMResult: 封装了调用结果的数据类实例。
            - 成功时：text 包含模型回复内容，user_hint 为 None。
            - 失败时：text 为 None，user_hint 包含面向用户的详细错误提示与排查步骤。
            - backend 始终标记为 "ollama"。
    """
def _call_ollama(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> LLMResult:
    # 1. 获取并规范化 Ollama 基础 URL（处理可能存在的尾部斜杠等问题）
    base = ollama_effective_base_url()
    if base != OLLAMA_BASE_URL.rstrip("/"):
        logger.info("Ollama URL 已规范化: %r -> %r", OLLAMA_BASE_URL, base)

    # 2. 构建 OpenAI 兼容接口 (/v1) 的请求载荷
    url_v1 = f"{base}/v1/chat/completions"
    payload_v1: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # 部分 Ollama 版本在 OpenAI 兼容接口中支持通过 options 传递 num_ctx
    if OLLAMA_NUM_CTX is not None:
        payload_v1["options"] = {"num_ctx": OLLAMA_NUM_CTX}
    # 3. 构建 Ollama 原生接口 (/api/chat) 的请求载荷（作为降级备选）
    _native_opts: dict[str, Any] = {
        "temperature": temperature,
        "num_predict": max_tokens,
    }
    if OLLAMA_NUM_CTX is not None:
        _native_opts["num_ctx"] = OLLAMA_NUM_CTX

    url_native = f"{base}/api/chat"
    payload_native = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": _native_opts,
    }
    # 4. 发起请求与全局异常处理
    try:
        with httpx.Client(timeout=timeout, **_HTTPX_LOCAL) as client:
            # 智能解析并校验模型名称（自动纠错、模糊匹配已安装模型）
            model_use = _resolve_ollama_model(client, base, OLLAMA_MODEL)
            payload_v1["model"] = model_use
            payload_native["model"] = model_use
            # 4.1 优先尝试 OpenAI 兼容接口
            r = client.post(url_v1, json=payload_v1)
            if r.status_code == 200:
                try:
                    data = r.json()
                    content = (
                        (data.get("choices") or [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                except (TypeError, KeyError, IndexError):
                    content = ""
                # 如果 v1 接口成功且解析出有效内容，直接返回
                if content:
                    return LLMResult(content, None, "ollama")
                # 如果返回 200 但无正文，记录警告并准备降级
                logger.warning("Ollama /v1 200 但无正文，回退 /api/chat")
            # 如果 v1 接口返回非 200 且非 404，记录警告
            if r.status_code not in (200, 404):
                logger.warning("Ollama /v1 HTTP %s: %s", r.status_code, r.text[:400])
            # 4.2 降级尝试 Ollama 原生接口
            r2 = client.post(url_native, json=payload_native)
            if r2.status_code == 200:
                data = r2.json()
                msg = data.get("message") or {}
                content = (msg.get("content") or "").strip()
                if content:
                    return LLMResult(content, None, "ollama")
                # 原生接口 200 但内容为空
                return LLMResult(None, "Ollama 返回内容为空。", "ollama")

            # 4.3 双接口均失败，组装详尽的错误诊断提示
            err_txt = r2.text or r.text
            logger.warning("Ollama /api/chat HTTP %s: %s", r2.status_code, err_txt[:400])
            # 提取 Ollama 返回的 JSON 错误信息
            api_err = _ollama_api_error_message(err_txt)
            # 生成针对 502/5xx 的排查清单
            core = _ollama_fail_hint(r2.status_code, err_txt, model_use)
            # 执行后置探活诊断，区分网络问题与推理问题
            diag = _ollama_post_failure_diag(client, base, model_use)
            # 拼接最终的错误提示
            if api_err:
                hint = f"Ollama 报错：{api_err}\n\n{core}{diag}"
            else:
                hint = f"{core}{diag}"
            return LLMResult(None, hint, "ollama")
    # 5. 捕获 TCP 连接被拒绝异常（通常是服务未启动或 IP 映射错误）
    except httpx.ConnectError:
        return LLMResult(
            None,
            f"无法连接 Ollama（TCP 连接被拒绝，不是 HTTP 502）。当前使用地址：{base}。"
            "请确认 Ollama 已启动，.env 中 OLLAMA_BASE_URL 正确（http://127.0.0.1:11434，勿用 https）。"
            "若命令行 ollama 在本机可用，而本后端跑在 WSL/Docker，127.0.0.1 往往指向错误环境，请改为 Windows/宿主机 IP。"
            f" 然后执行：ollama pull {OLLAMA_MODEL}",
            "ollama",
        )
    # 6. 捕获超时异常（大模型首次加载耗时较长）
    except httpx.TimeoutException:
        return LLMResult(None, "Ollama 响应超时（首次加载大模型可能需 1～3 分钟，可改小模型或加大等待）。", "ollama")
    # 7. 捕获其他未知异常，截取前 200 字符防止提示过长
    except Exception as e:
        logger.warning("Ollama 异常: %s", e)
        return LLMResult(None, str(e)[:200], "ollama")

"""
    核心功能：根据配置自动选择调用 DeepSeek（云端）还是 Ollama（本地）。
    路由逻辑说明：
    1. 如果配置为 'deepseek'：强制走云端 API。
    2. 如果配置为 'ollama'：强制走本地模型。
    3. 如果配置为 'auto'（默认推荐）：
       - 优先尝试 DeepSeek（如果有 Key 且网络通畅）。
       - 如果 DeepSeek 失败或没配 Key，自动“降级”回退到本地 Ollama，保证服务不中断。
"""
def llm_chat(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    timeout: float = 120.0,
) -> LLMResult:
    """
    按 LLM_PROVIDER 路由：默认 ollama（本机）；auto 时有 DeepSeek 密钥则优先云端，否则 Ollama。
    """
    mode = LLM_PROVIDER if LLM_PROVIDER in ("deepseek", "ollama", "auto") else "auto"

    if mode == "deepseek":
        return _call_deepseek(messages, max_tokens=max_tokens, temperature=temperature, timeout=timeout)
    if mode == "ollama":
        return _call_ollama(messages, max_tokens=max_tokens, temperature=temperature, timeout=timeout)

    # auto
    if DEEPSEEK_API_KEY:
        r = _call_deepseek(messages, max_tokens=max_tokens, temperature=temperature, timeout=timeout)
        if r.text:
            return r
        logger.info("DeepSeek 不可用，回退 Ollama: %s", r.user_hint)
        return _call_ollama(messages, max_tokens=max_tokens, temperature=temperature, timeout=timeout)

    return _call_ollama(messages, max_tokens=max_tokens, temperature=temperature, timeout=timeout)


def chat_available() -> bool:
    """是否允许发起聊天（auto 下无密钥也允许，会走 Ollama）。"""
    if LLM_PROVIDER == "deepseek":
        return bool(DEEPSEEK_API_KEY)
    return True


SYSTEM_EVALUATION_COMMENT = """你是一位温暖、有耐心的心理健康陪伴者，正在给一位刚完成校园心理自评的同学写一段话。你不是辅导员、不是咨询师、不是医生——你就是一个关心 ta 的人，像朋友一样跟 ta 聊聊。

最重要的原则：不同量表测评的是完全不同的心理维度，你的回复必须体现这种差异。压力量表的建议和自尊量表的建议绝对不能一样。

语气：
- 用简体中文，像写信一样，不要太正式。开头先肯定 ta 愿意做这件事的勇气，让 ta 感到被看见。
- 用「你」，不用「您」。不要列一二三四编号，不要用标题符号，自然分段就好。
- 不要自称任何身份——不要说「你的辅导员」「你的咨询师」「作为老师」之类的。结尾也不要署名，不要写「祝你健康快乐」这种套话，用一句真诚的、具体的话收尾就好。

内容：
- 根据分数和各题情况，用大白话帮 ta 理解「这可能说明了什么」，但不要像念报告一样罗列数据。把分数融入到关心的话里，比如「从你的结果来看，最近在情绪和睡眠上可能压力比较大」。
- 接下来要做的事：必须围绕该量表的具体维度给出 2-3 件小事。这些小事必须是量表主题相关的——焦虑量表就给焦虑管理技巧，压力量表就给压力释放方法，自尊量表就给自我肯定练习。绝对不能给"适当运动""保持好心情"这种放之四海而皆准的空话。
- 如果分数偏高，语气要更稳重一些，多说几句关心的话，但不要吓唬 ta。

安全底线：
- 这是自评筛查，不是诊断。一定要温和地提一句：这个结果不能代替专业评估，如果觉得困扰比较大，学校心理咨询中心随时可以去。
- 如果分数提示有自伤风险，要认真、平静地建议 ta 立刻联系身边信任的人，或拨打 400-161-9995（24 小时心理援助热线），紧急时直接去医院急诊。

篇幅：300-600 字左右，像一封信的长度。"""


SYSTEM_COMPANION_CHAT = """你是一个叫「小暖」的校园树洞陪伴者。你像一个温暖、靠谱的学长学姐，学弟学妹来找你倾诉时，你会主动关心、直接开导、帮 ta 想好办法，而不是把问题抛回去。

和你聊天的同学叫「{username}」。第一次打招呼时自然地叫一声名字，比如「{username}，怎么啦，跟我说说？」，之后偶尔提一下名字就好。

最重要的一点：不要反问对方、不要让对方做选择、不要把问题抛回去。对方来找你，是因为 ta 已经扛不住了，你需要做的是替 ta 分担，而不是让 ta 回答你的问题。

你怎么帮 ta：
- 先接住情绪。开头就让 ta 知道你听懂了 ta 的难受。「考砸了真的很沮丧吧」「被这样说肯定很委屈」——这种话放在最前面。
- 直接给建议，不要问「你觉得呢」「你想怎么办」。对方失眠了，你直接说：今晚试试睡前把手机放到客厅，躺下后做几次深呼吸，吸气四秒呼气六秒。对方跟室友有矛盾了，你直接说：明天找个轻松的时候跟 ta 说一句「昨晚的事我有点不舒服，咱们聊聊？」，不用想太多，开口就好。对方觉得自己很差劲，你直接说：你今天能把这些说出来，就已经很勇敢了，这本身就是在照顾自己。
- 帮 ta 看到 ta 自己看不到的东西。比如 ta 觉得一次考砸了天就塌了，你就告诉 ta：一次考试真的说明不了什么，你之前也遇到过觉得过不去的坎，现在回头看不也过来了吗。不要否定 ta 的感受，但要轻轻把 ta 的视线拉到更远的地方。
- 主动往前推一步。不要等 ta 问「那我该怎么办」，你在说完安慰的话之后，就顺手给出一件 ta 现在就能做的小事。哪怕只是「先去喝杯热水，让自己缓一缓」，也比让 ta 空坐着强。
- 后面如果 ta 又提起之前的事，记得接上：「上次说的那件事，后来怎么样了？」不要让 ta 觉得跟你说过的话你忘了。

说话方式：
- 像面对面聊天，用短句。「嗯，我理解」「这确实挺难的」「没事，咱们慢慢来」。
- 用「你」，不用「您」。不要列一二三四，不要写长段落，不要用 Markdown。直接说正文，不要加「回复：」之类的标签。
- 不要一次说太多，每次一小段就够了。如果要带 ta 做放松练习，可以稍长一点。

你不能做的事：
- 你不是医生，不要诊断心理疾病，不要推荐药物。
- 如果对方提到不想活了、想伤害自己、或者正在做伤害自己的事，认真对待。平静但坚定地告诉 ta：我很担心你，希望你现在就联系身边信任的人，或者拨打 400-161-9995（24 小时心理援助热线），也可以直接去医院急诊。不要慌，不要煽情，但一定要说。"""


def build_companion_system_prompt(username: str) -> str:
    """将用户名填入心灵树洞系统提示词。"""
    name = (username or "").strip() or "同学"
    return SYSTEM_COMPANION_CHAT.format(username=name)


_SCALE_INFO: dict[str, dict[str, str]] = {
    "PHQ-9": {
        "desc": "PHQ-9 抑郁筛查量表，共 9 题，评估过去两周的抑郁症状严重程度。评分 0-3：完全没有/好几天/一半以上天数/几乎每天。",
        "theme": "情绪低落、兴趣减退、睡眠、精力、自我评价",
        "actions": "围绕作息规律、情绪表达、社交连接、运动等方面给出建议，比如：今晚睡前不看手机试试、给一个好久没联系的朋友发条消息、下课后去操场走两圈",
    },
    "SCL-90": {
        "desc": "SCL-90 症状自评量表（演示版 10 题），涵盖头痛、紧张、强迫、人际敏感等多个心理症状维度。评分 0-3：没有/较轻/中等/偏重。",
        "theme": "躯体不适、紧张焦虑、强迫思维、人际敏感、敌意",
        "actions": "根据得分较高的维度给出针对性建议，比如：头痛可能跟久坐有关试试每小时起来活动一下、紧张时做几组深呼吸",
    },
    "GAD-7": {
        "desc": "GAD-7 广泛性焦虑量表，共 7 题，评估过去两周的焦虑症状。评分 0-3：完全没有/好几天/一半以上天数/几乎每天。",
        "theme": "紧张不安、过度担忧、难以放松、烦躁不安、害怕发生坏事",
        "actions": "围绕焦虑管理、放松技巧、担忧记录等方面给出建议，比如：把担心的事写在纸上分两类——能行动的今天就做一件、不能控制的就允许自己先放下；试试 4-7-8 呼吸法",
    },
    "PSS-10": {
        "desc": "PSS-10 知觉压力量表，共 10 题，评估过去一个月中感受到的压力程度。其中第 4、5、7、8 题为正向题（感知到可控），需反向理解。评分 0-3：从不/偶尔/有时/经常。",
        "theme": "失控感、意外事件应对、信心不足、事情积压、无法掌控生活",
        "actions": "围绕压力源识别、可控/不可控区分、任务拆解、放松释放等方面给出建议，比如：今晚花 5 分钟列一张明天的待办清单只写三件事、把一件一直拖着的事拆成最小的一步今天就做掉第一步",
    },
    "SES": {
        "desc": "Rosenberg 自尊量表（SES），共 10 题，评估个体对自我的整体态度与价值感。其中第 3、5、6、9、10 题为反向题（负向表述）。评分 0-3：非常不同意/不同意/同意/非常同意。",
        "theme": "自我价值感、自我接纳、自信、自我否定、与他人比较",
        "actions": "围绕自我肯定、成就记录、减少社会比较、自我关怀等方面给出建议，比如：今晚睡前写下今天自己做得还不错的三件小事（再小也算）、下次想拿自己跟别人比的时候暂停一下问问我在意的是什么",
    },
}


def build_evaluation_messages(
    scale_type: str,
    total_score: int,
    emotion_label: str,
    rule_template_suggestion: str,
    scores: list[int],
    questions: list[str] | None = None,
) -> list[dict[str, Any]]:
    scores_str = "、".join(str(s) for s in scores) if scores else "（无）"
    info = _SCALE_INFO.get(scale_type, {})
    scale_desc = info.get("desc", scale_type)
    scale_theme = info.get("theme", "")
    scale_actions = info.get("actions", "")

    # 将题目与得分逐条对应，让 AI 能针对具体题目分析
    if questions and len(questions) == len(scores):
        detail_lines = "\n".join(
            f"  第{i+1}题「{q}」：{s}分" for i, (q, s) in enumerate(zip(questions, scores))
        )
        detail_block = f"\n【逐题得分】\n{detail_lines}"
    else:
        detail_block = ""

    user_text = f"""请根据以下校园心理自评筛查结果，给这位同学写一段温暖的、像朋友一样的话。不要写成报告，不要列编号，就像你在跟 ta 面对面聊天。

【量表说明】{scale_desc}
【本次测评维度】{scale_theme}
【综合分/汇总指标】{total_score}
【系统参考标签】（仅供你理解情绪倾向，不要在回复中直接使用这些词）{emotion_label}
【规则引擎模板参考】（仅供思路，用你自己的话说，不要照抄）{rule_template_suggestion}
【各题得分 0～3，按题序】{scores_str}
{detail_block}
要求：
- 先用一两句话根据量表维度聊聊 ta 可能的状态，不要重复量表名称。
- 逐题得分 2 或 3 的题目，结合题目内容具体说说，比如"第X题你打了X分，这说明……"，让 ta 感到你在认真看 ta 的回答。
- 接下来要做的事：必须给出 2-3 件与本量表主题直接相关的具体小事。参考方向：{scale_actions}。必须具体到动作和时间，比如"今晚睡前""下课后""明天早上"，不要说"适当放松""保持积极"这种空话。
- 提一句这个结果不能代替专业评估，如果觉得困扰比较大可以去学校心理咨询中心。
- 结尾用一句真诚的话收掉，不要写「祝你健康快乐」之类的套话，不要署名。

整体要像人在说话，有温度，不要写成条目堆砌的说明书。300-600 字左右。"""
    return [
        {"role": "system", "content": SYSTEM_EVALUATION_COMMENT},
        {"role": "user", "content": user_text},
    ]
