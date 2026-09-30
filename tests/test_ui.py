"""Teste de interface: fluxo principal no navegador (Chromium headless), desktop e celular.

Entrar → Pesquisar → Filtrar → Abrir detalhes → Salvar lead → Status/observação → Leads salvos.
Pulado automaticamente se o Chromium não estiver disponível.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from prospeccao.services.jobs import JobRunner  # noqa: E402
from prospeccao.services.mock_seed import seed_mock  # noqa: E402

from .conftest import PASSWORD, FakeSources  # noqa: E402

CHROMIUM = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server(settings):
    import uvicorn

    from prospeccao.db import new_session
    from prospeccao.main import create_app

    app = create_app(settings, runner=JobRunner(synchronous=True), sources=FakeSources(settings))
    with new_session() as s:
        seed_mock(s, settings, n_companies=80, n_customers=10)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(5)


@pytest.fixture
def browser():
    exe = CHROMIUM if CHROMIUM and Path(CHROMIUM).is_file() else None
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=exe)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium indisponível: {exc}")
        yield b
        b.close()


@pytest.mark.parametrize("viewport", [{"width": 1366, "height": 900}, {"width": 390, "height": 844}],
                         ids=["desktop", "celular"])
def test_main_flow(live_server, browser, viewport):
    page = browser.new_page(viewport=viewport)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    page.goto(live_server + "/buscar")
    assert page.url.endswith("/login")
    page.fill("#password", "errada")
    page.fill("#username", "paulo")
    page.click("button[type=submit]")
    assert page.locator(".notice.err").inner_text().startswith("Usuário ou senha inválidos")
    page.fill("#username", "paulo")
    page.fill("#password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url(live_server + "/")
    errors.clear()  # o 401 da tentativa com senha errada é esperado
    assert page.locator(".mock-banner").is_visible()

    # sem rolagem horizontal no celular
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    # pesquisa livre
    page.fill("input[name=nl]", "instaladores em São Paulo")
    page.press("input[name=nl]", "Enter")
    page.wait_for_url("**/buscar?**")
    assert "Segmento: Instaladores" in page.locator("form#search-form").inner_text()
    results = page.locator("li.result")
    assert results.count() > 0

    # remover um filtro pelo chip
    total_before = page.locator("strong", has_text="encontrada").inner_text()
    page.locator(".chip a[aria-label='Remover filtro UF']").click()
    page.wait_for_load_state()
    assert page.locator("strong", has_text="encontrada").inner_text() != total_before

    # detalhes
    page.locator("li.result .name a").first.click()
    page.wait_for_url("**/empresas/**")
    assert page.locator("h2", has_text="Compatibilidade com perfil atual").is_visible()
    assert page.locator("text=Não constituem aconselhamento tributário").is_visible()

    # salvar lead, mudar status, observação
    page.click("button[data-action=save-lead]")
    page.wait_for_selector("select#lead-status")
    page.select_option("select#lead-status", label="Contato realizado")
    page.wait_for_selector("#toast div")
    page.fill("form[data-form=note] textarea", "Primeiro contato feito por telefone")
    page.click("form[data-form=note] button[type=submit]")
    page.wait_for_selector("text=Primeiro contato feito por telefone")

    # leads salvos
    page.goto(live_server + "/leads")
    row = page.locator("tbody tr").first
    assert "Primeiro contato" in row.inner_text()
    assert row.locator("select").evaluate("s => s.options[s.selectedIndex].text") == "Contato realizado"

    assert not errors, errors
