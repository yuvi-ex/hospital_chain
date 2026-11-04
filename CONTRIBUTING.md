# Contributing

Thanks for helping. This is a demo repository, so changes that make it easier to install, understand or present are
the most welcome.

- **Bugs and questions:** open an issue with your OS, `exakit --version`, the build step that failed and its output.
- **Pull requests:** keep them small and focused. Before opening one:
  - run `python3 -m py_compile` on changed Python files and `bash -n` on changed scripts;
  - if you change `data/generate.py`, run `.venv/bin/python data/generate.py --files-only` and commit the regenerated
    `data/out` (then `data/imaging.py refresh` if the imaging plan changed);
  - keep all data synthetic and the chain fictional: no real people, hospitals, cities, phone numbers or email domains;
  - never commit anything from `secrets/`, `config.local.env` or `.work/`.

By contributing you agree that your contribution is licensed under the MIT license of this repository, and to follow
the [Code of Conduct](CODE_OF_CONDUCT.md).
