# -*- coding: utf-8 -*-

import sikuli_utils, os

sikuli_utils.start_app()
if os.path.isfile("usecase.py"):
    try:
        execfile("usecase.py")
        sikuli_utils.wait_for_app_to_terminate()
    except:
        sikuli_utils.close_window()
        raise
