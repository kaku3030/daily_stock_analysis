"""E05 bounded Shadow projections; production behavior is intentionally untouched."""

from dataclasses import dataclass
from types import MappingProxyType, SimpleNamespace

from src.services.data_capability_service import DataCapabilityService, _REALTIME_SOURCE_PROVIDER


@dataclass(frozen=True)
class StaticCapabilityView:
    provider: str
    adapter: str | None
    datasets: tuple[str, ...]
    markets: tuple[str, ...]
    configured: bool
    enabled: bool


@dataclass(frozen=True)
class RuntimeProviderObservation:
    provider: str
    status: str
    available: bool | None
    last_error: str | None
    cooldown: object


@dataclass(frozen=True)
class RoutingObservation:
    scenario: str
    market: str | None
    source_tokens: tuple[str, ...]
    selected_source: str | None
    fallback_from: tuple[str, ...]
    warnings: tuple[str, ...]


def _views(overview):
    static = tuple(
        StaticCapabilityView(
            provider=item["name"],
            adapter=item.get("fetcher"),
            datasets=tuple(item.get("datasets") or ()),
            markets=tuple(sorted((item.get("dataset_markets") or {}).get("quote.realtime", ()))),
            configured=bool(item["configured"]),
            enabled=bool(item["enabled"]),
        )
        for item in overview["providers"]
    )
    runtime = tuple(
        RuntimeProviderObservation(
            item["name"], item["status"], item.get("available"), item.get("last_error"), item.get("cooldown")
        )
        for item in overview["providers"]
    )
    routing = tuple(
        RoutingObservation(
            item["scenario"], None, tuple(item.get("providers") or ()), item.get("source"),
            tuple(item.get("fallback_from") or ()), tuple(item.get("warnings") or ()),
        )
        for item in overview["priorities"]
    )
    return MappingProxyType({"static": static, "runtime": runtime, "routing": routing})


class _Fetcher:
    def __init__(self, name, priority, *, available=None, request_available=None, last_error=""):
        self.name, self.priority = name, priority
        if available is not None:
            self._available = available
        if request_available is not None:
            self.is_available_for_request = lambda _capability="": request_available
        if last_error:
            self.last_error = last_error


class _Manager:
    def __init__(self, fetchers): self.fetchers = fetchers
    def _get_fetchers_snapshot(self): return list(self.fetchers)


def _config(**overrides):
    values = dict(tushare_token=None, tickflow_api_key=None, tickflow_priority=2,
                  futu_opend_host=None, longbridge_app_key=None, longbridge_app_secret=None,
                  longbridge_access_token=None, finnhub_api_key=None, alphavantage_api_key=None,
                  enable_realtime_quote=True, enable_fundamental_pipeline=True,
                  realtime_source_priority="tencent,akshare_sina,efinance,akshare_em",
                  futu_hk_realtime_source_priority="futu,longbridge,akshare,yfinance",
                  screening_enabled=False, agent_event_monitor_enabled=False)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_e05_views_are_immutable_and_reuse_service_output():
    overview = DataCapabilityService(config=_config(), fetcher_manager=_Manager([_Fetcher("AkshareFetcher", 1, available=True)])).get_overview()
    views = _views(overview)
    assert isinstance(views["static"], tuple) and isinstance(views["runtime"], tuple)
    assert views["runtime"]
    try:
        views["static"][0].provider = "other"
    except Exception:
        pass
    else:
        raise AssertionError("projection must be immutable")


def test_e05_golden_contract_edges():
    service = DataCapabilityService(
        config=_config(longbridge_app_key="key", tickflow_api_key="configured", futu_opend_host=None),
        fetcher_manager=_Manager([
            _Fetcher("LongbridgeFetcher", 1, available=True, request_available=False),
            _Fetcher("AkshareFetcher", 2, available=True, last_error=" provider   failed "),
            _Fetcher("TickFlowFetcher", 3),
        ]),
    )
    views = _views(service.get_overview())
    runtime = {v.provider: v for v in views["runtime"]}
    routes = {v.scenario: v for v in views["routing"]}
    assert runtime["longbridge"].status == "unavailable"
    assert runtime["tickflow"].status == "unknown"
    assert routes["us.realtime"].source_tokens[0] == "yfinance"
    assert "futu" not in routes["hk.realtime"].source_tokens
    assert runtime["akshare"].last_error == "provider failed"
    assert runtime["akshare"].cooldown is None


def test_e05_runtime_cooldown_is_projected_without_normalization():
    overview = {
        "providers": [
            {
                "name": "synthetic",
                "status": "unknown",
                "available": None,
                "last_error": None,
                "cooldown": {"remaining": "7.5", "marker": object()},
                "fetcher": None,
                "datasets": [],
                "dataset_markets": {},
                "configured": False,
                "enabled": False,
            }
        ],
        "priorities": [],
    }

    cooldown = overview["providers"][0]["cooldown"]
    runtime = _views(overview)["runtime"]

    assert runtime[0].cooldown is cooldown


def test_e05_cn_stock_and_index_routes_are_separate_and_source_authority_is_preserved():
    service = DataCapabilityService(config=_config(), fetcher_manager=_Manager([_Fetcher("AkshareFetcher", 1, available=True)]))
    views = _views(service.get_overview())
    routes = {v.scenario: v for v in views["routing"]}
    assert routes["cn.realtime"].source_tokens != routes["cn.index.daily"].source_tokens
    assert "tencent" in routes["cn.realtime"].source_tokens
    static = {v.provider: v for v in views["static"]}
    assert _REALTIME_SOURCE_PROVIDER["tencent"] == "akshare"
    assert static["tencent"].adapter != "TencentFetcher"
    assert any(token == "tencent" for token in routes["cn.realtime"].source_tokens)
