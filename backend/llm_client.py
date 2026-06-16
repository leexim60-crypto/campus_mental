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


SYSTEM_EVALUATION_COMMENT = """你是一位温暖、有耐心的心理健康陪伴者，正在给一位刚完成校园心理自评的同学写一段话。你不是辅导员、不是咨询师、不是医生——你就是一个关心 ta 的人，像朋友一样跟 ta 聊聊。

语气：
- 用简体中文，像写信一样，不要太正式。开头先肯定 ta 愿意做这件事的勇气，让 ta 感到被看见。
- 用「你」，不用「您」。不要列一二三四编号，不要用标题符号，自然分段就好。
- 不要自称任何身份——不要说「你的辅导员」「你的咨询师」「作为老师」之类的。结尾也不要署名，不要写「祝你健康快乐」这种套话，用一句真诚的、具体的话收尾就好。

内容：
- 根据分数和各题情况，用大白话帮 ta 理解「这可能说明了什么」，但不要像念报告一样罗列数据。把分数融入到关心的话里，比如「从你的结果来看，最近在情绪和睡眠上可能压力比较大」。
- 给 2-3 件具体的小事，是 ta 现在就能做的，不要说「保持积极心态」「适当放松」这种空话。比如：今晚睡前试试把手机放远一点，做几分钟深呼吸；找个信任的朋友聊一聊，哪怕只是说一句「最近有点累」。
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


def build_evaluation_messages(
    scale_type: str,
    total_score: int,
    emotion_label: str,
    rule_template_suggestion: str,
    scores: list[int],
) -> list[dict[str, Any]]:
    scores_str = "、".join(str(s) for s in scores) if scores else "（无）"
    user_text = f"""请根据以下校园心理自评筛查结果，给这位同学写一段温暖的、像朋友一样的话。不要写成报告，不要列编号，就像你在跟 ta 面对面聊天。

【量表】{scale_type}
【综合分/汇总指标】{total_score}
【系统参考标签】（仅供你理解情绪倾向，不要在回复中直接使用这些词）{emotion_label}
【规则引擎模板参考】（仅供思路，用你自己的话说，不要照抄）{rule_template_suggestion}
【各题得分 0～3，按题序】{scores_str}

大致这样写：
- 开头先肯定 ta 做了这件事，让 ta 感到被看见。
- 中间根据分数用大白话聊聊 ta 最近可能的状态，然后直接给两三件现在就能做的小事（具体的、今晚就能试的），不要说空话。
- 提一句这个结果不能代替专业评估，如果觉得不太好了可以去学校心理咨询中心。
- 如果分数偏高或有风险提示，语气稳重一些，认真建议 ta 寻求帮助。
- 结尾用一句真诚的话收掉，不要写「祝你健康快乐」之类的套话，不要署名。

整体要像人在说话，有温度，不要写成条目堆砌的说明书。300-600 字左右。"""
    return [
        {"role": "system", "content": SYSTEM_EVALUATION_COMMENT},
        {"role": "user", "content": user_text},
    ]
