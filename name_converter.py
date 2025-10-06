import re
import pymorphy3
from utils import convert_surnames_to_nominative
import argparse
import os
import pandas as pd
import json

# Завантаження конфігурації з name_map (для особливих випадків імен)
def load_name_map(config_file='config.json'):
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config.get('name_map', {})
    except Exception as e:
        print(f"Помилка при завантаженні name_map з конфігурації: {e}")
        return {}

# Завантажуємо name_map при імпорті модуля
name_map = load_name_map()

morph = pymorphy3.MorphAnalyzer(lang='uk')

def to_nominative_pymorphy(word):
    parsed = morph.parse(word)
    for p in parsed:
        if any(x in str(p.tag) for x in ['Surn', 'Name', 'Patr']):  # фамилия, имя, отчество
            form = p.inflect({'nomn'})
            if form:
                # Сохраняем регистр
                if word.istitle():
                    return form.word.capitalize()
                elif word.isupper():
                    return form.word.upper()
                else:
                    return form.word
    return None

def to_nominative(word):
    """Сначала пытается pymorphy3, если не получилось — Stanza, иначе возвращает исходное слово."""
    if not word or not isinstance(word, str):
        return word
    result = to_nominative_pymorphy(word)
    if result:
        return result
    try:
        stanza_result = convert_surnames_to_nominative(word)
        if stanza_result and stanza_result.lower() != word.lower():
            return stanza_result
    except Exception:
        pass
    return word

def convert_full_name_to_nominative(full_name):
    """
    Преобразует ФИО из родительного падежа в именительный с помощью Stanza.
    """
    parts = full_name.strip().split()
    if len(parts) != 3:
        # Если не три части, пробуем обработать как есть
        return convert_surnames_to_nominative(full_name)
    surname, name, patronymic = parts
    surname_nom = to_nominative(surname)
    name_nom = to_nominative(name)
    patronymic_nom = to_nominative(patronymic)
    # Восстановить регистр фамилии
    if surname.isupper():
        surname_nom = surname_nom.upper()
    return f"{surname_nom} {name_nom} {patronymic_nom}"

def process_full_name(full_name_genitive):
    """Обробляє повне ПІБ з родового відмінка в називний у форматі ПРІЗВИЩЕ Ім'я По-батькові."""
    if not isinstance(full_name_genitive, str):
        return ""
    clean_name = re.sub(r'\s+', ' ', full_name_genitive.strip())
    return convert_full_name_to_nominative(clean_name)

def convert_names_in_excel(input_file, output_file, column_name_genitive, new_column_name_nominative):
    """
    Читає Excel файл, перетворює ПІБ з родового відмінка в називний
    і зберігає результат у нову колонку.
    """
    try:
        df = pd.read_excel(input_file)
    except FileNotFoundError:
        print(f"Помилка: Файл '{input_file}' не знайдено.")
        return
    except Exception as e:
        print(f"Помилка читання Excel файлу '{input_file}': {e}")
        return

    if column_name_genitive not in df.columns:
        print(f"Помилка: Колонка '{column_name_genitive}' не знайдена у файлі '{input_file}'.")
        print(f"Доступні колонки: {', '.join(df.columns)}")
        return

    # Знаходимо індекс колонки, після якої треба вставити нову
    try:
        insert_loc = df.columns.get_loc(column_name_genitive) + 1
    except KeyError:
        # На випадок, якщо колонка є, але get_loc її не знаходить (малоймовірно)
        insert_loc = len(df.columns)

    # Застосовуємо функцію перетворення до колонки з ПІБ у родовому відмінку
    # Використовуємо .fillna('') щоб уникнути помилок з NaN значеннями
    nominative_series = df[column_name_genitive].fillna('').astype(str).apply(process_full_name)

    # Вставляємо нову колонку у вказане місце
    df.insert(loc=insert_loc, column=new_column_name_nominative, value=nominative_series)

    try:
        df.to_excel(output_file, index=False)
        print(f"Успішно оброблено. Результат збережено у файл '{output_file}'")
    except Exception as e:
        print(f"Помилка запису у файл '{output_file}': {e}")

if __name__ == "__main__":
    # Налаштування парсера аргументів командного рядка
    parser = argparse.ArgumentParser(description="Перетворення ПІБ з родового відмінка в називний у Excel файлі.")
    parser.add_argument('input_file', 
                        type=str, 
                        help='Шлях до вхідного Excel файлу.')
    parser.add_argument('-o', '--output', 
                        type=str, 
                        default=None, 
                        help='Шлях до вихідного Excel файлу (за замовчуванням: <input_file>_output.xlsx).')
    parser.add_argument('-c', '--column', 
                        type=str, 
                        default='name', 
                        help='Назва колонки з ПІБ у родовому відмінку (за замовчуванням: name).')
    parser.add_argument('-n', '--new-column', 
                        type=str, 
                        default='ПІБ Називний', 
                        help='Назва нової колонки для ПІБ у називному відмінку (за замовчуванням: ПІБ Називний).')

    # Отримуємо аргументи
    args = parser.parse_args()

    # Визначаємо ім'я вихідного файлу, якщо воно не задане
    if args.output is None:
        base, ext = os.path.splitext(args.input_file)
        output_file = f"{base}_output{ext}"
    else:
        output_file = args.output

    # Використовуємо отримані аргументи
    input_excel_file = args.input_file
    output_excel_file = output_file
    column_name_genitive = args.column
    new_column_name_nominative = args.new_column

    print(f"Обробка файлу '{input_excel_file}'...")
    print(f"Колонка з родовим відмінком: '{column_name_genitive}'")
    print(f"Нова колонка для називного відмінка: '{new_column_name_nominative}'")
    print(f"Вихідний файл: '{output_excel_file}'")

    convert_names_in_excel(
        input_excel_file,
        output_excel_file,
        column_name_genitive,
        new_column_name_nominative
    )
    print("Завершено.") 