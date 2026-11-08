"""Проверка страниц Streamlit без установленного Streamlit.

Скрипт подменяет модуль ``streamlit`` минимальной заглушкой, которая
записывает вызовы и возвращает заранее заданные значения виджетов, после
чего отрисовывает все разделы приложения и проверяет, что:

* ни одна страница не падает с исключением;
* графики действительно являются PNG;
* таблицы и метрики заполняются;
* действия (добавление вентиля, загрузка демо, запуск схемы, серия
  экспериментов) меняют состояние и приводят к результату.

Запуск: ``python tools/ui_check.py``. Это вспомогательный инструмент
разработчика; в контейнер он не входит.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _Rerun(Exception):
    """Аналог st.rerun()."""


class _Stop(Exception):
    """Аналог st.stop()."""


class _Progress:
    def __init__(self, recorder: "Recorder") -> None:
        self.recorder = recorder
        self.values: List[float] = []

    def progress(self, value: float, text: Optional[str] = None) -> None:
        self.values.append(float(value))

    def empty(self) -> None:
        return None


class _ColumnConfig:
    def __getattr__(self, name: str):
        def factory(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            return {"type": name, "args": args, "kwargs": kwargs}

        return factory


class Recorder:
    """Хранилище вызовов и настроек сценария."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.calls: List[str] = []
        self.images: List[bytes] = []
        self.dataframes: List[Any] = []
        self.downloads: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.infos: List[str] = []
        self.successes: List[str] = []
        self.metrics: List[Dict[str, Any]] = []
        self.overrides: Dict[str, Any] = {}
        self.clicked: set[str] = set()
        self.progress: List[_Progress] = []

    def scenario(
        self,
        overrides: Optional[Dict[str, Any]] = None,
        clicked: Optional[set[str]] = None,
    ) -> None:
        self.calls.clear()
        self.images.clear()
        self.dataframes.clear()
        self.downloads.clear()
        self.errors.clear()
        self.warnings.clear()
        self.infos.clear()
        self.successes.clear()
        self.metrics.clear()
        self.progress.clear()
        self.overrides = dict(overrides or {})
        self.clicked = set(clicked or ())


class SessionState(dict):
    """Словарь с интерфейсом st.session_state.

    Повторяет ограничение Streamlit: значение виджета нельзя изменить через
    API после того, как виджет создан в текущем запуске скрипта.
    """

    locked: set[str]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.locked = set()

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self.locked:
            raise RuntimeError(
                f"st.session_state.{key} нельзя изменить после создания виджета"
            )
        dict.__setitem__(self, key, value)


class Container:
    """Контейнер (колонка, вкладка, expander), поддерживающий `with`."""

    def __init__(self, module: "FakeStreamlit", name: str) -> None:
        self._module = module
        self._name = name

    def __enter__(self) -> "Container":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        return False

    def __getattr__(self, name: str):
        return getattr(self._module, name)


class FakeStreamlit:
    """Минимальная заглушка API Streamlit, используемая приложением."""

    def __init__(self) -> None:
        self.recorder = Recorder()
        self.session_state = SessionState()
        self.sidebar = Container(self, "sidebar")
        self.column_config = _ColumnConfig()
        self._call_helpers()

    # ------------------------------------------------------------------
    def _call_helpers(self) -> None:
        self._names = (
            "markdown title caption subheader write code latex divider text "
            "header set_page_config stop rerun"
        ).split()

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.recorder.calls.append(name)

    def _widget_value(self, key: Optional[str], default: Any, options: Any = None) -> Any:
        """Значение виджета: override → session_state → значение по умолчанию.

        Ведёт себя как Streamlit: значение виджета сохраняется в
        session_state под его ключом.
        """

        if key and key in self.recorder.overrides:
            value = self.recorder.overrides[key]
        elif key and key in self.session_state:
            value = self.session_state[key]
        else:
            value = default
        if options is not None:
            options = list(options)
            if value not in options:
                value = options[0] if options else None
        if key:
            dict.__setitem__(self.session_state, key, value)
            self.session_state.locked.add(key)
        return value

    # --- виджеты ------------------------------------------------------
    def button(self, label: str, key: Optional[str] = None, **kwargs: Any) -> bool:
        self._record("button")
        return key in self.recorder.clicked

    def download_button(self, label: str, data: Any = b"", key: Optional[str] = None, **kwargs: Any) -> bool:
        self._record("download_button")
        self.recorder.downloads.append(
            {"label": label, "data": data, "file_name": kwargs.get("file_name")}
        )
        return False

    def selectbox(self, label: str, options: Any = (), index: int = 0, key: Optional[str] = None, **kwargs: Any) -> Any:
        self._record("selectbox")
        options = list(options)
        index = min(max(int(index), 0), len(options) - 1) if options else 0
        return self._widget_value(key, options[index] if options else None, options)

    def multiselect(self, label: str, options: Any = (), default: Any = None, key: Optional[str] = None, **kwargs: Any) -> List[Any]:
        self._record("multiselect")
        value = self._widget_value(key, list(default or []))
        return list(value or [])

    def radio(self, label: str, options: Any = (), index: int = 0, key: Optional[str] = None, **kwargs: Any) -> Any:
        self._record("radio")
        options = list(options)
        index = min(max(int(index), 0), len(options) - 1) if options else 0
        return self._widget_value(key, options[index] if options else None, options)

    def number_input(self, label: str, min_value: Any = None, max_value: Any = None, value: Any = None, key: Optional[str] = None, **kwargs: Any) -> Any:
        self._record("number_input")
        default = value if value is not None else (min_value if min_value is not None else 0)
        return self._widget_value(key, default)

    def slider(self, label: str, min_value: Any = 0, max_value: Any = 100, value: Any = None, key: Optional[str] = None, **kwargs: Any) -> Any:
        self._record("slider")
        default = value if value is not None else min_value
        return self._widget_value(key, default)

    def text_input(self, label: str, value: str = "", key: Optional[str] = None, **kwargs: Any) -> str:
        self._record("text_input")
        return self._widget_value(key, value)

    def checkbox(self, label: str, value: bool = False, key: Optional[str] = None, **kwargs: Any) -> bool:
        self._record("checkbox")
        return bool(self._widget_value(key, value))

    def toggle(self, label: str, value: bool = False, key: Optional[str] = None, **kwargs: Any) -> bool:
        self._record("toggle")
        return bool(self._widget_value(key, value))

    def file_uploader(self, label: str, key: Optional[str] = None, **kwargs: Any) -> Any:
        self._record("file_uploader")
        return self.recorder.overrides.get(key or label)

    def progress(self, value: float = 0.0, text: Optional[str] = None) -> _Progress:
        self._record("progress")
        progress = _Progress(self.recorder)
        self.recorder.progress.append(progress)
        return progress

    def empty(self) -> Container:
        return Container(self, "empty")

    # --- контейнеры ---------------------------------------------------
    def columns(self, spec: Any, **kwargs: Any) -> List[Container]:
        self._record("columns")
        count = spec if isinstance(spec, int) else len(spec)
        return [Container(self, f"column{i}") for i in range(count)]

    def tabs(self, labels: Any, **kwargs: Any) -> List[Container]:
        self._record("tabs")
        return [Container(self, f"tab{i}") for i, _ in enumerate(labels)]

    def expander(self, label: str, **kwargs: Any) -> Container:
        self._record("expander")
        return Container(self, "expander")

    def container(self, **kwargs: Any) -> Container:
        self._record("container")
        return Container(self, "container")

    def form(self, *args: Any, **kwargs: Any) -> Container:
        self._record("form")
        return Container(self, "form")

    def form_submit_button(self, *args: Any, **kwargs: Any) -> bool:
        return self.button(args[0] if args else "submit", key=kwargs.get("key"))

    # --- вывод --------------------------------------------------------
    def image(self, image: Any, caption: str = "", **kwargs: Any) -> None:
        self._record("image")
        self.recorder.images.append(image)

    def dataframe(self, data: Any, **kwargs: Any) -> None:
        self._record("dataframe")
        self.recorder.dataframes.append(data)

    def metric(self, label: str, value: Any, **kwargs: Any) -> None:
        self._record("metric")
        self.recorder.metrics.append({"label": label, "value": value})

    def error(self, message: Any, **kwargs: Any) -> None:
        self.recorder.errors.append(str(message))
        self.recorder.calls.append("error")

    def warning(self, message: Any, **kwargs: Any) -> None:
        self.recorder.warnings.append(str(message))
        self.recorder.calls.append("warning")

    def info(self, message: Any, **kwargs: Any) -> None:
        self.recorder.infos.append(str(message))
        self.recorder.calls.append("info")

    def success(self, message: Any, **kwargs: Any) -> None:
        self.recorder.successes.append(str(message))
        self.recorder.calls.append("success")

    def rerun(self, *args: Any, **kwargs: Any) -> None:
        raise _Rerun()

    def stop(self, *args: Any, **kwargs: Any) -> None:
        raise _Stop()

    def exception(self, *args: Any, **kwargs: Any) -> None:
        self.recorder.calls.append("exception")

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def noop(*args: Any, **kwargs: Any) -> None:
            self.recorder.calls.append(name)

        return noop


def install_stub() -> FakeStreamlit:
    """Подменить модуль streamlit заглушкой."""

    stub = FakeStreamlit()
    module = type(sys)("streamlit")
    module.__dict__.update(
        {
            name: getattr(stub, name)
            for name in dir(stub)
            if not name.startswith("_") and name not in {"session_state", "sidebar", "column_config"}
        }
    )
    module.session_state = stub.session_state
    module.sidebar = stub.sidebar
    module.column_config = stub.column_config

    # Любой отсутствующий атрибут (st.title, st.set_page_config, ...)
    # превращается в функцию-заглушку: PEP 562 — __getattr__ модуля.
    module.__getattr__ = lambda name: getattr(stub, name)

    sys.modules["streamlit"] = module
    return stub


def main() -> int:
    stub = install_stub()

    from src.ui import (
        architecture,
        circuit_editor,
        experiments_view,
        help_view,
        noise_view,
        run_view,
    )
    from src.ui.state import (
        NAV_EXPERIMENTS,
        NAV_RESULTS,
        apply_pending_action,
        get_circuit,
        get_experiment,
        get_noise,
        get_result,
        init_state,
    )

    failures: List[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    def render(module, overrides=None, clicked=None) -> str:
        # Новый запуск скрипта: ограничения на изменение виджетов сняты.
        stub.session_state.locked.clear()
        stub.recorder.scenario(overrides, clicked)
        try:
            module.render()
        except _Rerun:
            return "rerun"
        except _Stop:
            return "stop"
        except Exception:
            failures.append(
                f"{module.__name__}: исключение\n{traceback.format_exc()}"
            )
            return "error"
        return "ok"

    def fresh_state() -> None:
        stub.session_state.clear()
        stub.session_state.locked.clear()
        stub.recorder.reset()
        init_state()

    # 1. Все страницы открываются.
    for module, name, expect_images in (
        (architecture, "Архитектура", True),
        (circuit_editor, "Конструктор", True),
        (run_view, "Результаты", True),
        (noise_view, "Ошибки", True),
        (experiments_view, "Эксперименты", False),
        (help_view, "Справка", False),
    ):
        fresh_state()
        status = render(module)
        check(status == "ok", f"раздел «{name}»: статус {status}")
        check(not stub.recorder.errors, f"раздел «{name}»: неожиданные ошибки {stub.recorder.errors}")
        if expect_images:
            check(len(stub.recorder.images) >= 1, f"раздел «{name}»: нет изображений")
        for image in stub.recorder.images:
            check(
                isinstance(image, bytes) and image.startswith(b"\x89PNG\r\n\x1a\n"),
                f"раздел «{name}»: изображение не PNG",
            )

    # 2. Конструктор: добавление вентиля.
    fresh_state()
    before = get_circuit().gate_count
    status = render(circuit_editor, clicked={"add_operation_button"})
    check(status == "rerun", "добавление вентиля должно вызывать перезапуск")
    check(get_circuit().gate_count == before + 1, "вентиль не добавлен")

    # 3. Конструктор: удаление и очистка.
    fresh_state()
    get_circuit().add_gate("x", 0)
    before = get_circuit().gate_count
    render(circuit_editor, clicked={"delete_0"})
    check(get_circuit().gate_count == before - 1, "операция не удалена")

    fresh_state()
    render(circuit_editor, clicked={"clear_circuit_button"})
    check(get_circuit().gate_count == 0, "схема не очищена")

    # 4. Конструктор: загрузка демонстрационной схемы через отложенное действие.
    fresh_state()
    render(
        circuit_editor,
        overrides={"demo_choice": "2 кубита: состояние Белла (H + CNOT)"},
        clicked={"load_demo_button"},
    )
    stub.session_state.locked.clear()
    apply_pending_action()
    check(get_circuit().n_qubits == 2, "демо-схема не загрузилась")
    check(get_circuit().gate_count == 2, "неверное число операций в демо-схеме")
    check(
        stub.session_state.get("target") == "11",
        "целевая строка демо-схемы не подставлена",
    )

    # 4б. Переход между разделами через кнопку (отложенное действие).
    fresh_state()
    status = render(circuit_editor, clicked={"goto_results_button"})
    check(status == "rerun", "кнопка перехода должна вызывать перезапуск")
    stub.session_state.locked.clear()
    apply_pending_action()
    check(
        stub.session_state.get("nav") == NAV_RESULTS,
        "переход в раздел результатов не выполнен",
    )

    # 5. Запуск: результат появляется и содержит изображения.
    fresh_state()
    stub.session_state["shots"] = 500
    status = render(run_view, clicked={"run_circuit_button"})
    check(status == "ok", f"страница результатов: статус {status}")
    result = get_result()
    check(result is not None, "результат запуска не создан")
    if result is not None:
        check(sum(result.counts.values()) == 500, "неверное число измерений")
        check(result.mode == "ideal", "неожиданный режим запуска")
    check(len(stub.recorder.images) >= 2, "графики распределений не построены")

    # 6. Запуск в режиме ошибок.
    fresh_state()
    from src.quantum.noise import NoiseConfig

    stub.session_state["noise"] = NoiseConfig(
        enabled=True, p_bit_flip=0.1, p_readout=0.05
    )
    stub.session_state["shots"] = 400
    render(run_view, clicked={"run_circuit_button"})
    result = get_result()
    check(result is not None and result.noisy_counts is not None, "шумовой запуск не выполнен")

    # 7. Страница ошибок: переключение в шумовой режим и сравнение.
    fresh_state()
    status = render(noise_view, overrides={"noise_mode": "Модель с ошибками"})
    check(status == "ok", f"страница ошибок: статус {status}")
    check(get_noise().enabled, "режим ошибок не включён")
    check(len(stub.recorder.images) >= 1, "сравнение не построено")

    # 8. Эксперименты: маленькая серия.
    fresh_state()
    stub.session_state["nav"] = NAV_EXPERIMENTS
    overrides = {
        "exp_kind": "TVD от вероятности bit-flip",
        "exp_shots": 200,
        "exp_repeats": 2,
        "exp_p_max": 0.05,
        "exp_p_step": 0.05,
        "exp_p_min": 0.0,
        "exp_seed": 7,
    }
    status = render(experiments_view, overrides=overrides, clicked={"run_experiment_button"})
    check(status == "ok", f"эксперименты: статус {status}")
    experiment = get_experiment()
    check(experiment is not None, "результат эксперимента не создан")
    if experiment is not None:
        check(experiment.total_runs == 2 * 2, "неверное число запусков серии")
        check(len(experiment.series[0].points) == 2, "неверное число точек")
    check(len(stub.recorder.images) >= 1, "график эксперимента не построен")
    check(
        any(d["file_name"] and d["file_name"].endswith(".csv") for d in stub.recorder.downloads),
        "нет кнопки экспорта CSV",
    )
    check(
        any(d["file_name"] and d["file_name"].endswith(".png") for d in stub.recorder.downloads),
        "нет кнопки экспорта PNG",
    )

    # 8б. Эксперимент «TVD от числа измерений».
    fresh_state()
    shots_overrides = {
        "exp_kind": "TVD от числа измерений (shots)",
        "exp_repeats": 2,
        "exp_seed": 3,
        "exp_shots_grid": [100, 500],
        "exp_p_fixed": 0.05,
    }
    status = render(
        experiments_view,
        overrides=shots_overrides,
        clicked={"run_experiment_button"},
    )
    check(status == "ok", f"эксперимент shots: статус {status}")
    shots_result = get_experiment()
    check(
        shots_result is not None and shots_result.kind == "shots",
        "серия по shots не создана",
    )
    if shots_result is not None and shots_result.kind == "shots":
        check(
            [point.value for point in shots_result.series[0].points] == [100.0, 500.0],
            "неверная сетка shots",
        )
        check(shots_result.total_runs == 4, "неверное число запусков серии по shots")

    # 9. Полный запуск приложения через app.main().
    fresh_state()
    stub.session_state["nav"] = NAV_RESULTS
    try:
        import app as app_module

        app_module.main()
        app_ok = True
    except Exception:
        app_ok = False
        failures.append(f"app.main(): исключение\n{traceback.format_exc()}")
    check(app_ok, "app.main() завершился с ошибкой")

    # 10. Страница ошибок в идеальном режиме открывается без падения.
    fresh_state()
    check(render(noise_view) == "ok", "страница ошибок в идеальном режиме")

    if failures:
        print("ПРОВЕРКА НЕ ПРОЙДЕНА:")
        for failure in failures:
            print(" -", failure)
        return 1

    print("Проверка интерфейса пройдена: все разделы отрисованы, действия работают.")
    print(f"Всего вызовов Streamlit в последнем сценарии: {len(stub.recorder.calls)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
