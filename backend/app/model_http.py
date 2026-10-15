"""模型 HTTP 请求的代理选择边界。"""

from collections.abc import Callable
from typing import Literal, Protocol
from urllib.request import ProxyHandler, Request, build_opener


NetworkMode = Literal["auto", "system_proxy", "direct"]


class OpenResponse(Protocol):
    def __enter__(self): ...
    def __exit__(self, *args): ...
    def read(self) -> bytes: ...


def open_model_request(
    request: Request,
    timeout: int,
    network_mode: NetworkMode,
    inherited_open: Callable[..., OpenResponse],
) -> OpenResponse:
    """按请求时的网络方式打开连接；直连显式忽略进程代理。"""
    if network_mode == "auto":
        return inherited_open(request, timeout=timeout)
    proxy_handler = ProxyHandler({}) if network_mode == "direct" else ProxyHandler()
    return build_opener(proxy_handler).open(request, timeout=timeout)
