"""
Модуль работы с файловым хранилищем документов
"""

import os
import uuid
from werkzeug.utils import secure_filename
from config import Config

def get_upload_folder():
    """Возвращает путь к папке для загрузки файлов"""
    upload_folder = os.path.join(os.path.dirname(__file__), '..', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    return upload_folder

def get_department_folder(department_id):
    """Возвращает путь к папке отдела"""
    upload_folder = get_upload_folder()
    department_folder = os.path.join(upload_folder, f'department_{department_id}')
    os.makedirs(department_folder, exist_ok=True)
    return department_folder

def get_public_folder():
    """Возвращает путь к папке публичных документов"""
    upload_folder = get_upload_folder()
    public_folder = os.path.join(upload_folder, 'public')
    os.makedirs(public_folder, exist_ok=True)
    return public_folder

def save_document_file(file, department_id, confidentiality_level):
    """
    Сохраняет файл документа в соответствующую папку
    
    Args:
        file: файл из request.files
        department_id: ID отдела
        confidentiality_level: уровень конфиденциальности
    
    Returns:
        tuple: (file_path, file_name, file_size) или (None, None, None) при ошибке
    """
    try:
        if file and file.filename:
            # Безопасное имя файла
            original_filename = secure_filename(file.filename)
            file_extension = os.path.splitext(original_filename)[1]
            
            # Генерируем уникальное имя файла
            unique_filename = f"{uuid.uuid4().hex}{file_extension}"
            
            # Выбираем папку для сохранения
            if confidentiality_level == 0:
                # Публичные документы
                save_folder = get_public_folder()
            else:
                # Документы отдела
                save_folder = get_department_folder(department_id)
            
            # Полный путь к файлу
            file_path = os.path.join(save_folder, unique_filename)
            
            # Сохраняем файл
            file.save(file_path)
            
            # Получаем размер файла
            file_size = os.path.getsize(file_path)
            
            # Относительный путь для хранения в БД
            relative_path = file_path.replace(get_upload_folder() + '/', '')
            
            return relative_path, original_filename, file_size
            
    except Exception as e:
        print(f"Error saving document file: {e}")
    
    return None, None, None

def get_document_file_path(stored_file_path):
    """
    Возвращает абсолютный путь к файлу документа
    
    Args:
        stored_file_path: путь из БД
    
    Returns:
        str: абсолютный путь к файлу
    """
    upload_folder = get_upload_folder()
    return os.path.join(upload_folder, stored_file_path)

def document_file_exists(stored_file_path):
    """Проверяет существует ли файл документа"""
    file_path = get_document_file_path(stored_file_path)
    return os.path.exists(file_path)

def delete_document_file(stored_file_path):
    """
    Удаляет файл документа
    
    Args:
        stored_file_path: путь из БД
    
    Returns:
        bool: True если файл удален
    """
    try:
        file_path = get_document_file_path(stored_file_path)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
    except Exception as e:
        print(f"Error deleting document file: {e}")
    
    return False