""":py:mod:`flask` views for the IBP REST API.
"""

import flask
import nameparser

import ibp
from . import models
from . import schemas


@ibp.app.route('/inmate/<jurisdiction>/<int:id_>', methods=['GET'])
def get_inmate(jurisdiction, id_):
    """:py:mod:`flask` view to handle a GET request for an inmate's info.
    """

    inmates, errors = models.Inmate.query.providers_by_id(id_)
    inmate = inmates.filter_by(jurisdiction=jurisdiction).first_or_404()
    result = schemas.inmate.dump(inmate)
    return {'inmate': result, 'errors': errors}


@ibp.app.route('/inmates', methods=['GET'])
def get_inmates():
    """:py:mod:`flask` view to handle a GET request for an inmate search.
    """

    try:
        search = flask.request.args['search']
    except KeyError:
        return {'message': "Search input must be provided"}, 400

    if not search:
        return {'message': "Some search input must be provided"}, 400

    query = models.Inmate.query

    try:
        id_ = int(search.replace('-', ''))
        inmates, errors = query.providers_by_id(id_)

    except ValueError:
        name = nameparser.HumanName(search)
        inmates, errors = query.providers_by_name(name.first, name.last)

    result = schemas.inmates.dump(inmates)
    return {'inmates': result, 'errors': errors}
