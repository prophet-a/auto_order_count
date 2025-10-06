"""
Модуль для обробки та нормалізації тексту з військових наказів.
Основні функції:
- normalize_text: Нормалізує текст для надійного пошуку
- remove_section_content: Видаляє вміст вказаної секції, залишаючи заголовок
- should_exclude_record: Перевіряє, чи слід виключити запис
- get_subsection_cause: Визначає причину на основі тексту підрозділу
"""

import re

def normalize_text(text):
    """
    Нормалізує текст для надійного пошуку:
    - Замінює послідовності горизонтальних пробілів на один
    - Зберігає переноси рядків (\n)
    - Нормалізує лапки
    - Прибирає зайві пробіли на початку та в кінці рядків та всього тексту
    
    Args:
        text (str): Текст для нормалізації
        
    Returns:
        str: Нормалізований текст
    """
    if not text:
        return ""
    
    # Замінюємо різні типи переносів на стандартний \n
    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Замінюємо множинні горизонтальні пробіли (пробіл, таб) на один пробіл
    normalized = re.sub(r'[ \t]+', ' ', normalized)
    
    # Видаляємо пробіли на початку/кінці кожного рядка (після заміни табів)
    lines = normalized.split('\n')
    stripped_lines = [line.strip() for line in lines]
    # Видаляємо порожні рядки, що могли утворитися
    non_empty_lines = [line for line in stripped_lines if line]
    normalized = '\n'.join(non_empty_lines)
    
    # Нормалізація лапок (різні типи лапок на стандартні)
    normalized = re.sub(r'[«»""„"]', '"', normalized)
    
    # Прибираємо пробіли на початку та в кінці всього тексту (на випадок, якщо текст був порожнім)
    normalized = normalized.strip()
    
    return normalized


def should_exclude_record(entry_text, section_text):
    """
    Перевіряє, чи запис слід виключити на основі відсутності інформації про котлове забезпечення.
    Повертає True, якщо запис слід виключити, False - якщо запис можна обробляти.
    
    Args:
        entry_text (str): Текст запису для перевірки
        section_text (str): Текст розділу, в якому знаходиться запис
        
    Returns:
        bool: True якщо запис слід виключити, False якщо обробляти
    """
    # Перевіряємо, чи є запис в секції звільнених від виконання службових обов'язків
    if "звільнені від виконання службових обов'язків" in section_text.lower() or "звільнений від виконання службових обов'язків" in section_text.lower():
        return True
        
    # Перевіряємо, чи є в записі або загальному контексті згадка про зарахування на котлове забезпечення
    has_kotlove_in_entry = any(phrase in entry_text.lower() for phrase in [
        "зарахувати на котлове забезпечення", 
        "котлове забезпечення зарахувати",
        "на котлове забезпечення"
    ])
    
    has_kotlove_in_section = any(phrase in section_text.lower() for phrase in [
        "зарахувати на котлове забезпечення", 
        "котлове забезпечення зарахувати",
        "на котлове забезпечення"
    ])
    
    # Виключаємо запис, якщо:
    # - В секції згадується котлове забезпечення, але не для цього конкретного запису
    # - В секції звільнених від обов'язків
    if has_kotlove_in_section and not has_kotlove_in_entry:
        # Додаткова перевірка: якщо в записі є ім'я військовослужбовця, але нема згадки про котлове
        # забезпечення, тоді виключаємо запис
        return True
        
    # За замовчуванням не виключаємо запис
    return False


def remove_section_content(text, section_header):
    """
    Видаляє вміст секції, залишаючи її заголовок.

    Args:
        text (str): Повний текст для обробки.
        section_header (str): Точний текст заголовка секції, вміст якої треба видалити.

    Returns:
        str: Текст з видаленим вмістом вказаної секції.
    """
    # Використовуємо регулярний вираз для пошуку заголовка
    # Заголовок може бути з номером (e.g., "11.7. ") або без
    escaped_header = re.escape(section_header)
    # Regex to find the header, optionally preceded by "X.Y." or "X.Y.Z." and whitespace
    header_pattern = rf"(^|\n)\s*(\d+\.\d+(\.\d+)?\.?\s*)?({escaped_header})"
    
    match = re.search(header_pattern, text)
    
    if not match:
        print(f"DEBUG: Заголовок секції для видалення контенту не знайдено за патерном: '{section_header}'")
        return text # Повертаємо оригінальний текст, якщо заголовок не знайдено

    start_idx = match.start() # Start of the entire matched pattern (including potential newline)
    actual_header_start_idx = match.start(4) # Start of the captured header text itself
    full_header_text = match.group(0).strip() # Get the full matched header including number

    print(f"DEBUG: Знайдено заголовок '{full_header_text}' для видалення контенту на позиції {actual_header_start_idx}")

    # Знаходимо кінець заголовка (перший перенос рядка після повного знайденого заголовка)
    header_end_idx = text.find('\n', actual_header_start_idx + len(section_header))
    if header_end_idx == -1:
        # Якщо переносу рядка немає, можливо це кінець тексту
        print(f"DEBUG: Не знайдено кінець заголовка (перенос рядка) після '{full_header_text}'")
        return text
        
    content_start_idx = header_end_idx + 1

    # Шукаємо початок НАСТУПНОЇ секції
    # Використовуємо ті ж маркери
    next_section_markers = [
        'Відповідно до мобілізаційного призначення',
        'З відрядження',
        'З частини щорічної основної відпустки',
        'З відпустки за сімейними обставинами',
        'З відпустки для лікування',
        'з лікувального закладу', # Note lowercase
        'Нижчепойменованих військовослужбовців вважати такими, що прибули у службове відрядження',
        'Вважати такими, що вибули' 
    ]
    
    content_end_idx = len(text) # За замовчуванням - кінець тексту
    found_next_marker = False

    # Шукаємо найближчий маркер НАСТУПНОЇ секції ПІСЛЯ початку поточного контенту
    for marker in next_section_markers:
        # Екрануємо маркер і шукаємо його, можливо, з номером попереду
        escaped_marker = re.escape(marker)
        marker_pattern = rf"(^|\n)\s*(\d+\.\d+(\.\d+)?\.?\s*)?({escaped_marker})"
        marker_match = re.search(marker_pattern, text[content_start_idx:])
        
        if marker_match:
            # Знайшли потенційний початок наступної секції
            # marker_idx - це позиція відносно content_start_idx
            marker_idx_relative = marker_match.start()
            marker_idx_absolute = content_start_idx + marker_idx_relative

            # Обираємо найближчий
            if marker_idx_absolute < content_end_idx:
                content_end_idx = marker_idx_absolute
                found_next_marker = True
                print(f"DEBUG: Знайдено маркер наступної секції '{marker_match.group(4)}' на позиції {marker_idx_absolute}")

    if not found_next_marker:
        print(f"DEBUG: Не знайдено чіткого маркера наступної секції після '{full_header_text}'. Видаляємо до кінця тексту.")
        # Якщо маркер наступної секції не знайдено, видаляємо все до кінця тексту.

    # Формуємо новий текст: частина до початку знайденого повного заголовка + сам повний заголовок + частина після контенту
    text_before_header = text[:start_idx]
    # Ensure newline after header is preserved if it existed
    header_with_newline = full_header_text + ('\n' if text[header_end_idx] == '\n' else '')
    text_after_content = text[content_end_idx:]
    
    # Збираємо текст
    cleaned_text = text_before_header + header_with_newline + text_after_content
    
    print(f"DEBUG: Видалено контент секції '{section_header}' (приблизно {content_end_idx - content_start_idx} символів)")
    
    return cleaned_text


def get_subsection_cause(section_text, section_type="ППОС", full_text_context=""):
    """
    Визначає підставу (cause) відповідно до підрозділу документа.
    
    Args:
        section_text (str): Текст розділу для аналізу
        section_type (str): Тип секції, в якій знаходиться запис (використовується як пріоритетне значення)
        full_text_context (str): Повний контекст для додаткового аналізу
    
    Returns:
        str: Визначена підстава
    """
    # Нормалізуємо текст для пошуку
    normalized_text = normalize_text(section_text.lower())
    
    # 1. Пріоритет базується на контексті запису та типі секції
    
    # Особливі випадки для кожної секції, які мають найвищий пріоритет
    if section_type == "ППОС" and ("відповідно до мобілізаційного призначення" in normalized_text or 
                                   "за мобілізаційним планом" in normalized_text):
        return "ППОС"
    
    if section_type == "Відрядження" and ("з військової частини" in normalized_text or 
                                          "з відрядження" in normalized_text or
                                          "посвідчення про відрядження" in normalized_text):
        return "з Відрядження"
        
    if section_type == "Прибуття у відрядження (навчання)" and ("відрядження" in normalized_text and 
                                                                "навчання" in normalized_text and
                                                                "вважати такими, що прибули у службове відрядження" in normalized_text):
        return "Прибуття у відрядження (навчання)"
    
    if section_type == "Відпустка" and ("відпустка" in normalized_text or 
                                       "відпускний квиток" in normalized_text):
        return "з Відпустки"
    
    if section_type == "Лікарня" and ("лікувальний заклад" in normalized_text or 
                                     "лікарня" in normalized_text or
                                     "виписний епікриз" in normalized_text):
        return "з Лікарні"
    
    if section_type == "Хвороба" and ("звільнені від виконання службових обов'язків" in normalized_text or 
                                     "звільнений від виконання службових обов'язків" in normalized_text):
        return "Хвороба"
    
    if section_type == "Прибуття у відрядження" and ("відрядження" in normalized_text):
        return "Прибуття у відрядження"
    
    # 2. Якщо нічого не знайдено, використовуємо тип секції як підставу з модифікаціями
    if section_type == "Відрядження":
        return "з Відрядження"
    elif section_type == "Лікарня":
        return "з Лікарні"
    elif section_type == "Відпустка":
        return "з Відпустки"
    else:
        return section_type 