from marshmallow import Schema, fields, validate, ValidationError

class PostSchema(Schema):
    text = fields.Str(
        required=False,
        validate=[
            validate.Length(
                max=500,
                error="Текст поста должен быть не более 500 символов."
            )
        ],
        allow_none=True
    )
    photos = fields.List(
        fields.Raw(),  # Используем Raw, так как файлы обрабатываются отдельно
        required=False,
        validate=[
            validate.Length(
                max=10,
                error="Максимальное количество фотографий — 10."
            )
        ]
    )