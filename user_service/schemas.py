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
    birth_date = fields.Date(format='%Y-%m-%d')  # Ожидает строку "YYYY-MM-DD"
    profile_photo = fields.Str(validate=validate.Length(max=200))


# from marshmallow import Schema, fields, validate, ValidationError, validates_schema

# class UserSchema(Schema):
#     first_name = fields.Str(required=True, validate=[
#         validate.Length(min=1, max=50, error="Имя должно быть от 1 до 50 символов."),
#         validate.Regexp(r'^[A-ZА-Я][a-zа-я]*$', error="Имя должно начинаться с заглавной буквы и содержать только буквы.")
#     ])
#     last_name = fields.Str(required=True, validate=[
#         validate.Length(min=1, max=50, error="Фамилия должна быть от 1 до 50 символов."),
#         validate.Regexp(r'^[A-ZА-Я][a-zа-я]*$', error="Фамилия должна начинаться с заглавной буквы и содержать только буквы.")
#     ])
#     login = fields.Str(required=True, validate=[
#         validate.Length(min=3, max=20, error="Логин должен быть от 3 до 20 символов."),
#         validate.Regexp(r'^[a-zA-Z0-9_]+$', error="Логин должен содержать только латинские буквы, цифры и символ подчеркивания.")
#     ])
#     password = fields.Str(required=True, validate=[
#         validate.Length(min=6, error="Пароль должен содержать минимум 6 символов."),
#         validate.Regexp(r'^(?=.*[A-Za-z])(?=.*\d).{6,}$', 
#                        error="Пароль должен содержать минимум 6 символов, включая хотя бы одну букву и одну цифру.")
#     ])
#     confirm_password = fields.Str(required=True, error="Подтверждение пароля обязательно.")
#     email = fields.Email(required=True, error="Некорректный email.")

#     @validates_schema
#     def validate_passwords(self, data, **kwargs):
#         if data['password'] != data['confirm_password']:
#             raise ValidationError("Пароли не совпадают.", field_name="confirm_password")






# from marshmallow import Schema, fields, validate, ValidationError, validates_schema
# from datetime import datetime, date  # Добавлен импорт date

# class ProfileSchema(Schema):
#     first_name = fields.Str(required=False, validate=[
#         validate.Length(min=1, max=50, error="Имя должно быть от 1 до 50 символов."),
#         validate.Regexp(r'^[A-ZА-Я][a-zа-я]*$', error="Имя должно начинаться с заглавной буквы и содержать только буквы.")
#     ])
#     last_name = fields.Str(required=False, validate=[
#         validate.Length(min=1, max=50, error="Фамилия должна быть от 1 до 50 символов."),
#         validate.Regexp(r'^[A-ZА-Я][a-zа-я]*$', error="Фамилия должна начинаться с заглавной буквы и содержать только буквы.")
#     ])
#     gender = fields.Str(required=False, validate=[
#         validate.OneOf(["Мужской", "Женский"], error="Пол должен быть 'Мужской' или 'Женский'.")
#     ])
#     country = fields.Str(required=False, validate=[
#         validate.Length(min=2, max=50, error="Название страны должно быть от 2 до 50 символов.")
#     ])
#     city = fields.Str(required=False, validate=[
#         validate.Length(min=2, max=50, error="Название города должно быть от 2 до 50 символов.")
#     ])
#     birth_date = fields.Date(required=False, error="Некорректный формат даты. Используйте YYYY-MM-DD.")
#     profile_photo = fields.Str(required=False)

#     @validates_schema
#     def validate_data(self, data, **kwargs):
#         if 'birth_date' in data and data['birth_date']:
#             if isinstance(data['birth_date'], str):  # Проверяем, является ли birth_date строкой
#                 try:
#                     datetime.strptime(data['birth_date'], '%Y-%m-%d')  # Преобразуем строку в datetime
#                 except ValueError:
#                     raise ValidationError("Некорректный формат даты. Используйте YYYY-MM-DD.", field_name="birth_date")
#             elif isinstance(data['birth_date'], date):  # Если это уже объект date, пропускаем
#                 pass
#             else:
#                 raise ValidationError("Некорректный формат даты. Используйте YYYY-MM-DD.", field_name="birth_date")