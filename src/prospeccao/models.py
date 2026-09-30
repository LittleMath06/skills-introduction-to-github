"""Modelo de dados (ver docs/04-database.md)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)


class Segment(TimestampMixin, Base):
    __tablename__ = "segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Prefixos de CNAE (2 a 7 dígitos) separados por vírgula
    cnae_prefixes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Palavras-chave (sem acento, minúsculas) separadas por vírgula
    keywords: Mapped[str] = mapped_column(Text, default="", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Company(Base):
    """Estabelecimento identificado por CNPJ (matriz ou filial)."""

    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, nullable=False)
    cnpj_basico: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    is_matriz: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    razao_social: Mapped[str | None] = mapped_column(String(255))
    nome_fantasia: Mapped[str | None] = mapped_column(String(255))
    situacao_cadastral: Mapped[str | None] = mapped_column(String(2), index=True)
    data_situacao: Mapped[date | None] = mapped_column(Date)
    data_abertura: Mapped[date | None] = mapped_column(Date)
    natureza_juridica_code: Mapped[str | None] = mapped_column(String(4))
    natureza_juridica: Mapped[str | None] = mapped_column(String(255))
    porte: Mapped[str | None] = mapped_column(String(2), index=True)
    capital_social: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    logradouro: Mapped[str | None] = mapped_column(String(255))
    numero: Mapped[str | None] = mapped_column(String(30))
    complemento: Mapped[str | None] = mapped_column(String(255))
    bairro: Mapped[str | None] = mapped_column(String(120))
    cep: Mapped[str | None] = mapped_column(String(8))
    municipio_code: Mapped[str | None] = mapped_column(String(7))
    municipio: Mapped[str | None] = mapped_column(String(120))
    uf: Mapped[str | None] = mapped_column(String(2), index=True)
    region: Mapped[str | None] = mapped_column(String(20), index=True)

    cnae_principal: Mapped[str | None] = mapped_column(String(7), index=True)
    cnae_principal_desc: Mapped[str | None] = mapped_column(String(255))
    cnaes_secundarios: Mapped[str | None] = mapped_column(Text)  # "4321500,4742300"
    # Texto normalizado (sem acento, minúsculo) para a pesquisa livre
    search_text: Mapped[str | None] = mapped_column(Text)

    has_phone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    has_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    has_website: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    website: Mapped[str | None] = mapped_column(String(255))
    # "manual" | "verificado" | "inferido" (domínio do e-mail, ainda não confirmado)
    website_status: Mapped[str | None] = mapped_column(String(20))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    site_title: Mapped[str | None] = mapped_column(String(255))
    site_description: Mapped[str | None] = mapped_column(Text)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime)

    simples_opcao: Mapped[bool | None] = mapped_column(Boolean)
    mei_opcao: Mapped[bool | None] = mapped_column(Boolean)
    simples_data_opcao: Mapped[date | None] = mapped_column(Date)
    simples_data_exclusao: Mapped[date | None] = mapped_column(Date)
    # "confirmado_habilitado" | "confirmado_nao_habilitado" | "nao_contribuinte" | "provavel" | "nao_verificado"
    icms_status: Mapped[str] = mapped_column(
        String(30), default="nao_verificado", nullable=False, index=True
    )

    segment_id: Mapped[int | None] = mapped_column(ForeignKey("segments.id", ondelete="SET NULL"))
    segment_method: Mapped[str | None] = mapped_column(String(20))
    segment_confidence: Mapped[float | None] = mapped_column(Float)
    segment_explanation: Mapped[str | None] = mapped_column(Text)

    similarity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    similarity_details: Mapped[dict | None] = mapped_column(JSON)
    potential: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    potential_details: Mapped[dict | None] = mapped_column(JSON)
    completeness: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)

    is_customer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    customer_group: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(120))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    data_hash: Mapped[str | None] = mapped_column(String(64))

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    segment: Mapped[Segment | None] = relationship(lazy="joined")
    contacts: Mapped[list[CompanyContact]] = relationship(
        back_populates="company", cascade="all, delete-orphan", lazy="selectin"
    )
    fiscal_infos: Mapped[list[FiscalInfo]] = relationship(
        back_populates="company", cascade="all, delete-orphan", lazy="selectin"
    )
    lead: Mapped[Lead | None] = relationship(back_populates="company", uselist=False, lazy="joined")

    __table_args__ = (
        Index("ix_companies_uf_municipio", "uf", "municipio"),
        Index("ix_companies_segment_similarity", "segment_id", "similarity"),
        Index("ix_companies_cnae_prefix", "cnae_principal", "uf"),
    )

    @property
    def secondary_cnaes(self) -> list[str]:
        return [c for c in (self.cnaes_secundarios or "").split(",") if c]

    @property
    def display_name(self) -> str:
        return self.nome_fantasia or self.razao_social or self.cnpj


class CompanyContact(Base):
    __tablename__ = "company_contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    # telefone | email | site | whatsapp | linkedin | instagram | facebook
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    # True = contato institucional da empresa; False = possível dado de pessoa física
    is_company: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    company: Mapped[Company] = relationship(back_populates="contacts")
    __table_args__ = (UniqueConstraint("company_id", "kind", "value", name="uq_contact"),)


class FiscalInfo(Base):
    """Informação fiscal com rastreabilidade. Inclui benefícios e regimes especiais."""

    __tablename__ = "fiscal_infos"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    # inscricao_estadual | icms | simples | mei | regime_apuracao | beneficio | regime_especial | outro
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    # confirmado | provavel | possivel
    level: Mapped[str] = mapped_column(String(12), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    consulted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    data_date: Mapped[date | None] = mapped_column(Date)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(12), default="sistema", nullable=False)
    company: Mapped[Company] = relationship(back_populates="fiscal_infos")


class CompanyChange(Base):
    __tablename__ = "company_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(60), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class Customer(Base):
    """Linha da base de clientes atuais de Paulo (dado privado)."""

    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str | None] = mapped_column(String(14), unique=True)
    razao_social: Mapped[str | None] = mapped_column(String(255))
    nome_fantasia: Mapped[str | None] = mapped_column(String(255))
    municipio: Mapped[str | None] = mapped_column(String(120))
    uf: Mapped[str | None] = mapped_column(String(2))
    cnae: Mapped[str | None] = mapped_column(String(7))
    segmento_informado: Mapped[str | None] = mapped_column(String(120))
    porte: Mapped[str | None] = mapped_column(String(2))
    raw: Mapped[dict | None] = mapped_column(JSON)
    # ok | sem_cnpj | nao_encontrado
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    import_batch: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    company: Mapped[Company | None] = relationship()


class LeadStatus(Base):
    __tablename__ = "lead_statuses"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Lead(TimestampMixin, Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status_id: Mapped[int] = mapped_column(ForeignKey("lead_statuses.id"), nullable=False, index=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    discarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    company: Mapped[Company] = relationship(back_populates="lead", lazy="joined")
    status: Mapped[LeadStatus] = relationship(lazy="joined")
    notes: Mapped[list[LeadNote]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="LeadNote.created_at.desc()",
        lazy="selectin",
    )


class LeadNote(Base):
    __tablename__ = "lead_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    lead: Mapped[Lead] = relationship(back_populates="notes")


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reference: Mapped[str | None] = mapped_column(String(60))
    records_last_run: Mapped[int | None] = mapped_column(Integer)
    stale_after_days: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # queued | running | done | failed
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="queued", index=True)
    params: Mapped[dict | None] = mapped_column(JSON)
    total: Mapped[int | None] = mapped_column(Integer)
    processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    log: Mapped[list | None] = mapped_column(JSON)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict | list | str | float | None] = mapped_column(JSON)


class Cnae(Base):
    __tablename__ = "cnaes"
    code: Mapped[str] = mapped_column(String(7), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)


class Municipio(Base):
    __tablename__ = "municipios"
    code: Mapped[str] = mapped_column(String(7), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class NaturezaJuridica(Base):
    __tablename__ = "naturezas_juridicas"
    code: Mapped[str] = mapped_column(String(4), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
