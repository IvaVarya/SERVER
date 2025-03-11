from marshmallow import Schema, fields, validate, ValidationError

class PostSchema(Schema):
    text = fields.Str(required=False, validate=[
        validate.Length(max=500, error="Текст поста должен быть не более 500 символов.")
    ])
    photos = fields.List(fields.Str(), required=False)