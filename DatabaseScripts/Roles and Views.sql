-- ================================ СОЗДАНИЕ РОЛЕЙ =========================
CREATE ROLE company_director;
CREATE ROLE department_manager; 
CREATE ROLE employee;
CREATE ROLE hr_manager;
CREATE ROLE auditor;
CREATE ROLE db_admin;
CREATE ROLE public_users;

-- ================================ СОЗДАНИЕ ПОЛЬЗОВАТЕЛЕЙ =================
CREATE USER ivanov_ii WITH PASSWORD 'secure_password_123';
CREATE USER petrova_es WITH PASSWORD 'secure_password_123';
CREATE USER sidorov_ad WITH PASSWORD 'secure_password_123';
CREATE USER kozlova_mv WITH PASSWORD 'secure_password_123';
CREATE USER vasilyeva_am WITH PASSWORD 'secure_password_123';
CREATE USER grigoryev_dv WITH PASSWORD 'secure_password_123';
CREATE USER afanasiev_vv WITH PASSWORD 'secure_password_123';
CREATE USER user_public WITH PASSWORD 'secure_password_123';
CREATE USER db_amdin_user WITH PASSWORD 'secure_password_123';

-- ================================ НАЗНАЧЕНИЕ РОЛЕЙ ПОЛЬЗОВАТЕЛЯМ =========
GRANT db_admin TO db_amdin_user;
GRANT company_director TO ivanov_ii;
GRANT department_manager TO petrova_es;
GRANT employee TO sidorov_ad;
GRANT employee TO kozlova_mv;
GRANT hr_manager TO vasilyeva_am;
GRANT department_manager TO grigoryev_dv;
GRANT auditor TO afanasiev_vv;
GRANT public_users TO user_public;

-- ================================ ПРЕДСТАВЛЕНИЯ =========================

-- Представление для сотрудников - просмотр и редактирование полисов
CREATE VIEW employee_policies_view AS
SELECT 
    p.policy_id,
    p.policy_number,
    p.cost,
    p.start_date,
    p.end_date,
    p.conclusion_date,
    c.full_name as client_name,
    c.phone as client_phone,
    cb.brand_name as car_brand,
    cm.model_name as car_model,
    p.car_reg_number,
    p.car_vin,
    ps.status_name,
    e.full_name as created_by_employee,
    d.name as department_name
FROM policies p
JOIN clients c ON p.owner_client_id = c.client_id
JOIN car_brands cb ON p.car_brand_id = cb.brand_id
JOIN car_models cm ON p.car_model_id = cm.model_id
JOIN policy_statuses ps ON p.status_id = ps.status_id
JOIN employees e ON p.created_by_employee_id = e.employee_id
JOIN departments d ON p.created_in_department_id = d.department_id;

-- Представление для публичных пользователей - только публичные документы
CREATE VIEW public_documents_view AS
SELECT 
    document_id,
    file_name,
    description,
    stored_file_path,
    file_size,
    created_at
FROM documents 
WHERE confidentiality_level = 0;

-- Представление для аудиторов - все таблицы кроме документов уровня 2
CREATE VIEW auditor_view AS
SELECT 
    'departments' as table_name,
    department_id as id,
    name,
    manager_id
FROM departments
UNION ALL
SELECT 
    'employees' as table_name,
    employee_id as id,
    full_name as name,
    department_id as manager_id
FROM employees
UNION ALL
SELECT 
    'clients' as table_name,
    client_id as id,
    full_name as name,
    NULL as manager_id
FROM clients
UNION ALL
SELECT 
    'policies' as table_name,
    policy_id as id,
    policy_number as name,
    status_id as manager_id
FROM policies
UNION ALL
SELECT 
    'documents' as table_name,
    document_id as id,
    file_name as name,
    confidentiality_level as manager_id
FROM documents 
WHERE confidentiality_level < 2;

-- Представление для начальников отделов - документы их отдела
CREATE VIEW department_manager_documents_view AS
SELECT 
    d.document_id,
    d.file_name,
    d.description,
    d.stored_file_path,
    d.file_size,
    d.confidentiality_level,
    d.created_at,
    dep.name as department_name,
    emp.full_name as created_by
FROM documents d
JOIN departments dep ON d.created_in_department_id = dep.department_id
JOIN employees emp ON d.created_by_employee_id = emp.employee_id
WHERE d.confidentiality_level < 2;

-- Представление для HR - информация о сотрудниках
CREATE VIEW hr_employees_view AS
SELECT 
    e.employee_id,
    e.full_name,
    e.phone,
    e.email,
    d.name as department_name,
    e.is_active,
    e.created_at
FROM employees e
JOIN departments d ON e.department_id = d.department_id;

-- ================================ ПРИВИЛЕГИИ ============================

-- Привилегии для company_director (руководитель)
GRANT USAGE ON SCHEMA public TO company_director;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO company_director;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO company_director;

-- Привилегии для department_manager (начальники отделов)
GRANT USAGE ON SCHEMA public TO department_manager;
GRANT SELECT ON departments, employees, clients, car_brands, car_models, policy_statuses TO department_manager;
GRANT SELECT, INSERT, UPDATE ON policies TO department_manager;
GRANT SELECT, INSERT, UPDATE ON department_manager_documents_view TO department_manager;
GRANT SELECT ON employee_policies_view TO department_manager;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO department_manager;

-- Привилегии для employee (сотрудники)
GRANT USAGE ON SCHEMA public TO employee;
GRANT SELECT ON departments, employees, car_brands, car_models, policy_statuses TO employee;
GRANT SELECT, INSERT, UPDATE ON employee_policies_view TO employee;
GRANT SELECT ON clients TO employee;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO employee;

-- Привилегии для hr_manager (HR)
GRANT USAGE ON SCHEMA public TO hr_manager;
GRANT SELECT, INSERT, UPDATE ON hr_employees_view TO hr_manager;
GRANT SELECT ON departments TO hr_manager;
GRANT SELECT ON public_documents_view TO hr_manager;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO hr_manager;

-- Привилегии для auditor (аудитор)
GRANT USAGE ON SCHEMA public TO auditor;
GRANT SELECT ON auditor_view TO auditor;
GRANT SELECT ON departments, employees, policy_statuses TO auditor;

-- Привилегии для db_admin (администратор БД)
GRANT USAGE ON SCHEMA public TO db_admin;
GRANT SELECT, INSERT, UPDATE ON departments, employees, clients, car_brands, car_models, policy_statuses TO db_admin;
GRANT SELECT, INSERT, UPDATE ON policies TO db_admin;
GRANT SELECT, INSERT, UPDATE ON documents TO db_admin;
GRANT SELECT ON notifications TO db_admin;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO db_admin;

-- Привилегии для public_user (публичный доступ)
GRANT USAGE ON SCHEMA public TO public_users;
GRANT SELECT ON public_documents_view TO public_users;
