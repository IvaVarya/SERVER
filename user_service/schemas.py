from marshmallow import Schema, fields, validate, ValidationError, validates_schema
from datetime import datetime, date

class UserSchema(Schema):
    first_name = fields.Str(
        required=True,
        validate=[
            validate.Length(min=1, max=50, error="Имя должно быть от 1 до 50 символов."),
            validate.Regexp(
                r'^[A-ZА-Я][a-zа-я]*$',
                error="Имя должно начинаться с заглавной буквы и содержать только буквы (без цифр и символов).")
        ])
    last_name = fields.Str(
        required=True,
        validate=[
            validate.Length(min=1, max=50, error="Фамилия должна быть от 1 до 50 символов."),
            validate.Regexp(
                r'^[A-ZА-Я][a-zа-я]*$',
                error="Фамилия должна начинаться с заглавной буквы и содержать только буквы (без цифр и символов).")
        ])
    login = fields.Str(
        required=True,
        validate=[
            validate.Length(min=3, max=20, error="Логин должен быть от 3 до 20 символов."),
            validate.Regexp(
                r'^[a-zA-Z][a-zA-Z0-9_]*$',
                error="Логин должен начинаться с латинской буквы, содержать только латинские буквы, цифры и подчеркивание.")
        ])
    password = fields.Str(
        required=True,
        validate=[
            validate.Length(min=6, max=128, error="Пароль должен содержать от 6 до 128 символов."),
            validate.Regexp(
                r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{6,}$',
                error="Пароль должен содержать минимум 6 символов, включая заглавную букву, строчную букву, цифру и специальный символ (@$!%*?&).")
        ])
    confirm_password = fields.Str(
        required=True,
        validate=validate.Length(min=6, max=128, error="Подтверждение пароля должно быть от 6 до 128 символов."))
    email = fields.Email(
        required=True,
        validate=validate.Length(max=120, error="Email должен быть не длиннее 120 символов."))

    @validates_schema
    def validate_passwords(self, data, **kwargs):
        if data.get('password') != data.get('confirm_password'):
            raise ValidationError("Пароли не совпадают.", field_name="confirm_password")

class ProfileSchema(Schema):
    first_name = fields.Str(
        required=False,
        validate=[
            validate.Length(min=1, max=50, error="Имя должно быть от 1 до 50 символов."),
            validate.Regexp(
                r'^[A-ZА-Я][a-zа-я]*$',
                error="Имя должно начинаться с заглавной буквы и содержать только буквы (без цифр и символов).")
        ])
    last_name = fields.Str(
        required=False,
        validate=[
            validate.Length(min=1, max=50, error="Фамилия должна быть от 1 до 50 символов."),
            validate.Regexp(
                r'^[A-ZА-Я][a-zа-я]*$',
                error="Фамилия должна начинаться с заглавной буквы и содержать только буквы (без цифр и символов).")
        ])
    gender = fields.Str(
        required=False,
        validate=validate.OneOf(
            ["Мужской", "Женский"],
            error="Пол должен быть 'Мужской' или 'Женский'."))
    country = fields.Str(
        required=False,
        validate=validate.Length(min=2, max=50, error="Название страны должно быть от 2 до 50 символов."))
    city = fields.Str(
        required=False,
        validate=validate.Length(min=2, max=50, error="Название города должно быть от 2 до 50 символов."))
    birth_date = fields.Date(
        required=False,
        format='%Y-%m-%d',
        error_messages={"invalid": "Некорректный формат даты. Используйте YYYY-MM-DD."})
    profile_photo = fields.Str(
        required=False,
        validate=validate.Length(max=200, error="URL фото профиля должен быть не длиннее 200 символов."))

    @validates_schema
    def validate_birth_date(self, data, **kwargs):
        if 'birth_date' in data and data['birth_date']:
            if isinstance(data['birth_date'], str):
                try:
                    birth_date = datetime.strptime(data['birth_date'], '%Y-%m-%d').date()
                    today = date.today()
                    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                    if age < 13:
                        raise ValidationError("Пользователь должен быть старше 13 лет.", field_name="birth_date")
                    if birth_date > today:
                        raise ValidationError("Дата рождения не может быть в будущем.", field_name="birth_date")
                except ValueError:
                    raise ValidationError("Некорректный формат даты. Используйте YYYY-MM-DD.", field_name="birth_date")
            elif isinstance(data['birth_date'], date):
                today = date.today()
                age = today.year - data['birth_date'].year - ((today.month, today.day) < (data['birth_date'].month, data['birth_date'].day))
                if age < 13:
                    raise ValidationError("Пользователь должен быть старше 13 лет.", field_name="birth_date")
                if data['birth_date'] > today:
                    raise ValidationError("Дата рождения не может быть в будущем.", field_name="birth_date")
            else:
                raise ValidationError("Некорректный формат даты. Используйте YYYY-MM-DD.", field_name="birth_date")