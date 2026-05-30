"""Put server/ on sys.path so tests import flat modules by bare name
(e.g. `import leak_classifier as L`). See server/INTERFACES.md."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
