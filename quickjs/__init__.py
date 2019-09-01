import concurrent.futures
import json
import threading
import sys
import os.path

BASE_PATH = os.path.abspath(os.path.dirname(__file__))

sys.path += [BASE_PATH]

import _quickjs

Context = _quickjs.Context
Object = _quickjs.Object
JSException = _quickjs.JSException
StackOverflow = _quickjs.StackOverflow
