"""Entry point: `python -m beam_check_desk` opens the window.

Absolute import on purpose: PyInstaller runs this file as a top-level script,
where a relative import has no parent package and fails.
"""

from beam_check_desk.ui.main_window import main

if __name__ == "__main__":
    main()
