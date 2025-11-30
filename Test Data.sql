-- 1. Вставляем отделы компании
INSERT INTO departments (name, manager_id) VALUES 
('Руководство', NULL),           -- department_id = 1
('Отдел продаж', NULL),          -- department_id = 2  
('HR отдел', NULL),              -- department_id = 3
('Отдел безопасности', NULL);     -- department_id = 4

-- 2. Вставляем сотрудников (пароль: '123456' в bcrypt хэше)
INSERT INTO employees (full_name, department_id, phone, email) VALUES
-- Руководство
('Иванов Иван Иванович', 1, '79101112233', 'director@company.ru'),
-- Отдел продаж
('Петрова Елена Сергеевна', 2, '79112223344', 'petrova@company.ru'),
('Сидоров Алексей Дмитриевич', 2, '79113334455', 'sidorov@company.ru'),
('Козлова Мария Викторовна', 2, '79114445566', 'kozlova@company.ru'),
-- HR отдел
('Васильева Анна Михайловна', 3, '79117778899', 'vasilyeva@company.ru'),
-- Отдел безопасности
('Григорьев Денис Владимирович', 4, '79118889900', 'grigoryev@company.ru'),
('Афанасьев Владимир Владимирович', 4, '79118889100', 'afanasiev@company.ru');

-- 3. Обновляем начальников отделов
UPDATE departments SET manager_id = 1 WHERE department_id = 1; -- Иванов - руководитель
UPDATE departments SET manager_id = 2 WHERE department_id = 2; -- Петрова - нач. отдела продаж
UPDATE departments SET manager_id = 5 WHERE department_id = 3; -- Васильева - HR
UPDATE departments SET manager_id = 6 WHERE department_id = 4; -- Григорьев - Безопасник

-- 4. Назначаем роли сотрудникам
INSERT INTO user_roles (user_id, role) VALUES
(1, 'company_director'),    -- Иванов - руководитель компании
(2, 'department_manager'),  -- Петрова - начальник отдела продаж
(3, 'employee'),            -- Сидоров - сотрудник отдела продаж
(4, 'employee'),            -- Козлова - сотрудник отдела продаж
(5, 'hr_manager'),          -- Васильева - HR менеджер
(6, 'department_manager'),  -- Григорьев - начальник отдела безопасности
(7, 'employee'); 			-- Афанасьев - аудитор

-- 5. Вставляем клиентов
INSERT INTO clients (full_name, phone, email, passport_series, passport_number, birth_date, registration_address, driver_license_series, driver_license_number) VALUES
('Смирнов Алексей Владимирович', '79031112233', 'smirnov@mail.ru', '4510', '123456', '1985-03-15', 'г. Москва, ул. Ленина, д. 10, кв. 25', '77AA', '123456'),
('Кузнецова Ольга Петровна', '79032223344', 'kuznetsova@gmail.com', '4511', '234567', '1990-07-22', 'г. Москва, ул. Пушкина, д. 15, кв. 12', '77AB', '234567'),
('Попов Дмитрий Сергеевич', '79033334455', 'popov@yandex.ru', '4512', '345678', '1988-11-30', 'г. Москва, пр. Мира, д. 25, кв. 8', '77AC', '345678'),
('Волкова Ирина Александровна', '79034445566', 'volkova@mail.ru', '4513', '456789', '1992-05-18', 'г. Москва, ул. Гагарина, д. 8, кв. 15', '77AD', '456789');

-- 6. Вставляем марки и модели автомобилей
INSERT INTO car_brands (brand_name) VALUES 
('Toyota'),
('BMW'),
('Lada'),
('Kia');

INSERT INTO car_models (model_name, brand_id) VALUES
('Camry', 1),
('RAV4', 1),
('X5', 2),
('3 Series', 2),
('Vesta', 3),
('Granta', 3),
('Rio', 4),
('Sportage', 4);

-- 7. Вставляем статусы полисов
INSERT INTO policy_statuses (status_name) VALUES 
('Оформлен'),
('Активен'),
('Аннулирован'),
('Истек');

-- 8. Вставляем полисы
INSERT INTO policies (status_id, created_by_employee_id, created_in_department_id, policy_number, cost, start_date, end_date, conclusion_date, car_brand_id, car_model_id, car_vin, car_reg_number, owner_client_id, additional_drivers) VALUES
(2, 3, 2, 'OSAGO-2024-001', 12500.00, '2024-01-01', '2025-01-01', '2024-01-01', 1, 1, 'JTDKB20U300000123', 'А123ВС77', 1, '[2]'),
(2, 4, 2, 'OSAGO-2024-002', 11800.00, '2024-01-15', '2025-01-15', '2024-01-15', 2, 3, 'WBAFR710X0LV12345', 'Е456КХ77', 2, '[]'),
(1, 3, 2, 'KASKO-2024-001', 45000.00, '2024-02-01', '2025-02-01', '2024-02-01', 4, 7, 'Z94CB41BAER123456', 'О789ТТ77', 3, '[4]'),
(3, 4, 2, 'OSAGO-2023-001', 11000.00, '2023-01-01', '2024-01-01', '2023-01-01', 3, 5, 'XTA219120C1234567', 'В321МР77', 4, '[]');

-- 9. Вставляем документы с разными уровнями конфиденциальности
INSERT INTO documents (policy_id, created_by_employee_id, created_in_department_id, file_name, description, stored_file_path, file_size, confidentiality_level) VALUES
-- Публичные документы (confidentiality_level = 0)
(NULL, 1, 1, 'Правила страхования.pdf', 'Публичные правила страхования ОСАГО', '/docs/public/rules_osago.pdf', 2048576, 0),
(NULL, 1, 1, 'Тарифы 2024.pdf', 'Публичные тарифы на 2024 год', '/docs/public/tariffs_2025.pdf', 1536890, 0),

-- Документы ДСП отдела продаж (confidentiality_level = 1)
(NULL, 3, 2, 'Расписание смен сотрудников.pdf', 'Детальное описание рабочего времени сотрудников', '/docs/sales/policy_001.pdf', 3456789, 1),
(NULL, 3, 2, 'План показателей для сотрудников.pdf', 'Информация о базовой ставке и надбавках', '/docs/sales/policy_002.pdf', 2987654, 1),

-- Документы только для начальников (confidentiality_level = 2)
(NULL, 1, 1, 'Финансовый отчет 2025.xlsx', 'Годовой финансовый отчет', '/docs/confidential/fin_report.xlsx', 5678901, 2),
(NULL, 1, 1, 'Стратегия развития.pdf', 'Стратегия развития компании на 2025-2030', '/docs/confidential/strategy.pdf', 4456789, 2),
(NULL, 2, 2, 'План продаж.xlsx', 'План продаж на следующий квартал', '/docs/confidential/sales_plan.xlsx', 2345678, 2);

-- 10. Вставляем несколько уведомлений
INSERT INTO notifications (document_id, changed_by_employee_id, change_description) VALUES
(3, 2, 'Была исправлена стоимость полиса'),
(6, 1, 'Добавлены новые условия страхования'),
(7, 1, 'Обновлены финансовые показатели');