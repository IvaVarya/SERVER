from marshmallow import Schema, fields, validate, ValidationError

class UserSchema(Schema):
    first_name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    last_name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    login = fields.Str(required=True, validate=validate.Length(min=3, max=50))
    password = fields.Str(required=True, validate=validate.Length(min=6))
    confirm_password = fields.Str(required=True)
    email = fields.Email(required=True, validate=validate.Length(max=120))

class ProfileSchema(Schema):
    first_name = fields.Str(validate=validate.Length(min=1, max=50))
    last_name = fields.Str(validate=validate.Length(min=1, max=50))
    gender = fields.Str(validate=validate.Length(max=20))
    country = fields.Str(validate=validate.Length(max=50))
    city = fields.Str(validate=validate.Length(max=50))
    birth_date = fields.Date(format='%Y-%m-%d')
    profile_photo = fields.Str(validate=validate.Length(max=200))