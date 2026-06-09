"""共用的 token 計算工具函式。"""

_tiktoken_enc = None


def count_tokens(text: str) -> int:
    """近似 token 計數。優先使用 tiktoken，否則以字元數 / 2 估算。"""
    global _tiktoken_enc
    if _tiktoken_enc is None:
        try:
            import tiktoken
            _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            pass
    if _tiktoken_enc is not None:
        return len(_tiktoken_enc.encode(text))
    return len(text) // 2
