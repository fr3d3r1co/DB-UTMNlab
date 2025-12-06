"""
Модуль уведомлений об изменениях документов
"""

from database.db import execute_query

def create_notification(document_id, changed_by_user_id, change_description):
    """
    Создает уведомление об изменении документа
    
    Args:
        document_id: ID измененного документа
        changed_by_user_id: ID пользователя, который внес изменения
        change_description: описание изменений
    
    Returns:
        bool: True если уведомление создано успешно
    """
    try:
        # Получаем информацию о создателе документа
        creator_query = """
            SELECT created_by_employee_id, file_name 
            FROM documents 
            WHERE document_id = %s
        """
        doc_info = execute_query(creator_query, (document_id,))
        
        if not doc_info:
            return False
        
        creator_id = doc_info[0]['created_by_employee_id']
        file_name = doc_info[0]['file_name']
        
        # Создаем уведомление только если изменял не сам создатель
        if creator_id != changed_by_user_id:
            # Получаем имя изменившего пользователя
            changer_query = """
                SELECT full_name FROM employees WHERE employee_id = %s
            """
            changer_info = execute_query(changer_query, (changed_by_user_id,))
            changer_name = changer_info[0]['full_name'] if changer_info else "Неизвестный пользователь"
            
            # Формируем описание уведомления
            notification_text = f"Документ '{file_name}' был изменен пользователем {changer_name}. {change_description}"
            
            execute_query("""
                INSERT INTO notifications (document_id, changed_by_employee_id, change_description)
                VALUES (%s, %s, %s)
            """, (document_id, changed_by_user_id, notification_text), fetch=False)
        
        return True
    except Exception as e:
        print(f"Error creating notification: {e}")
        return False

def get_user_notifications(user_id):
    """
    Получает уведомления пользователя
    
    Args:
        user_id: ID пользователя
    
    Returns:
        list: список уведомлений
    """
    try:
        # Получаем документы, созданные пользователем
        user_documents = execute_query("""
            SELECT document_id FROM documents WHERE created_by_employee_id = %s
        """, (user_id,))
        
        if not user_documents:
            return []
        
        document_ids = [doc['document_id'] for doc in user_documents]
        
        # Получаем уведомления об изменениях этих документов
        placeholders = ','.join(['%s'] * len(document_ids))
        query = f"""
            SELECT n.*, d.file_name, emp.full_name as changed_by_name
            FROM notifications n
            JOIN documents d ON n.document_id = d.document_id
            JOIN employees emp ON n.changed_by_employee_id = emp.employee_id
            WHERE n.document_id IN ({placeholders})
            ORDER BY n.created_at DESC
            LIMIT 50
        """
        
        return execute_query(query, document_ids)
        
    except Exception as e:
        print(f"Error getting user notifications: {e}")
        return []

def mark_notification_as_read(notification_id):
    """
    Помечает уведомление как прочитанное
    (В будущем можно добавить поле is_read в таблицу notifications)
    """
    # Заглушка для будущей реализации
    return True