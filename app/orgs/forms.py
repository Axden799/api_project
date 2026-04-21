from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length
from ..models import ROLES


class CreateOrgForm(FlaskForm):
    name = StringField('Organization Name', validators=[DataRequired(), Length(max=120)])
    submit = SubmitField('Create Organization')


class InviteForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email(), Length(max=120)])
    role = SelectField(
        'Role',
        choices=[('admin', 'Admin'), ('member', 'Member')],
        validators=[DataRequired()],
    )
    submit = SubmitField('Send Invite')
