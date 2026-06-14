# Тесты Nika

## Структура

- **`test_golden.py`** — параметризованный runner. Для каждого `cases/**/<name>.lisp`
  он запускает программный интерпретатор (`lang.runtime.interpret`) и обе
  модели машины (`lang.machine.simulation` -- seq), сверяет:
  - `acc` после `HALT`;
  - `output` (PORT_OUT, опционально по `output_startswith`);
  - полный мнемонический дамп бинарного кода (`<name>.bin.txt`);
  - репрезентативный фрагмент журнала seq-модели (`<name>.log.txt`).
- **`test_machine.py`** — проверки специфичные для машины: метрики симуляции, бинарный round-trip ISA. Семантическая parity
  runtime ↔ machine уже покрыта в test_golden.

## Запуск

```
python -m unittest discover -s tests
```

## Регенерация эталонов

При изменении компилятора `*.bin.txt` и `*.log.txt` нужно перегенерировать:

```
REGEN=1 python -m unittest discover -s tests
```

JSON-файлы с ожидаемым `acc`/`output` обновляются вручную (или через
`python tests/cases/_seed.py`, если случай заведён в seed).

## Добавление нового кейса

1. Добавить запись в `tests/cases/_seed.py` (категория + источник + ожидания).
2. `python tests/cases/_seed.py` — пишет `.lisp` + `.json`.
3. `REGEN=1 python -m unittest discover -s tests` — создаёт `.bin.txt` и `.log.txt`.
4. Запустить без `REGEN` ещё раз — убедиться, что эталоны воспроизводятся.

## JSON-формат

```json
{
  "acc": 42,
  "output": "Hello",
  "output_startswith": "Hello",
  "input": [5, 72, 101, 108, 108, 111],
  "machine_parity": true,
  "skip": "reason"
}
```

- `acc` — обязателен.
- `output` либо `output_startswith` — для проверки PORT_OUT.
- `input` — список int'ов, поступающих через trap (см. `lang/machine.py:trap_queue`).
- `machine_parity` (default true) — гонять ли кейс через `simulation` помимо `interpret`.
- `skip` — пропустить кейс с указанной причиной.
