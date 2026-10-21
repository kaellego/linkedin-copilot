# browser/driver_factory.py
import json
import time
from urllib.error import URLError
from urllib.request import urlopen

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchWindowException, WebDriverException


DEBUGGER_URL = "http://127.0.0.1:9222"


def _debug_page_targets():
    try:
        with urlopen(f"{DEBUGGER_URL}/json/list", timeout=1) as response:
            targets = json.loads(response.read().decode("utf-8"))
        return [
            target for target in targets
            if target.get("type") == "page" and target.get("webSocketDebuggerUrl")
        ]
    except (OSError, URLError, json.JSONDecodeError, TypeError):
        return []


def _wait_for_debug_page(timeout: float = 20.0, stop_event=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Conexão com o Chrome interrompida pelo usuário.")
        targets = _debug_page_targets()
        if targets:
            return targets
        wait_for = min(0.25, max(0.0, deadline - time.monotonic()))
        if stop_event is None:
            time.sleep(wait_for)
        elif stop_event.wait(wait_for):
            raise InterruptedError("Conexão com o Chrome interrompida pelo usuário.")
    raise RuntimeError(
        "O Chrome abriu a porta 9222, mas não disponibilizou nenhuma guia ativa. "
        "Mantenha uma guia do Chrome aberta e tente novamente."
    )

def create_driver(stop_event=None) -> webdriver.Chrome:
    """Attach Selenium to a ready Chrome debugging target and select a live tab."""
    targets = _wait_for_debug_page(stop_event=stop_event)
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    driver = webdriver.Chrome(options=chrome_options)
    try:
        handles = driver.window_handles
        target_ids = [target.get("id") for target in targets]
        ordered_handles = [f"CDwindow-{target_id}" for target_id in target_ids]
        ordered_handles.extend(handle for handle in handles if handle not in ordered_handles)

        for handle in ordered_handles:
            if handle not in handles:
                continue
            try:
                driver.switch_to.window(handle)
                _ = driver.current_url
                return driver
            except (NoSuchWindowException, WebDriverException):
                continue

        raise RuntimeError(
            "O Chrome respondeu, mas todas as guias foram fechadas antes da conexão do robô. "
            "Abra uma guia e tente novamente."
        )
    except Exception:
        # Stop only the temporary driver service; keep the user's Chrome session open.
        try:
            driver.service.stop()
        except Exception:
            pass
        raise
