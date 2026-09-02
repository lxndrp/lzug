"""Pydantic models used at the public FastAPI contract boundary."""

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    error: str


class HealthResponse(BaseModel):
    status: str
    version: str
    revision: str
    links: dict[str, object] = Field(alias="_links")


class ApiRootResponse(BaseModel):
    version: str
    links: dict[str, object] = Field(alias="_links")


class LoginRequest(BaseModel):
    email: str = ""
    password: str = ""
    second_factor: str = ""


class TokenRequest(BaseModel):
    token: str = ""


class FactorActivationRequest(BaseModel):
    token: str = ""
    password: str = ""
    totp_secret: str = ""
    totp_code: str = ""


class FrontendErrorRequest(BaseModel):
    kind: str
    status: int | None = None


class SessionResponse(BaseModel):
    authenticated: bool
    account_id: int
    person_id: int | None
    committee_member_id: int | None
    is_operator: bool


class SessionRotationResponse(BaseModel):
    status: str
    expires_at: str


class DomainResourceWrite(BaseModel):
    model_config = ConfigDict(extra="allow")


class DomainResourceResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class DomainCollectionResponse(BaseModel):
    items: list[DomainResourceResponse]
    links: dict[str, object] = Field(alias="_links")
