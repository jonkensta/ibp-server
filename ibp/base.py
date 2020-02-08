import bottle

# setup bottle application
app = bottle.Bottle()  # pylint: disable=invalid-name

from . import models
from . import routes
