"""Enriquecimento a partir do site oficial da própria empresa.

Regras (docs/02-fontes-de-dados.md §5):
* só o site da empresa: página inicial + no máximo 1 página de contato do mesmo domínio;
* robots.txt respeitado (se robots.txt não puder ser lido por erro 5xx/rede, a coleta é abortada);
* User-Agent identificado, intervalo mínimo por domínio, timeout, limite de 1 MB por página;
* nenhum contato é criado sem URL de origem.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from ..domain.text import (
    email_domain,
    is_free_email,
    norm,
    normalize_email,
    normalize_phone,
    only_digits,
)
from .base import CompanyWebsiteSource, RateLimiter, SourceError, SourceStatus

MAX_BYTES = 1_000_000
_SOCIAL = {
    "linkedin": re.compile(r"^https?://([a-z]+\.)?linkedin\.com/(company|school)/[^/?#]+", re.I),
    "instagram": re.compile(r"^https?://(www\.)?instagram\.com/[A-Za-z0-9_.]+/?$", re.I),
    "facebook": re.compile(r"^https?://(www\.|pt-br\.)?facebook\.com/[^/?#]+/?$", re.I),
}
_GENERIC_LOCAL = re.compile(
    r"^(contato|comercial|vendas|atendimento|sac|financeiro|faleconosco|fale|compras|orcamento|"
    r"orcamentos|info|contact|adm|administrativo|suporte|rh|marketing|loja|pedidos)", re.I
)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self.description: str | None = None
        self.og_image: str | None = None
        self.icons: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._current_a: str | None = None
        self._a_text: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name in {"description", "og:description"} and not self.description:
                self.description = a.get("content", "").strip()[:500] or None
            if name == "og:image" and a.get("content"):
                self.og_image = a["content"].strip()
        elif tag == "link" and "icon" in a.get("rel", "").lower() and a.get("href"):
            self.icons.append(a["href"].strip())
        elif tag == "a" and a.get("href"):
            self._current_a = a["href"].strip()
            self._a_text = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._current_a is not None:
            self.links.append((self._current_a, " ".join(self._a_text).strip()))
            self._current_a = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._current_a is not None:
            self._a_text.append(data)
        if len(self.text_parts) < 5000:
            self.text_parts.append(data)


@dataclass
class ContactFound:
    kind: str
    value: str
    source_url: str
    is_company: bool = True


@dataclass
class WebsiteResult:
    url: str
    final_url: str
    verified: bool
    verification_reason: str
    title: str | None = None
    description: str | None = None
    logo_url: str | None = None
    contacts: list[ContactFound] = field(default_factory=list)


def candidate_from_email(email: str | None) -> str | None:
    """Domínio do e-mail cadastral vira candidato a site (se não for provedor gratuito)."""
    email = normalize_email(email)
    if not email or is_free_email(email):
        return None
    return f"https://{email_domain(email)}/"


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.hostname or "." not in parsed.hostname:
        return None
    return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{parsed.path or '/'}"


def parse_page(html: str, page_url: str, company_domain: str) -> tuple[_PageParser, list[ContactFound]]:
    parser = _PageParser()
    parser.feed(html)
    contacts: list[ContactFound] = []
    for href, _ in parser.links:
        low = href.lower()
        if low.startswith("tel:"):
            digits = only_digits(href[4:]).lstrip("0")
            if digits.startswith("55") and len(digits) in (12, 13):  # código do país
                digits = digits[2:]
            phone = normalize_phone(None, digits)
            if phone:
                contacts.append(ContactFound("telefone", phone, page_url))
        elif low.startswith("mailto:"):
            email = normalize_email(href[7:].split("?")[0])
            if email:
                personal = is_free_email(email) or (
                    email_domain(email) == company_domain
                    and not _GENERIC_LOCAL.match(email.split("@")[0])
                    and "." in email.split("@")[0]
                )
                contacts.append(ContactFound("email", email, page_url, is_company=not personal))
        elif "wa.me/" in low or "api.whatsapp.com/send" in low:
            number = ""
            if "wa.me/" in low:
                number = only_digits(low.split("wa.me/", 1)[1].split("?")[0])
            else:
                number = only_digits((parse_qs(urlparse(href).query).get("phone") or [""])[0])
            if 12 <= len(number) <= 13:
                contacts.append(ContactFound("whatsapp", number, page_url))
        else:
            absolute = urljoin(page_url, href)
            for kind, pattern in _SOCIAL.items():
                m = pattern.match(absolute)
                if m:
                    contacts.append(ContactFound(kind, m.group(0).rstrip("/"), page_url))
    unique: dict[tuple[str, str], ContactFound] = {}
    for c in contacts:
        unique.setdefault((c.kind, c.value), c)
    return parser, list(unique.values())


def verify_ownership(page_text: str, cnpj: str, razao_social: str | None,
                     nome_fantasia: str | None) -> tuple[bool, str]:
    digits = only_digits(page_text)
    if cnpj and cnpj in digits:
        return True, "CNPJ encontrado na página"
    text = norm(page_text)
    for name in (nome_fantasia, razao_social):
        n = norm(name)
        n = re.sub(r"\b(ltda|me|epp|eireli|s a|sa)\b", "", n).strip()
        if len(n) >= 5 and n in text:
            return True, "Nome da empresa encontrado na página"
    return False, "Nome/CNPJ não encontrados na página — site não confirmado"


class WebsiteSource(CompanyWebsiteSource):
    key = "website"
    name = "Site oficial da empresa"

    def __init__(self, user_agent: str, min_interval: float = 5.0,
                 client: httpx.Client | None = None, enabled: bool = True):
        self.user_agent = user_agent
        self._client = client
        self._limiter = RateLimiter(min_interval)
        self._robots: dict[str, RobotFileParser | None] = {}
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    def check(self) -> SourceStatus:
        return SourceStatus(self._enabled, "Ativo (robots.txt respeitado)" if self._enabled
                            else "Desativado por configuração")

    def _http(self) -> httpx.Client:
        return self._client or httpx.Client(
            timeout=10, follow_redirects=True, headers={"User-Agent": self.user_agent},
        )

    def _allowed(self, client: httpx.Client, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                self._limiter.wait(parsed.netloc)
                resp = client.get(base + "/robots.txt")
            except httpx.HTTPError:
                self._robots[base] = None  # não foi possível ler → não coletar
                return False
            if resp.status_code in (401, 403):
                rp.disallow_all = True
            elif resp.status_code >= 500:
                self._robots[base] = None
                return False
            elif resp.status_code >= 400:
                rp.allow_all = True
            else:
                rp.parse(resp.text.splitlines())
            self._robots[base] = rp
        rp = self._robots[base]
        return rp is not None and rp.can_fetch(self.user_agent, url)

    def _get(self, client: httpx.Client, url: str) -> httpx.Response | None:
        if not self._allowed(client, url):
            return None
        self._limiter.wait(urlparse(url).netloc)
        resp = client.get(url)
        if resp.status_code != 200:
            return None
        if "html" not in resp.headers.get("content-type", "text/html").lower():
            return None
        if len(resp.content) > MAX_BYTES:
            return None
        return resp

    def fetch(self, url: str, cnpj: str, razao_social: str | None,
              nome_fantasia: str | None) -> WebsiteResult:
        url = normalize_url(url)
        if not url:
            raise SourceError("URL inválida")
        client = self._http()
        try:
            try:
                resp = self._get(client, url)
            except httpx.HTTPError as exc:
                raise SourceError(f"Site inacessível: {exc.__class__.__name__}") from exc
            if resp is None:
                raise SourceError("Site indisponível, não-HTML ou bloqueado por robots.txt")
            final_url = str(resp.url)
            domain = (urlparse(final_url).hostname or "").removeprefix("www.")
            page, contacts = parse_page(resp.text, final_url, domain)
            text = " ".join(page.text_parts)
            # Página de contato (1 no máximo, mesmo domínio)
            contact_link = next(
                (urljoin(final_url, h) for h, t in page.links
                 if re.search(r"contato|contact|fale", f"{h} {t}", re.I)
                 and (urlparse(urljoin(final_url, h)).hostname or "").removeprefix("www.") == domain),
                None,
            )
            if contact_link and contact_link.rstrip("/") != final_url.rstrip("/"):
                try:
                    cresp = self._get(client, contact_link)
                except httpx.HTTPError:
                    cresp = None
                if cresp is not None:
                    cpage, ccontacts = parse_page(cresp.text, str(cresp.url), domain)
                    text += " " + " ".join(cpage.text_parts)
                    seen = {(c.kind, c.value) for c in contacts}
                    contacts += [c for c in ccontacts if (c.kind, c.value) not in seen]
            verified, reason = verify_ownership(text, cnpj, razao_social, nome_fantasia)
            logo = urljoin(final_url, page.og_image or (page.icons[0] if page.icons else "/favicon.ico"))
            if not logo.startswith(("https://", "http://")):  # descarta data:/javascript: etc.
                logo = urljoin(final_url, "/favicon.ico")
            return WebsiteResult(
                url=url, final_url=final_url, verified=verified, verification_reason=reason,
                title=(page.title or "").strip()[:255] or None, description=page.description,
                logo_url=logo[:500], contacts=contacts,
            )
        finally:
            if self._client is None:
                client.close()
