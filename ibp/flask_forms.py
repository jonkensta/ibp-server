import decimal

from flask_wtf import FlaskForm
from wtforms import fields, validators


def validate_inmate_id(form, field):
    data = field.data or ''
    try:
        data = int(data.replace('-', ''))
    except ValueError:
        msg = "'{}' is not a valid inmate ID".format(data)
        raise validators.ValidationError(msg)
    return data


class InmateSearchForm(FlaskForm):
    first_name = fields.StringField('First Name')
    last_name = fields.StringField('Last Name')
    id_ = fields.StringField('Inmate ID', [validate_inmate_id])

    def validate(self):
        first = self.first_name.data
        last = self.last_name.data
        id_ = self.id_.data

        if first and last:
            return True

        elif first or last:
            msg = "Both first and last names must be given."
            first.errors.append(msg)
            last.errors.append(msg)
            return False

        elif id_:
            return FlaskForm.validate(self)

        else:
            return False


states = [
    (state, state) for state in [
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IO', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
    ]
]


class Unit(FlaskForm):
    street1 = fields.StringField(
        'Street Address 1',
        [validators.InputRequired()]
    )
    street2 = fields.StringField(
        'Street Address 2',
        [validators.Optional()]
    )
    city = fields.StringField(
        'City',
        [validators.InputRequired()]
    )
    state = fields.SelectField(
        'State',
        choices=states
    )
    zipcode = fields.StringField(
        'Zipcode',
        [validators.InputRequired(), validators.Length(min=5, max=11)]
    )
    shipping_method = fields.SelectField(
        'Shipping Method',
        choices=[('', ''), ('Box', 'Box'), ('Individual', 'Individual')]
    )
    url = fields.StringField(
        'URL',
        [validators.Optional(), validators.URL()]
    )

    def __init__(self, *args, **kwargs):
        super(Unit, self).__init__(*args, **kwargs)

    def update_from_model(self, model):
        self.url.data = model.url or ''
        self.city.data = model.city
        self.state.data = model.state
        self.street1.data = model.street1
        self.street2.data = model.street2
        self.zipcode.data = model.zipcode
        self.shipping_method.data = model.shipping_method or ''


class Comment(FlaskForm):
    author = fields.StringField(
        'author', [
            validators.InputRequired(),
            validators.length(
                min=1,
                message="Please input your name"
            )
        ]
    )
    comment = fields.StringField(
        'comment', [
            validators.InputRequired(),
            validators.length(
                min=1, max=60,
                message="Please input a message under 60 characters."
            )
        ]
    )


class Shipment(FlaskForm):
    request_ids = fields.FieldList(
        fields.IntegerField('request_ids', [validators.InputRequired()]),
        min_entries=1
    )
    tracking_code = fields.StringField(
        'weight', [validators.InputRequired()],
    )
    weight = fields.IntegerField(
        'weight', [validators.InputRequired()],
    )
    postage = fields.IntegerField(
        'postage', [validators.InputRequired()],
    )
