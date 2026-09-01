# Changelog

Все заметные изменения в этом проекте фиксируются здесь. Формат основан на [Keep a Changelog](https://keepachangelog.com/), версии — по [Semantic Versioning](https://semver.org/).

> Как читать: `MAJOR.MINOR.PATCH`. `MAJOR` ломает совместимость, `MINOR` добавляет фичи, `PATCH` чинит баги.

## [Unreleased]

### Будет
- Что-то, что ещё в работе

## [1.0.0] — 2026-09-01

### Added
- Первый публичный релиз.
- Скачивание моделей / датасетов / спейсов с Hugging Face (файлы и целые репозитории).
- Пауза / возобновление загрузок с HTTP Range headers (докачка после сбоя).
- Очередь задач с режимом «строго по одной».
- Закладки на часто скачиваемые репозитории.
- Автоподхват ссылок из буфера обмена (с разрешения юзера).
- Локальный журнал событий (WARN/ERROR) с фильтром и копированием.
- 12 языков интерфейса: en, zh, hi, es, fr, ar, bn, pt, ru, ur, de, ja.
- Проверка обновлений через GitHub Releases (только уведомление, без автозагрузки).
- Сборки под Windows / macOS / Linux через GitHub Actions (тег `vX.Y.Z` → релиз).

### Fixed
- Модалка журнала могла «застрять» на старом языке при смене языка, если в логе были записи — `renderLogs` затирал `logsEmpty` через `innerHTML`, и `applyLang` падал с `TypeError: Cannot set properties of null`. Теперь `renderLogs` удаляет только `.log-entry`, оставляя плейсхолдер пустого состояния в DOM. Бонус: записи лога рендерятся через `createElement`+`textContent` вместо конкатенации HTML (XSS-safe).

### Security
- Замаскированы токены HF, Authorization-заголовки, имена репозиториев в `.hfdl_log.txt`.

---

## Шаблон для следующих релизов

```markdown
## [X.Y.Z] — YYYY-MM-DD

### Added
- Новая фича.

### Changed
- Изменили поведение существующей фичи.

### Fixed
- Что-то починили.

### Removed
- Что-то удалили (deprecated).

### Security
- Что-то связанное с безопасностью.
```

[Unreleased]: https://github.com/alexveliyar-coder/HF-Downloader/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/alexveliyar-coder/HF-Downloader/releases/tag/v1.0.0
