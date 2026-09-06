"""Optional, privacy-bounded map and geocoding provider integration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .settings import IntegrationSettings, RuntimeSettings

LOGGER = logging.getLogger(__name__)
MAP_PROVIDER_MODES = frozenset({"off", "osm", "google"})
DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class MapProviderConfigurationError(ValueError):
    """The operator supplied an incomplete or unsafe provider configuration."""


class MapProviderDisabledError(ValueError):
    """An external map action was requested while the feature is disabled."""


class MapProviderUnavailableError(ValueError):
    """The configured provider did not return a usable geocoding result."""


@dataclass(frozen=True)
class MapProviderConfig:
    """Secret-aware configuration read only from protected deployment values."""

    mode: str = "off"
    nominatim_url: str = DEFAULT_NOMINATIM_URL
    nominatim_user_agent: str | None = None
    google_maps_api_key: str | None = None

    @property
    def active(self) -> bool:
        return self.mode != "off"

    @classmethod
    def from_environment(cls, environment: dict[str, str] | None = None) -> MapProviderConfig:
        try:
            settings = RuntimeSettings.from_environment(environment).integrations
        except ValueError as error:
            raise MapProviderConfigurationError(str(error)) from error
        return cls.from_settings(settings)

    @classmethod
    def from_settings(cls, settings: IntegrationSettings) -> MapProviderConfig:
        mode = settings.map_provider
        nominatim_url = settings.nominatim_url
        user_agent = settings.nominatim_user_agent
        google_key = settings.google_key
        if mode not in MAP_PROVIDER_MODES:
            raise MapProviderConfigurationError("LZUG_MAP_PROVIDER must be off, osm, or google")
        if mode == "off":
            return cls()
        _validate_nominatim_url(nominatim_url)
        if user_agent is None or "\n" in user_agent or "\r" in user_agent:
            raise MapProviderConfigurationError(
                "LZUG_NOMINATIM_USER_AGENT is required when maps are enabled"
            )
        if mode == "google" and google_key is None:
            raise MapProviderConfigurationError(
                "LZUG_GOOGLE_MAPS_API_KEY is required for Google Maps mode"
            )
        return cls(
            mode=mode,
            nominatim_url=nominatim_url,
            nominatim_user_agent=user_agent,
            google_maps_api_key=google_key,
        )

    def public_contract(self) -> dict[str, str]:
        """Expose mode metadata only; deployment credentials never cross this boundary."""
        if self.mode == "osm":
            return {
                "mode": "osm",
                "attribution": "© OpenStreetMap-Mitwirkende",
                "attribution_url": "https://www.openstreetmap.org/copyright",
            }
        if self.mode == "google":
            return {
                "mode": "google",
                "attribution": "Google Maps",
                "attribution_url": "https://www.google.com/intl/de/help/terms_maps/",
            }
        return {"mode": "off"}

    def browser_runtime_contract(self) -> dict[str, str]:
        """Return the intentionally browser-visible value needed by Google Embed.

        A Maps Embed browser key is not a secret: Google receives it in the
        iframe URL.  It is deliberately kept out of the JSON API, diagnostics,
        and application text, and must be restricted by the operator.
        """
        if self.mode != "google" or self.google_maps_api_key is None:
            return {}
        return {"googleMapsEmbedKey": self.google_maps_api_key}


class NominatimGeocoder:
    """Run one explicit, data-minimized Nominatim lookup without retries."""

    def __init__(self, config: MapProviderConfig, *, timeout_seconds: float = 4.0):
        self.config = config
        self.timeout_seconds = timeout_seconds

    def geocode(self, address: str) -> dict[str, Any]:
        if not self.config.active:
            raise MapProviderDisabledError("Map provider is disabled")
        query = urlencode({"format": "jsonv2", "limit": "1", "q": address})
        request = Request(
            f"{self.config.nominatim_url}?{query}",
            headers={"User-Agent": self.config.nominatim_user_agent or ""},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except TimeoutError as error:
            self._raise_unavailable("timeout", error)
        except HTTPError as error:
            category = "quota" if error.code in {429, 503} else "provider_error"
            error.close()
            self._raise_unavailable(category, error)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            self._raise_unavailable("provider_error", error)
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            self._raise_unavailable("not_found", None)
        candidate = payload[0]
        try:
            latitude = float(candidate["lat"])
            longitude = float(candidate["lon"])
        except (KeyError, TypeError, ValueError) as error:
            self._raise_unavailable("invalid_response", error)
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            self._raise_unavailable("invalid_response", None)
        return {"latitude": latitude, "longitude": longitude, "source": "nominatim"}

    def _raise_unavailable(self, category: str, error: Exception | None) -> None:
        LOGGER.warning("map_provider_request_failed provider=nominatim category=%s", category)
        raise MapProviderUnavailableError("Geocoding is currently unavailable") from error


def planning_requires_confirmed_coordinates() -> bool:
    """Keep the shared planning guard aligned with the deployed provider mode."""
    return MapProviderConfig.from_environment().active


def _validate_nominatim_url(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise MapProviderConfigurationError("LZUG_NOMINATIM_URL must be an HTTPS endpoint")
