# Источники

Список разделён на книги, документацию библиотек и учебные материалы.
Ссылки на книги даны по изданию и ISBN; ссылки на программную документацию
ведут на официальные сайты.

## Книги

1. Nielsen M. A., Chuang I. L. *Quantum Computation and Quantum Information*
   (10th Anniversary Edition). Cambridge University Press, 2010.
   ISBN 978-1-107-00217-3. — каноническое изложение вентилей, измерения,
   запутанности, шумовых каналов и метрик различия состояний.

2. Mermin N. D. *Quantum Computer Science: An Introduction*. Cambridge
   University Press, 2007. ISBN 978-0-521-87658-2. — компактное введение в
   квантовые схемы и измерение.

3. Levin D. A., Peres Y., Wilmer E. L. *Markov Chains and Mixing Times*.
   American Mathematical Society, 2009. ISBN 978-0-8218-4739-8. — определение
   и свойства полного вариационного расстояния (total variation distance).

4. Preskill J. *Quantum Computation* (конспект лекций, Caltech). —
   дополнительный учебный материал по квантовой информации; конспект
   доступен на сайте автора.

## Документация программного обеспечения

5. NumPy. *NumPy Documentation*. <https://numpy.org/doc/stable/> — массивы,
   `complex128`, `numpy.random.Generator`, `SeedSequence`, тензорные операции.

6. Streamlit. *Streamlit Documentation*. <https://docs.streamlit.io/> —
   виджеты, состояние сессии, кэширование, развёртывание локального
   приложения.

7. Python Software Foundation. *Python 3 Documentation*.
   <https://docs.python.org/3/> — язык, `dataclasses`, `json`, `csv`,
   `unittest`.

8. Pillow. *Pillow Documentation*. <https://pillow.readthedocs.io/en/stable/> —
   отрисовка изображений, шрифты TrueType, сохранение PNG.

9. pandas. *pandas Documentation*. <https://pandas.pydata.org/docs/> —
   таблицы, экспорт CSV.

10. Docker. *Docker Documentation*. <https://docs.docker.com/> — образы,
    `docker save`/`docker load`, публикация портов, healthcheck.

11. pytest. *pytest Documentation*. <https://docs.pytest.org/en/stable/> —
    запуск тестов (тесты проекта совместимы и с `unittest`).

## Квантовые вычисления и шумовые модели (документация)

12. Qiskit Aer. *Qiskit Aer Documentation*. <https://qiskit.github.io/qiskit-aer/>
    — модели шума (bit-flip, phase-flip, readout) и траекторное моделирование;
    использовано как ориентир при описании моделей, но приложение от Qiskit
    не зависит.

13. IBM Quantum. *IBM Quantum Documentation*. <https://docs.quantum.ibm.com/> —
    описание калибровки, ошибок считывания и метрик устройств.

## Данные и лицензии

14. DejaVu Fonts. <https://dejavu-fonts.github.io/> — свободный шрифт с
    поддержкой кириллицы, поставляется в `assets/fonts`.
    Лицензия: <https://dejavu-fonts.github.io/License.html> (на основе
    лицензии Bitstream Vera).

## Как оформлены ссылки

Источники, использованные при разработке: формулы вентилей и измерения
сверены с Nielsen & Chuang; семантика траекторного моделирования — с
документацией Qiskit Aer; метрика TVD — с Levin, Peres, Wilmer. Все
библиографические данные приведены по изданиям, указанным выше; ссылки на
программную документацию ведут на официальные сайты.
