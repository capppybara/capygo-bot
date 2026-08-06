"""capygo-bot: a small perception-action framework for automating CapyBara Go!.

Layers:
  window      find the game window and its live bounds
  capture     grab the window as an image
  perception  turn image regions into matches (template matching, later OCR)
  input       post synthetic clicks at window-relative positions
  task        base classes + registry for pluggable automation tasks
  controller  wires everything together and runs a task
"""

__version__ = "0.1.0"
