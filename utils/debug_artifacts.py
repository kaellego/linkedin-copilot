"""Creates unique, redacted failure bundles without page screenshots."""

import json
import os
import re
import time
import uuid
from pathlib import Path

import config
from utils.privacy import sanitize_html, sanitize_text, sanitize_url


_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def save_failure_context(driver, stage: str, error: object, signals: dict = None, selector: str = None) -> str:
    config.ensure_runtime_dirs()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe_stage = _SAFE_NAME_RE.sub("_", sanitize_text(stage, 80)).strip("_") or "unknown"
    folder = config.DEBUG_DIR / f"{stamp}_{time.time_ns()}_{uuid.uuid4().hex[:8]}_{safe_stage}"
    folder.mkdir(parents=True, exist_ok=False)

    html = "Snapshot do componente indisponível."
    try:
        html = driver.execute_script(
            """
            const selector = arguments[0];
            const candidates = selector ? [selector] : [
              'div[role="dialog"]', '.artdeco-modal__content', '.jobs-easy-apply-modal',
              '.jobs-search__job-details--wrapper', '.jobs-search-results-list'
            ];
            let root = null;
            for (const candidate of candidates) {
              root = document.querySelector(candidate);
              if (root) break;
            }
            if (!root) return '<!-- componente da tela não encontrado -->';
            const clone = root.cloneNode(true);
            clone.querySelectorAll('script,iframe, input[type="hidden"]').forEach(node => node.remove());
            clone.querySelectorAll('input,textarea,select,[contenteditable="true"]').forEach(node => {
              node.removeAttribute('value');
              node.removeAttribute('checked');
              node.removeAttribute('selected');
              if (node.tagName === 'TEXTAREA' || node.isContentEditable) node.textContent = '';
            });
            clone.querySelectorAll('[value]').forEach(node => node.removeAttribute('value'));
            clone.querySelectorAll('dd, [aria-checked], [aria-selected]').forEach(node => {
              node.removeAttribute('aria-checked');
              node.removeAttribute('aria-selected');
              if (node.tagName === 'DD') node.textContent = '[valor ocultado]';
            });
            return clone.outerHTML;
            """,
            selector,
        ) or "<!-- snapshot vazio -->"
    except Exception as capture_error:
        html = f"<!-- falha ao capturar componente: {sanitize_text(capture_error)} -->"

    (folder / "componente.html").write_text(sanitize_html(html), encoding="utf-8")
    try:
        current_url = sanitize_url(driver.current_url)
    except Exception:
        current_url = "[url indisponível]"
    def sanitize_structure(value):
        if isinstance(value, dict):
            return {sanitize_text(key): sanitize_structure(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [sanitize_structure(item) for item in value]
        if isinstance(value, str):
            return sanitize_text(value)
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return sanitize_text(value)

    metadata = {
        "data_hora": time.strftime("%Y-%m-%d %H:%M:%S"),
        "etapa": sanitize_text(stage, 120),
        "url": current_url,
        "erro": sanitize_text(error),
        "sinais": sanitize_structure(signals or {}),
        "html": "componente.html",
        "observacao": "Valores de campos, scripts e consultas de URL são removidos do snapshot.",
    }
    (folder / "resumo.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if os.name != "nt":
        for file_path in folder.iterdir():
            file_path.chmod(0o600)
        folder.chmod(0o700)
    return str(folder)
