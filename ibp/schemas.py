""":py:mod:`marshmallow` schemas for IBP models.
"""

from marshmallow import Schema, fields

class UnitSchema(Schema):
    """:py:mod:`marshmallow` schema for :py:class:`ibp.models.Unit`.
    """

    name = fields.Str()
    url = fields.URL()


class LookupSchema(Schema):
    """:py:mod:`marshmallow` schema for :py:class:`ibp.models.Lookup`.
    """

    datetime = fields.DateTime()


class CommentSchema(Schema):
    """Schema for Comment model."""

    index = fields.Int(dump_only=True)
    datetime = fields.DateTime()
    author = fields.Str()
    body = fields.Str()


class RequestSchema(Schema):
    """Schema for Request model."""

    index = fields.Int(dump_only=True)
    date_postmarked = fields.Date()
    action = fields.Str()

request = RequestSchema()

class InmateSchema(Schema):
    """Schema for Inmate model."""

    jurisdiction = fields.Str()
    id = fields.Int()

    first_name = fields.Str()
    last_name = fields.Str()

    sex = fields.Str()
    url = fields.URL()
    race = fields.Str()
    release = fields.Str()

    unit = fields.Nested(UnitSchema, only=['name', 'url'])
    lookups = fields.Nested(LookupSchema, many=True)
    comments = fields.Nested(CommentSchema, many=True)
    requests = fields.Nested(RequestSchema, many=True)


inmate = InmateSchema()
inmates = InmateSchema(
    many=True,
    only=[
        'jurisdiction',
        'id',
        'first_name',
        'last_name',
        'unit.name',
    ]
)
