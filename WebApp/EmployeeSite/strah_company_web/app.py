from flask import Flask, render_template, session, request, redirect, url_for, send_from_directory, send_file
from config import Config
from auth.decorators import login_required, role_required
from database.db import execute_query
import psycopg2
import time
from database.db import get_db_connection, execute_query


# Добавляем импорты для Документов и
from documents.access_control import (
    get_user_department, get_documents_for_user, get_document_by_id, 
    check_document_access, can_edit_document, can_delete_document
)
from documents.notifications import create_notification, get_user_notifications
from documents.file_storage import save_document_file, get_document_file_path, delete_document_file
from config import allowed_file
import os


app = Flask(__name__)
app.config.from_object(Config)


# Убедитесь, что SECRET_KEY установлен
if not app.config.get('SECRET_KEY'):
    app.config['SECRET_KEY'] = 'dev-secret-key-' + os.urandom(24).hex()

app.config['SESSION_PERMANENT'] = True
app.permanent_session_lifetime = 3600  # 1 час

failed_attempts = {}

def is_employee(username):
    """Проверяет, является ли пользователь сотрудником компании"""
    try:
        # Для пользователей с ролью db_admin создаем специальную запись
        roles_query = """
            SELECT r.rolname 
            FROM pg_roles r
            JOIN pg_auth_members am ON r.oid = am.roleid
            JOIN pg_user u ON u.usesysid = am.member
            WHERE u.usename = %s
        """
        roles = execute_query(roles_query, (username,))
        
        if roles:
            role_names = [role['rolname'] for role in roles]
            
            # Если пользователь db_admin, создаем специальную запись
            if 'db_admin' in role_names:
                return {
                    'employee_id': 0,  # Специальный ID для db_admin
                    'full_name': 'Администратор БД',
                    'email': f"{username}@company.ru",
                    'is_active': True
                }
        
        # Для остальных пользователей ищем в таблице employees
        employee_query = """
            SELECT employee_id, full_name, email, is_active 
            FROM employees 
            WHERE (
                -- Ищем по начальной части email (до @)
                SPLIT_PART(email, '@', 1) = %s
                OR
                -- Или по начальной части username (до _)
                SPLIT_PART(email, '@', 1) = SPLIT_PART(%s, '_', 1)
                OR
                -- Или username содержится в email
                email ILIKE %s
            ) AND is_active = true
            LIMIT 1
        """
        search_pattern = f"%{username}%"
        employee_data = execute_query(employee_query, (username, username, search_pattern))
        
        if employee_data:
            return employee_data[0]
        
        # Если не нашли, но пользователь имеет другие роли сотрудника
        role_check_query = """
            SELECT EXISTS(
                SELECT 1 
                FROM pg_roles r
                JOIN pg_auth_members am ON r.oid = am.roleid
                JOIN pg_user u ON u.usesysid = am.member
                WHERE u.usename = %s 
                AND r.rolname IN ('company_director', 'hr_manager', 'department_manager', 'auditor', 'employee')
            ) as has_employee_role
        """
        role_check = execute_query(role_check_query, (username,))
        
        if role_check and role_check[0]['has_employee_role']:
            # Возвращаем первого активного сотрудника как fallback
            any_employee_query = """
                SELECT employee_id, full_name, email, is_active 
                FROM employees 
                WHERE is_active = true
                LIMIT 1
            """
            any_employee = execute_query(any_employee_query)
            if any_employee:
                return any_employee[0]
        
        return None
        
    except Exception as e:
        print(f"Error checking employee: {e}")
        return None

def get_user_role_db(username):
    try:
        # Сначала проверяем PostgreSQL роли
        roles_query = """
            SELECT r.rolname 
            FROM pg_roles r
            JOIN pg_auth_members am ON r.oid = am.roleid  
            JOIN pg_user u ON u.usesysid = am.member
            WHERE u.usename = %s
            AND r.rolname IN ('company_director', 'hr_manager', 'department_manager', 'auditor', 'db_admin', 'employee')
        """
        roles = execute_query(roles_query, (username,))
        
        if roles:
            role_names = [role['rolname'] for role in roles]
            
            # grigoryev_dv имеет роль auditor, но он начальник отдела безопасности
            # Проверяем является ли пользователь начальником отдела
            if 'auditor' in role_names:
                # Проверяем, является ли этот пользователь начальником какого-либо отдела
                manager_check = execute_query("""
                    SELECT department_id FROM departments WHERE manager_id = (
                        SELECT employee_id FROM employees WHERE email ILIKE %s
                    )
                """, (f"%{username}%",))
                
                if manager_check:
                    # Если он начальник отдела, возвращаем department_manager
                    return 'department_manager'
            
            # Возвращаем первую найденную роль
            for role_name in ['company_director', 'hr_manager', 'department_manager', 'auditor', 'db_admin', 'employee']:
                if role_name in role_names:
                    return role_name
        
        # Fallback: проверяем по данным employees
        employee_role_query = """
            SELECT 
                CASE 
                    WHEN e.employee_id = d.manager_id AND d.department_id = 1 THEN 'company_director'
                    WHEN e.employee_id = d.manager_id THEN 'department_manager'  -- Начальник любого отдела
                    WHEN e.department_id = 3 THEN 'hr_manager'
                    WHEN e.department_id = 4 THEN 'auditor'  -- Сотрудник отдела безопасности
                    ELSE 'employee'
                END as role
            FROM employees e
            LEFT JOIN departments d ON e.department_id = d.department_id
            WHERE (e.email ILIKE %s OR e.email ILIKE %s) AND e.is_active = true
        """
        search_pattern = f"%{username}%"
        role_data = execute_query(employee_role_query, (search_pattern, f"{username}@company.ru"))
        
        if role_data and role_data[0]['role']:
            return role_data[0]['role']
        
        # Fallback для неизвестных пользователей
        return 'employee'
            
    except Exception as e:
        print(f"Error getting user role: {e}")
        return 'employee'
    
def validate_username(username):
    import re
    # Более строгая валидация имени пользователя
    pattern = r'^[a-zA-Z0-9_@.\-]+$'
    if not re.match(pattern, username):
        return False
    
    # Проверка длины
    if len(username) < 3 or len(username) > 100:
        return False
    
    return True

def update_failed_attempts(username):
    if username in failed_attempts:
        failed_attempts[username] += 1
    else:
        failed_attempts[username] = 1

def verify_postgres_credentials(username, password):
    """Проверяет логин/пароль через прямое подключение к PostgreSQL"""
    try:
        test_conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            database=Config.DB_NAME,
            user=username,
            password=password
        )
        test_conn.close()
        return True
    except psycopg2.Error:
        return False

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET'])
def login():
    if 'user_id' in session and 'user_role' in session:
        return redirect(url_for('dashboard'))
    
    error = request.args.get('error')
    return render_template('login.html', error=error)

@app.route('/login', methods=['POST'])
def login_post():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    
    # Проверка на пустые поля
    if not username or not password:
        return redirect(url_for('login', error='invalid_credentials'))
    
    # Проверка количества попыток
    if username in failed_attempts and failed_attempts[username] >= 5:
        return redirect(url_for('login', error='too_many_attempts'))
    
    # Валидация username
    if not validate_username(username):
        update_failed_attempts(username)
        return redirect(url_for('login', error='invalid_credentials'))
    
    try:
        # 1. Проверяем credentials в PostgreSQL
        if not verify_postgres_credentials(username, password):
            update_failed_attempts(username)
            return redirect(url_for('login', error='invalid_credentials'))
        
        # 2. Проверяем, является ли пользователь сотрудником
        employee_data = is_employee(username)
        
        if not employee_data:
            update_failed_attempts(username)
            return redirect(url_for('login', error='not_employee'))
        
         # 3. Получаем роль пользователя
        user_role = get_user_role_db(username)
        
        # 4. Определяем расширенную роль с учетом отдела
        user_role = get_extended_user_role(username, user_role)
        
        # 5. Запрещаем доступ пользователям без ролей сотрудника
        if user_role == 'public_users' or not user_role:
            update_failed_attempts(username)
            return redirect(url_for('login', error='not_employee'))
        
          # 6. Создаем сессию
        session.clear()
        session.permanent = True
        
        session['user_id'] = employee_data['employee_id']
        session['user_name'] = employee_data['full_name']
        session['user_email'] = employee_data['email']
        session['user_login'] = username
        session['user_role'] = user_role
        session['authenticated'] = True
        session['login_time'] = int(time.time())
        
        # ДОБАВЛЯЕМ отдел пользователя в сессию
        user_dept = get_user_department(employee_data['employee_id'])
        print(f"DEBUG: User {username} department = {user_dept}")
        if user_dept:
            session['user_dept_id'] = user_dept
        
        # Принудительно сохраняем сессию
        session.modified = True
        
        return redirect(url_for('dashboard'))
            
    except Exception as e:
        print(f"Login error: {e}")
        update_failed_attempts(username)
        return redirect(url_for('login', error='system_error'))

def is_session_valid():
    """Проверяет валидность сессии"""
    # Базовая проверка - если пользователь аутентифицирован и есть роль
    if session.get('authenticated') and session.get('user_role'):
        # Проверка времени сессии (максимум 1 час)
        if time.time() - session.get('login_time', 0) > 3600:
            return False
        return True
    return False

@app.route('/dashboard')
@login_required
def dashboard():
    user_role = session.get('user_role')
    
    try:
        if user_role == 'employee':
            policies = execute_query("SELECT COUNT(*) as count FROM employee_policies_view")
            policies_count = policies[0]['count'] if policies else 0
            return render_template('employee/dashboard.html', policies_count=policies_count)
        
        elif user_role == 'department_manager':
            # Проверяем, действительно ли пользователь начальник отдела
            user_id = session.get('user_id')
            department_info = execute_query("""
                SELECT d.department_id, d.name
                FROM departments d
                WHERE d.manager_id = %s
            """, (user_id,))
            
            if not department_info:
                # Если не начальник, проверяем может ли он быть аудитором из отдела безопасности
                user_dept = get_user_department(user_id)
                if user_dept == 4:  # Отдел безопасности
                    # Это аудитор из отдела безопасности
                    session['user_role'] = 'auditor'
                    return redirect(url_for('dashboard'))
                else:
                    # Не начальник и не аудитор безопасности
                    return render_template('employee/dashboard.html', policies_count=0)
            
            # Пользователь действительно начальник отдела
            department_id = department_info[0]['department_id']
            department_name = department_info[0]['name']
            
            # Получаем статистику для отдела
            department_stats = execute_query("""
                SELECT 
                    (SELECT COUNT(*) FROM employees WHERE department_id = %s) as employees_count,
                    (SELECT COUNT(*) FROM policies WHERE created_in_department_id = %s) as policies_count,
                    (SELECT COUNT(*) FROM documents WHERE created_in_department_id = %s) as documents_count
            """, (department_id, department_id, department_id))
            
            stats_data = department_stats[0] if department_stats else {
                'employees_count': 0,
                'policies_count': 0,
                'documents_count': 0
            }
            
            return render_template('department_manager/dashboard.html',
                                department_name=department_name,
                                stats=stats_data)
        
        elif user_role == 'hr_manager':
            employees_count = execute_query("SELECT COUNT(*) as count FROM employees")
            active_count = execute_query("SELECT COUNT(*) as count FROM employees WHERE is_active = true")
            total_employees = employees_count[0]['count'] if employees_count else 0
            active_employees = active_count[0]['count'] if active_count else 0
            return render_template('hr_manager/dashboard.html',
                                total_employees=total_employees,
                                active_employees=active_employees)
        
        elif user_role == 'company_director':
            stats = execute_query("""
                SELECT 
                    (SELECT COUNT(*) FROM employees) as employees_count,
                    (SELECT COUNT(*) FROM clients) as clients_count,
                    (SELECT COUNT(*) FROM policies) as policies_count,
                    (SELECT COUNT(*) FROM documents) as documents_count
            """)
            stats_data = stats[0] if stats else {
                'employees_count': 0,
                'clients_count': 0, 
                'policies_count': 0,
                'documents_count': 0
            }
            return render_template('company_director/dashboard.html', stats=stats_data)
        
        elif user_role == 'auditor':
            return redirect(url_for('auditor_dashboard'))
        
        elif user_role == 'db_admin':
            # Статистика для администратора БД
            stats = execute_query("""
                SELECT 
                    (SELECT COUNT(*) FROM employees) as employees_count,
                    (SELECT COUNT(*) FROM clients) as clients_count,
                    (SELECT COUNT(*) FROM policies) as policies_count,
                    (SELECT COUNT(*) FROM documents) as documents_count
            """)
            stats_data = stats[0] if stats else {
                'employees_count': 0,
                'clients_count': 0, 
                'policies_count': 0,
                'documents_count': 0
            }
            return render_template('db_admin/dashboard.html', stats=stats_data)
        
        else:
            # Fallback для неизвестных ролей
            return render_template('employee/dashboard.html', policies_count=0)
            
    except Exception as e:
        print(f"Dashboard error: {e}")
        # При любой ошибке возвращаем базовый дашборд с безопасными значениями
        return render_template('employee/dashboard.html', policies_count=0)

@app.route('/logout')
def logout():
    # Полная очистка сессии
    session.clear()
    return redirect(url_for('login'))

@app.route('/clients')
@login_required
@role_required(['employee', 'department_manager', 'company_director'])
def clients_list():
    try:
        clients_data = execute_query("""
            SELECT 
                client_id,
                full_name,
                phone,
                email,
                passport_series,
                passport_number,
                birth_date,
                registration_address,
                driver_license_series,
                driver_license_number,
                created_at
            FROM clients 
            ORDER BY full_name
        """)
        return render_template('employee/clients.html', clients=clients_data)
    except Exception as e:
        print(f"Error loading clients: {e}")
        return render_template('employee/clients.html', clients=[])

@app.route('/policies')
@login_required
def policies():
    try:
        policies_data = execute_query("SELECT * FROM employee_policies_view")
        return render_template('employee/policies.html', policies=policies_data)
    except Exception as e:
        return render_template('employee/policies.html', policies=[])




#----------------------------ДОКУМЕНТЫ---------------------------------------------------------------------------------------------

@app.route('/documents')
@login_required
def documents_list():
    """Список документов с учетом прав доступа"""
    try:
        user_id = session.get('user_id')
        user_role = session.get('user_role')
        
        # Получаем отдел пользователя
        user_dept = get_user_department(user_id)
        if user_dept:
            session['user_dept_id'] = user_dept
        
        user_dept_id = session.get('user_dept_id')
        
        # ОСОБЫЙ СЛУЧАЙ: Если пользователь начальник отдела, но имеет роль auditor
        # Проверяем, является ли пользователь начальником отдела
        is_manager = execute_query("""
            SELECT COUNT(*) as count 
            FROM departments 
            WHERE manager_id = %s
        """, (user_id,))
        
        if is_manager and is_manager[0]['count'] > 0:
            # Пользователь является начальником отдела
            user_role = 'department_manager'
            session['user_role'] = 'department_manager'
        
        print(f"DEBUG: Final user_role={user_role}, user_dept_id={user_dept_id}")
        
        # Получаем документы доступные пользователю
        documents = get_documents_for_user(user_role, user_dept_id, user_id)
        
        # Получаем параметры уведомлений
        success = request.args.get('success')
        error = request.args.get('error')
        
        # Определяем шаблон в зависимости от роли
        if user_role == 'employee':
            template = 'employee/documents.html'
        elif user_role == 'department_manager':
            template = 'department_manager/documents.html'
        elif user_role == 'hr_manager':
            template = 'hr_manager/documents.html'
        elif user_role in ['company_director', 'db_admin']:
            template = 'company_director/documents.html'
        elif user_role == 'auditor':
            template = 'auditor/documents.html'
        else:
            template = 'shared/access_denied.html'
        
        return render_template(template, 
                             documents=documents, 
                             success=success,
                             error=error,
                             user_role=user_role)
                             
    except Exception as e:
        print(f"Error loading documents: {e}")
        return render_template('shared/access_denied.html', 
                             error="Ошибка при загрузке документов")
    
# Добавляем функцию для получения отдела пользователя
def get_user_department(user_id):
    """Получает отдел пользователя по его ID"""
    try:
        result = execute_query(
            "SELECT department_id FROM employees WHERE employee_id = %s", 
            (user_id,)
        )
        if result:
            dept_id = result[0]['department_id']
            print(f"DEBUG: get_user_department for user_id={user_id} returned dept_id={dept_id}")
            return dept_id
        print(f"DEBUG: get_user_department for user_id={user_id} returned None")
        return None
    except Exception as e:
        print(f"Error getting user department: {e}")
        return None


def can_manage_table(user_role, table_name, record=None, user_dept_id=None):
    """Проверяет может ли пользователь управлять таблицей"""
    
    # db_admin может всё
    if user_role == 'db_admin':
        return True
    
    # company_director может всё
    if user_role == 'company_director':
        return True
    
    # hr_manager может управлять сотрудниками
    if user_role == 'hr_manager' and table_name == 'employees':
        return True
    
    # department_manager может управлять сотрудниками своего отдела
    if user_role == 'department_manager' and table_name == 'employees':
        if record and record.get('department_id') == user_dept_id:
            return True
    
    # employee может управлять полисами и клиентами
    if user_role == 'employee' and table_name in ['policies', 'clients']:
        return True
    
    # Аудитор из отдела безопасности может управлять документами своего отдела
    if user_role == 'auditor' and user_dept_id == 4 and table_name == 'documents':
        return True
    
    # Начальник отдела безопасности может управлять документами своего отдела
    if user_role == 'department_manager' and user_dept_id == 4 and table_name == 'documents':
        return True
    
    return False


@app.route('/documents/<int:document_id>')
@login_required
def view_document(document_id):
    """Просмотр информации о документе"""
    try:
        user_id = session.get('user_id')
        user_role = session.get('user_role')
        user_dept_id = get_user_department(user_id)
        
        # Проверяем доступ к документу
        has_access, document = check_document_access(user_role, user_dept_id, user_id, document_id, 'view')
        
        if not has_access:
            return render_template('shared/access_denied.html', 
                                 error="Доступ к документу запрещен")
        
        return render_template('shared/view_document.html', 
                             document=document,
                             user_role=user_role)
                             
    except Exception as e:
        print(f"Error viewing document: {e}")
        return redirect(url_for('documents_list', error="Ошибка при просмотре документа"))

@app.route('/documents/<int:document_id>/download')
@login_required
def download_document(document_id):
    """Скачивание документа"""
    try:
        user_id = session.get('user_id')
        user_role = session.get('user_role')
        user_dept_id = get_user_department(user_id)
        
        # Проверяем доступ к документу
        has_access, document = check_document_access(user_role, user_dept_id, user_id, document_id, 'view')
        
        if not has_access or not document:
            return redirect(url_for('documents_list', error="Доступ к файлу запрещен"))
        
        # Проверяем существует ли файл
        file_path = get_document_file_path(document['stored_file_path'])
        if not os.path.exists(file_path):
            return redirect(url_for('documents_list', error="Файл не найден"))
        
        # Отправляем файл для скачивания
        return send_file(file_path, 
                        as_attachment=True,
                        download_name=document['file_name'])
                        
    except Exception as e:
        print(f"Error downloading document: {e}")
        return redirect(url_for('documents_list', error="Ошибка при скачивании файла"))
    
@app.route('/documents/add', methods=['GET', 'POST'])
@login_required
def add_document():
    """Добавление нового документа"""
    try:
        user_id = session.get('user_id')
        user_role = session.get('user_role')
        user_dept_id = session.get('user_dept_id')
        
        # Проверяем права на добавление документов
        allowed_roles = ['department_manager', 'hr_manager', 'company_director', 'db_admin']
        
        # Аудитор из отдела безопасности также может добавлять документы
        if user_role == 'auditor' and user_dept_id == 4:
            allowed_roles.append('auditor')
        
        if user_role not in allowed_roles:
            return render_template('shared/access_denied.html', 
                                 error="Недостаточно прав для добавления документов")
        
        # Получаем справочные данные
        departments = execute_query("SELECT department_id, name FROM departments ORDER BY name")
        employees = execute_query("SELECT employee_id, full_name FROM employees WHERE is_active = true ORDER BY full_name")
        policies = execute_query("SELECT policy_id, policy_number FROM policies ORDER BY policy_number")
        
        if request.method == 'POST':
            # Обработка загрузки файла
            if 'document_file' not in request.files:
                return render_template('company_director/documents/add_document.html',
                                    departments=departments,
                                    employees=employees,
                                    policies=policies,
                                    error="Файл не выбран")
            
            file = request.files['document_file']
            if file.filename == '':
                return render_template('company_director/documents/add_document.html',
                                    departments=departments,
                                    employees=employees,
                                    policies=policies,
                                    error="Файл не выбран")
            
            if file and not allowed_file(file.filename):
                return render_template('company_director/documents/add_document.html',
                                    departments=departments,
                                    employees=employees,
                                    policies=policies,
                                    error="Недопустимый тип файла")
            
            # Получаем данные из формы
            file_name = request.form.get('file_name', '').strip() or file.filename
            description = request.form.get('description', '').strip()
            confidentiality_level = request.form.get('confidentiality_level', '0')
            policy_id = request.form.get('policy_id') or None
            
            # Для аудиторов и начальников отделов - документы создаются в их отделе
            if user_role in ['department_manager', 'auditor'] and user_dept_id:
                created_in_department_id = user_dept_id
                created_by_employee_id = user_id
            else:
                created_by_employee_id = request.form.get('created_by_employee_id', user_id)
                created_in_department_id = request.form.get('created_in_department_id', user_dept_id)
            
            # Валидация
            if not file_name:
                return render_template('company_director/documents/add_document.html',
                                    departments=departments,
                                    employees=employees,
                                    policies=policies,
                                    error="Название файла обязательно")
            
            if not created_in_department_id:
                return render_template('company_director/documents/add_document.html',
                                    departments=departments,
                                    employees=employees,
                                    policies=policies,
                                    error="Необходимо указать отдел")
            
            # Сохраняем файл
            stored_file_path, saved_filename, file_size = save_document_file(
                file, created_in_department_id, int(confidentiality_level)
            )
            
            if not stored_file_path:
                return render_template('company_director/documents/add_document.html',
                                    departments=departments,
                                    employees=employees,
                                    policies=policies,
                                    error="Ошибка при сохранении файла")
            
            # Сохраняем документ в БД
            insert_query = """
                INSERT INTO documents (
                    policy_id, created_by_employee_id, created_in_department_id,
                    file_name, description, stored_file_path, file_size, confidentiality_level
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            execute_query(insert_query, (
                policy_id, created_by_employee_id, created_in_department_id,
                file_name, description, stored_file_path, file_size, confidentiality_level
            ), fetch=False)
            
            return redirect(url_for('documents_list', success="Документ успешно добавлен"))
        
        # Для аудиторов и начальников отделов предзаполняем отдел
        default_department_id = user_dept_id if user_role in ['department_manager', 'auditor'] else None
        
        return render_template('company_director/documents/add_document.html',
                            departments=departments,
                            employees=employees,
                            policies=policies,
                            default_department_id=default_department_id)
                            
    except Exception as e:
        print(f"Error adding document: {e}")
        return render_template('company_director/documents/add_document.html',
                            departments=[],
                            employees=[],
                            policies=[],
                            error=f"Ошибка при добавлении документа: {str(e)}")
    

@app.route('/documents/<int:document_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_document(document_id):
    """Редактирование документа с уведомлением создателю"""
    try:
        user_id = session.get('user_id')
        user_role = session.get('user_role')
        user_dept_id = session.get('user_dept_id')
        
        # Проверяем доступ к редактированию документа
        has_access, document = check_document_access(user_role, user_dept_id, user_id, document_id, 'edit')
        
        if not has_access:
            return render_template('shared/access_denied.html', 
                                 error="Недостаточно прав для редактирования документа")
        
        # Получаем справочные данные
        departments = execute_query("SELECT department_id, name FROM departments ORDER BY name")
        employees = execute_query("SELECT employee_id, full_name FROM employees WHERE is_active = true ORDER BY full_name")
        policies = execute_query("SELECT policy_id, policy_number FROM policies ORDER BY policy_number")
        
        if request.method == 'POST':
            # Получаем данные из формы
            file_name = request.form.get('file_name', '').strip()
            description = request.form.get('description', '').strip()
            confidentiality_level = request.form.get('confidentiality_level', '0')
            policy_id = request.form.get('policy_id') or None
            created_by_employee_id = request.form.get('created_by_employee_id')
            created_in_department_id = request.form.get('created_in_department_id')
            
            # Валидация
            if not file_name:
                return render_template('company_director/documents/edit_document.html',
                                    document=document,
                                    departments=departments,
                                    employees=employees,
                                    policies=policies,
                                    error="Название файла обязательно")
            
            if not created_by_employee_id:
                return render_template('company_director/documents/edit_document.html',
                                    document=document,
                                    departments=departments,
                                    employees=employees,
                                    policies=policies,
                                    error="Необходимо указать сотрудника")
            
            if not created_in_department_id:
                return render_template('company_director/documents/edit_document.html',
                                    document=document,
                                    departments=departments,
                                    employees=employees,
                                    policies=policies,
                                    error="Необходимо указать отдел")
            
            # Формируем описание изменений
            change_description = ""
            if document['file_name'] != file_name:
                change_description += f"Название изменено с '{document['file_name']}' на '{file_name}'. "
            if document['description'] != description:
                change_description += "Изменено описание. "
            if int(document['confidentiality_level']) != int(confidentiality_level):
                change_description += f"Уровень доступа изменен с {document['confidentiality_level']} на {confidentiality_level}. "
            
            # Обновляем документ в БД
            update_query = """
                UPDATE documents SET
                    policy_id = %s,
                    created_by_employee_id = %s,
                    created_in_department_id = %s,
                    file_name = %s,
                    description = %s,
                    confidentiality_level = %s
                WHERE document_id = %s
            """
            
            execute_query(update_query, (
                policy_id, created_by_employee_id, created_in_department_id,
                file_name, description, confidentiality_level,
                document_id
            ), fetch=False)
            
            # Создаем уведомление об изменении
            if change_description:
                create_notification(document_id, user_id, change_description.strip())
            else:
                create_notification(document_id, user_id, "Документ был отредактирован")
            
            return redirect(url_for('view_document', document_id=document_id, success="Документ успешно обновлен"))
        
        return render_template('company_director/documents/edit_document.html',
                            document=document,
                            departments=departments,
                            employees=employees,
                            policies=policies)
                            
    except Exception as e:
        print(f"Error editing document: {e}")
        return redirect(url_for('documents_list', error=f"Ошибка при редактировании документа: {str(e)}"))
    
@app.route('/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    """Удаление документа"""
    try:
        user_id = session.get('user_id')
        user_role = session.get('user_role')
        user_dept_id = get_user_department(user_id)
        
        # Проверяем доступ к удалению документа
        has_access, document = check_document_access(user_role, user_dept_id, user_id, document_id, 'delete')
        
        if not has_access:
            return redirect(url_for('documents_list', error="Недостаточно прав для удаления документа"))
        
        # Удаляем файл из файловой системы
        if document.get('stored_file_path'):
            delete_document_file(document['stored_file_path'])
        
        # Удаляем документ из БД
        delete_query = "DELETE FROM documents WHERE document_id = %s"
        execute_query(delete_query, (document_id,), fetch=False)
        
        return redirect(url_for('documents_list', success="Документ успешно удален"))
        
    except Exception as e:
        print(f"Error deleting document: {e}")
        return redirect(url_for('documents_list', error=f"Ошибка при удалении документа: {str(e)}"))
    


@app.route('/notifications')
@login_required
def notifications_list():
    """Список уведомлений пользователя"""
    try:
        user_id = session.get('user_id')
        notifications = get_user_notifications(user_id)
        
        return render_template('shared/notifications.html', 
                             notifications=notifications)
                             
    except Exception as e:
        print(f"Error loading notifications: {e}")
        return render_template('shared/notifications.html', 
                             notifications=[])
    
    
#---------------------------------------------------------------------------------------------------------------------------------------

@app.route('/employees')
@login_required
@role_required(['hr_manager', 'company_director', 'department_manager'])
def employees_list():
    try:
        employees_data = execute_query("SELECT * FROM hr_employees_view")
        return render_template('hr_manager/employees.html', employees=employees_data)
    except Exception as e:
        print(f"Error loading employees: {e}")
        return render_template('hr_manager/employees.html', employees=[])

@app.route('/audit')
@login_required
@role_required(['auditor', 'company_director'])
def audit():
    try:
        audit_data = execute_query("SELECT * FROM auditor_view")
        return render_template('auditor/audit.html', audit_data=audit_data)
    except Exception as e:
        return render_template('auditor/audit.html', audit_data=[])

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Защита от кэширования для страниц с данными
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@app.route('/department_employees')
@login_required
@role_required(['department_manager', 'hr_manager', 'company_director'])
def department_employees():
    try:
        user_role = session.get('user_role')
        
        if user_role == 'department_manager':
            # Находим отдел для начальника
            department_info = get_department_for_manager(session['user_login'])
            
            if not department_info:
                return render_template('department_manager/employees.html', employees=[])
            
            department_id = department_info['department_id']
            
            # Находим всех сотрудников этого отдела
            employees_query = """
                SELECT 
                    e.employee_id,
                    e.full_name,
                    e.phone,
                    e.email,
                    d.name as department_name,
                    e.is_active
                FROM employees e
                JOIN departments d ON e.department_id = d.department_id
                WHERE e.department_id = %s
                ORDER BY e.full_name
            """
            employees_data = execute_query(employees_query, (department_id,))
        else:
            # Для HR и директора - все сотрудники
            employees_data = execute_query("SELECT * FROM hr_employees_view")
            
        return render_template('department_manager/employees.html', employees=employees_data)
    except Exception as e:
        print(f"Error loading department employees: {e}")
        return render_template('department_manager/employees.html', employees=[])
    
def get_department_for_manager(username):
    """Находит отдел для начальника по username"""
    try:
        # Ищем начальника по username в email сотрудников
        department_query = """
            SELECT d.department_id, d.name
            FROM departments d
            JOIN employees e ON d.manager_id = e.employee_id
            WHERE e.email ILIKE %s OR e.email ILIKE %s
        """
        
        # Пробуем разные варианты поиска
        patterns = [
            f"%{username}%",           # username содержится в email
            f"{username}@company.ru",  # полный email
        ]
        
        for pattern in patterns:
            department_data = execute_query(department_query, (pattern, pattern))
            if department_data:
                print(f"DEBUG: Found department for manager {username}: {department_data[0]}")
                return department_data[0]
        
        # Если не нашли, проверяем по employee_id из сессии
        if 'user_id' in session:
            user_id = session['user_id']
            dept_query = """
                SELECT d.department_id, d.name
                FROM departments d
                WHERE d.manager_id = %s
            """
            dept_data = execute_query(dept_query, (user_id,))
            if dept_data:
                print(f"DEBUG: Found department by user_id {user_id}: {dept_data[0]}")
                return dept_data[0]
        
        print(f"DEBUG: No department found for manager {username}")
        return None
    except Exception as e:
        print(f"Error finding department for manager: {e}")
        return None
    
@app.route('/db_admin/table/<table_name>')
@login_required
@role_required(['db_admin'])
def manage_table(table_name):
    try:
        # Разрешенные таблицы для управления
        allowed_tables = [
            'employees', 'clients', 'policies', 'documents', 'departments',
            'car_brands', 'car_models', 'policy_statuses', 'notifications'
        ]
        
        if table_name not in allowed_tables:
            return redirect(url_for('dashboard'))
        
        # Получаем данные таблицы
        table_data = execute_query(f"SELECT * FROM {table_name} ORDER BY 1")
        
        # Получаем информацию о колонках
        columns_query = """
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = %s 
            ORDER BY ordinal_position
        """
        columns = execute_query(columns_query, (table_name,))
        
        return render_template('db_admin/table_management.html', 
                            table_name=table_name,
                            table_data=table_data,
                            columns=columns)
    except Exception as e:
        print(f"Error loading table {table_name}: {e}")
        return redirect(url_for('dashboard'))
    

@app.route('/db_admin/table/<table_name>/add', methods=['GET', 'POST'])
@login_required
@role_required(['db_admin'])
def add_table_record(table_name):
    """Добавление новой записи в таблицу"""
    try:
        allowed_tables = ['employees', 'clients', 'policies', 'documents', 'departments',
                         'car_brands', 'car_models', 'policy_statuses']
        
        if table_name not in allowed_tables:
            return redirect(url_for('dashboard'))

        # Получаем информацию о колонках
        columns_query = """
            SELECT 
                column_name, 
                data_type,
                is_nullable,
                column_default,
                character_maximum_length
            FROM information_schema.columns 
            WHERE table_name = %s 
            ORDER BY ordinal_position
        """
        columns = execute_query(columns_query, (table_name,))

        if request.method == 'POST':
            # Собираем данные из формы
            form_data = {}
            for column in columns:
                col_name = column['column_name']
                if col_name in ['created_at', 'updated_at']:
                    continue
                
                value = request.form.get(col_name)
                
                # Обработка разных типов данных
                if value == '' and column['is_nullable'] == 'NO' and not column['column_default']:
                    return render_template('db_admin/add_record.html', 
                                        table_name=table_name,
                                        columns=columns,
                                        error=f"Поле '{col_name}' обязательно для заполнения")
                
                if value != '':
                    # Преобразование типов
                    if column['data_type'] in ['integer', 'bigint']:
                        try:
                            form_data[col_name] = int(value) if value else None
                        except ValueError:
                            return render_template('db_admin/add_record.html', 
                                                table_name=table_name,
                                                columns=columns,
                                                error=f"Неверный формат числа в поле '{col_name}'")
                    
                    elif column['data_type'] in ['numeric', 'decimal']:
                        try:
                            form_data[col_name] = float(value) if value else None
                        except ValueError:
                            return render_template('db_admin/add_record.html', 
                                                table_name=table_name,
                                                columns=columns,
                                                error=f"Неверный формат числа в поле '{col_name}'")
                    
                    elif column['data_type'] == 'boolean':
                        form_data[col_name] = value.lower() in ['true', '1', 'yes', 'on']
                    
                    else:  # text, varchar, etc.
                        form_data[col_name] = value

            # Формируем SQL запрос
            columns_str = ', '.join(form_data.keys())
            placeholders = ', '.join([f'%s' for _ in form_data])
            values = list(form_data.values())
            
            insert_query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
            
            try:
                execute_query(insert_query, values, fetch=False)
                return redirect(url_for('manage_table', table_name=table_name, success=True))
            except Exception as e:
                return render_template('db_admin/add_record.html', 
                                    table_name=table_name,
                                    columns=columns,
                                    error=f"Ошибка при добавлении: {str(e)}")

        return render_template('db_admin/add_record.html', 
                            table_name=table_name, 
                            columns=columns)

    except Exception as e:
        print(f"Error adding record to {table_name}: {e}")
        return redirect(url_for('manage_table', table_name=table_name, error=str(e)))

@app.route('/db_admin/table/<table_name>/edit/<int:record_id>', methods=['GET', 'POST'])
@login_required
@role_required(['db_admin'])
def edit_table_record(table_name, record_id):
    """Редактирование записи в таблице"""
    try:
        allowed_tables = ['employees', 'clients', 'policies', 'documents', 'departments',
                         'car_brands', 'car_models', 'policy_statuses']
        
        if table_name not in allowed_tables:
            return redirect(url_for('dashboard'))

        # Получаем информацию о колонках
        columns_query = """
            SELECT 
                column_name, 
                data_type,
                is_nullable,
                column_default,
                character_maximum_length
            FROM information_schema.columns 
            WHERE table_name = %s 
            ORDER BY ordinal_position
        """
        columns = execute_query(columns_query, (table_name,))

        # Получаем текущие данные записи
        current_data = execute_query(f"SELECT * FROM {table_name} WHERE {get_primary_key_column(table_name)} = %s", (record_id,))
        
        if not current_data:
            return redirect(url_for('manage_table', table_name=table_name, error="Запись не найдена"))
        
        current_record = current_data[0]

        if request.method == 'POST':
            form_data = {}
            for column in columns:
                col_name = column['column_name']
                if col_name in ['created_at', 'updated_at']:  # Системные поля не редактируем
                    continue
                
                value = request.form.get(col_name)
                
                # Обработка обязательных полей
                if value == '' and column['is_nullable'] == 'NO' and not column['column_default']:
                    return render_template('db_admin/edit_record.html', 
                                        table_name=table_name,
                                        record_id=record_id,
                                        columns=columns,
                                        current_record=current_record,
                                        error=f"Поле '{col_name}' обязательно для заполнения")
                
                if value is not None:
                    # Преобразование типов
                    if column['data_type'] in ['integer', 'bigint']:
                        try:
                            form_data[col_name] = int(value) if value else None
                        except ValueError:
                            return render_template('db_admin/edit_record.html', 
                                                table_name=table_name,
                                                record_id=record_id,
                                                columns=columns,
                                                current_record=current_record,
                                                error=f"Неверный формат числа в поле '{col_name}'")
                    
                    elif column['data_type'] in ['numeric', 'decimal']:
                        try:
                            form_data[col_name] = float(value) if value else None
                        except ValueError:
                            return render_template('db_admin/edit_record.html', 
                                                table_name=table_name,
                                                record_id=record_id,
                                                columns=columns,
                                                current_record=current_record,
                                                error=f"Неверный формат числа в поле '{col_name}'")
                    
                    elif column['data_type'] == 'boolean':
                        form_data[col_name] = value.lower() in ['true', '1', 'yes', 'on']
                    
                    else:  # text, varchar, etc.
                        form_data[col_name] = value

            # Формируем SQL запрос для UPDATE
            set_clause = ', '.join([f"{col} = %s" for col in form_data.keys()])
            values = list(form_data.values())
            values.append(record_id)  # для WHERE условия
            
            update_query = f"UPDATE {table_name} SET {set_clause} WHERE {get_primary_key_column(table_name)} = %s"
            
            try:
                execute_query(update_query, values, fetch=False)
                return redirect(url_for('manage_table', table_name=table_name, success=True))
            except Exception as e:
                return render_template('db_admin/edit_record.html', 
                                    table_name=table_name,
                                    record_id=record_id,
                                    columns=columns,
                                    current_record=current_record,
                                    error=f"Ошибка при обновлении: {str(e)}")

        return render_template('db_admin/edit_record.html', 
                            table_name=table_name,
                            record_id=record_id,
                            columns=columns,
                            current_record=current_record)

    except Exception as e:
        print(f"Error editing record in {table_name}: {e}")
        return redirect(url_for('manage_table', table_name=table_name, error=str(e)))

@app.route('/db_admin/table/<table_name>/delete/<int:record_id>', methods=['POST'])
@login_required
@role_required(['db_admin'])
def delete_table_record(table_name, record_id):
    """Удаление записи из таблицы"""
    try:
        allowed_tables = ['employees', 'clients', 'policies', 'documents', 'departments',
                         'car_brands', 'car_models', 'policy_statuses']
        
        if table_name not in allowed_tables:
            return redirect(url_for('dashboard'))

        # Проверяем существование записи
        current_data = execute_query(f"SELECT * FROM {table_name} WHERE {get_primary_key_column(table_name)} = %s", (record_id,))
        
        if not current_data:
            return redirect(url_for('manage_table', table_name=table_name, error="Запись не найдена"))

        # Выполняем удаление
        delete_query = f"DELETE FROM {table_name} WHERE {get_primary_key_column(table_name)} = %s"
        execute_query(delete_query, (record_id,), fetch=False)
        
        return redirect(url_for('manage_table', table_name=table_name, success=True))

    except Exception as e:
        print(f"Error deleting record from {table_name}: {e}")
        return redirect(url_for('manage_table', table_name=table_name, error=f"Ошибка при удалении: {str(e)}"))

def get_primary_key_column(table_name):
    """Получает имя первичного ключа для таблицы"""
    pk_columns = {
        'employees': 'employee_id',
        'clients': 'client_id', 
        'policies': 'policy_id',
        'documents': 'document_id',
        'departments': 'department_id',
        'car_brands': 'brand_id',
        'car_models': 'model_id',
        'policy_statuses': 'status_id'
    }
    return pk_columns.get(table_name, 'id')


# Маршруты для управления сотрудниками (company_director)
@app.route('/company_director/employees')
@login_required
@role_required(['company_director'])
def manage_employees():
    """Управление сотрудниками - главная страница"""
    try:
        # Получаем параметры уведомлений
        success = request.args.get('success')
        error = request.args.get('error')
        
        # Получаем всех сотрудников с информацией об отделах
        employees_query = """
            SELECT 
                e.employee_id,
                e.full_name,
                e.phone,
                e.email,
                d.name as department_name,
                e.is_active,
                e.created_at,
                e.updated_at
            FROM employees e
            LEFT JOIN departments d ON e.department_id = d.department_id
            ORDER BY e.full_name
        """
        employees = execute_query(employees_query)
        
        # Получаем отделы для фильтрации
        departments = execute_query("SELECT department_id, name FROM departments ORDER BY name")
        
        return render_template('company_director/employees.html', 
                             employees=employees,
                             departments=departments,
                             success=success,
                             error=error)
    except Exception as e:
        print(f"Error loading employees: {e}")
        return render_template('company_director/employees.html', 
                             employees=[],
                             departments=[],
                             error=str(e))

@app.route('/company_director/employees/add', methods=['GET', 'POST'])
@login_required
@role_required(['company_director'])
def add_employee():
    """Добавление нового сотрудника"""
    try:
        # Получаем отделы для выпадающего списка
        departments = execute_query("SELECT department_id, name FROM departments ORDER BY name")
        
        if request.method == 'POST':
            # Собираем данные из формы
            full_name = request.form.get('full_name', '').strip()
            phone = request.form.get('phone', '').strip()
            email = request.form.get('email', '').strip()
            department_id = request.form.get('department_id')
            is_active = request.form.get('is_active', 'true')
            
            # Валидация обязательных полей
            errors = []
            if not full_name:
                errors.append("ФИО обязательно")
            if not phone:
                errors.append("Телефон обязателен")
            if not email:
                errors.append("Email обязателен")
            if not department_id:
                errors.append("Отдел обязателен")
            
            # Проверка формата email
            if email and '@' not in email:
                errors.append("Неверный формат email")
            
            # Проверка формата телефона (только цифры)
            if phone and not phone.replace('+', '').isdigit():
                errors.append("Телефон должен содержать только цифры")
            
            if errors:
                return render_template('company_director/add_employee.html',
                                    departments=departments,
                                    errors=errors)
            
            # Преобразование типов
            try:
                department_id = int(department_id)
                is_active = is_active.lower() in ['true', '1', 'yes', 'on']
            except ValueError:
                return render_template('company_director/add_employee.html',
                                    departments=departments,
                                    errors=["Неверный формат данных"])
            
            # Проверка уникальности email и телефона
            check_query = """
                SELECT EXISTS(
                    SELECT 1 FROM employees 
                    WHERE email = %s OR phone = %s
                ) as exists
            """
            check_result = execute_query(check_query, (email, phone))
            
            if check_result and check_result[0]['exists']:
                return render_template('company_director/add_employee.html',
                                    departments=departments,
                                    errors=["Сотрудник с таким email или телефоном уже существует"])
            
            # Вставляем сотрудника
            insert_query = """
                INSERT INTO employees (
                    full_name, department_id, phone, email, is_active
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING employee_id
            """
            
            try:
                result = execute_query(insert_query, (
                    full_name, department_id, phone, email, is_active
                ), fetch=True)
                
                if result:
                    # Обновляем отдел, если этот сотрудник назначен начальником
                    update_manager = request.form.get('is_manager') == 'true'
                    if update_manager:
                        update_department_query = """
                            UPDATE departments 
                            SET manager_id = %s 
                            WHERE department_id = %s
                        """
                        execute_query(update_department_query, (result[0]['employee_id'], department_id), fetch=False)
                
                return redirect(url_for('manage_employees', success=True))
                
            except Exception as e:
                return render_template('company_director/add_employee.html',
                                    departments=departments,
                                    errors=[f"Ошибка при добавлении сотрудника: {str(e)}"])

        return render_template('company_director/add_employee.html',
                            departments=departments)

    except Exception as e:
        print(f"Error adding employee: {e}")
        return redirect(url_for('manage_employees', error=str(e)))

@app.route('/company_director/employees/edit/<int:employee_id>', methods=['GET', 'POST'])
@login_required
@role_required(['company_director'])
def edit_employee(employee_id):
    """Редактирование сотрудника"""
    try:
        # Получаем текущие данные сотрудника
        employee_query = """
            SELECT 
                e.employee_id,
                e.full_name,
                e.phone,
                e.email,
                e.department_id,
                e.is_active,
                d.manager_id
            FROM employees e
            LEFT JOIN departments d ON e.department_id = d.department_id
            WHERE e.employee_id = %s
        """
        employee_data = execute_query(employee_query, (employee_id,))
        
        if not employee_data:
            return redirect(url_for('manage_employees', error="Сотрудник не найден"))
        
        employee = employee_data[0]
        is_manager = employee['manager_id'] == employee_id

        # Получаем отделы
        departments = execute_query("SELECT department_id, name FROM departments ORDER BY name")
        
        if request.method == 'POST':
            # Собираем данные из формы
            full_name = request.form.get('full_name', '').strip()
            phone = request.form.get('phone', '').strip()
            email = request.form.get('email', '').strip()
            department_id = request.form.get('department_id')
            is_active = request.form.get('is_active', 'true')
            is_manager_new = request.form.get('is_manager') == 'true'
            
            # Валидация обязательных полей
            errors = []
            if not full_name:
                errors.append("ФИО обязательно")
            if not phone:
                errors.append("Телефон обязателен")
            if not email:
                errors.append("Email обязателен")
            if not department_id:
                errors.append("Отдел обязателен")
            
            # Проверка формата email
            if email and '@' not in email:
                errors.append("Неверный формат email")
            
            # Проверка формата телефона
            if phone and not phone.replace('+', '').isdigit():
                errors.append("Телефон должен содержать только цифры")
            
            if errors:
                return render_template('company_director/edit_employee.html',
                                    employee=employee,
                                    departments=departments,
                                    is_manager=is_manager,
                                    errors=errors)
            
            # Преобразование типов
            try:
                department_id = int(department_id)
                is_active = is_active.lower() in ['true', '1', 'yes', 'on']
            except ValueError:
                return render_template('company_director/edit_employee.html',
                                    employee=employee,
                                    departments=departments,
                                    is_manager=is_manager,
                                    errors=["Неверный формат данных"])
            
            # Проверка уникальности email и телефона (кроме текущего сотрудника)
            check_query = """
                SELECT EXISTS(
                    SELECT 1 FROM employees 
                    WHERE (email = %s OR phone = %s)
                    AND employee_id != %s
                ) as exists
            """
            check_result = execute_query(check_query, (email, phone, employee_id))
            
            if check_result and check_result[0]['exists']:
                return render_template('company_director/edit_employee.html',
                                    employee=employee,
                                    departments=departments,
                                    is_manager=is_manager,
                                    errors=["Сотрудник с таким email или телефоном уже существует"])
            
            # Начинаем транзакцию
            conn = get_db_connection()
            cur = conn.cursor()
            
            try:
                # Обновляем сотрудника
                update_employee_query = """
                    UPDATE employees SET
                        full_name = %s,
                        department_id = %s,
                        phone = %s,
                        email = %s,
                        is_active = %s,
                        updated_at = NOW()
                    WHERE employee_id = %s
                """
                cur.execute(update_employee_query, (
                    full_name, department_id, phone, email, is_active, employee_id
                ))
                
                # Управление назначением начальником отдела
                old_department_id = employee['department_id']
                
                if is_manager_new and not is_manager:
                    # Назначаем нового начальника
                    update_department_query = """
                        UPDATE departments 
                        SET manager_id = %s 
                        WHERE department_id = %s
                    """
                    cur.execute(update_department_query, (employee_id, department_id))
                    
                elif not is_manager_new and is_manager:
                    # Снимаем с должности начальника
                    if department_id == old_department_id:
                        # Если отдел не изменился, очищаем manager_id
                        clear_manager_query = """
                            UPDATE departments 
                            SET manager_id = NULL 
                            WHERE department_id = %s AND manager_id = %s
                        """
                        cur.execute(clear_manager_query, (department_id, employee_id))
                    else:
                        # Если отдел изменился, начальником старого отдела больше не является
                        pass
                
                elif is_manager_new and is_manager and department_id != old_department_id:
                    # Переводим начальника в другой отдел
                    # Очищаем старый отдел
                    clear_old_department_query = """
                        UPDATE departments 
                        SET manager_id = NULL 
                        WHERE department_id = %s AND manager_id = %s
                    """
                    cur.execute(clear_old_department_query, (old_department_id, employee_id))
                    
                    # Назначаем в новый отдел
                    update_new_department_query = """
                        UPDATE departments 
                        SET manager_id = %s 
                        WHERE department_id = %s
                    """
                    cur.execute(update_new_department_query, (employee_id, department_id))
                
                conn.commit()
                cur.close()
                conn.close()
                
                return redirect(url_for('manage_employees', success=True))
                
            except Exception as e:
                conn.rollback()
                cur.close()
                conn.close()
                return render_template('company_director/edit_employee.html',
                                    employee=employee,
                                    departments=departments,
                                    is_manager=is_manager,
                                    errors=[f"Ошибка при обновлении сотрудника: {str(e)}"])

        return render_template('company_director/edit_employee.html',
                            employee=employee,
                            departments=departments,
                            is_manager=is_manager)

    except Exception as e:
        print(f"Error editing employee: {e}")
        return redirect(url_for('manage_employees', error=str(e)))

@app.route('/company_director/employees/delete/<int:employee_id>', methods=['POST'])
@login_required
@role_required(['company_director'])
def delete_employee(employee_id):
    """Удаление сотрудника"""
    try:
        # Проверяем существование сотрудника
        employee_data = execute_query("SELECT * FROM employees WHERE employee_id = %s", (employee_id,))
        
        if not employee_data:
            return redirect(url_for('manage_employees', error="Сотрудник не найден"))
        
        # Проверяем, является ли сотрудник начальником отдела
        is_manager_query = """
            SELECT EXISTS(
                SELECT 1 FROM departments 
                WHERE manager_id = %s
            ) as is_manager
        """
        is_manager_result = execute_query(is_manager_query, (employee_id,))
        
        # Проверяем, есть ли связанные записи
        has_policies_query = """
            SELECT EXISTS(
                SELECT 1 FROM policies 
                WHERE created_by_employee_id = %s
            ) as has_policies
        """
        has_policies_result = execute_query(has_policies_query, (employee_id,))
        
        has_documents_query = """
            SELECT EXISTS(
                SELECT 1 FROM documents 
                WHERE created_by_employee_id = %s
            ) as has_documents
        """
        has_documents_result = execute_query(has_documents_query, (employee_id,))
        
        # Удаляем сотрудника
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            # Если сотрудник начальник отдела, очищаем это поле
            if is_manager_result and is_manager_result[0]['is_manager']:
                clear_manager_query = """
                    UPDATE departments 
                    SET manager_id = NULL 
                    WHERE manager_id = %s
                """
                cur.execute(clear_manager_query, (employee_id,))
            
            # Удаляем сотрудника
            delete_query = "DELETE FROM employees WHERE employee_id = %s"
            cur.execute(delete_query, (employee_id,))
            
            conn.commit()
            cur.close()
            conn.close()
            
            return redirect(url_for('manage_employees', success=True))
            
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            
            # Проверяем, если ошибка из-за внешних ключей
            if "foreign key constraint" in str(e).lower():
                return redirect(url_for('manage_employees', 
                                     error="Невозможно удалить сотрудника: имеются связанные записи в полисах или документах"))
            else:
                return redirect(url_for('manage_employees', error=f"Ошибка при удалении: {str(e)}"))

    except Exception as e:
        print(f"Error deleting employee: {e}")
        return redirect(url_for('manage_employees', error=str(e)))


def get_employee_department(username):
    """Определяет отдел сотрудника по username"""
    try:
        query = """
            SELECT d.department_id, d.name
            FROM employees e
            JOIN departments d ON e.department_id = d.department_id
            WHERE e.email ILIKE %s OR e.email ILIKE %s
            LIMIT 1
        """
        # Пробуем найти по email
        email_pattern = f"%{username}@company.ru"
        search_pattern = f"%{username}%"
        result = execute_query(query, (email_pattern, search_pattern))
        
        if result:
            return result[0]
        return None
    except Exception as e:
        print(f"Error getting employee department: {e}")
        return None

def get_extended_user_role(username, role):
    """Определяет расширенную роль с учетом отдела"""
    try:
        # Если пользователь auditor, проверяем его отдел
        if role == 'auditor':
            dept = get_employee_department(username)
            if dept:
                return 'auditor'  # Все аудиторы теперь имеют расширенные права
        return role
    except Exception as e:
        print(f"Error getting extended role: {e}")
        return role



@app.route('/auditor/dashboard')
@login_required
@role_required(['auditor'])
def auditor_dashboard():
    """Дашборд для аудиторов"""
    try:
        # Получаем статистику
        stats_query = """
            SELECT 
                (SELECT COUNT(*) FROM employees) as employees_count,
                (SELECT COUNT(*) FROM policies) as policies_total,
                (SELECT COUNT(*) FROM documents WHERE confidentiality_level < 2) as documents_count,
                (SELECT COUNT(*) FROM clients) as clients_count
        """
        stats = execute_query(stats_query)
        
        stats_data = stats[0] if stats else {
            'employees_count': 0,
            'policies_total': 0,
            'documents_count': 0,
            'clients_count': 0
        }
        
        return render_template('auditor/dashboard.html', stats=stats_data)
        
    except Exception as e:
        print(f"Auditor dashboard error: {e}")
        return render_template('auditor/dashboard.html', stats={})

@app.route('/auditor/policies')
@login_required
@role_required(['auditor'])
def auditor_policies():
    """Просмотр полисов для аудиторов"""
    try:
        policies_data = execute_query("SELECT * FROM employee_policies_view")
        return render_template('auditor/policies.html', policies=policies_data)
    except Exception as e:
        return render_template('auditor/policies.html', policies=[])

@app.route('/auditor/documents')
@login_required
@role_required(['auditor'])
def auditor_documents():
    """Просмотр документов для аудиторов"""
    try:
        # Аудиторы видят все документы кроме секретных (уровень 2)
        docs_query = """
            SELECT d.*, dep.name as department_name, emp.full_name as created_by
            FROM documents d
            JOIN departments dep ON d.created_in_department_id = dep.department_id
            JOIN employees emp ON d.created_by_employee_id = emp.employee_id
            WHERE d.confidentiality_level < 2
            ORDER BY d.created_at DESC
        """
        docs = execute_query(docs_query)
        return render_template('auditor/documents.html', documents=docs)
    except Exception as e:
        return render_template('auditor/documents.html', documents=[])

@app.route('/auditor/clients')
@login_required
@role_required(['auditor'])
def auditor_clients():
    """Просмотр клиентов для аудиторов"""
    try:
        clients_data = execute_query("""
            SELECT 
                client_id,
                full_name,
                phone,
                email,
                passport_series,
                passport_number,
                birth_date,
                registration_address,
                driver_license_series,
                driver_license_number,
                created_at
            FROM clients 
            ORDER BY full_name
        """)
        return render_template('auditor/clients.html', clients=clients_data)
    except Exception as e:
        return render_template('auditor/clients.html', clients=[])
    

    

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)

if __name__ == '__main__':
    app.run(debug=True)