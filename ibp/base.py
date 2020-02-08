import bottle

# setup bottle application
app = bottle.Bottle()  # pylint: disable=invalid-name

from . import views
from . import models
