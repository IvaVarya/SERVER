from marshmallow import Schema, fields, validate, ValidationError, validates_schema
from datetime import datetime, date  # Добавлен импорт date

class ProfileSchema(Schema):
    first_name = fields.Str(required=False, validate=[
        validate.Length(min=1, max=50, error="Имя должно быть от 1 до 50 символов."),
        validate.Regexp(r'^[A-ZА-Я][a-zа-я]*$', error="Имя должно начинаться с заглавной буквы и содержать только буквы.")
    ])
    last_name = fields.Str(required=False, validate=[
        validate.Length(min=1, max=50, error="Фамилия должна быть от 1 до 50 символов."),
        validate.Regexp(r'^[A-ZА-Я][a-zа-я]*$', error="Фамилия должна начинаться с заглавной буквы и содержать только буквы.")
    ])
    gender = fields.Str(required=False, validate=[
        validate.OneOf(["Мужской", "Женский"], error="Пол должен быть 'Мужской' или 'Женский'.")
    ])
    country = fields.Str(required=False, validate=[
        validate.Length(min=2, max=50, error="Название страны должно быть от 2 до 50 символов.")
    ])
    city = fields.Str(required=False, validate=[
        validate.Length(min=2, max=50, error="Название города должно быть от 2 до 50 символов.")
    ])
    birth_date = fields.Date(required=False, error="Некорректный формат даты. Используйте YYYY-MM-DD.")
    profile_photo = fields.Str(required=False)

    @validates_schema
    def validate_data(self, data, **kwargs):
        if 'birth_date' in data and data['birth_date']:
            if isinstance(data['birth_date'], str):  # Проверяем, является ли birth_date строкой
                try:
                    datetime.strptime(data['birth_date'], '%Y-%m-%d')  # Преобразуем строку в datetime
                except ValueError:
                    raise ValidationError("Некорректный формат даты. Используйте YYYY-MM-DD.", field_name="birth_date")
            elif isinstance(data['birth_date'], date):  # Если это уже объект date, пропускаем
                pass
            else:
                raise ValidationError("Некорректный формат даты. Используйте YYYY-MM-DD.", field_name="birth_date")