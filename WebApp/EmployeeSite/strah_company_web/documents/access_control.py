"""
Модуль контроля доступа к документам
Проверяет права пользователей на просмотр, редактирование и удаление документов
"""

from database.db import execute_query

def get_user_department(user_id):
    """Получает отдел пользователя по его ID"""
    try:
        result = execute_query(
            "SELECT department_id FROM employees WHERE employee_id = %s", 
            (user_id,)
        )
        if result:
            return result[0]['department_id']
        return None
    except Exception as e:
        print(f"Error getting user department: {e}")
        return None

def can_view_document(user_role, user_dept_id, user_id, document):
    """
    Проверяет может ли пользователь просматривать документ
    
    Args:
        user_role: роль пользователя
        user_dept_id: ID отдела пользователя
        user_id: ID пользователя
        document: словарь с данными документа из БД
    
    Returns:
        bool: True если доступ разрешен
    """
    
    # company_director видит всё
    if user_role == 'company_director':
        return True
    
    # db_admin видит всё
    if user_role == 'db_admin':
        return True
    
    # Публичные документы видны всем
    if document.get('confidentiality_level') == 0:
        return True
    
    # Сотрудник видит документы своего отдела (уровни 0,1) и свои документы
    if user_role == 'employee':
        return (document.get('created_in_department_id') == user_dept_id 
                and document.get('confidentiality_level') in [0, 1]
                or document.get('created_by_employee_id') == user_id)
    
    # Начальник отдела видит все документы своего отдела
    if user_role == 'department_manager':
        return document.get('created_in_department_id') == user_dept_id
    
    # HR видит документы своего отдела (уровни 0,1)
    if user_role == 'hr_manager':
        return (document.get('created_in_department_id') == user_dept_id 
                and document.get('confidentiality_level') in [0, 1])
    
    # Аудитор
    if user_role == 'auditor':
        # Аудитор из отдела безопасности видит все документы своего отдела
        if user_dept_id == 4:  # Отдел безопасности
            return document.get('created_in_department_id') == user_dept_id
        else:
            # Остальные аудиторы видят публичные и ДСП
            return document.get('confidentiality_level') in [0, 1]
    
    # Публичные пользователи
    if user_role == 'public_users':
        return document.get('confidentiality_level') == 0
    
    return False

def can_edit_document(user_role, user_dept_id, user_id, document):
    """
    Проверяет может ли пользователь редактировать документ
    
    Args:
        user_role: роль пользователя
        user_dept_id: ID отдела пользователя
        user_id: ID пользователя
        document: словарь с данными документа из БД
    
    Returns:
        bool: True если редактирование разрешено
    """
    
    # Создатель может редактировать свой документ
    if document.get('created_by_employee_id') == user_id:
        return True
    
    # Начальник отдела может редактировать документы своего отдела
    if user_role == 'department_manager' and document.get('created_in_department_id') == user_dept_id:
        return True
    
    # HR может редактировать документы своего отдела (уровни 0,1)
    if user_role == 'hr_manager' and document.get('created_in_department_id') == user_dept_id and document.get('confidentiality_level') in [0, 1]:
        return True
    
    # Аудитор из отдела безопасности может редактировать ВСЕ документы своего отдела
    if user_role == 'auditor' and user_dept_id == 4 and document.get('created_in_department_id') == user_dept_id:
        return True
    
    # Руководитель и админ БД могут всё
    if user_role in ['company_director', 'db_admin']:
        return True
    
    return False

def can_delete_document(user_role, user_dept_id, user_id, document):
    """
    Проверяет может ли пользователь удалять документ
    
    Args:
        user_role: роль пользователя
        user_dept_id: ID отдела пользователя
        user_id: ID пользователя
        document: словарь с данными документа из БД
    
    Returns:
        bool: True если удаление разрешено
    """
    
    # Создатель может удалять свой документ
    if document.get('created_by_employee_id') == user_id:
        return True
    
    # Начальник отдела может удалять документы своего отдела
    if user_role == 'department_manager' and document.get('created_in_department_id') == user_dept_id:
        return True
    
    # Руководитель и админ БД могут всё
    if user_role in ['company_director', 'db_admin']:
        return True
    
    return False

def get_documents_for_user(user_role, user_dept_id, user_id):
    """
    Получает список документов, доступных пользователю
    
    Args:
        user_role: роль пользователя
        user_dept_id: ID отдела пользователя
        user_id: ID пользователя
    
    Returns:
        list: список документов или None при ошибке
    """
    
    try:
        if user_role in ['company_director', 'db_admin']:
            # Видят все документы
            return execute_query("""
                SELECT d.*, dep.name as department_name, emp.full_name as created_by_name
                FROM documents d
                LEFT JOIN departments dep ON d.created_in_department_id = dep.department_id
                LEFT JOIN employees emp ON d.created_by_employee_id = emp.employee_id
                ORDER BY d.created_at DESC
            """)
        
        elif user_role == 'department_manager':
            # Видят все документы своего отдела И все публичные документы
            return execute_query("""
                SELECT d.*, dep.name as department_name, emp.full_name as created_by_name
                FROM documents d
                LEFT JOIN departments dep ON d.created_in_department_id = dep.department_id
                LEFT JOIN employees emp ON d.created_by_employee_id = emp.employee_id
                WHERE d.created_in_department_id = %s 
                   OR d.confidentiality_level = 0
                ORDER BY d.created_at DESC
            """, (user_dept_id,))
        
        elif user_role == 'hr_manager':
            # Видят документы своего отдела (уровни 0,1) И все публичные
            return execute_query("""
                SELECT d.*, dep.name as department_name, emp.full_name as created_by_name
                FROM documents d
                LEFT JOIN departments dep ON d.created_in_department_id = dep.department_id
                LEFT JOIN employees emp ON d.created_by_employee_id = emp.employee_id
                WHERE (d.created_in_department_id = %s AND d.confidentiality_level IN (0, 1))
                   OR d.confidentiality_level = 0
                ORDER BY d.created_at DESC
            """, (user_dept_id,))
        
        elif user_role == 'employee':
            # Видят документы своего отдела (уровни 0,1), свои документы И все публичные
            return execute_query("""
                SELECT d.*, dep.name as department_name, emp.full_name as created_by_name
                FROM documents d
                LEFT JOIN departments dep ON d.created_in_department_id = dep.department_id
                LEFT JOIN employees emp ON d.created_by_employee_id = emp.employee_id
                WHERE (d.created_in_department_id = %s AND d.confidentiality_level IN (0, 1))
                   OR d.created_by_employee_id = %s
                   OR d.confidentiality_level = 0
                ORDER BY d.created_at DESC
            """, (user_dept_id, user_id))
        
        elif user_role == 'auditor':
            # Аудитор из отдела безопасности видит все документы своего отдела
            if user_dept_id == 4:  # Отдел безопасности
                return execute_query("""
                    SELECT d.*, dep.name as department_name, emp.full_name as created_by_name
                    FROM documents d
                    LEFT JOIN departments dep ON d.created_in_department_id = dep.department_id
                    LEFT JOIN employees emp ON d.created_by_employee_id = emp.employee_id
                    WHERE d.created_in_department_id = %s
                    ORDER BY d.created_at DESC
                """, (user_dept_id,))
            else:
                # Остальные аудиторы видят публичные и ДСП
                return execute_query("""
                    SELECT d.*, dep.name as department_name, emp.full_name as created_by_name
                    FROM documents d
                    LEFT JOIN departments dep ON d.created_in_department_id = dep.department_id
                    LEFT JOIN employees emp ON d.created_by_employee_id = emp.employee_id
                    WHERE d.confidentiality_level IN (0, 1)
                    ORDER BY d.created_at DESC
                """)
        
        elif user_role == 'public_users':
            # Видят только публичные документы
            return execute_query("""
                SELECT d.*, dep.name as department_name, emp.full_name as created_by_name
                FROM documents d
                LEFT JOIN departments dep ON d.created_in_department_id = dep.department_id
                LEFT JOIN employees emp ON d.created_by_employee_id = emp.employee_id
                WHERE d.confidentiality_level = 0
                ORDER BY d.created_at DESC
            """)
        
        else:
            return []
            
    except Exception as e:
        print(f"Error getting documents for user: {e}")
        return []

def get_document_by_id(document_id):
    """
    Получает документ по ID
    
    Args:
        document_id: ID документа
    
    Returns:
        dict: данные документа или None если не найден
    """
    try:
        result = execute_query("""
            SELECT d.*, dep.name as department_name, emp.full_name as created_by_name
            FROM documents d
            LEFT JOIN departments dep ON d.created_in_department_id = dep.department_id
            LEFT JOIN employees emp ON d.created_by_employee_id = emp.employee_id
            WHERE d.document_id = %s
        """, (document_id,))
        
        return result[0] if result else None
    except Exception as e:
        print(f"Error getting document by ID: {e}")
        return None

def check_document_access(user_role, user_dept_id, user_id, document_id, action='view'):
    """
    Универсальная функция проверки доступа к документу
    
    Args:
        user_role: роль пользователя
        user_dept_id: ID отдела пользователя
        user_id: ID пользователя
        document_id: ID документа
        action: тип действия ('view', 'edit', 'delete')
    
    Returns:
        tuple: (bool, dict) - доступ разрешен и данные документа
    """
    
    document = get_document_by_id(document_id)
    if not document:
        return False, None
    
    if action == 'view':
        has_access = can_view_document(user_role, user_dept_id, user_id, document)
    elif action == 'edit':
        has_access = can_edit_document(user_role, user_dept_id, user_id, document)
    elif action == 'delete':
        has_access = can_delete_document(user_role, user_dept_id, user_id, document)
    else:
        has_access = False
    
    return has_access, document