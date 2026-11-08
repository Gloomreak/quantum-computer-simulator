"""Точка входа приложения «Симулятор квантового компьютера».

Запуск:

.. code-block:: bash

    streamlit run app.py

Все расчёты выполняются локально в этом процессе; сеть не используется.
"""

from __future__ import annotations

import streamlit as st

from src.ui import (
    architecture,
    circuit_editor,
    experiments_view,
    help_view,
    noise_view,
    run_view,
)
from src.ui.state import (
    NAV_ARCHITECTURE,
    NAV_EDITOR,
    NAV_EXPERIMENTS,
    NAV_HELP,
    NAV_ITEMS,
    NAV_NOISE,
    NAV_RESULTS,
    apply_pending_action,
    get_circuit,
    get_noise,
    init_state,
)

PAGES = {
    NAV_ARCHITECTURE: architecture.render,
    NAV_EDITOR: circuit_editor.render,
    NAV_RESULTS: run_view.render,
    NAV_NOISE: noise_view.render,
    NAV_EXPERIMENTS: experiments_view.render,
    NAV_HELP: help_view.render,
}

CUSTOM_CSS = """
<style>
    .block-container {padding-top: 2.2rem; padding-bottom: 2.5rem; max-width: 1400px;}
    h1 {font-size: 1.85rem; letter-spacing: -0.01em; margin-bottom: 0.2rem;}
    h2 {font-size: 1.25rem; margin-top: 0.6rem;}
    h3 {font-size: 1.05rem;}
    [data-testid="stMetricValue"] {font-size: 1.35rem;}
    [data-testid="stSidebar"] {background-color: #F8FAFC;}
    [data-testid="stSidebar"] hr {margin: 0.6rem 0;}
    div[data-testid="stAlert"] {border-radius: 8px;}
    .stTabs [data-baseweb="tab"] {font-size: 0.95rem;}
    figure {margin: 0;}

    /* Весь вспомогательный текст — чёрный, без серого оттенка. */
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] *,
    [data-testid="stMetricLabel"],
    [data-testid="stMetricLabel"] *,
    [data-testid="stWidgetLabel"] p,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] li,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] small,
    [data-testid="stMarkdownContainer"] em {
        color: #000000 !important;
    }
</style>
"""


def _sidebar() -> str:
    """Боковая панель: навигация и состояние схемы."""

    with st.sidebar:
        st.markdown("### Симулятор квантового компьютера")
        st.caption(
            "Учебная модель: схемы, исполнение, измерение и исследование "
            "аппаратных ошибок."
        )
        st.divider()
        page = st.radio("Разделы", options=NAV_ITEMS, key="nav")
        st.divider()

        circuit = get_circuit()
        noise = get_noise()
        st.caption(
            f"**Схема:** {circuit.n_qubits} кубит(ов) · {circuit.gate_count} операций "
            f"· глубина {circuit.depth()}"
        )
        st.caption(
            "**Режим:** "
            + ("модель с ошибками" if noise.enabled else "идеальная модель")
        )
        st.caption(
            f"**Запуск:** shots = {st.session_state.get('shots', '—')}, "
            f"seed = {st.session_state.get('seed', '—')}"
        )
    return page


def main() -> None:
    """Отрисовка выбранного раздела."""

    st.set_page_config(
        page_title="Симулятор квантового компьютера",
        page_icon="⚛",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    init_state()
    apply_pending_action()
    page = _sidebar()

    renderer = PAGES.get(page, architecture.render)
    try:
        renderer()
    except Exception as exc:  # noqa: BLE001 - приложение не должно падать
        st.error(
            "Произошла непредвиденная ошибка при отрисовке раздела. "
            "Попробуйте вернуться на главную страницу или перезапустить приложение."
        )
        with st.expander("Технические подробности"):
            st.exception(exc)


if __name__ == "__main__":
    main()


__all__ = ["main"]
