# Documentation

This folder describes how Automator classifies AFIP invoices, where files land,
and how the code is put together. Start here, then follow the document that
matches the question.

## Product

| Document | What it covers |
|---|---|
| [features.md](features.md) | Classification, safe routing, companies vs suppliers, history, copy mode and first launch. |
| [configuration.md](configuration.md) | `config.json` locations, fields, folder names, the destination template and validation. |
| [how-it-works.md](how-it-works.md) | Path of a PDF from the inbox through parse, filing policy and placement. |
| [ui.md](ui.md) | CustomTkinter shell, views, controllers, widgets and dialogs. |
| [invariant.md](invariant.md) | The safety invariant and the cases that go to review or quarantine. |

## Internals

| Document | What it covers |
|---|---|
| [architecture.md](architecture.md) | Layers (`ui -> services -> domain`), packages and the flow of a file. |
| [data-model.md](data-model.md) | `ParsedInvoice`, identities, outcomes and buyer resolution. |
| [persistence.md](persistence.md) | Atomic `config.json`, SQLite history, supplier registry and rotating logs. |
| [concurrency.md](concurrency.md) | Engine generations, the work queue and the Tkinter event pump. |
| [testing.md](testing.md) | Pytest layout, the 90% core coverage floor and UI smokes. |

## Decisions

| Document | What it covers |
|---|---|
| [adr/README.md](adr/README.md) | Architecture decision records for filing, layers and persistence. |

## Contributing

| Document | What it covers |
|---|---|
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Environment, workflow, code standards and where new code belongs. |
| [../CHANGELOG.md](../CHANGELOG.md) | Version history. |
| [../README.md](../README.md) | Project entry: install, run, build and the package tree. |
