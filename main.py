#!/usr/bin/env python3
"""
Головний модуль для обробки військових наказів.
Обробляє документи з наказами та витягує інформацію про військовослужбовців.
"""

import argparse
import os
import sys
from datetime import datetime
import re
import json
import pandas as pd # Додаємо імпорт pandas
from docx import Document

from text_processing import normalize_text
from section_detection import find_sections
from utils import load_doc, load_config, save_results, parse_date, format_excel_file, highlight_names_in_documents
from processors.arrival_processor import process_arrival_at_assignment, process_arrival_at_training
from processors.hospital_processor import process_hospital_return
from processors.return_processor import process_return_from_assignment
from processors.mobilization_processor import process_mobilization
from processors.vacation_return_processor import process_vacation_return
from processors.szch_processor import process_szch_section, find_szch_sections  # Додаємо імпорт процесора СЗЧ
from processors.departure_processor import process_departure  # Додаємо імпорт процесора вибуття
from processors.transfer_processor import process_transfer_records # Додаємо імпорт процесора переведень
from name_converter import process_full_name # Переведення імен в називний відмінок

# Додаємо імпорт процесора для військовослужбовців у відрядженні А1890
from processors.departure_processor import process_personnel_on_assignment_a1890


def process_military_order(text, rank_map, location_triggers):
    """
    Обробляє текст наказу по стройовій частині та витягує всі необхідні дані.
    
    Args:
        text (str): СИРИЙ Текст наказу (НЕ нормалізований)
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        
    Returns:
        list: Список записів про військовослужбовців
    """
    raw_full_text = text # Працюємо з сирим текстом
    print(f"DEBUG: Raw full text length: {len(raw_full_text)}")

    # Спочатку шукаємо секції СЗЧ в усьому документі
    print("\n--- Пошук секцій СЗЧ в усьому документі ---")
    szch_sections = find_szch_sections(raw_full_text, rank_map)
    
    results = []
    processed_persons = set() # Track processed persons across all sections
    
    # Обробка знайдених секцій СЗЧ
    if szch_sections:
        print(f"Знайдено {len(szch_sections)} секцій СЗЧ")
        for section_type, section_text_raw, start_pos_relative in szch_sections:
            print(f"\n--- Обробка СИРОЇ секції СЗЧ (з позиції {start_pos_relative}) ---")
            print(f"Довжина секції: {len(section_text_raw)} символів")
            print(f"Перші 100 символів СИРОЇ секції: {section_text_raw[:100]}...")
            
            section_results = process_szch_section(
                section_text_raw, rank_map, location_triggers,
                processed_persons=processed_persons
            )
            
            if section_results:
                print(f"  Процесор СЗЧ повернув {len(section_results)} записів.")
                results.extend(section_results)
            else:
                print(f"  Процесор СЗЧ не повернув жодного запису для цієї секції.")
    else:
        print("Секцій СЗЧ не знайдено")

    # --- Визначення меж за маркерами-фразами --- 
    start_pattern_flexible = r"Вважати\s+такими,\s+що\s+прибули\s+та\s+приступили\s+до\s+виконання\s+службових\s+обов\'язків\s*:?"
    end_pattern_flexible = r"Вважати\s+такими,\s+що\s+вибули\s*:?"

    start_matches_raw = list(re.finditer(start_pattern_flexible, raw_full_text, re.IGNORECASE))
    end_matches_raw = list(re.finditer(end_pattern_flexible, raw_full_text, re.IGNORECASE))

    text_to_process_raw = ""
    start_pos_raw = -1
    end_pos_raw = len(raw_full_text) # За замовчуванням - кінець тексту

    if start_matches_raw:
        # Беремо перший початковий маркер
        first_start_match = start_matches_raw[0]
        start_pos_raw = first_start_match.end() # Починаємо ОБРОБКУ ПІСЛЯ цього маркера
        print(f"DEBUG: Found start phrase marker ending at position {start_pos_raw}")

        # Шукаємо перший кінцевий маркер ПІСЛЯ початкового
        valid_end_positions = [m.start() for m in end_matches_raw if m.start() > start_pos_raw]
        
        if valid_end_positions:
            end_pos_raw = min(valid_end_positions) # Кінець обробки - ПЕРЕД цим маркером
            print(f"DEBUG: Found end phrase marker starting at position {end_pos_raw}")
            text_to_process_raw = raw_full_text[start_pos_raw:end_pos_raw]
            print(f"--- INFO: Extracted RAW main section between phrase markers (pos {start_pos_raw} to {end_pos_raw}, len {len(text_to_process_raw)}) ---")
        else:
            # Знайшли початок, але не кінець після нього
            text_to_process_raw = raw_full_text[start_pos_raw:]
            print(f"--- WARNING: Found start phrase marker but no valid end phrase marker AFTER it. Processing RAW text from start marker end (pos {start_pos_raw}) to end of document. ---")
    else:
        # Не знайдено початковий маркер
        print(f"--- ERROR: Start phrase marker not found! Cannot reliably extract the main processing block. Processing entire document as fallback. ---")
        text_to_process_raw = raw_full_text # Обробляємо весь текст як запасний варіант

    if not text_to_process_raw.strip():
        print("--- ERROR: RAW Text for processing is empty. No sections to process. ---")
        return results  # Return results from СЗЧ processing

    # 4. Визначаємо маркери для ПІДСЕКЦІЙ (покращені для врахування нумерації)
    specific_section_markers = [
        # Маркери ППОС - додаємо варіант з нумерацією
        (r'\d+\.\d+\.\s*Відповідно до мобілізаційного призначення', 'ППОС'),
        ('Відповідно до мобілізаційного призначення', 'ППОС'),
        # Маркери повернень - додаємо варіанти з нумерацією
        (r'\d+\.\d+\.\d+\s+з військової частини', 'Повернення з відрядження'),
        (r'\d+\.\d+\.\s*З відрядження', 'Повернення з відрядження'),
        ('З відрядження', 'Повернення з відрядження'),
        # Make vacation markers more specific - додаємо нумерацію
        (r'\d+\.\d+\.\s*З частини щорічної основної відпустки', 'Відпустка щорічна'),
        ('З частини щорічної основної відпустки', 'Відпустка щорічна'),
        (r'\d+\.\d+\.\s*З відпустки за сімейними обставинами', 'Відпустка сімейна'),
        ('З відпустки за сімейними обставинами', 'Відпустка сімейна'),
        (r'\d+\.\d+\.\s*З відпустки для лікування', 'Відпустка лікування'),
        ('З відпустки для лікування', 'Відпустка лікування'),
        (r'\d+\.\d+\.\d+\s+з.*?лікувального закладу', 'Лікарня'),
        ('з лікувального закладу', 'Лікарня'), # Note: lowercase 'з'
        # Маркери прибуття у відрядження (навчання та службове завдання)
        (r'\d+\.\d+\.\s*Нижчепойменованих військовослужбовців вважати такими, що прибули у службове відрядження', 'Прибуття у відрядження'),
        ('Нижчепойменованих військовослужбовців вважати такими, що прибули у службове відрядження до', 'Прибуття у відрядження'),
        ('Нижчепойменованих військовослужбовців вважати такими, що прибули у службове відрядження', 'Прибуття у відрядження'),
        # Новий маркер для секції "Звільнені від обов'язків у зв'язку з хворобою"
        (r'\d+\.\d+\.\s*Нижчепойменовані військовослужбовці, які були звільнені від виконання службових обов\'язків', 'Хвороба'),
        ('Нижчепойменовані військовослужбовці, які були звільнені від виконання службових обов\'язків у зв\'язку з хворобою', 'Хвороба'),
        # Маркер для військовослужбовців, які перебували у відрядженні у в/ч А1890
        (r'\d+\.\d+\.\d+\s+військовослужбов.*?А1890.*?вважати такими, що вибули', 'Відрядження А1890'),
        ('Нижчепойменованих військовослужбовців, які перебували у відрядженні у військовій частині А1890, вважати такими, що вибули', 'Відрядження А1890'),
        # Маркер для переведення між батальйонами/локаціями
        ('до \d+ навчального батальйону (?:школи )?(?:індивідуальної підготовки)?', 'Переведення між локаціями'),
    ]
    
    print(f"DEBUG: Raw text length to process: {len(text_to_process_raw)}")

    # 5. Знаходимо всі ПІДСЕКЦІЇ всередині СИРОГО блоку тексту
    print("\n--- Пошук підсекцій всередині виділеного СИРОГО блоку тексту ---")
    all_sections = find_sections(text_to_process_raw, specific_section_markers)
    
    if not all_sections:
        print("УВАГА: Не знайдено жодної підсекції за відомими маркерами всередині головного блоку!")
        return results  # Return results from СЗЧ processing

    print(f"Знайдено {len(all_sections)} підсекцій всередині головного блоку.")

    # 6. Обробляємо кожну знайдену ПІДСЕКЦІЮ (вона тепер містить СИРИЙ текст)
    for section_type, section_text_raw, start_pos_relative in all_sections: # section_text_raw тепер сирий
        print(f"\n--- Обробка СИРОЇ підсекції: {section_type} (з відносної позиції {start_pos_relative}) ---")
        print(f"Довжина підсекції: {len(section_text_raw)} символів")
        print(f"Перші 100 символів СИРОЇ підсекції: {section_text_raw[:100]}...")

        # Call the appropriate processor, passing the RAW section text
        section_results = []
        
        # Виклик відповідних процесорів (вони тепер отримують сирий текст секції)
        if section_type == "Прибуття у відрядження (навчання)":
            section_results = process_arrival_at_training(
                section_text_raw, rank_map, location_triggers,
                default_date=None, default_meal="зі сніданку",
                processed_persons=processed_persons
            )
        elif section_type == "Прибуття у відрядження":
             if "навчальн" in section_text_raw[:500].lower() or "школи" in section_text_raw[:500].lower():
                  print("  Уточнення: обробляємо як Прибуття у відрядження (навчання)")
                  section_results = process_arrival_at_training(
                      section_text_raw, rank_map, location_triggers,
                      default_date=None, default_meal="зі сніданку",
                      processed_persons=processed_persons
                  )
             else:
                  print("  Обробляємо як Прибуття у відрядження (виконання завдання)")
                  section_results = process_arrival_at_assignment(
                     section_text_raw, rank_map, location_triggers,
                     default_date=None, default_meal="зі сніданку",
                     processed_persons=processed_persons
                  )
        elif section_type == "Лікарня":
            section_results = process_hospital_return(
                section_text_raw, rank_map, location_triggers,
                processed_persons=processed_persons
            )
        elif section_type == "Повернення з відрядження":
            section_results = process_return_from_assignment(
                section_text_raw, rank_map, location_triggers,
                processed_persons=processed_persons
            )
        elif section_type == "ППОС":
            section_results = process_mobilization(
                section_text_raw, rank_map, location_triggers,
                processed_persons=processed_persons
            )
        elif section_type == "Хвороба":
            section_results = process_hospital_return(
                section_text_raw, rank_map, location_triggers,
                processed_persons=processed_persons,
                cause_override="Звільнення від обов\'язків через хворобу" 
            )
        elif section_type in ["Відпустка щорічна", "Відпустка сімейна", "Відпустка лікування"]:
             section_results = process_vacation_return(
                 section_text_raw, rank_map, location_triggers,
                 processed_persons=processed_persons
             )
        elif section_type == "Відпустка": # Fallback
             print(f"  УВАГА: Обробка загального типу 'Відпустка'.")
             section_results = process_vacation_return(
                 section_text_raw, rank_map, location_triggers,
                 processed_persons=processed_persons
             )
        elif section_type == "Відрядження (завдання)":
            section_results = process_return_from_assignment(
                section_text_raw, rank_map, location_triggers,
                processed_persons=processed_persons
            )
        elif section_type == "СЗЧ":
            # Обробка секції СЗЧ
            section_results = process_szch_section(
                section_text_raw, rank_map, location_triggers,
                processed_persons=processed_persons
            )
        elif section_type == "Відрядження А1890":
            # Обробка секції військовослужбовців, які перебували у відрядженні у в/ч А1890
            section_results = process_personnel_on_assignment_a1890(
                section_text_raw, rank_map, location_triggers,
                processed_persons=processed_persons
            )
        elif section_type == "Переведення між локаціями":
            # Обробка секції переведення військовослужбовців між локаціями
            section_results = process_transfer_records(
                section_text_raw, rank_map, location_triggers,
                processed_persons=processed_persons
            )
        else:
             print(f"  УВАГА: Немає явного обробника для типу підсекції '{section_type}'. Спроба автовизначення...")
             section_text_lower_raw = section_text_raw.lower()
             # Перевіряємо на випадок переведення між локаціями
             if "до навчального батальйону" in section_text_lower_raw or "виключити з котлового забезпечення" in section_text_lower_raw and "зарахувати на котлове забезпечення" in section_text_lower_raw:
                 print(f"  Спроба обробки як 'Переведення між локаціями'")
                 section_results = process_transfer_records(section_text_raw, rank_map, location_triggers, processed_persons=processed_persons)
             elif "лікуваль" in section_text_lower_raw or "лікарн" in section_text_lower_raw:
                 print(f"  Спроба обробки як 'Лікарня'")
                 section_results = process_hospital_return(section_text_raw, rank_map, location_triggers, processed_persons=processed_persons)
             elif "відпустк" in section_text_lower_raw:
                 print(f"  Спроба обробки як 'Відпустка'")
                 section_results = process_vacation_return(section_text_raw, rank_map, location_triggers, processed_persons=processed_persons)
             elif "відрядженн" in section_text_lower_raw:
                  if "повернення" in section_text_lower_raw or "з відрядження" in section_text_lower_raw:
                       print(f"  Спроба обробки як 'Повернення з відрядження'")
                       section_results = process_return_from_assignment(section_text_raw, rank_map, location_triggers, processed_persons=processed_persons)
                  elif "навчання" in section_text_lower_raw or "навчальн" in section_text_lower_raw:
                       print(f"  Спроба обробки як 'Прибуття у відрядження (навчання)'")
                       section_results = process_arrival_at_training(section_text_raw, rank_map, location_triggers, default_date=None, default_meal="зі сніданку", processed_persons=processed_persons)
                  else:
                       print(f"  Спроба обробки як 'Прибуття у відрядження'")
                       section_results = process_arrival_at_assignment(section_text_raw, rank_map, location_triggers, default_date=None, default_meal="зі сніданку", processed_persons=processed_persons)
             elif "мобілізаці" in section_text_lower_raw:
                 print(f"  Спроба обробки як 'ППОС'")
                 section_results = process_mobilization(section_text_raw, rank_map, location_triggers, processed_persons=processed_persons)
             elif "самовільним залишенням частини" in section_text_lower_raw:
                 print(f"  Спроба обробки як 'СЗЧ'")
                 section_results = process_szch_section(section_text_raw, rank_map, location_triggers, processed_persons=processed_persons)

        if section_results:
            print(f"  Процесор {section_type} повернув {len(section_results)} записів.")
            results.extend(section_results)
        else:
            print(f"  Процесор {section_type} не повернув жодного запису для цієї підсекції.")

    # Обробляємо секцію "Вважати такими, що вибули"
    if end_matches_raw:
        # Отримуємо початок секції "Вважати такими, що вибули"
        departure_start_pos = end_matches_raw[0].end()
        
        # Знаходимо кінець секції - може бути маркер "Командир військової частини" або кінець документа
        commander_pattern = r"Командир\s+військової\s+частини\s+А1890"
        commander_matches = list(re.finditer(commander_pattern, raw_full_text, re.IGNORECASE))
        
        departure_end_pos = len(raw_full_text)
        if commander_matches:
            for match in commander_matches:
                if match.start() > departure_start_pos:
                    departure_end_pos = match.start()
                    break
        
        # Витягуємо текст секції "Вважати такими, що вибули"
        departure_section_text = raw_full_text[departure_start_pos:departure_end_pos]
        
        if departure_section_text.strip():
            print(f"\n--- Обробка секції 'Вважати такими, що вибули' (розмір: {len(departure_section_text)}) ---")
            print(f"Перші 100 символів секції: {departure_section_text[:100]}...")
            
            # Викликаємо процесор для секції вибуття
            departure_results = process_departure(
                departure_section_text, rank_map, location_triggers,
                processed_persons=processed_persons
            )
            
            if departure_results:
                print(f"Процесор 'Вважати такими, що вибули' повернув {len(departure_results)} записів.")
                results.extend(departure_results)
            else:
                print(f"Процесор 'Вважати такими, що вибули' не повернув жодного запису.")
        else:
            print("Секція 'Вважати такими, що вибули' пуста, пропускаємо обробку.")
    else:
        print("Не знайдено маркер 'Вважати такими, що вибули', пропускаємо обробку цієї секції.")

    print(f"\nЗагальна кількість записів після обробки всіх секцій: {len(results)}")
    
    # Додаємо поле 'action' зі значенням 'зарахувати' для всіх записів з основної секції
    # (всі, крім тих, що вже мають це поле зі значенням 'виключити')
    for record in results:
        if 'action' not in record:
            record['action'] = 'зарахувати'
    
    # --- Модифікація поля 'cause' згідно з новими правилами ---
    print("\n--- Застосування правил модифікації до поля 'cause' ---")
    modified_count = 0
    for record in results:
        original_cause = record.get('cause', '')
        new_cause = original_cause # За замовчуванням залишаємо як є

        if isinstance(original_cause, str):
            # 1. ППОС
            if original_cause.startswith("ППОС"):
                new_cause = "ППОС"
            # 2. З відрядження
            elif original_cause == "повернення з відрядження": # Точна відповідність
                new_cause = "З відрядження"
            # 3. Відпустка (різні варіанти повернення)
            elif "повернення з" in original_cause.lower() and "відпустки" in original_cause.lower():
                 new_cause = "Відпустка"
            # 4. Шпиталь
            elif original_cause == "Поверненя з лікувального закладу": # Точна відповідність
                new_cause = "Шпиталь"
            # 5. Відрядження (навчання)
            elif original_cause == "Прибуття у відрядження для навчання":
                new_cause = "Відрядження (навчання)"
             # 6. Відрядження (завдання) - Важливо перевірити ПІСЛЯ навчання
            elif original_cause == "Прибуття у відрядження для виконання службового завдання":
                 new_cause = "Відрядження (завдання)"
            # 6.1 Спроба впіймати інші варіанти повернення з відрядження
            elif original_cause.lower().startswith("повернення з відрядження") or original_cause.lower() == "з відрядження":
                 new_cause = "З відрядження"
            # 6.2 Спроба впіймати інші варіанти повернення зі шпиталю
            elif original_cause.lower().startswith("повернення з лікувального закладу"):
                 new_cause = "Шпиталь"
            # 7. СЗЧ
            elif original_cause == "СЗЧ":
                new_cause = "СЗЧ"
            # 8. Для подальшого проходження служби
            elif original_cause == "Вибув для подальшого":
                new_cause = "Вибув для подальшого"
            # 9. Звільнення в запас
            elif original_cause == "Звільнення в запас":
                new_cause = "Звільнення в запас"
            # 10. Відрядження (з секції "Вважати такими, що вибули")
            elif original_cause in ["Відрядження (навчання)", "Відрядження (завдання)"]:
                new_cause = original_cause


        if new_cause != original_cause:
            record['cause'] = new_cause
            modified_count += 1
            # print(f"  Змінено: '{original_cause}' -> '{new_cause}'") # Для дебагу

    print(f"Модифіковано {modified_count} записів за правилами")

    # --- Додавання нормалізованого ПІБ ---
    print("\n--- Нормалізація ПІБ та додавання поля 'name_normal' ---")
    normalization_count = 0
    for record in results:
        original_name = record.get('name')
        if original_name and isinstance(original_name, str):
            try:
                normalized_name = process_full_name(original_name)
                record['name_normal'] = normalized_name
                normalization_count += 1
                # print(f"  Normalized: '{original_name}' -> '{normalized_name}'") # Debug print
            except Exception as e:
                print(f"  Помилка нормалізації імені '{original_name}': {e}")
                record['name_normal'] = original_name # Fallback to original name on error
        else:
             # Handle cases where name is missing or not a string
             record['name_normal'] = original_name

    print(f"Нормалізовано та додано 'name_normal' для {normalization_count} записів.")
    # --- Кінець додавання нормалізованого ПІБ ---

    return results


def process_directory(input_dir, output_dir, config_file='config.json'):
    """
    Обробляє всі документи у вказаній директорії і зберігає результати в Excel-файли.
    
    Args:
        input_dir (str): Шлях до директорії з вхідними .docx файлами
        output_dir (str): Шлях до директорії для збереження Excel-результатів
        config_file (str): Шлях до файлу конфігурації
        
    Returns:
        tuple: (кількість оброблених документів, загальна кількість унікальних записів)
    """
    # Перевірка наявності директорії input_dir
    if not os.path.exists(input_dir):
        print(f"Помилка: Директорія з вхідними файлами '{input_dir}' не існує.")
        return 0, 0
    
    # Створення директорії output_dir, якщо вона не існує
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Створено директорію для результатів: {output_dir}")
    
    # Завантаження конфігурації
    if not os.path.exists(config_file):
        print(f"Помилка: Файл конфігурації '{config_file}' не знайдено.")
        return 0, 0
    
    config = load_config(config_file)
    rank_map = config.get('rank_map', {})
    location_triggers = config.get('location_triggers', {})
    
    # Пошук всіх .docx файлів в директорії input_dir
    docx_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.docx')]
    
    # Діагностика: виводимо всі знайдені .docx файли
    print(f"\n=== ДІАГНОСТИКА: Знайдені .docx файли в папці '{input_dir}' ===")
    for i, file in enumerate(docx_files, 1):
        print(f"{i}. {file}")
    print("=== Кінець списку файлів ===\n")
    
    if not docx_files:
        print(f"Попередження: В директорії '{input_dir}' не знайдено жодного документу .docx")
        return 0, 0
    
    # Статистика
    processed_docs_count = 0
    all_records = []
    unique_names = set()
    
    # Обробка кожного документу
    for docx_file in docx_files:
        input_docx_path = os.path.join(input_dir, docx_file)
        output_excel_path = os.path.join(output_dir, os.path.splitext(docx_file)[0] + '.xlsx')
        
        print(f"\n===== Обробка документу: {docx_file} з папки '{input_dir}' =====")
        
        # Завантаження та обробка документу
        text_raw = load_doc(input_docx_path)
        if not text_raw:
            print(f"Помилка: Не вдалося завантажити документ {docx_file}. Пропускаємо...")
            continue
        
        print(f"Документ завантажено. Розмір (сирий): {len(text_raw)} символів.")
        
        # Обробка документу
        results = process_military_order(text_raw, rank_map, location_triggers)
        
        # Збереження результатів в Excel
        if results:
            try:
                df = pd.DataFrame(results)
                df.to_excel(output_excel_path, index=False, engine='openpyxl')
                print(f"Результати збережено у Excel файл: {output_excel_path}")
                
                # Застосовуємо форматування до файлу Excel
                if format_excel_file(output_excel_path):
                    print(f"Форматування успішно застосовано до {output_excel_path}")
                else:
                    print(f"Не вдалося застосувати форматування до {output_excel_path}")
                
                # Додавання до загальної статистики
                processed_docs_count += 1
                all_records.extend(results)
                for record in results:
                    if 'name_normal' in record and record['name_normal']:
                        unique_names.add(record['name_normal'])
                
            except Exception as e:
                print(f"Помилка збереження результатів у Excel файл '{output_excel_path}': {e}")
        else:
            print(f"Документ {docx_file} не містить релевантних записів для збереження.")
    
    # Повертаємо статистику
    return processed_docs_count, len(all_records)


def main():
    """
    Головна функція для запуску обробки наказів.
    """
    # Перевірка наявності аргументів командного рядка
    if len(sys.argv) == 1 or '-j' in sys.argv or '--json' in sys.argv:
        # Запуск без параметрів або з прапорцем -j - обробка всіх документів у директорії "in"
        print("\n===== Запуск у режимі пакетної обробки =====")
        
        # Шляхи до директорій відносно файлу main.py
        script_dir = os.path.dirname(os.path.abspath(__file__))
        input_dir = os.path.join(script_dir, "in")
        output_dir = os.path.join(script_dir, "out")
        config_file = os.path.join(script_dir, "config.json")
        
        # Виклик функції обробки директорії
        docs_processed, total_records = process_directory(input_dir, output_dir, config_file)
        
        # Вивід підсумкової інформації
        print("\n===== Завершено пакетну обробку =====")
        print(f"Оброблено документів: {docs_processed}")
        print(f"Додано записів в усі файли: {total_records}")
        
        # Якщо вказано прапорець -j, зберігаємо результати в JSON
        if '-j' in sys.argv or '--json' in sys.argv:
            # Збираємо всі результати з усіх Excel файлів
            all_results = []
            for filename in os.listdir(output_dir):
                if filename.endswith('.xlsx'):
                    try:
                        excel_path = os.path.join(output_dir, filename)
                        df = pd.read_excel(excel_path)
                        # Конвертуємо DataFrame у список словників
                        file_results = df.to_dict('records')
                        all_results.extend(file_results)
                        print(f"Додано {len(file_results)} записів з {filename}")
                    except Exception as e:
                        print(f"Помилка при читанні {filename}: {e}")
            
            # Зберігаємо всі результати в один JSON файл
            if all_results:
                json_output_filename = 'results.json'
                try:
                    print(f"\nЗбереження всіх результатів у JSON файл: {json_output_filename}...")
                    with open(json_output_filename, 'w', encoding='utf-8') as f:
                        json.dump(all_results, f, ensure_ascii=False, indent=4)
                    print(f"✅ Всі результати успішно збережено в {json_output_filename} ({len(all_results)} записів)")
                    
                    # Автоматично виділяємо прізвища у документах після збереження JSON
                    print("\n" + "="*80)
                    highlight_names_in_documents(
                        input_dir=input_dir,
                        output_dir=os.path.join(script_dir, "out_highlighted"),
                        results_file=os.path.join(script_dir, "results.json")
                    )
                except Exception as e:
                    print(f"❌ Помилка при збереженні в JSON: {e}", file=sys.stderr)
        
        return 0
    
    # Стандартна обробка з параметрами командного рядка (тільки якщо НЕ вказано -j)
    parser = argparse.ArgumentParser(description='Обробка наказу з файлу DOCX та збереження результатів у JSON.')
    parser.add_argument('input_file', type=str, help='Шлях до вхідного файлу наказу (.docx)')
    parser.add_argument('-o', '--output', type=str, default='results.json', help='Шлях до вихідного JSON файлу (за замовчуванням: results.json)')
    parser.add_argument('-x', '--excel', type=str, default=None, help='Необов''язковий шлях для збереження результатів у форматі Excel (.xlsx)')
    parser.add_argument('-l', '--locations', type=str, default='locations.json', help='Шлях до файлу конфігурації локацій (за замовчуванням: locations.json)')
    parser.add_argument('-j', '--json', action='store_true', help='Зберегти результати в JSON файл (results.json)')

    args = parser.parse_args()

    input_docx_file = args.input_file
    output_json_file = args.output
    excel_output_file = args.excel
    config_file = 'config.json' # Використовуємо стандартний шлях до config.json

    if not os.path.exists(input_docx_file):
        print(f"Помилка: Вхідний файл '{input_docx_file}' не знайдено.")
        return 1

    if not os.path.exists(config_file):
        print(f"Помилка: Файл конфігурації '{config_file}' не знайдено.")
        return 1

    config = load_config(config_file)
    rank_map = config.get('rank_map', {})
    location_triggers = config.get('location_triggers', {})
    
    print(f"Завантаження документа: {input_docx_file}")
    text_raw = load_doc(input_docx_file) # Завантажуємо СИРИЙ текст
    
    if not text_raw:
        print("Помилка: Не вдалося завантажити документ.")
        return 1
    
    print(f"Документ завантажено. Розмір (сирий): {len(text_raw)} символів.")
    
    print("Початок обробки документа...")
    # Передаємо СИРИЙ текст в обробник
    results = process_military_order(text_raw, rank_map, location_triggers) 
    
    print(f"Обробка завершена. Знайдено {len(results)} записів.")
    save_results(results, output_json_file)
    print(f"Результати збережено у файл: {output_json_file}")
    
    if excel_output_file:
        if not excel_output_file.lower().endswith('.xlsx'):
             excel_output_file += '.xlsx'
             print(f"Додано розширення .xlsx до вихідного файлу Excel: {excel_output_file}")
             
        try:
            df = pd.DataFrame(results)
            df.to_excel(excel_output_file, index=False, engine='openpyxl')
            print(f"Результати також збережено у Excel файл: {excel_output_file}")
            
            # Застосовуємо форматування до файлу Excel
            if format_excel_file(excel_output_file):
                print(f"Форматування успішно застосовано до {excel_output_file}")
            else:
                print(f"Не вдалося застосувати форматування до {excel_output_file}")
        except ImportError:
             print("\nПОПЕРЕДЖЕННЯ: Для збереження в Excel потрібні бібліотеки pandas та openpyxl.")
             print("Встановіть їх командою: pip install pandas openpyxl")
        except Exception as e:
            print(f"\nПомилка збереження в Excel файл '{excel_output_file}': {e}")

    print("\nОбробка завершена.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
