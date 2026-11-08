"""Проверка приложения в настоящем рантайме Streamlit (AppTest).

Запуск (из каталога проекта, нужен установленный Streamlit):

.. code-block:: bash

    python tools/app_test.py


Запускает app.py, переходит по всем разделам и выполняет основные действия:
загрузку демо-схемы, запуск схемы, включение ошибок, серию экспериментов.
"""

from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")
sys.path.insert(0, ROOT)

try:  # консоль Windows может быть в cp1251/cp866 — выводим в UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover - не критично для проверки
    pass

from streamlit.testing.v1 import AppTest  # noqa: E402

FAILURES = []


def check(name, condition, detail=""):
    status = "OK  " if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


def exceptions(at):
    return [str(item.value) for item in at.exception]


def navigate(at, page, expected_title):
    at.session_state["nav"] = page
    at.run()
    errors = exceptions(at)
    titles = [title.value for title in at.title]
    check(
        f"раздел «{page}»",
        not errors and expected_title in titles,
        f"exceptions={errors[:1]}, titles={titles}",
    )


def widget(elements, key):
    for element in elements:
        if getattr(element, "key", None) == key:
            return element
    raise KeyError(f"виджет {key!r} не найден")


def main() -> int:
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()

    check("приложение стартует", not exceptions(at), str(exceptions(at))[:200])
    radios = at.sidebar.radio[0]
    check("боковая навигация из 6 разделов", len(radios.options) == 6)
    check(
        "в навигации нет иконок",
        all(option in {"Архитектура", "Конструктор схем", "Запуск и результаты",
                       "Аппаратные ошибки", "Эксперименты", "Справка"}
            for option in radios.options),
        str(radios.options),
    )
    check(
        "в сайдбаре нет кнопки демо",
        all(getattr(button, "key", None) != "sidebar_bell_demo" for button in at.button),
    )
    sidebar_captions = " ".join(caption.value for caption in at.sidebar.caption)
    check(
        "в сайдбаре нет версии и строки про облачные сервисы",
        "Версия" not in sidebar_captions and "облачных" not in sidebar_captions,
        sidebar_captions,
    )

    navigate(at, "Архитектура", "Моделирование архитектуры квантового компьютера")
    navigate(at, "Конструктор схем", "Конструктор квантовой схемы")
    navigate(at, "Запуск и результаты", "Запуск и результаты")
    navigate(at, "Аппаратные ошибки", "Модели аппаратных ошибок")
    navigate(at, "Эксперименты", "Эксперименты")
    navigate(at, "Справка", "Справка")
    help_markdown = " ".join(markdown.value for markdown in at.markdown)
    check(
        "в справке нет блока «Документация проекта»",
        "Документация проекта" not in help_markdown,
    )
    check(
        "в справке нет строки про демонстрацию 3–5 минут",
        "Демонстрация за 3–5 минут" not in help_markdown,
    )

    # --- Конструктор: загрузка демо-схемы Белла ---
    navigate(at, "Конструктор схем", "Конструктор квантовой схемы")
    demo = widget(at.selectbox, "demo_choice")
    demo.select("2 кубита: состояние Белла (H + CNOT)")
    at.run()
    widget(at.button, "load_demo_button").click()
    at.run()
    check("демо-схема загружена", not exceptions(at), str(exceptions(at))[:300])
    circuit = at.session_state["circuit"]
    check(
        "схема Белла: 2 кубита, 2 операции",
        circuit.n_qubits == 2 and circuit.gate_count == 2,
        f"{circuit.n_qubits} кубита, {circuit.gate_count} операций",
    )
    check("изображение схемы построено", len(at.get("imgs")) >= 1)

    # --- Конструктор: добавление и удаление операции ---
    before = circuit.gate_count
    widget(at.button, "add_operation_button").click()
    at.run()
    after = at.session_state["circuit"].gate_count
    check("добавление операции", after == before + 1, f"{before} → {after}")
    widget(at.button, "delete_0").click()
    at.run()
    check(
        "удаление операции",
        at.session_state["circuit"].gate_count == before,
        f"{after} → {at.session_state['circuit'].gate_count}",
    )

    # Возвращаем исходную схему Белла после экспериментов с редактированием.
    widget(at.button, "load_demo_button").click()
    at.run()

    # --- Запуск идеальной схемы ---
    navigate(at, "Запуск и результаты", "Запуск и результаты")
    at.session_state["shots"] = 500
    widget(at.number_input, "shots").set_value(500)
    at.run()
    widget(at.button, "run_circuit_button").click()
    at.run()
    check("идеальный запуск", not exceptions(at), str(exceptions(at))[:300])
    result = at.session_state["result"]
    check("результат получен", result is not None)
    if result is not None:
        check("500 измерений", sum(result.counts.values()) == 500, str(result.counts))
        check("идеальный режим", result.mode == "ideal", result.mode)
        check(
            "Белл: только 00 и 11",
            result.counts.get("01", 0) == 0 and result.counts.get("10", 0) == 0,
        )

    # --- Включение модели ошибок ---
    navigate(at, "Аппаратные ошибки", "Модели аппаратных ошибок")
    widget(at.radio, "noise_mode").set_value("Модель с ошибками")
    at.run()
    check("режим ошибок включён", at.session_state["noise"].enabled)
    widget(at.slider, "noise_bit_flip_prob").set_value(0.08)
    widget(at.slider, "noise_readout_prob").set_value(0.04)
    at.run()
    noise = at.session_state["noise"]
    check(
        "вероятности применены",
        abs(noise.p_bit_flip - 0.08) < 1e-9 and abs(noise.p_readout - 0.04) < 1e-9,
        f"p_bit_flip={noise.p_bit_flip}, p_readout={noise.p_readout}",
    )
    check("сравнение режимов построено", len(at.get("imgs")) >= 1)

    # --- Шумовой запуск ---
    navigate(at, "Запуск и результаты", "Запуск и результаты")
    widget(at.button, "run_circuit_button").click()
    at.run()
    noisy = at.session_state["result"]
    check("шумовой запуск", not exceptions(at), str(exceptions(at))[:300])
    check(
        "есть шумовые частоты",
        noisy is not None and noisy.noisy_counts is not None,
    )

    # --- Эксперимент bit-flip ---
    navigate(at, "Эксперименты", "Эксперименты")
    widget(at.selectbox, "exp_kind").select("TVD от вероятности bit-flip")
    at.run()
    widget(at.number_input, "exp_shots").set_value(200)
    widget(at.number_input, "exp_repeats").set_value(2)
    widget(at.number_input, "exp_p_max").set_value(0.05)
    widget(at.number_input, "exp_p_step").set_value(0.05)
    at.run()
    widget(at.button, "run_experiment_button").click()
    at.run()
    check("серия bit-flip", not exceptions(at), str(exceptions(at))[:400])
    experiment = at.session_state["experiment_result"] if "experiment_result" in at.session_state else None
    check("результат серии получен", experiment is not None)
    if experiment is not None:
        check("2 точки по 2 повтора", experiment.total_runs == 4, str(experiment.total_runs))
        check("график серии построен", len(at.get("imgs")) >= 1)

    # --- Эксперимент «TVD от числа измерений» ---
    widget(at.selectbox, "exp_kind").select("TVD от числа измерений (shots)")
    at.run()
    widget(at.multiselect, "exp_shots_grid").set_value([100, 500])
    widget(at.number_input, "exp_repeats").set_value(2)
    at.run()
    widget(at.button, "run_experiment_button").click()
    at.run()
    shots_result = at.session_state["experiment_result"] if "experiment_result" in at.session_state else None
    check("серия по shots", not exceptions(at), str(exceptions(at))[:400])
    check(
        "сетка shots применена",
        shots_result is not None
        and shots_result.kind == "shots"
        and [p.value for p in shots_result.series[0].points] == [100.0, 500.0],
    )

    # --- Архитектура: текстовая схема и выбор блока ---
    navigate(at, "Архитектура", "Моделирование архитектуры квантового компьютера")
    check(
        "на странице архитектуры есть схема-изображение",
        len(at.get("imgs")) >= 1,
        f"изображений: {len(at.get('imgs'))}",
    )
    architecture_captions = " ".join(caption.value for caption in at.caption)
    check(
        "на странице архитектуры нет строки «Учебный симулятор»",
        "Учебный симулятор" not in architecture_captions,
    )

    print()
    if FAILURES:
        print(f"НЕ ПРОЙДЕНО: {len(FAILURES)}")
        for name in FAILURES:
            print(" -", name)
        return 1
    print("Все проверки в реальном рантайме Streamlit пройдены.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
