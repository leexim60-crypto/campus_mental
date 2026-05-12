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
    text: Optional[str] = None
    user_hint: Optional[str] = None
    """使用的后端：便于前端展示"""
    backend: Optional[str] = None


def _deepseek_url() -> str:
    base = DEEPSEEK_BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _iter_openai_sse_content(response: httpx.Response) -> Iterator[str]:
    """解析 OpenAI 兼容的 SSE（DeepSeek / Ollama /v1）。"""
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


def _call_ollama(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> LLMResult:
    """
    优先走 OpenAI 兼容接口 /v1/chat/completions（新版 Ollama 更稳），
    失败再回退 /api/chat。502 多为模型名、显存或引擎未就绪，而非「没装 Ollama」。
    """
    base = ollama_effective_base_url()
    if base != OLLAMA_BASE_URL.rstrip("/"):
        logger.info("Ollama URL 已规范化: %r -> %r", OLLAMA_BASE_URL, base)

    url_v1 = f"{base}/v1/chat/completions"
    payload_v1: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if OLLAMA_NUM_CTX is not None:
        #部分 Ollama 版本在 OpenAI 兼容接口中支持 options.num_ctx
        payload_v1["options"] = {"num_ctx": OLLAMA_NUM_CTX}

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
    try:
        with httpx.Client(timeout=timeout, **_HTTPX_LOCAL) as client:
            model_use = _resolve_ollama_model(client, base, OLLAMA_MODEL)
            payload_v1["model"] = model_use
            payload_native["model"] = model_use

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
                if content:
                    return LLMResult(content, None, "ollama")
                logger.warning("Ollama /v1 200 但无正文，回退 /api/chat")

            if r.status_code not in (200, 404):
                logger.warning("Ollama /v1 HTTP %s: %s", r.status_code, r.text[:400])

            r2 = client.post(url_native, json=payload_native)
            if r2.status_code == 200:
                data = r2.json()
                msg = data.get("message") or {}
                content = (msg.get("content") or "").strip()
                if content:
                    return LLMResult(content, None, "ollama")
                return LLMResult(None, "Ollama 返回内容为空。", "ollama")

            err_txt = r2.text or r.text
            logger.warning("Ollama /api/chat HTTP %s: %s", r2.status_code, err_txt[:400])
            api_err = _ollama_api_error_message(err_txt)
            core = _ollama_fail_hint(r2.status_code, err_txt, model_use)
            diag = _ollama_post_failure_diag(client, base, model_use)
            if api_err:
                hint = f"Ollama 报错：{api_err}\n\n{core}{diag}"
            else:
                hint = f"{core}{diag}"
            return LLMResult(None, hint, "ollama")
    except httpx.ConnectError:
        return LLMResult(
            None,
            f"无法连接 Ollama（TCP 连接被拒绝，不是 HTTP 502）。当前使用地址：{base}。"
            "请确认 Ollama 已启动，.env 中 OLLAMA_BASE_URL 正确（http://127.0.0.1:11434，勿用 https）。"
            "若命令行 ollama 在本机可用，而本后端跑在 WSL/Docker，127.0.0.1 往往指向错误环境，请改为 Windows/宿主机 IP。"
            f" 然后执行：ollama pull {OLLAMA_MODEL}",
            "ollama",
        )
    except httpx.TimeoutException:
        return LLMResult(None, "Ollama 响应超时（首次加载大模型可能需 1～3 分钟，可改小模型或加大等待）。", "ollama")
    except Exception as e:
        logger.warning("Ollama 异常: %s", e)
        return LLMResult(None, str(e)[:200], "ollama")


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


SYSTEM_EVALUATION_COMMENT = """你以「资深学校心理咨询师 / 心理健康教育教师」的书面语风格辅助撰写反馈（你是 AI，文稿供学生阅读参考）。

语气与立场：
- 用简体中文；字里行间要有温度：像一位真正关心学生的老师坐在对面说话——先看见对方的努力与不易，再谈建议。
- 多用人本取向的表述：反映情绪（「听起来你可能……」「这段时间一定不容易」）、肯定求助与完成量表的勇气，避免冷冰冰的评语腔或说教。
- 内容要具体、可执行（小步、可尝试的行动），少用空泛套话；可适度使用「我们」拉近距离，但不要显得轻浮或过度亲昵。

专业边界（必须遵守）：
- 对方完成的是自评筛查，不是医学诊断；文中要明确、温和地说明「结果不能代替专业评估」，并鼓励有需要时联系学校心理咨询中心。
- 不做疾病命名或「你就是××症」式判断；不夸大或恐吓，也不淡化痛苦。
- 若字里行间提示较高风险（强烈绝望、自伤自杀意念或计划等），要清晰、稳重地建议立即联系身边信任的人、学校心理中心、当地心理危机干预热线，必要时急诊就医——语气温和而坚定。

形式：
- 不要输出 JSON；不要用 Markdown 标题符号（如 #）；用自然分段即可。"""


SYSTEM_COMPANION_CHAT = """你是校园里的「心灵树洞」陪伴对话助手（AI，不是真人咨询师）。请用温暖、有同理心的简体中文，像一位受过训练的倾听者那样说话。

核心态度：
- 先接住对方的感受：适当复述或猜测其心情（「听起来你有些……」「如果是我，可能也会……」），让对方感到被听懂，而不是被评判或立刻被「纠正」。
- 语气柔和、有耐心，可以短句与停顿感并用，避免公文腔、百科腔或过度励志口号；同情心与真诚比「正确」更重要。
- 少给未经邀请的大道理；若对方需要，再轻量分享可能的视角或小步尝试，并始终尊重对方的节奏。

边界与安全：
- 不做医学或精神疾病诊断，不提供治疗方案或用药建议；不替代面对面心理咨询或精神科诊疗。
- 若对方提到自伤、自杀想法或正在伤害自己，请用稳重、关切的语气明确建议：尽快联系身边信任的人、学校心理咨询中心，或拨打当地心理危机干预热线；紧急时请前往医院急诊。不要表现冷漠，也不要煽情。

输出要求：
- 单次回复约 80～400 字为宜；若对方明确需要放松或呼吸等步骤，可略长，仍保持口语化、好读。
- 只输出你对用户说的正文；不要输出 JSON、不要复述或模仿 `{"messages":[...]}` 等请求结构，不要用代码块包裹整段对话记录。"""


def build_evaluation_messages(
    scale_type: str,
    total_score: int,
    emotion_label: str,
    rule_template_suggestion: str,
    scores: list[int],
) -> list[dict[str, Any]]:
    scores_str = "、".join(str(s) for s in scores) if scores else "（无）"
    user_text = f"""请根据以下校园心理自评筛查结果，写一段「个性化心理支持与自助建议」（约 300～800 字，自然分段，像一位有同理心的辅导老师写给学生的信）。

【量表】{scale_type}
【综合分/汇总指标】{total_score}
【系统参考标签】（后台统计用，你可委婉呼应其情绪色彩，勿机械重复原词）{emotion_label}
【规则引擎模板参考】（仅供思路，请内化后用自己的话重写，禁止照抄）{rule_template_suggestion}
【各题得分 0～3，按题序】{scores_str}

写作结构建议（可灵活，不必列小标题）：
1）开头：共情与「被看见」——肯定对方愿意完成自评，简要反映你可能读到的情绪与压力，避免评判。
2）中段：结合分数与题目模式，用具体、生活化的语言解读「这可能意味着什么」，并给出 2～4 条小而可行的自助建议（情绪、作息、人际、学业节奏、放松方式等，视情况选取）。
3）资源：温和提醒本结果不能替代专业诊断；鼓励在困扰持续或加重时联系学校心理咨询中心；若有强烈不安或风险意念，应优先寻求专业与身边人支持。
4）结尾：一句踏实、温暖的鼓励，避免空洞口号。

整体要求：有感情、有温度，像人在说话，不要写成条目堆砌的说明书；若整体提示困扰较重，语气要更稳重、关切，并突出求助渠道。"""
    return [
        {"role": "system", "content": SYSTEM_EVALUATION_COMMENT},
        {"role": "user", "content": user_text},
    ]
