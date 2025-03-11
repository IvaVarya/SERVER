from marshmallow import Schema, fields, validate, ValidationError, validates_schema

class UserSchema(Schema):
    first_name = fields.Str(required=True, validate=[
        validate.Length(min=1, max=50, error="Имя должно быть от 1 до 50 символов."),
        validate.Regexp(r'^[A-ZА-Я][a-zа-я]*$', error="Имя должно начинаться с заглавной буквы и содержать только буквы.")
    ])
    last_name = fields.Str(required=True, validate=[
        validate.Length(min=1, max=50, error="Фамилия должна быть от 1 до 50 символов."),
        validate.Regexp(r'^[A-ZА-Я][a-zа-я]*$', error="Фамилия должна начинаться с заглавной буквы и содержать только буквы.")
    ])
    login = fields.Str(required=True, validate=[
        validate.Length(min=3, max=20, error="Логин должен быть от 3 до 20 символов."),
        validate.Regexp(r'^[a-zA-Z0-9_]+$', error="Логин должен содержать только латинские буквы, цифры и символ подчеркивания.")
    ])
    password = fields.Str(required=True, validate=[
        validate.Length(min=6, error="Пароль должен содержать минимум 6 символов."),
        validate.Regexp(r'^(?=.*[A-Za-z])(?=.*\d).{6,}$', 
                       error="Пароль должен содержать минимум 6 символов, включая хотя бы одну букву и одну цифру.")
    ])
    confirm_password = fields.Str(required=True, error="Подтверждение пароля обязательно.")
    email = fields.Email(required=True, error="Некорректный email.")

    @validates_schema
    def validate_passwords(self, data, **kwargs):
        if data['password'] != data['confirm_password']:
            raise ValidationError("Пароли не совпадают.", field_name="confirm_password")